"""Register one comprehensive matched diagnosis of v5/v4 and fused/unfused regressions."""
import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
SCRIPTS=ROOT/'experiments/EXP-128/scripts'
RECORD=ROOT/'experiments/EXP-128/records/v5-regression-20261027'
ORIGIN=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-unfused-phasefix-performance-20261027'
RUN='EXP-128-cc-v5-regression-diagnostic-20261027'
DATA=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/results-983952-984725'


def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def commit(paths,message):
    files=[str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m',message,'--',*files],cwd=ROOT,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def main():
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='exp-128-cc-local-real','wrong branch')
    config=ROOT/'configs/experiments'/(RUN+'.json');mgr.require(not config.exists(),'diagnostic already registered')
    selection=read(RECORD/'selection.json');proof=read(RECORD/'compile-preflight.json');facts=read(RECORD/'source-facts.json');tests=read(RECORD/'host-tests.json')
    mgr.require(proof['complete'] and not proof['failures'] and facts['complete'] and tests['complete'],'host preflight failed')
    mgr.require(selection['original_below_one']==dict(previous=95,unfused_cc=43) and selection['original_below_095']==dict(previous=17,unfused_cc=18),'original selection differs')
    mgr.require(shutil.disk_usage(ROOT).free>12*1024**3,'insufficient diagnostic storage headroom')
    cfg=read(ORIGIN/'preregistration.json');origin=read(ORIGIN/'provenance.json')
    mgr.require(origin['complete'] and origin['job_id']=='984725','completed source measurement required')
    for k in ('validation_acceptance','validation_acceptances','queued_submission','continuation','installations_sha256'):cfg.pop(k,None)
    cfg['arms']={a:copy.deepcopy(cfg['arms'][a]) for a in ('previous','unfused_cc','candidate')}
    for a,x in cfg['arms'].items():mgr.require(mgr.common.sha(Path(x['install'])/'lib/librocfft.so.0.1')==x['library_sha256'],'library differs: '+a)
    binary=ROOT/'experiments/EXP-128/artifacts/build/measurement'/ORIGIN.name/'fft_test_1d'
    device=binary.with_name('device_identity')
    mgr.require(all(x['binary_sha256']==mgr.common.sha(binary) for x in origin['arms'].values()),'measured executable differs')
    mgr.require(mgr.common.sha(device)==origin['identity_binary_sha256'],'identity executable differs')
    shim=ROOT/'experiments/EXP-128/artifacts/preflight/ablation-957127/rtc_source_diagnostic.so'
    old=read(ROOT/'configs/experiments/EXP-128-cc-rows-v3-regression-diagnostic-20261023.json')
    mgr.require(mgr.common.sha(shim)==old['rtc_shim']['sha256'],'validated diagnostic interposer differs')
    capabilities=read(RECORD/'profiler-help.json')
    mgr.require('--pmc-write' in capabilities['stdout'],'write counter mode is unavailable')
    # Inventory every negative pair separately; a row may occur in both comparisons.
    by={(x['N'],x['func']):x for x in facts['cases']}
    original_rows=read(DATA/'all-samples-and-statistics.json');inventory=[]
    for row in original_rows:
        for ref in ('previous','unfused_cc'):
            if row['speedup_'+ref]>=1:continue
            f=by[row['N'],row['type']+'_1d']
            inventory.append(dict(N=row['N'],type=row['type'],C=row['C'],Q=row['Q'],comparison=ref,
                original_speedup=row['speedup_'+ref],below_095=row['speedup_'+ref]<.95,
                original_assessment=row['assessment_'+ref],generated_row_equal_v4_v5=f['sources']['row']['equal_except_version_name'],
                generated_column_equal_v4_v5=f['sources']['column']['equal_except_version_name'],row_load=f['row_load'],
                diagnosis='pending controlled device measurements; source equality or LDS selection alone is not a causal verdict'))
    write(RECORD/'case-inventory.json',inventory)
    with (RECORD/'case-inventory.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
    schedule=selection['clean_schedule'];details=selection['mandatory_detailed'];trials=selection['ablations']
    original_severe=[x for x in selection['cases'] if any(v<.95 for v in x['ratios'].values())]
    anchors=sum(1+sum(v<.95 for v in x['ratios'].values()) for x in original_severe)
    required=set((x['N'],x['func'],x['arm']) for x in details)
    for x in trials:
        for a in ('previous','candidate'):required.add((x['N'],x['func'],a))
    minimum_pmc=sum(2+(f=='z2d_1d') for n,f,a in required)
    intervention_pmc=sum(2+(x['func']=='z2d_1d') for x in trials)
    work=dict(formal=False,negative_comparisons=138,negative_cases=115,
        severe_comparisons=35,severe_cases=30,cases_with_controls=len(selection['cases']),
        clean_repeats=2,clean_processes=2*len(schedule),minimum_profile_case_arms=len(required),
        minimum_metadata_and_trace_processes=2*len(required),minimum_counter_processes=minimum_pmc,
        row_intervention_cases=len(trials),row_intervention_processes=6*len(trials),
        row_intervention_counter_processes=intervention_pmc,end_anchor_processes=anchors,
        warmups=10,samples_per_successful_process=30,
        adaptive_policy=selection['adaptive_rule'],production_libraries_rebuilt=False)
    work['minimum_processes']=sum(work[k] for k in ('clean_processes','minimum_metadata_and_trace_processes',
        'minimum_counter_processes','row_intervention_processes','row_intervention_counter_processes','end_anchor_processes'))
    write(RECORD/'workload.json',work)
    cfg.update(run_id=RUN,cases=[dict(N=x['N'],func=x['func']) for x in selection['cases']],
        regression_selection=selection,geometry={str(x['N']):dict(C=x['C'],Q=x['Q']) for x in selection['cases']},
        kernel_versions=dict(previous=4,candidate=5),
        case_scope='Every v5/v4 and fused/same-CC-unfused ratio below one; all ratios below 0.95 have mandatory stage/PMC evidence. Add matched row-type positive controls.',
        diagnostic_program=dict(binary=str(binary),binary_sha256=mgr.common.sha(binary),identity=str(device),
            identity_sha256=mgr.common.sha(device),provenance=str(ORIGIN/'provenance.json'),provenance_sha256=mgr.common.sha(ORIGIN/'provenance.json')),
        rtc_shim=dict(binary=str(shim),sha256=mgr.common.sha(shim),source=str(SCRIPTS/'rtc_source_diagnostic.cpp')),
        diagnostic_workload=work,
        acceptance='Diagnostic only. Matched clean repeats, actual default kernels/sources, separate stage traces and raw PMC units, '
            'whole input/output-region restoration with identity controls, strict numerical checks, all independent failures retained. '
            'Timestamp anomalies invalidate stage times only; retain correlated dispatch/source/counter evidence. No production changes or stable promotion.')
    cfg['resources']=dict(partition='hx1hdnormal01',cpus=8,time_limit='02:00:00',node_exclusive=True,exclude='a01r4n05')
    cfg['comparison_description']='诊断第五版相对第四版和同CC未融合版的退化。单卡受控复测、逐阶段时间、实际资源、读写与共享存储计数、行端单项恢复；不替换已有正式数据。'
    cfg['measurement_conditions']['reference']='复用已验收第四版、第五版和修正容量后的同CC未融合库。诊断时间只与本任务同卡对照，不跨历史节点横比。'
    owned=[SCRIPTS/n for n in ('cc_v5_regression_common.py','preflight_cc_v5_regressions.py',
        'diagnose_cc_v5_regressions.py','test_cc_v5_diagnostic.py','register_cc_v5_regressions.py')]
    owned += [RECORD/n for n in ('selection.json','source-facts.json','compile-preflight.json','host-tests.json',
        'case-inventory.json','case-inventory.csv','workload.json','profiler-help.json','证据现状与诊断安排.md')]
    commit_id=commit(owned,'Prepare complete v5 regression diagnosis with matched stage, counter and row-region evidence')
    dependencies=[ROOT/n for n in ('manage.py','jobs/workspace_task.slurm','tools/workspace_manager/manager.py',
        'tools/workspace_manager/diagnostics.py','tools/fft_measurement/common.py','tools/fft_measurement/sample_contract.py',
        'tools/fft_measurement/cufft261012_contract.py','experiments/EXP-128/scripts/diagnose_rows_v3_regression.py',
        'experiments/EXP-128/scripts/validate_cc_local_unified.py','experiments/EXP-128/scripts/validate_cc_local_grouped.py',
        'experiments/EXP-128/scripts/validate_cc_local_boundary.py','experiments/EXP-128/scripts/cc_dispatch.py',
        'experiments/EXP-128/scripts/cc_regression_evidence.py','experiments/EXP-128/scripts/cc_v5_regression_common.py',
        'experiments/EXP-128/scripts/rtc_source_diagnostic.cpp')]
    dependencies += [RECORD/n for n in ('selection.json','source-facts.json','compile-preflight.json','host-tests.json')]
    runner=SCRIPTS/'diagnose_cc_v5_regressions.py'
    cfg['diagnostic']=dict(script=str(runner),sha256=mgr.common.sha(runner),tool_source_commit=commit_id,
        inputs=[dict(path=str(p),sha256=mgr.common.sha(p)) for p in dependencies],
        reason='Separate reproducible code regressions from changing launch/device conditions, then locate per-case fusion overhead by actual stage timing, resource/counter evidence, and isolated restoration of the v4 row region.')
    write(config,cfg)
    command=[mgr.PYTHON,str(ROOT/'manage.py'),'diagnose','--config',str(config)]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    (RECORD/'preview.err').write_text(result.stderr);mgr.require(result.returncode==0,result.stderr)
    preview=json.loads(result.stdout);write(RECORD/'preview.json',preview)
    mgr.require(not any(x.startswith('--nodelist=') for x in preview['submission_command']),'unexpected fixed node')
    commit([config,RECORD/'preview.json'],'Register one existing-library v5 regression diagnostic allocation')
    print(json.dumps(dict(config=str(config),tool_commit=commit_id,workload=work,
        submission_command=preview['submission_command']),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
