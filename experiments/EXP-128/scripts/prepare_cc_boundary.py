"""Register boundary v5 and a genuinely unfused same-CC control, with four-arm timing."""
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
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr

RECORD=ROOT/'experiments/EXP-128/records/boundary-v5-20261027'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027'
CONFIGS=ROOT/'configs/experiments'
DATE='20261027'
PREFIX='EXP-128-cc-local-boundary-v5'
OFF='EXP-128-cc-local-unfused-cc'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def commit(paths,message):
    files=[str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m',message,'--',*files],cwd=ROOT,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def validation_preflight():
    import validate_cc_local_boundary as validator
    import test_cc_unified_validation as flow
    temporary=ART/'test-tmp';temporary.mkdir(exist_ok=True);tempfile.tempdir=str(temporary)
    flow.validation=validator
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(flow.ValidationFlow))
    mgr.require(result.wasSuccessful(),'numerical failure/aggregation tests failed')
    cases=0;features=[]
    for path in (ART/'default').glob('*.cpp'):
        if path.name.endswith('.hip.cpp'):continue
        text=path.read_text();name=re.search(r'extern "C" __global__.*? void ([^(]+)\(',text)[1]
        match=re.search(r'_cc_local_v5_role([457])_C(\d+)_Q(\d+)_',name)
        if not match or match[1]=='4':continue
        role,c,q=map(int,match.groups());func='z2d_1d' if role==5 else 'd2z_1d'
        features.append(validator.row_features(name,text,c,q,func));cases+=1
    mgr.require(cases==1132,'unexpected generated row parser coverage')
    # Use actual historical standalone-boundary names, not a guessed spelling.
    evidence=read(ROOT/'experiments/EXP-128/records/regression-955252-20261022/analysis-957127/source-comparison.json')
    historical=[x for x in evidence['kernels'] if x['N']==69938 and x['arm']=='baseline']
    mgr.require(len(historical)==2,'standalone historical name fixture missing')
    for x in historical:
        names=[k['name'] for k in x['kernels']]
        validator.validate_names(names,289,121,x['func'],False)
        for bad in ([names[0],names[0],*names[1:]],
                    [name+'_paired_post_rows_N69938' if '_sbrc_' in name else name for name in names]):
            try:validator.validate_names(bad,289,121,x['func'],False)
            except ValueError:pass
            else:raise RuntimeError('bad unfused dispatch accepted')
        try:validator.validate_names(names,289,125,x['func'],False)
        except ValueError:pass
        else:raise RuntimeError('wrong CC decomposition accepted')
    for fused in (False,True):
        value='ON' if fused else 'OFF'
        good=''.join(key+':BOOL='+value+'\n' for key in ('ROCFFT_CC_REAL_FUSION','ROCFFT_CC_LOCAL_REAL_FUSION'))
        validator.build_switches(good,fused)
        for bad in (good.replace('ROCFFT_CC_REAL_FUSION:BOOL='+value,'ROCFFT_CC_REAL_FUSION:BOOL='+('OFF' if fused else 'ON')),
                    good.splitlines()[0]+'\n'):
            try:validator.build_switches(bad,fused)
            except ValueError:pass
            else:raise RuntimeError('invalid fused/unfused build switches accepted')
    return dict(complete=True,device_execution=False,flow_tests=result.testsRun,
                generated_row_parser_cases=cases,historical_unfused_cases=2,
                packed_sources=sum(x.get('packed_output',False) for x in features),
                recurrent_sources=sum(x.get('phase_recurrence',False) for x in features))


