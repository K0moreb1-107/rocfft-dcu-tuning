"""Register and preview one comprehensive v2/v3 diagnosis without rebuilding FFT libraries."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

RECORD=ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023'
SCRIPTS=ROOT/'experiments/EXP-128/scripts'
ORIGINAL=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-rowsimplify-retry1-performance-20261022'
RUN='EXP-128-cc-rows-v3-regression-diagnostic-20261023'


def read(path): return json.loads(path.read_text())


def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def main():
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
                =='exp-128-cc-local-real','wrong experiment branch')
    config=ROOT/'configs/experiments'/(RUN+'.json')
    mgr.require(not config.exists(),'diagnosis already registered; inspect its receipts')
    sel=read(RECORD/'selection.json')
    proof=read(RECORD/'host-evidence.json');restore=read(RECORD/'restoration-preflight.json')
    mgr.require(proof['complete'] and restore['complete'] and not proof['failures'] and not restore['failures'],
                'host preflight incomplete')
    mgr.require(len(sel['cases'])==57 and sel['severe_count']==24 and sel['type_count']==9,'selection changed')
    mgr.require(shutil.disk_usage(ROOT).free>8*1024**3,'insufficient diagnostic artifact headroom')
    cfg=read(ORIGINAL/'preregistration.json');origin=read(ORIGINAL/'provenance.json')
    mgr.require(origin['complete'] and origin['job_id']=='960099','original measurement incomplete')
    cfg['arms']={arm:copy.deepcopy(cfg['arms'][arm]) for arm in ('previous','candidate')}
    for arm,identity in cfg['arms'].items():
        mgr.require(mgr.common.sha(Path(identity['install'])/'lib/librocfft.so.0.1')==identity['library_sha256'],
                    arm+' library identity differs')
    binary=ROOT/'experiments/EXP-128/artifacts/build/measurement'/ORIGINAL.name/'fft_test_1d'
    device=binary.with_name('device_identity')
    mgr.require(all(a['binary_sha256']==mgr.common.sha(binary) for a in origin['arms'].values()),'timing executable differs')
    mgr.require(mgr.common.sha(device)==origin['identity_binary_sha256'],'identity executable differs')
    shim_dir=ROOT/'experiments/EXP-128/artifacts/preflight/ablation-957127'
    shim=shim_dir/'rtc_source_diagnostic.so'
    old=read(ROOT/'experiments/EXP-128/records/regression-955252-20261022/ablation-957127/selection.json')
    mgr.require(mgr.common.sha(shim)==old['shim']['sha256'],'accepted RTC source interposer differs')
    host_test=read(ROOT/'experiments/EXP-128/records/regression-955252-20261022/ablation-957127/host-interposition-test.json')
    mgr.require(host_test['returncode']==0,'source interposition host test not accepted')
    for key in ('queued_submission','validation_acceptance','deferred_measurement'):
        cfg.pop(key,None)
    cases=[dict(N=x['N'],func=x['func']) for x in sel['cases']]
    counters=[]
    for index,item in enumerate(sel['pmc_cases']):
        order=('previous','candidate') if index%2==0 else ('candidate','previous')
        for arm in order: counters.append(dict(item,index=len(counters),arm=arm))
    ablations=list(sel['ablations'])
    for n in (262144,167042):
        ablations.append(dict(N=n,func='d2z_1d',variant='identity',pmc_modes=[]))
    # Keep each pair of row restorations together for adjacent clean controls.
    keys=list(dict.fromkeys((x['N'],x['func']) for x in ablations))
    ablations=[item for key in keys for item in ablations if (item['N'],item['func'])==key]
    extra_counters=sum(len(item['pmc_modes']) for item in ablations)
    metadata_extra=sum(bool(item['pmc_modes']) for item in ablations)
    work=dict(formal=False,cases=57,versions=2,severe_cases=24,types=9,
        clean_before_after_processes=2*len(cases)+2*24,
        metadata_processes=2*len(cases),clean_timeline_processes=2*len(cases),
        counter_processes=sum(len(x['modes']) for x in counters)+extra_counters,
        row_restoration_processes=len(ablations),row_restoration_metadata_processes=metadata_extra,
        adjacent_restoration_anchor_processes=3*len(keys),warmups=10,event_samples=30,
        profiler_export_compatibility_retries_at_most=4,expected_formal_samples=0)
    work['expected_processes']=sum(work[k] for k in (
        'clean_before_after_processes','metadata_processes','clean_timeline_processes','counter_processes',
        'row_restoration_processes','row_restoration_metadata_processes','adjacent_restoration_anchor_processes'))
    mgr.require(work['expected_processes']==567,'workload count differs')
    cfg.update(run_id=RUN,cases=cases,selection=sel['cases'],geometry={str(x['N']):dict(C=x['C'],Q=x['Q']) for x in sel['cases']},
        case_scope='All 24 ratios below 0.95 in job960099; 27 same-type controls; complete Q512 d2z class; Q289/Q343 positive controls.',
        kernel_versions=dict(previous=2,candidate=3),pmc_cases=counters,ablations=ablations,
        diagnostic_program=dict(binary=str(binary),binary_sha256=mgr.common.sha(binary),identity=str(device),
            identity_sha256=mgr.common.sha(device),provenance=str(ORIGINAL/'provenance.json'),
            provenance_sha256=mgr.common.sha(ORIGINAL/'provenance.json'),original_gpu=origin['gpu']),
        rtc_shim=dict(binary=str(shim),sha256=mgr.common.sha(shim),source=str(SCRIPTS/'rtc_source_diagnostic.cpp')),
        diagnostic_workload=work,
        acceptance='Diagnostic evidence only: numerical checks, actual default v2/v3 dispatch and timing windows, '
            'separate clean traces/metadata/PMC, adjacent input-only/output-only/both-old row restorations. '
            'Aggregate all independent failures. No production edits, new formal result, rebuilding or stable promotion.')
    cfg['resources']=dict(partition='hx1hdnormal01',cpus=8,time_limit='02:00:00',node_exclusive=True,exclude='a01r4n05')
    cfg['measurement_conditions']['reference']='通用融合v2与行端简化v3，同一次诊断中单卡相邻对照；原960099正式结果保留。'
    cfg['comparison_description']='仅诊断行端简化退化；对照为已验收v2与已保存v3，不使用EXP125或官方库。'
    runner=SCRIPTS/'diagnose_rows_v3_regression.py'
    dependencies=[ROOT/path for path in (
        'manage.py','jobs/workspace_task.slurm','tools/workspace_manager/manager.py',
        'tools/workspace_manager/diagnostics.py','tools/workspace_manager/validation_finish.py',
        'tools/fft_measurement/common.py','tools/fft_measurement/sample_contract.py','tools/fft_measurement/cufft261012_contract.py',
        'experiments/EXP-128/scripts/validate_cc_local_unified.py','experiments/EXP-128/scripts/cc_dispatch.py',
        'experiments/EXP-128/scripts/cc_regression_evidence.py','experiments/EXP-128/scripts/rtc_source_diagnostic.cpp')]
    dependencies += [RECORD/'selection.json',RECORD/'host-evidence.json',RECORD/'restoration-preflight.json']
    owned=[SCRIPTS/name for name in ('preflight_rows_regression.py','preflight_rows_diagnostic.py',
        'diagnose_rows_v3_regression.py','register_rows_regression.py')]
    owned += [RECORD/name for name in ('selection.json','host-evidence.json','host-pairs.json','restoration-preflight.json','分析与诊断安排.md')]
    files=[str(p.relative_to(ROOT)) for p in owned]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Register type-wide diagnosis of row-simplification regressions with matched RTC restorations',
                    '--',*files],cwd=ROOT,check=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    cfg['diagnostic']=dict(script=str(runner),sha256=mgr.common.sha(runner),
        inputs=[dict(path=str(path),sha256=mgr.common.sha(path)) for path in dependencies],tool_source_commit=commit,
        reason='Resolve all 24 v3/v2 regressions by row class: stage time, address/control scheduling, loaded capacity, '
               'memory/compute counters and adjacent input/output row restorations; retain all independent failures.')
    write(config,cfg)
    argv=[mgr.PYTHON,str(ROOT/'manage.py'),'diagnose','--config',str(config)]
    preview=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
    (RECORD/'preview.out').write_text(preview.stdout);(RECORD/'preview.err').write_text(preview.stderr)
    mgr.require(preview.returncode==0,'diagnostic preview failed: '+preview.stderr)
    plan=json.loads(preview.stdout)
    mgr.require('--exclude=a01r4n05' in plan['submission_command'],'failed node not excluded')
    mgr.require(not any(x.startswith('--nodelist=') for x in plan['submission_command']),'fixed node unexpectedly requested')
    write(RECORD/'preview.json',plan)
    write(RECORD/'workload.json',work)
    owned=[config,RECORD/'preview.json',RECORD/'workload.json']
    files=[str(p.relative_to(ROOT)) for p in owned]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record preview of existing-library row regression diagnosis',
                    '--',*files],cwd=ROOT,check=True)
    print(json.dumps(dict(config=str(config),tool_commit=commit,workload=work,submission_command=plan['submission_command'],
        fixed_node=False,source_modified=False,free_bytes=shutil.disk_usage(ROOT).free),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
