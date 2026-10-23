"""Type-based v2/v3 row-regression selection and offline compiler evidence; no GPU work."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa

RECORD=ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/rows-v3-regression-20261023'
SOURCE=ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
BUILD=ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-rowsimplify-20261022'
PRE=ROOT/'experiments/EXP-128/artifacts/preflight/rowsimplify-20261022'
V2='21ad4f809a3bb291ab4b32216f028a3b49a63f41'


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def run(argv,label,cwd=ART,timeout=240):
    proc=subprocess.run(list(map(str,argv)),cwd=cwd,env=mgr.environment(ART),capture_output=True,timeout=timeout)
    (ART/(label+'.out')).write_bytes(proc.stdout)
    (ART/(label+'.err')).write_bytes(proc.stderr)
    mgr.require(proc.returncode==0,label+': '+proc.stderr.decode(errors='replace')[-2000:])
    return proc.stdout.decode()


def selection():
    rows=json.loads((ROOT/'experiments/EXP-128/records/rowsimplify-retry1-20261022/results-960099/all-samples-and-statistics.json').read_text())
    severe=[r for r in rows if r['speedup_previous']<.95]
    assert len(severe)==24
    chosen={}
    def add(row,reason):
        key=(row['N'],row['type'])
        item=chosen.setdefault(key,dict(N=row['N'],func=row['type']+'_1d',C=row['C'],Q=row['Q'],
            speedup_previous=row['speedup_previous'],assessment=row['assessment_previous'],reasons=[]))
        if reason not in item['reasons']: item['reasons'].append(reason)
    for row in severe: add(row,'all 24 ratios below 0.95')
    pairs=sorted({(r['type'],r['Q']) for r in severe})
    controls=[]
    for func,q in pairs:
        candidates=sorted([r for r in rows if r['type']==func and r['Q']==q and r['speedup_previous']>=.95],key=lambda r:r['N'])
        assert len(candidates)>=3
        best=max(candidates,key=lambda r:r['speedup_previous'])
        picked=[]
        for row in (best,candidates[0],candidates[-1],*candidates):
            if row['N'] not in {r['N'] for r in picked}: picked.append(row)
            if len(picked)==3: break
        for row in picked:
            add(row,'three same-row-type controls')
            controls.append(dict(N=row['N'],func=func+'_1d',C=row['C'],Q=q))
    for row in rows:
        if row['type']=='d2z' and row['Q']==512: add(row,'entire existing Q512 forward class')
        if row['N'] in (167042,142688): add(row,'positive Q289/Q343 reference')
    cases=sorted(chosen.values(),key=lambda r:(r['N'],r['func']))
    counters={}
    def pmc(row,reason):
        key=(row['N'],row['func'])
        counters.setdefault(key,dict(N=row['N'],func=row['func'],modes=['general','read'],reasons=[]))['reasons'].append(reason)
    for func,q in pairs:
        group=[x for x in cases if x['func']==func+'_1d' and x['Q']==q and x['speedup_previous']<.95]
        group.sort(key=lambda r:(r['assessment']!='更慢',r['speedup_previous']))
        for row in group[:min(2,len(group))]: pmc(row,'type regression representative')
        candidates=[x for x in cases if x['func']==func+'_1d' and x['Q']==q and x['speedup_previous']>=.95]
        pmc(max(candidates,key=lambda r:r['speedup_previous']),'same-type positive/control')
    for n in (173056,262144,1048576):
        pmc(next(x for x in cases if x['N']==n and x['func']=='d2z_1d'),'Q512 odd/even columns and size range')
    for row in cases:
        if row['N'] in (167042,142688): pmc(row,'positive unchanged-type reference')
    ablation=[]
    # Input and output restorations are diagnostic RTC substitutions within v3.
    seeds=[(173056,'d2z_1d'),(262144,'d2z_1d'),(1048576,'d2z_1d'),(204800,'d2z_1d'),
           (497664,'d2z_1d'),(303750,'d2z_1d'),(425984,'d2z_1d'),(574992,'d2z_1d'),
           (167042,'d2z_1d'),(82134,'z2d_1d')]
    for n,func in seeds:
        assert (n,func) in {(r['N'],r['func']) for r in cases}
        for variant in (['restore_input','restore_output','restore_both'] if func=='d2z_1d' else ['restore_output']):
            ablation.append(dict(N=n,func=func,variant=variant,
                pmc_modes=['general','read'] if n in (173056,262144,1048576) and variant=='restore_input' else []))
    result=dict(source_run='960099',threshold=.95,severe_count=24,type_count=len(pairs),cases=cases,
        controls=controls,pmc_cases=list(counters.values()),ablations=ablation,
        timing_rounds=['before profiling for all cases','after profiling for all 24 regressions'],
        scope='Existing default CC plans only; all Q512 d2z sizes and at least three controls per affected row type.',
        formal=False,production_source_modified=False)
    save(RECORD/'selection.json',result)
    return result


def generate_v2(sel):
    overlay=ART/'v2-source';overlay.mkdir(exist_ok=True)
    prefix=SOURCE.relative_to(ROOT).as_posix()
    for rel in ('rtc_stockham_gen.cpp','device/generator/stockham_gen_cc_real_rows.h'):
        path=overlay/rel;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(subprocess.check_output(['git','show',V2+':'+prefix+'/library/src/'+rel],cwd=ROOT))
    matrix=(ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt').read_text().splitlines()
    geometries={(c['C'],c['Q']) for c in sel['cases']}
    selected=[line for line in matrix if tuple(map(int,line.split()[1:3])) in geometries]
    assert len(selected)==len(geometries)
    (ART/'matrix.txt').write_text('\n'.join(selected)+'\n')
    commands=json.loads((BUILD/'compile_commands.json').read_text())
    entry=next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    args=shlex.split(entry['command'])+['--offload-arch=gfx936','-mcumode',
        '-I'+str(SOURCE/'library/src'),'-I'+str(SOURCE/'library/src/device/generator')]
    args[args.index('-o')+1]=str(ART/'v2-generator.o')
    args[args.index('-c')+1]=str(overlay/'rtc_stockham_gen.cpp')
    run(args,'compile-v2-generator',Path(entry['directory']))
    objects=[p for p in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o') if p.name!='rtc_stockham_gen.cpp.o']
    objects+=list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects+=list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    assert objects
    run([mgr.DTK+'/bin/hipcc','--offload-arch=gfx936','-mcumode',PRE/'driver.o',ART/'v2-generator.o',
         *objects,'-pthread','-ldl','-lstdc++fs','-o',ART/'generate-v2'],'link-v2')
    for name,program in [('previous',ART/'generate-v2'),('candidate',PRE/'generate')]:
        folder=ART/name;folder.mkdir(exist_ok=True)
        lines=run([program,ART/'matrix.txt',folder],'generate-'+name).splitlines()
        assert len(lines)==8*len(geometries)
    # Prove the untouched column source, and the consistency of fresh v3 generation.
    compared=[]
    for c,q in sorted(geometries):
        for role in (4,6):
            for cb in (0,1):
                old=(ART/'previous'/f'{c}-{q}-{role}-{cb}.cpp').read_text()
                new=(ART/'candidate'/f'{c}-{q}-{role}-{cb}.cpp').read_text()
                assert new.replace('_cc_local_v3_','_cc_local_v2_')==old
                compared.append(dict(C=c,Q=q,role=role,callback=cb))
    return dict(reference_commit=V2,columns_source_equal_except_version_name=compared,
        reference_generator=str(ART/'generate-v2'),reference_generator_sha256=mgr.common.sha(ART/'generate-v2'),
        candidate_generator=str(PRE/'generate'),candidate_generator_sha256=mgr.common.sha(PRE/'generate'))


def compile_one(item):
    stem=ART/'assembly'/('%d-%s-%s'%(item['N'],item['func'],item['arm']))
    source=Path(item['generated_source'])
    cpp=stem.with_suffix('.hip.cpp');asm=stem.with_suffix('.s')
    cpp.write_text('#include <hip/hip_runtime.h>\n'+source.read_text())
    command=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936','--cuda-device-only','-S','-mcumode',str(cpp),'-o',str(asm)]
    proc=subprocess.run(command,env=mgr.environment(ART),capture_output=True,text=True,timeout=150)
    stem.with_suffix('.err').write_text(proc.stderr)
    if proc.returncode:
        return dict(item,complete=False,error=proc.stderr[-2000:])
    text=asm.read_text()
    info=analyze_isa(text)
    resources=info['resources']
    for key in ('group_segment_fixed_size','wavefront_size','max_flat_workgroup_size'):
        match=re.search(r'\.'+key+r':\s*(\d+)',text)
        if match: resources[key]=int(match[1])
    return dict(item,complete=True,assembly=str(asm),source_sha256=mgr.common.sha(source),command=command,**info)


def main():
    ART.mkdir(parents=True,exist_ok=True);RECORD.mkdir(exist_ok=True)
    sel=selection()
    generated=generate_v2(sel)
    (ART/'assembly').mkdir(exist_ok=True)
    tasks=[]
    for case in sel['cases']:
        role=5 if case['func']=='z2d_1d' else 7
        for arm in ('previous','candidate'):
            path=ART/arm/('%d-%d-%d-0.cpp'%(case['C'],case['Q'],role))
            assert path.exists()
            tasks.append(dict(N=case['N'],func=case['func'],C=case['C'],Q=case['Q'],role=role,arm=arm,generated_source=str(path)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(compile_one,tasks))
    failures=[r for r in result if not r['complete']]
    report=dict(complete=not failures,device_execution=False,generated=generated,kernels=result,failures=failures,
        limitation='Offline compilation of reconstructed native default row sources. Loaded resources and stage time require new device traces/counters.')
    save(RECORD/'host-evidence.json',report)
    pairs=[]
    for case in sel['cases']:
        values={r['arm']:r for r in result if r['N']==case['N'] and r['func']==case['func']}
        if all(x['complete'] for x in values.values()):
            pairs.append(dict(N=case['N'],func=case['func'],C=case['C'],Q=case['Q'],
                resources={arm:x['resources'] for arm,x in values.items()},
                instructions={arm:x['static_instruction_groups'] for arm,x in values.items()},
                static_instructions_equal=values['previous']['instruction_text_sha256']==values['candidate']['instruction_text_sha256']))
    save(RECORD/'host-pairs.json',pairs)
    print(json.dumps(dict(complete=report['complete'],cases=len(sel['cases']),severe=24,types=sel['type_count'],
        compiled=len(result),failures=failures,pmc_pairs=len(sel['pmc_cases']),ablations=len(sel['ablations']),
        Q512=[r for r in pairs if r['func']=='d2z_1d' and r['Q']==512][:4]),ensure_ascii=False,indent=2))
    mgr.require(report['complete'],'offline compiler failures retained')


if __name__=='__main__': main()