def main():
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
        =='exp-128-cc-local-real','wrong branch')
    proof=read(RECORD/'host-preflight.json');entry=read(RECORD/'entry-tests.json')
    mgr.require(proof['complete'] and proof['geometries']==283 and not proof['failures'],'generation/compile failed')
    mgr.require(entry['complete'] and not entry['failures'] and not entry['errors'],'four-arm entry tests failed')
    validators=validation_preflight();write(RECORD/'validation-preflight.json',validators)
    free=shutil.disk_usage(ROOT).free;mgr.require(free>32*1024**3,'insufficient space for two independent builds')
    coverage_path=ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    public=read(coverage_path)['public'];by_n={x['N']:x for x in public}
    original=read(ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-grouped-performance-20261026/preregistration.json')
    mgr.require(len(original['cases'])==388 and len({x['N'] for x in original['cases']})==194,'wrong performance matrix')
    baseline=copy.deepcopy(original['arms']['baseline']);previous=copy.deepcopy(original['arms']['candidate'])
    mgr.require(previous['library_sha256']=='6b4a635fd1e29ca12a42fefc2fdf3f981054c9506fa8c8380c9b1bfc7afdb21f',
                'previous must be the accepted fourth version')
    for arm in (baseline,previous):
        mgr.require(sha(Path(arm['install'])/'lib/librocfft.so.0.1')==arm['library_sha256'],'reference library differs')
    old=read(CONFIGS/'EXP-128-cc-local-grouped-validate-20261026.json')
    sample=sorted(set(old['validation']['sample_N'])|{max(by_n)})
    # One representative for every changed native row layout; reuse the previous matrix.
    matrix=[line.split() for line in (ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt').read_text().splitlines()]
    geometry={(int(f[1]),int(f[2])):f for f in matrix}
    def row_class(n):
        g=by_n[n];f=geometry[g['C'],g['Q']]
        return (g['Q'],int(f[7]),int(f[8]),f[10])
    for row in sorted({row_class(n) for n in by_n}):
        if row not in {row_class(n) for n in sample}:
            sample.append(min(n for n in by_n if row_class(n)==row))
    sample=sorted(sample)
    off_sample=sorted({65536,131072,262144,524288,1048576,69938,72250,82134,102400,173056,191664,max(by_n)})
    mgr.require(set(sample+off_sample)<=by_n.keys(),'invalid representative')
    decisions=dict(scope='1D double batch1 OOP even N>=65536 generic CC; all default plans',
        changes=['z2d packed output iff C and row-block count are even and C is divisible by that count',
                 'd2z ordinary row phases recur in native first-pass order iff lookup count decreases'],
        unfused_switches=dict(ROCFFT_CC_REAL_FUSION='OFF',ROCFFT_CC_LOCAL_REAL_FUSION='OFF'),
        same_decomposition=True,default_decomposition_changed=False,
        references=dict(baseline=baseline,previous=previous),new_arms=['unfused_cc','candidate'],
        reference_installs_rebuilt=False,source_state_freeze=False,
        validation_N=dict(candidate=sample,unfused_cc=off_sample),validation='numerical and actual path only',
        performance_N=194,performance_cases=388,processes=1552,event_samples=46560,
        free_bytes=free,reserved_peak_bytes=32*1024**3,
        limitations=['Same-CC OFF/ON measures the complete fusion pipeline, including its necessary intermediate layout changes.',
                     'No device correctness or performance acceptance is implied by host preflight.'])
    write(RECORD/'decisions.json',decisions)
    files=[ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device/generator/stockham_gen_cc_real_rows.h',
           ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/rtc_stockham_gen.cpp']
    files += [ROOT/'tools'/name for name in (
        'fft_measurement/cufft261012_contract.py','fft_measurement/plot_cufft261012.py',
        'fft_measurement/summarize_cufft261012.py','fft_measurement/test_cufft261012.py',
        'workspace_manager/manager.py','workspace_manager/pending_build_validation.py',
        'workspace_manager/revalidate.py','workspace_manager/test_dual_revalidate.py')]
    files += [ROOT/'experiments/EXP-128/scripts'/name for name in
        ('validate_cc_local_boundary.py','preflight_cc_boundary.py','prepare_cc_boundary.py','submit_cc_boundary.py')]
    files += [RECORD/name for name in ('host-preflight.json','entry-tests.json','validation-preflight.json','decisions.json','实现说明.md')]
    source_commit=commit(files,'EXP128: simplify packed row output and recur native row boundary phases')
    cfgpaths=[];builds={}
    for variant,prefix,on in [('candidate',PREFIX,True),('unfused_cc',OFF,False)]:
        build=read(CONFIGS/'EXP-128-cc-local-grouped-build-20261026.json')
        build.update(run_id=prefix+'-build-'+DATE)
        build['build'].update(build_id=prefix+'-'+DATE,source_commit=source_commit)
        build['build']['cmake'].update(ROCFFT_CC_REAL_FUSION='ON' if on else 'OFF',ROCFFT_CC_LOCAL_REAL_FUSION='ON' if on else 'OFF')
        build['resources'].pop('nodelist',None);build['acceptance']='Pure '+variant+' build; independent numerical/path validation follows.'
        validation=copy.deepcopy(old)
        for key in ('pending_build_validation','validation_acceptance','queued_submission'):validation.pop(key,None)
        validation.update(run_id=prefix+'-validate-'+DATE,build=copy.deepcopy(build['build']))
        validation['resources'].pop('dependency',None);validation['resources'].pop('nodelist',None)
        validation['existing_build_validation']=dict(build_record=str(mgr.locations(build,'build')['run']/'build-provenance.json'),
            evidence_record='cc-boundary-validation.json',isolated_helpers=False)
        script=ROOT/'experiments/EXP-128/scripts/validate_cc_local_boundary.py'
        inputs=[ROOT/'experiments/EXP-128/scripts'/name for name in ('cc_dispatch.py','validate_cc_local_grouped.py')]+[coverage_path]
        validation['post_build_validation']=dict(script=str(script),sha256=sha(script),
            inputs=[dict(path=str(p),sha256=sha(p)) for p in inputs])
        validation['validation']=dict(profile='cc-boundary-v5-two-checks',variant='fused' if on else 'unfused_cc',
            coverage=str(coverage_path),smoke_N=[65536,102400] if on else [65536,69938],
            sample_N=sample if on else off_sample,
            scope='Numerical results, exact default C/Q, and actual two v5 stages.' if on
                  else 'Numerical results, exact default C/Q, and three independent stages; both fusion gates OFF including old five powers of two.')
        validation['acceptance']='Only numerical and actual-path checks; aggregate all independent main-matrix failures.'
        for kind,cfg in [('build',build),('validate',validation)]:
            path=CONFIGS/(prefix+'-'+kind+'-'+DATE+'.json');mgr.require(not path.exists(),'config already exists: '+str(path))
            write(path,cfg);mgr.load(path);cfgpaths.append(path)
        builds[variant]=build
        preview=mgr.task_plan('build',build);p=RECORD/(variant+'-build-preview.json');write(p,preview);cfgpaths.append(p)
    measure=copy.deepcopy(original)
    for key in ('validation_acceptance','validation_acceptances','queued_submission','pending_build_validation','installations_sha256'):measure.pop(key,None)
    measure.update(run_id=PREFIX+'-performance-'+DATE,comparison_kind='version_comparison')
    measure['arms']=dict(baseline=baseline,previous=previous,
        unfused_cc=dict(build_record=str(mgr.locations(builds['unfused_cc'],'build')['run']/'build-provenance.json')),
        candidate=dict(build_record=str(mgr.locations(builds['candidate'],'build')['run']/'build-provenance.json')))
    measure['arm_labels']=dict(baseline='EXP125保留版',previous='通用融合第四版',unfused_cc='同CC未融合',candidate='行端改进第五版')
    measure['resources'].pop('dependency',None);measure['resources'].pop('nodelist',None)
    measure['comparison_description']='四版同卡相邻交替：EXP125保留版、已验收第四版、同CC分解未融合版、第五版。未融合版同时关闭新旧融合，五个二次幂也执行独立前后处理。'
    measure['measurement_conditions']['reference']='复用EXP125与第四版；另构建同源同CC未融合对照。四版每组合10次预热、30次计时，1552进程、46560个正式样本。'
    measure['acceptance']='Start only after candidate and same-CC unfused independent validation both succeed; preserve all samples, use medians only.'
    mp=CONFIGS/(PREFIX+'-performance-'+DATE+'.json');mgr.require(not mp.exists(),'measurement config already exists')
    write(mp,measure);mgr.load(mp);cfgpaths.append(mp)
    commit(cfgpaths,'Register EXP128 boundary v5 and same-CC unfused four-arm experiment')
    print(json.dumps(dict(source_commit=source_commit,validation_N=dict(candidate=len(sample),unfused_cc=len(off_sample)),
        default_N=194,cases=388,processes=1552,samples=46560,validation_preflight=validators,
        reference_installs_rebuilt=False),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
