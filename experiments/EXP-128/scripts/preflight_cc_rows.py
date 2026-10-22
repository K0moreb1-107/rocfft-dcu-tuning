"""Generate the full native CC matrix and syntax-check distinct row control shapes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT=Path('/public/home/zhangkewei/zr')
SOURCE=ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
OLD=ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021'
BUILD=ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-phasefix-20261022'
OUT=ROOT/'experiments/EXP-128/artifacts/preflight/rowsimplify-20261022'
RECORD=ROOT/'experiments/EXP-128/records/rowsimplify-20261022'
DTK=Path('/public/software/compiler/dtk-26.04')


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def run(argv,label,cwd=OUT,timeout=240):
    p=subprocess.run(list(map(str,argv)),cwd=cwd,capture_output=True,timeout=timeout)
    (OUT/(label+'.out')).write_bytes(p.stdout)
    (OUT/(label+'.err')).write_bytes(p.stderr)
    if p.returncode:
        raise RuntimeError(label+': '+p.stderr.decode(errors='replace')[-4000:])
    return p.stdout.decode()


def models(matrix):
    checked=0
    for fields in matrix:
        n,c,q,cp,ct,ch=map(int,fields[:6])
        p,t=map(int,fields[7:9])
        assert n==2*c*q and p*t>0
        first_factor=int(fields[10].split(',')[0])
        count=q//first_factor
        native=[lane+h*p+w*count for h in range((count+p-1)//p)
                for lane in range(p) if lane+h*p<count for w in range(first_factor)]
        assert sorted(native)==list(range(q))
        for first in sorted({0,(c-1)//t*t}):
            valid=min(t,c-first)
            for component in (0,1):
                head=(first+c*component)%2
                for tid in range(p*t):
                    slot=tid%t
                    for i in range((q+p-1)//p):
                        task=tid+i*p*t
                        j=tid//t+i*p
                        assert task%t==slot and task//t==j
                        if task>=q*t or slot>=valid:
                            assert j>=q or slot>=valid
                            continue
                        index=first+slot+c*(2*j+component)
                        base=first+slot+c*component
                        assert index==base+2*c*j and index%2==base%2
                        vector=slot>=head and (slot-head)%2==0 and slot+1<valid
                        old_scalar=(slot==0 and head==1) or (slot+1==valid and index%2==0)
                        new_scalar=(slot==0 and head==1) or (slot+1==valid and base%2==0)
                        assert old_scalar==new_scalar
                        if vector: assert index%2==0
                        checked+=1
        for row in sorted({1,c-1}):
            for j in range(q):
                k=2*c*j+row
                assert (k>n//2)==(j>=(q+1)//2)
                assert (n-k if k>n//2 else k)==(n-k if j>=(q+1)//2 else k)
                checked+=1
    return checked


def main():
    start=time.monotonic()
    OUT.mkdir(parents=True,exist_ok=True);RECORD.mkdir(parents=True,exist_ok=True)
    matrix=[line.split() for line in (OLD/'native-matrix.txt').read_text().splitlines()]
    assert len(matrix)==283
    checked=models(matrix)
    driver=(OLD/'generate-unified.cpp').read_text()
    driver=driver.replace('if (argc != 3)','if (argc != 3 && argc != 4)')
    driver=driver.replace('cb < 1','cb < 2').replace('if (keep)','if (true)')
    driver=driver.replace('const bool col = role == 4 || role == 6;',
        'if (argc == 4 && role != 7) continue;\nconst bool col = role == 4 || role == 6;')
    driver=driver.replace('auto cbtype = CallbackType::NONE;',
        'if (argc == 4) specs.real_io.load = RealBlockLoad::LDS;\nauto cbtype = CallbackType::NONE;')
    (OUT/'generate.cpp').write_text(driver)
    commands=json.loads((BUILD/'compile_commands.json').read_text())
    entry=next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    args=shlex.split(entry['command'])+['--offload-arch=gfx936','-mcumode']
    args[args.index('-o')+1]=str(OUT/'generator.o')
    run(args,'compile-generator',Path(entry['directory']))
    args[args.index('-o')+1]=str(OUT/'driver.o')
    args[args.index('-c')+1]=str(OUT/'generate.cpp')
    run(args,'compile-driver',Path(entry['directory']))
    objects=[p for p in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o')
             if p.name!='rtc_stockham_gen.cpp.o']
    objects+=list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects+=list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    assert objects
    run([DTK/'bin/hipcc','--offload-arch=gfx936','-mcumode',OUT/'driver.o',OUT/'generator.o',
         *objects,'-pthread','-ldl','-lstdc++fs','-o',OUT/'generate'],'link')
    syntax={}
    comparison=[]
    for mode,extra in [('default',[]),('retained-lds',['lds'])]:
        folder=OUT/mode;folder.mkdir(exist_ok=True)
        lines=[line.split() for line in run([OUT/'generate',OLD/'native-matrix.txt',folder,*extra],
                                           'generate-'+mode).splitlines()]
        assert len(lines)==(2264 if mode=='default' else 566)
        for n,c,q,role,cb,size,name in lines:
            c,q,role,cb=map(int,(c,q,role,cb))
            path=folder/f'{c}-{q}-{role}-{cb}.cpp'
            text=path.read_text()
            assert '_cc_local_v3_role'+str(role) in name
            if role==5:
                assert 'cc_output_p0' in text and 'cc_output_task' not in text
            if role==7:
                assert 'cc_spectrum_p0' in text and 'cc_spectrum_task' not in text
                if mode=='default': assert 'cc_input_row' in text
                steps=((int(n)-1).bit_length()+7)//8
                assert re.search(r'cc_boundary_phase_steps\s*=\s*'+str(steps)+r'\s*;',text)
            if mode=='default' and role in (4,6):
                old=OLD/'unified'/path.name
                if old.exists():
                    assert text.replace('_cc_local_v3_','_cc_local_v2_')==old.read_text(),str(path)
                    comparison.append(dict(C=c,Q=q,role=role,callback=cb))
            if role not in (5,7): continue
            fields=next(f for f in matrix if int(f[1])==c and int(f[2])==q)
            p,t=map(int,fields[7:9])
            # Constants differ by C; these classes cover every row map, parity,
            # alignment, callback and supported loading backend without timing them.
            key=(mode,q,p,t,c%2,c%t==0,role,cb)
            syntax.setdefault(key,path)
    print('GENERATED',2830,'SYNTAX_CLASSES',len(syntax),'MODELED_INDICES',checked,flush=True)

    def compile_one(item):
        key,path=item
        hip=path.with_suffix('.hip.cpp')
        hip.write_text('#include <hip/hip_runtime.h>\n'+path.read_text())
        label='syntax-'+key[0]+'-'+path.stem
        command=[DTK/'bin/hipcc','-std=c++17','--offload-arch=gfx936','-mcumode',
                 '--cuda-device-only','-fsyntax-only',hip]
        try:
            run(command,label,timeout=120)
            return dict(shape=key,source=str(path),returncode=0)
        except Exception as error:
            return dict(shape=key,source=str(path),returncode=1,error=str(error))
        finally:
            hip.unlink()
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(compile_one,item) for item in syntax.items()]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results)%25==0: print('SYNTAX_CHECKED',len(results),'of',len(syntax),flush=True)
    failures=[row for row in results if row['returncode']]
    report=dict(complete=not failures,host_only=True,device_execution=False,
        geometries=283,generated_default_sources=2264,generated_retained_lds_sources=566,
        modeled_indices=checked,syntax_classes=len(syntax),syntax_results=results,
        unchanged_column_fixtures=comparison,failures=failures,
        elapsed_seconds=time.monotonic()-start,
        limitation='Host generation and device-language syntax only; numerical and actual dispatch await device validation.')
    save(RECORD/'host-preflight.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('syntax_results','unchanged_column_fixtures')}))
    return int(bool(failures))


if __name__=='__main__':
    raise SystemExit(main())
