"""Generate v5 boundary adapters, verify native ownership, and compile distinct changed layouts."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa
from prototype_exp125_cc_implementation import model

SOURCE = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
BUILD = ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-grouped-20261026'
PREVIOUS = ROOT/'experiments/EXP-128/artifacts/preflight/grouped-20261026'
MATRIX = ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027'
RECORD = ROOT/'experiments/EXP-128/records/boundary-v5-20261027'


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def run(args, label, cwd=None):
    p=subprocess.run(list(map(str,args)),cwd=cwd or ART,env=mgr.environment(ART),
                     capture_output=True,timeout=240)
    (ART/(label+'.out')).write_bytes(p.stdout)
    (ART/(label+'.err')).write_bytes(p.stderr)
    mgr.require(p.returncode==0,label+': '+p.stderr.decode(errors='replace')[-2000:])
    return p.stdout.decode()


def phase_mapping(q, first, tpt):
    count=q//first
    assert count*first==q
    got=[];queries=0
    for lane in range(tpt):
        delta_initialized=False
        if lane<min(count,tpt):
            delta_initialized=True;queries+=1
        for h in range((count+tpt-1)//tpt):
            if lane+h*tpt>=count:
                continue
            current_initialized=False
            for w in range(first):
                j=lane+h*tpt+w*count
                if w==0:
                    current_initialized=True;queries+=1
                assert delta_initialized and current_initialized
                got.append((h*first+w,j))
    assert sorted(j for _,j in got)==list(range(q))
    assert queries==count+min(count,tpt)
    return dict(Q=q,first_factor=first,threads_per_transform=tpt,queries=queries,
                previous_queries=q,enabled=q>queries,partial_h=count%tpt!=0 and count>tpt)


def input_region(text):
    a=text.index('// load global into registers\n')
    b=text.index('// calc the thread_in_device',a)
    return a,b,text[a:b]


def output_regions(text):
    starts=[m.start() for m in re.finditer(r'const unsigned int (?:cc_output_first|cc_packed_slot) =',text)]
    assert len(starts)==2,starts
    return starts


def main():
    started=time.monotonic();ART.mkdir(exist_ok=True);RECORD.mkdir(exist_ok=True)
    fields=[line.split() for line in MATRIX.read_text().splitlines()]
    assert len(fields)==283
    by_shape={(int(f[1]),int(f[2])):f for f in fields}
    mappings=[phase_mapping(int(f[2]),int(f[10].split(',')[0]),int(f[7])) for f in fields]
    future=[phase_mapping(54,3,8),phase_mapping(80,2,16),phase_mapping(16,2,8)]
    assert future[0]['partial_h'] and future[1]['partial_h'] and not future[2]['enabled']
    commands=json.loads((BUILD/'compile_commands.json').read_text())
    entry=next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    args=shlex.split(entry['command'])+['--offload-arch=gfx936','-mcumode']
    args[args.index('-o')+1]=str(ART/'generator.o')
    run(args,'compile-generator',Path(entry['directory']))
    driver=ART/'generate.cpp';driver.write_text((PREVIOUS/'generate.cpp').read_text())
    args[args.index('-o')+1]=str(ART/'driver.o')
    args[args.index('-c')+1]=str(driver)
    run(args,'compile-driver',Path(entry['directory']))
    objects=[p for p in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o')
             if p.name!='rtc_stockham_gen.cpp.o']
    objects+=list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects+=list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    run([mgr.DTK+'/bin/hipcc','--offload-arch=gfx936','-mcumode',ART/'driver.o',ART/'generator.o',
         *objects,'-pthread','-ldl','-lstdc++fs','-o',ART/'generate'],'link')
    changed=[];unchanged=[];syntax={};generated=0
    for mode,extra,expected in [('default',[],2264),('retained-lds',['lds'],566)]:
        folder=ART/mode;folder.mkdir(exist_ok=True)
        lines=run([ART/'generate',MATRIX,folder,*extra],'generate-'+mode).splitlines()
        assert len(lines)==expected,len(lines)
        generated+=len(lines)
        for line in lines:
            n,c,q,role,cb,size,name=line.split();n,c,q,role,cb=map(int,(n,c,q,role,cb))
            path=folder/f'{c}-{q}-{role}-{cb}.cpp';text=path.read_text()
            assert '_cc_local_v5_role'+str(role) in name
            previous=(PREVIOUS/mode/path.name).read_text()
            native=by_shape[c,q];tpt,rows=map(int,native[7:9])
            packed=role==5 and c%2==rows%2==c%rows==0
            recurrent=role==7 and mode=='default' and phase_mapping(q,int(native[10].split(',')[0]),tpt)['enabled']
            normalized=text.replace('_cc_local_v5_','_cc_local_v4_')
            if not packed and not recurrent:
                assert normalized==previous,str(path)
                unchanged.append(str(path));continue
            if packed:
                assert 'cc_output_first' not in text and 'cc_packed_component' in text
                assert 'cc_packed_pair' in text
            if recurrent:
                a,b,region=input_region(text)
                first=int(native[10].split(',')[0]);count=q//first
                assert region.count('TW_NSteps<')==1+(count+tpt-1)//tpt
                dense=re.sub(r'\s+','',region)
                groups=(first+1)//2 if tpt>count else 1
                assert dense.count('if(cc_input_row==0)')==groups
                if tpt>count:
                    assert 'if(threadIdx.x%'+str(tpt)+'<'+str(count)+')' in dense
                olda,oldb,_=input_region(previous)
                assert normalized[:a]==previous[:olda] and normalized[b:]==previous[oldb:]
            changed.append(dict(N=n,C=c,Q=q,role=role,callback=cb,mode=mode,packed_output=packed,
                                phase_recurrence=recurrent,path=str(path)))
            key=(role,q,tpt,rows,cb,c%2,c%rows==0,2 if n<=65536 else 3)
            syntax.setdefault(key,path)
    assert sum(x['packed_output'] for x in changed)==214
    assert sum(x['phase_recurrence'] for x in changed)==566
    def compile_one(item):
        key,path=item
        hip=path.with_suffix('.hip.cpp');hip.write_text('#include <hip/hip_runtime.h>\n'+path.read_text())
        asm=path.with_suffix('.s')
        cmd=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936',
             '--cuda-device-only','-S','-mcumode',str(hip),'-o',str(asm)]
        p=subprocess.run(cmd,env=mgr.environment(ART),capture_output=True,text=True,timeout=150)
        path.with_suffix('.err').write_text(p.stderr)
        result=dict(shape=key,source=str(path),complete=p.returncode==0,returncode=p.returncode)
        if p.returncode:result['error']=p.stderr[-2500:]
        else:result['isa']=analyze_isa(asm.read_text())
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        compiled=list(pool.map(compile_one,syntax.items()))
    failures=[x for x in compiled if not x['complete']]
    models=model()
    result=dict(complete=not failures,device_execution=False,geometries=283,generated_sources=generated,
                unchanged_sources=len(unchanged),changed_sources=changed,phase_mapping=mappings,
                future_mapping_tests=future,address_and_phase_model=models,compiles=compiled,
                failures=failures,elapsed_seconds=time.monotonic()-started)
    save(RECORD/'host-preflight.json',result)
    print(json.dumps(dict(complete=not failures,generated=generated,changed=len(changed),
                          unchanged=len(unchanged),compiles=len(compiled),failures=failures,
                          elapsed_seconds=result['elapsed_seconds'])),flush=True)
    mgr.require(not failures,'v5 offline compiler errors')


if __name__=='__main__':main()
