"""Check native grouping maps, unchanged paths, and exact-runtime-source overlays."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa

SOURCE=ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
BUILD=ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-rowsimplify-20261022'
V3=ROOT/'experiments/EXP-128/artifacts/preflight/rowsimplify-20261022'
OLD=ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021'
OUT=ROOT/'experiments/EXP-128/artifacts/preflight/grouped-20261026'
RECORD=ROOT/'experiments/EXP-128/records/grouped-20261026'


def save(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def run(argv,label,cwd=None):
    p=subprocess.run(list(map(str,argv)),cwd=cwd or OUT,env=mgr.environment(OUT),
                     capture_output=True,timeout=240)
    (OUT/(label+'.out')).write_bytes(p.stdout);(OUT/(label+'.err')).write_bytes(p.stderr)
    mgr.require(p.returncode==0,label+': '+p.stderr.decode(errors='replace')[-3000:])
    return p.stdout.decode()


def input_region(text):
    a=text.index('// load global into registers\n');b=text.index('// calc the thread_in_device',a)
    return a,b,text[a:b]


def shape(fields):
    n,c,q=map(int,fields[:3]);tpt,tpb=map(int,fields[7:9]);factor=int(fields[10].split(',')[0])
    return n,c,q,tpt,tpb,factor


def mapping(fields):
    n,c,q,tpt,tpb,factor=shape(fields);count=q//factor
    assert n==2*c*q and q%factor==0
    if tpt<=count: return None
    groups=[list(range(a,min(a+2,factor))) for a in range(0,factor,2)]
    for lane in range(tpt):
        native=[(w,lane+w*count) for w in range(factor)] if lane<count else []
        grouped=[(reg,lane+reg*count) for group in groups for reg in group] if lane<count else []
        assert native==grouped
    assert sorted(lane+w*count for lane in range(count) for w in range(factor))==list(range(q))
    assert sum(map(len,groups))==factor and len(groups[-1])==(1 if factor%2 else 2)
    return dict(N=n,C=c,Q=q,tpt=tpt,first_factor=factor,active_lanes=count,groups=groups)


def main():
    start=time.monotonic();OUT.mkdir(exist_ok=True);RECORD.mkdir(exist_ok=True)
    matrix=[line.split() for line in (OLD/'native-matrix.txt').read_text().splitlines()]
    assert len(matrix)==283
    extra=[];q100=next(f for f in matrix if int(f[1])==512 and int(f[2])==100)
    for c in (336,343,512,1024):
        col=next(f for f in matrix if int(f[1])==c)
        extra.append([str(2*c*100),str(c),'100',*col[3:7],*q100[7:]])
    extra_path=OUT/'q100-generation-only.txt';extra_path.write_text(''.join(' '.join(f)+'\n' for f in extra))
    mapped=[x for f in matrix+extra if (x:=mapping(f)) is not None]
    (OUT/'generate.cpp').write_text((V3/'generate.cpp').read_text())
    commands=json.loads((BUILD/'compile_commands.json').read_text())
    entry=next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    args=shlex.split(entry['command'])+['--offload-arch=gfx936','-mcumode']
    args[args.index('-o')+1]=str(OUT/'generator.o')
    run(args,'compile-generator',Path(entry['directory']))
    args[args.index('-o')+1]=str(OUT/'driver.o');args[args.index('-c')+1]=str(OUT/'generate.cpp')
    run(args,'compile-driver',Path(entry['directory']))
    objects=[p for p in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o') if p.name!='rtc_stockham_gen.cpp.o']
    objects+=list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects+=list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    run([mgr.DTK+'/bin/hipcc','--offload-arch=gfx936','-mcumode',OUT/'driver.o',OUT/'generator.o',
         *objects,'-pthread','-ldl','-lstdc++fs','-o',OUT/'generate'],'link')
    unchanged=[];changed=[];syntax={};generated=0
    for mode,manifest,extra_args,reference in [
        ('default',OLD/'native-matrix.txt',[],V3/'default'),
        ('retained-lds',OLD/'native-matrix.txt',['lds'],V3/'retained-lds'),
        ('q100-generation-only',extra_path,[],None)]:
        folder=OUT/mode;folder.mkdir(exist_ok=True)
        lines=[line.split() for line in run([OUT/'generate',manifest,folder,*extra_args],'generate-'+mode).splitlines()]
        assert len(lines)==(566 if mode=='retained-lds' else 32 if reference is None else 2264)
        generated+=len(lines)
        for n,c,q,role,cb,size,name in lines:
            c,q,role,cb=map(int,(c,q,role,cb));path=folder/f'{c}-{q}-{role}-{cb}.cpp'
            text=path.read_text();assert '_cc_local_v4_role'+str(role) in name
            fields=next(f for f in (extra if reference is None else matrix) if int(f[1])==c and int(f[2])==q)
            _,_,_,tpt,tpb,factor=shape(fields)
            is_grouped=role==7 and mode!='retained-lds' and tpt>q//factor
            if reference is not None:
                old=(reference/path.name).read_text()
                normalized=text.replace('_cc_local_v4_','_cc_local_v3_')
                if not is_grouped:
                    assert normalized==old,str(path)
                    unchanged.append(str(path))
                else:
                    a,b,region=input_region(normalized);x,y,old_region=input_region(old)
                    assert normalized[:a]==old[:x] and normalized[b:]==old[y:]
                    assert region.count('if(cc_input_row == 0)')==(factor+1)//2
                    assert region.count('cc_row_phase_')==old_region.count('cc_row_phase_')
                    changed.append(dict(N=int(n),C=c,Q=q,callback=cb,path=str(path)))
            if is_grouped:
                key=(q,tpt,tpb,c%2,c%tpb==0,cb)
                syntax.setdefault(key,path)
    # Actual loaded ABI/stride parameters, not just reconstructed native fixtures.
    record=json.loads((ROOT/'experiments/EXP-128/runs/EXP-128-cc-rows-v3-regression-diagnostic-20261023/diagnostic-result.json').read_text())
    metas=[(item['N'],Path(item['folder'])/'metadata/rtc.txt') for item in record['traces']
           if item['arm']=='candidate' and item['func']=='d2z_1d']
    metas.append((102400,ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-rowsimplify-retry1-validate-20261022/measurement-validation/102400-d2z_1d/metadata/rtc.txt'))
    actual=OUT/'actual-overlays';actual.mkdir(exist_ok=True);overlays=[]
    for n,log in metas:
        sources=dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',log.read_text(),re.M|re.S))
        for name,raw in sources.items():
            if '_cc_local_v3_role7_' not in name: continue
            c,q=map(int,re.search(r'_C(\d+)_Q(\d+)_',name).groups())
            fields=next(f for f in matrix if int(f[1])==c and int(f[2])==q)
            _,_,_,tpt,tpb,factor=shape(fields)
            if tpt<=q//factor: continue
            cb=int('_CB' in name);source=raw[:-1].replace('_cc_local_v3_','_cc_local_v4_')
            native=(OUT/'default'/f'{c}-{q}-7-{cb}.cpp').read_text()
            a,b,_=input_region(source);_,_,replacement=input_region(native)
            result=source[:a]+replacement+source[b:]
            path=actual/f'{n}-{cb}.cpp';path.write_text(result)
            overlays.append(dict(N=n,C=c,Q=q,callback=cb,path=str(path),runtime_log=str(log),
                                 source_sha256=hashlib.sha256(result.encode()).hexdigest()))
    assert len(overlays)==48,len(overlays)
    tasks=[dict(path=str(path),kind='native',shape=key) for key,path in syntax.items()]
    tasks += [dict(item,kind='actual') for item in overlays]
    def compile_one(item):
        path=Path(item['path']);hip=path.with_suffix('.hip.cpp')
        hip.write_text('#include <hip/hip_runtime.h>\n'+path.read_text())
        assembly=path.with_suffix('.s')
        emit_isa=item['kind']=='actual' and item['N'] in (173056,262144,1048576,204800,102400) and item['callback']==0
        command=[mgr.DTK+'/bin/hipcc','-std=c++17','--offload-arch=gfx936','-mcumode','--cuda-device-only']
        command+=['-O3','-S',hip,'-o',assembly] if emit_isa else ['-fsyntax-only',hip]
        p=subprocess.run(list(map(str,command)),env=mgr.environment(OUT),capture_output=True,text=True,timeout=120)
        path.with_suffix('.err').write_text(p.stderr)
        result=dict(item,complete=p.returncode==0,returncode=p.returncode)
        if p.returncode: result['error']=p.stderr[-2000:]
        if emit_isa and not p.returncode:
            result['isa']=analyze_isa(assembly.read_text());lines=assembly.read_text().splitlines()
            barrier=next(i for i,line in enumerate(lines) if 's_barrier' in line)
            result['static_wait_all_before_first_barrier']=sum('s_waitcnt vmcnt(0)' in line for line in lines[:barrier])
            assert result['isa']['resources']['vgpr_spill_count']==0
        return result
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(compile_one,tasks))
    failures=[x for x in results if not x['complete']]
    report=dict(complete=not failures,device_execution=False,geometries=283,generated_sources=generated,
        unchanged_sources=len(unchanged),changed_sources=changed,native_mapping=mapped,
        q100_extra_scope='Four legal generated/compiled geometries; only N102400 is a registered default performance case. The existing DP SBCC pool has no fifth column length in this N range.',
        q100_generation_N=[int(f[0]) for f in extra],actual_source_overlays=overlays,compiles=results,
        failures=failures,elapsed_seconds=time.monotonic()-start)
    save(RECORD/'host-preflight.json',report)
    print(json.dumps(dict(complete=report['complete'],geometries=283,generated_sources=generated,
        unchanged_sources=len(unchanged),changed_sources=len(changed),compiles=len(results),
        actual_overlays=len(overlays),failures=failures,elapsed_seconds=report['elapsed_seconds'])),flush=True)
    mgr.require(report['complete'],'offline compile failures; all independent cases retained')


if __name__=='__main__': main()
