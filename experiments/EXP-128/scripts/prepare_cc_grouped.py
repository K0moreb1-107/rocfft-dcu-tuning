"""Register native-layout grouping against retained EXP125 and measured row v3."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr

RECORD=ROOT/'experiments/EXP-128/records/grouped-20261026'
CONFIGS=ROOT/'configs/experiments'
PREFIX='EXP-128-cc-local-grouped'
DATE='20261026'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/grouped-20261026'


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def commit(paths,message):
    files=[str(path.relative_to(ROOT)) for path in paths]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m',message,'--',*files],cwd=ROOT,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def validation_preflight():
    import validate_cc_local_grouped as validator
    import test_cc_unified_validation as flow
    temporary=ART/'test-tmp';temporary.mkdir(exist_ok=True);tempfile.tempdir=str(temporary)
    flow.validation=validator
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(flow.ValidationFlow))
    mgr.require(tests.wasSuccessful(),'numerical/dispatch failure aggregation tests failed')
    checked=0
    for folder in (ART/'default',ART/'q100-generation-only',ART/'actual-overlays'):
        for path in folder.glob('*.cpp'):
            if path.name.endswith('.hip.cpp'): continue
            text=path.read_text()
            found=re.search(r'extern "C" __global__.*? void ([^(]+)\(',text)
            mgr.require(found is not None,'missing RTC function')
            name=found[1]
            if '_cc_local_v4_role7_' not in name: continue
            q=int(re.search(r'_Q(\d+)_',name)[1])
            validator.input_grouping(name,text,q);checked+=1
    mgr.require(checked==622,'unexpected grouping parser coverage: '+str(checked))
    source=next((ART/'actual-overlays').glob('262144-0.cpp')).read_text()
    name=re.search(r'extern "C" __global__.*? void ([^(]+)\(',source)[1]
    for bad in (source.replace('if(cc_input_row == 0)','if(cc_input_row == 1)',1),
                source.replace('threadIdx.x % 128 < 64','threadIdx.x % 128 < 63')):
        mgr.require(bad!=source,'negative grouping fixture did not change')
        try: validator.input_grouping(name,bad,512)
        except Exception: pass
        else: raise RuntimeError('invalid grouping fixture was accepted')
    return dict(complete=True,numerical_failure_tests=tests.testsRun,source_parser_cases=checked,
                rejected_bad_grouping=2,device_execution=False)


def main():
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
                =='exp-128-cc-local-real','wrong experiment branch')
    proof=read(RECORD/'host-preflight.json')
    mgr.require(proof['complete'] and proof['geometries']==283 and not proof['failures'],
                'grouping generation/compile preflight failed')
    validators=validation_preflight();write(RECORD/'validation-preflight.json',validators)
    free=shutil.disk_usage(ROOT).free;mgr.require(free>12*1024**3,'insufficient build headroom')
    coverage_path=ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    coverage=read(coverage_path);by_n={x['N']:x for x in coverage['public']}
    old=read(CONFIGS/'EXP-128-cc-local-rowsimplify-retry1-validate-20261022.json')
    sample=sorted(set(old['validation']['sample_N'])|{173056,262144,204800})
    mgr.require(set(sample)<=by_n.keys(),'validation case missing from coverage')
    original=read(ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-rowsimplify-retry1-performance-20261022/preregistration.json')
    mgr.require(len(original['cases'])==388 and len({x['N'] for x in original['cases']})==194,'wrong formal matrix')
    matrix=[line.split() for line in (ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt').read_text().splitlines()]
    geometries={(int(f[1]),int(f[2])):f for f in matrix}
    affected=[]
    for case in original['cases']:
        if case['func']!='d2z_1d': continue
        geo=by_n[case['N']];fields=geometries[geo['C'],geo['Q']]
        first=int(fields[10].split(',')[0]);tpt=int(fields[7])
        if tpt>geo['Q']//first: affected.append(dict(case,C=geo['C'],Q=geo['Q']))
    mgr.require(len(affected)==30,'unexpected default grouping scope')
    reference=copy.deepcopy(original['arms']['candidate'])
    baseline=copy.deepcopy(original['arms']['baseline'])
    for arm in (baseline,reference):
        mgr.require(sha(Path(arm['install'])/'lib/librocfft.so.0.1')==arm['library_sha256'],'reference library differs')
    decisions=dict(experiment='EXP-128',predecessor_commit='3bb8359690f4f7458e1683daf41e68e0193861c4',
        implementation='d2z register input: two-register classification groups iff tpt > Q / first factor',
        scope='1D double batch1 out-of-place even N>=65536 generic CC, default plans; no per-size gates',
        references=['EXP125 retained','measured generic row v3','new grouped input v4'],
        validation_N=sample,smoke_N=[262144,102400],validation_checks='numeric and actual fused/grouped path only',
        changed_default_cases=affected,performance_N=194,performance_cases=388,processes=1164,event_samples=34920,
        q100_default_N=[102400],q100_generation_only_N=proof['q100_generation_N'],
        q100_limit='One existing default case, four legal generated geometries. No fifth registered SBCC column kernel in the N range; no plan-table change.',
        free_bytes=free,reserved_peak_bytes=12*1024**3,source_state_freeze=False,reference_installs_rebuilt=False,
        unchanged_production_paths=['z2d','column kernels','d2z output','full-lane register input','retained LDS input','default decomposition'])
    write(RECORD/'decisions.json',decisions)
    source_files=[ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device/generator/stockham_gen_cc_real_rows.h',
                  ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/rtc_stockham_gen.cpp']
    source_files += [ROOT/'experiments/EXP-128/scripts'/name for name in
                     ('validate_cc_local_grouped.py','preflight_cc_grouped.py','prepare_cc_grouped.py')]
    source_files += [RECORD/name for name in ('host-preflight.json','validation-preflight.json','decisions.json','实现说明.md')]
    source_commit=commit(source_files,'EXP128: group partial-lane real CC input by native register pairs')
    build=read(CONFIGS/'EXP-128-cc-local-rowsimplify-build-20261022.json')
    build.update(run_id=PREFIX+'-build-'+DATE)
    build['build'].update(build_id=PREFIX+'-'+DATE,source_commit=source_commit)
    build['resources'].pop('nodelist',None);build['resources']['exclude']='a01r4n05'
    build['acceptance']='Build grouped-input v4 only; separate numerical and actual-path validation follows.'
    build_record=ROOT/'experiments/EXP-128/runs'/build['run_id']/'build-provenance.json'
    validation=copy.deepcopy(old)
    validation.update(run_id=PREFIX+'-validate-'+DATE,build=copy.deepcopy(build['build']))
    for key in ('pending_build_validation','validation_acceptance','queued_submission'): validation.pop(key,None)
    validation['resources'].pop('dependency',None);validation['resources'].pop('nodelist',None)
    validation['existing_build_validation']['build_record']=str(build_record)
    script=ROOT/'experiments/EXP-128/scripts/validate_cc_local_grouped.py'
    validation['post_build_validation']=dict(script=str(script),sha256=sha(script),inputs=[
        dict(path=str(ROOT/'experiments/EXP-128/scripts/cc_dispatch.py'),sha256=sha(ROOT/'experiments/EXP-128/scripts/cc_dispatch.py')),
        dict(path=str(coverage_path),sha256=sha(coverage_path))])
    validation['validation'].update(profile='cc-local-grouped-two-checks-v4',expected_cc_local_version=4,
        smoke_N=[262144,102400],sample_N=sample,
        scope='Numerical result and actual two-kernel v4 dispatch; check pair grouping from native first-pass layout. Include Q512 odd columns/tail, Q200, Q100 odd-factor tail and unchanged row classes.')
    validation['validation']['known_limitations']=[decisions['q100_limit']]
    validation['acceptance']='Two direct-hit smoke sizes, then aggregate remaining numeric and actual path checks. No release callback/memory suite.'
    measure=copy.deepcopy(original)
    for key in ('validation_acceptance','queued_submission','pending_build_validation','installations_sha256'):
        measure.pop(key,None)
    measure.update(run_id=PREFIX+'-performance-'+DATE)
    measure['arms']=dict(baseline=baseline,previous=reference,candidate=dict(build_record=str(build_record)))
    measure['arm_labels']=dict(baseline='EXP125保留对照',previous='通用行端简化v3',candidate='双寄存器分组v4')
    measure['resources'].pop('dependency',None);measure['resources'].pop('nodelist',None)
    measure['measurement_conditions']['reference']='baseline为EXP125保留版，previous为任务960099的行端简化v3，candidate为本轮双寄存器分组v4；三版在同一独占单卡紧邻交替重测。'
    measure['comparison_description']='只改d2z首轮部分线程布局的输入分组。previous为行端简化v3；baseline为EXP125保留版，不是官方库。不改默认分解。'
    measure['acceptance']='Reuse both measured references. Begin default-path timing after candidate numeric and actual v4 grouping validation succeeds. Preserve all 30 samples and median ratios.'
    paths=[]
    for kind,cfg in (('build',build),('validate',validation),('performance',measure)):
        path=CONFIGS/(PREFIX+'-'+kind+'-'+DATE+'.json')
        mgr.require(not path.exists(),'config already exists: '+str(path));write(path,cfg);mgr.load(path);paths.append(path)
    preview=mgr.task_plan('build',build);write(RECORD/'build-preview.json',preview)
    paths.append(RECORD/'build-preview.json')
    commit(paths,'Register EXP128 grouped-input v4 validation and default three-version timing')
    print(json.dumps(dict(source_commit=source_commit,configs=list(map(str,paths)),numeric_path_cases=2*len(sample),
        performance_N=194,performance_cases=388,processes=1164,samples=34920,
        grouped_default_cases=30,reference_installs_rebuilt=False,validation_preflight=validators),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
