"""Register generic row simplification, minimal path coverage and three-version timing."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr

RECORD=ROOT/'experiments/EXP-128/records/rowsimplify-20261022'
CONFIGS=ROOT/'configs/experiments'
PREFIX='EXP-128-cc-local-rowsimplify'
DATE='20261022'


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def commit(paths,message):
    files=[str(path.relative_to(ROOT)) for path in paths]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m',message,'--',*files],cwd=ROOT,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def main():
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
                =='exp-128-cc-local-real','wrong experiment branch')
    proof=read(RECORD/'host-preflight.json')
    mgr.require(proof['complete'] and proof['geometries']==283 and not proof['failures'],
                'native generation/syntax preflight failed')
    free=shutil.disk_usage(ROOT).free
    mgr.require(free>12*1024**3,'insufficient build/diagnostic headroom')
    # Reuse meaningful smoke/aggregation tests against the new validator module.
    temporary=ROOT/'experiments/EXP-128/artifacts/preflight/rowsimplify-20261022/test-tmp'
    temporary.mkdir(exist_ok=True)
    tempfile.tempdir=str(temporary)
    import test_cc_unified_validation as flow
    import validate_cc_local_rows as validator
    flow.validation=validator
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(flow.ValidationFlow))
    mgr.require(tests.wasSuccessful(),'validation failure-handling test failed')
    coverage_path=ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    coverage=read(coverage_path)
    by_n={case['N']:case for case in coverage['public']}
    old_validation=read(CONFIGS/'EXP-128-cc-local-phasefix-validate-20261022.json')
    sample=set(old_validation['validation']['sample_N'])
    controlled=read(ROOT/'experiments/EXP-128/records/regression-955252-20261022/ablation-957127/selection.json')
    sample.update(case['N'] for case in controlled['cases'])
    for q in sorted({case['Q'] for case in by_n.values()}):
        if not any(by_n[n]['Q']==q for n in sample):
            sample.add(next(n for n in sorted(by_n) if by_n[n]['Q']==q))
    for parity in sorted({(case['C']%2,case['Q']%2) for case in by_n.values()}):
        if not any((by_n[n]['C']%2,by_n[n]['Q']%2)==parity for n in sample):
            sample.add(next(n for n in sorted(by_n) if (by_n[n]['C']%2,by_n[n]['Q']%2)==parity))
    mgr.require({by_n[n]['Q'] for n in sample}=={case['Q'] for case in by_n.values()},'default row class omitted')
    build=read(CONFIGS/'EXP-128-cc-local-phasefix-build-20261022.json')
    validation=copy.deepcopy(old_validation)
    measure=read(ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-phasefix-performance-20261022/preregistration.json')
    current=copy.deepcopy(measure['arms']['candidate'])
    for key in ('validation_acceptance','queued_submission','pending_build_validation'):
        measure.pop(key,None);validation.pop(key,None)
    mgr.require(sha(Path(current['install'])/'lib/librocfft.so.0.1')==current['library_sha256'],
                'current v2 reference library identity differs')
    decisions=dict(experiment='EXP-128',predecessor_commit='c9df8682b44d32597374c89abee9c9a154f11430',
        source_scope='z2d output classification; d2z register-input classification and folded output indices',
        path_scope='1D double batch1 out-of-place even N>=65536 default generic CC; no per-N exceptions',
        references=['EXP125 retained','accepted generic CC v2','new generic row v3 candidate'],
        scheduling='No fixed node; gfx936 single-GPU detection and all timing arms on the same GPU per job',
        validation_N=sorted(sample),validation_rows=sorted({by_n[n]['Q'] for n in sample}),
        validation_checks='numerical correctness and actual v3 fused/simplified row dispatch only',
        host_geometries=283,performance_N=194,performance_cases=388,processes=1164,
        event_samples=34920,smoke_N=[65536,167042],free_bytes=free,reserved_peak_bytes=12*1024**3,
        source_state_freeze=False,reference_installs_rebuilt=False,
        excluded_production_changes=['mirror exchange','column boundary merge','old input/store restore','plan selection'])
    write(RECORD/'decisions.json',decisions)
    files=[ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device/generator/stockham_gen_cc_real_rows.h',
           ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/rtc_stockham_gen.cpp']
    files += [ROOT/'experiments/EXP-128/scripts'/name for name in
              ('validate_cc_local_rows.py','preflight_cc_rows.py','prepare_cc_rows.py')]
    files += [RECORD/name for name in ('host-preflight.json','decisions.json','实现说明.md')]
    source_commit=commit(files,'EXP128: simplify generic real CC row classification and folded indices')
    build.update(run_id=PREFIX+'-build-'+DATE)
    build['build'].update(build_id=PREFIX+'-'+DATE,source_commit=source_commit)
    build['resources'].pop('nodelist',None)
    build['acceptance']='Build only; separate numerical and actual v3 dispatch validation follows.'
    build_record=ROOT/'experiments/EXP-128/runs'/build['run_id']/'build-provenance.json'
    validation.update(run_id=PREFIX+'-validate-'+DATE,build=copy.deepcopy(build['build']))
    validation['resources'].pop('dependency',None);validation['resources'].pop('nodelist',None)
    validation['resources']['time_limit']='00:20:00'
    validation['existing_build_validation']['build_record']=str(build_record)
    script=ROOT/'experiments/EXP-128/scripts/validate_cc_local_rows.py'
    validation['post_build_validation']=dict(script=str(script),sha256=sha(script),inputs=[
        dict(path=str(ROOT/'experiments/EXP-128/scripts/cc_dispatch.py'),sha256=sha(ROOT/'experiments/EXP-128/scripts/cc_dispatch.py')),
        dict(path=str(coverage_path),sha256=sha(coverage_path))])
    validation['validation'].update(profile='cc-local-row-simplify-two-checks-v3',
        expected_cc_local_version=3,smoke_N=[65536,167042],sample_N=sorted(sample),
        scope='Numerical result and actual two-kernel v3 dispatch with simplified row source markers; all default row lengths, parities and retained risk cases. No release memory/callback suite.')
    validation['acceptance']='Separate candidate validation; smoke fails fast, then aggregate all independent cases. Actual executed row source must contain the v3 simplification.'
    measure.update(run_id=PREFIX+'-performance-'+DATE)
    measure['arms']['previous']=current
    measure['arms']['candidate']=dict(build_record=str(build_record))
    measure['arm_labels']=dict(baseline='EXP125保留对照',previous='当前通用融合v2',candidate='通用行端简化v3')
    measure['resources'].pop('nodelist',None)
    measure['resources']['time_limit']='02:00:00'
    measure['measurement_conditions']['reference']='baseline为EXP125保留版，previous为已验收通用CC v2，candidate为本轮仅行端简化v3；三版在本轮同一独占单卡重测。'
    measure['comparison_description']='baseline为EXP125保留安装，previous为任务955252已验收的通用CC v2，candidate为本轮仅行端简化v3。新旧EXP128间判断行端简化的增量收益；相对EXP125是版本整体差异。两版EXP128的65536均走通用CC，不改变计划选择。'
    measure['acceptance']='All exact cases must pass the original v3 numerical check outside timing. Measure default plans only after new candidate numeric and actual-dispatch validation succeeds. Preserve every sample and median ratios.'
    for kind,cfg in (('build',build),('validate',validation),('performance',measure)):
        path=CONFIGS/(PREFIX+'-'+kind+'-'+DATE+'.json')
        mgr.require(not path.exists(),'config already exists: '+str(path))
        write(path,cfg)
    paths=[CONFIGS/(PREFIX+'-'+kind+'-'+DATE+'.json') for kind in ('build','validate','performance')]
    for path in paths: mgr.load(path)
    preview=mgr.task_plan('build',build)
    write(RECORD/'build-preview.json',preview)
    commit(paths+[RECORD/'build-preview.json'],'Register EXP128 generic row simplification validation and three-version timing')
    print(json.dumps(dict(source_commit=source_commit,configs=list(map(str,paths)),
        validation_N=len(sample),default_row_lengths=len(decisions['validation_rows']),
        cases=len(measure['cases']),processes=3*len(measure['cases']),fixed_node=False,
        reference_arms={name:arm for name,arm in measure['arms'].items() if name!='candidate'}),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
