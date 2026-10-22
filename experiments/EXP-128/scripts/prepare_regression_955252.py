"""Register an instrumented diagnosis of the accepted 955252 libraries; no builds."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

RECORD = ROOT/'experiments/EXP-128/records/regression-955252-20261022'
SCRIPTS = ROOT/'experiments/EXP-128/scripts'
ORIGINAL = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-phasefix-performance-20261022'
RUN_ID = 'EXP-128-cc-regression-955252-diagnostic-20261022'


def read(path):
    return json.loads(path.read_text())


def main():
    selection = read(RECORD/'selection.json')
    original = read(ORIGINAL/'provenance.json')
    cfg = copy.deepcopy(read(ORIGINAL/'preregistration.json'))
    mgr.require(original['complete'] and original['job_id'] == '955252','original run not accepted')
    mgr.require(selection['trace_cases'] == len(selection['cases']) == 100,'diagnostic matrix changed')
    mgr.require(selection['severe_cases'] == 44 and selection['counter_processes'] == 196,
                'diagnostic inventory changed')
    mgr.require(shutil.disk_usage(ROOT).free > 5*1024**3,'insufficient diagnostic space reserve')
    binary = ROOT/'experiments/EXP-128/artifacts/build/measurement/EXP-128-cc-local-phasefix-performance-20261022/fft_test_1d'
    identity = binary.with_name('device_identity')
    mgr.require(mgr.common.sha(binary) == 'f46541efa81f6ce9aae4d4f14f743f0274ec974c89268820a92157826e96faba',
                'measured program identity differs')
    mgr.require(mgr.common.sha(identity) == 'c210e3db10d95706ffd328bdbfbbfc5e74d7beb8dad92716d86df6c6991e9a08',
                'measured identity program differs')
    for arm in cfg['arms'].values():
        mgr.require(mgr.common.sha(mgr.inside(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256'],
                    'accepted diagnostic library differs')
    for name in ('queued_submission','validation_acceptance'):
        cfg.pop(name,None)
    cfg.update(run_id=RUN_ID,case_scope=selection['case_scope'],
        cases=[dict(N=item['N'],func=item['func']) for item in selection['cases']],
        geometry={str(item['N']):dict(C=item['C'],Q=item['Q']) for item in selection['cases']},
        pmc_cases=selection['pmc_cases'],
        acceptance='Instrumented diagnosis only. Keep all independent failures and original 955252 formal data. '
                   'Validate exact numerical results and actual execution windows; compare the accepted default paths. '
                   'No candidate source change, no new formal timing, no automatic stable promotion.',
        diagnostic_program=dict(binary=str(binary),binary_sha256=mgr.common.sha(binary),
            identity=str(identity),identity_sha256=mgr.common.sha(identity),
            provenance=str(ORIGINAL/'provenance.json'),provenance_sha256=mgr.common.sha(ORIGINAL/'provenance.json'),
            gpu=original['gpu']),
        diagnostic_workload=dict(formal=False,severe_cases=44,cases=100,versions=3,
            metadata_processes=300,clean_trace_processes=300,counter_processes=196,
            expected_processes=796,max_counter_format_compatibility_retries=4,
            event_samples_per_timing_process=30,expected_formal_samples=0,
            interpretation='Metadata and clean timelines use separate processes. Counter timings are not formal performance. '
                           'Use measured windows after ten warmups; preserve raw SDK field names and units.'))
    cfg['resources'].update(time_limit='02:00:00',cpus=8,nodelist='a01r4n01',node_exclusive=True)
    cfg['resources'].pop('dependency',None)
    inputs = [ROOT/path for path in (
        'manage.py','jobs/workspace_task.slurm',
        'tools/workspace_manager/manager.py','tools/workspace_manager/diagnostics.py',
        'tools/workspace_manager/validation_finish.py',
        'tools/fft_measurement/common.py','tools/fft_measurement/sample_contract.py',
        'tools/fft_measurement/cufft261012_contract.py',
        'experiments/EXP-128/scripts/cc_dispatch.py',
        'experiments/EXP-128/scripts/validate_cc_local_unified.py',
        'experiments/EXP-128/scripts/cc_regression_evidence.py',
        'experiments/EXP-128/records/regression-955252-20261022/selection.json')]
    owned = [SCRIPTS/name for name in (
        'prepare_regression_955252.py','preflight_regression_955252.py',
        'cc_regression_evidence.py','test_cc_regression_evidence.py','diagnose_cc_regression_955252.py')]
    owned += [RECORD/name for name in ('selection.json','inventory.json','全部严重退化项.csv',
              '低于0.95-baseline.csv','低于0.95-previous.csv','host-evidence.json','README.md')]
    for path in owned:
        mgr.require(path.is_file(),'diagnostic preparation missing '+str(path))
    # Commit only this diagnosis's files; unrelated source and AGENTS stay untouched.
    subprocess.run(['git','add','--']+[str(path.relative_to(ROOT)) for path in owned],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record EXP128 severe-regression diagnostic inputs','--']+
                   [str(path.relative_to(ROOT)) for path in owned],cwd=ROOT,check=True)
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    runner = SCRIPTS/'diagnose_cc_regression_955252.py'
    cfg['diagnostic'] = dict(script=str(runner),sha256=mgr.common.sha(runner),
        inputs=[dict(path=str(path),sha256=mgr.common.sha(path)) for path in inputs],
        tool_source_commit=commit,
        reason='Diagnose all 44 exact cases below 0.95x in job 955252, separating plan selection, column/row time, '
               'resources and memory counters from hypotheses; controls cover each affected family.')
    config = ROOT/'configs/experiments'/(RUN_ID+'.json')
    config.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
    preview = subprocess.run([mgr.PYTHON,str(ROOT/'manage.py'),'diagnose','--config',str(config)],
                             cwd=ROOT,capture_output=True,text=True)
    (RECORD/'preview.out').write_text(preview.stdout)
    (RECORD/'preview.err').write_text(preview.stderr)
    mgr.require(preview.returncode == 0,'diagnostic preview failed; inspect recorded stderr')
    planned = json.loads(preview.stdout)
    (RECORD/'preview.json').write_text(json.dumps(planned,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(config=str(config),tool_commit=commit,workload=cfg['diagnostic_workload'],
        node=cfg['resources'],library_sha256={name:arm['library_sha256'] for name,arm in cfg['arms'].items()},
        submission_command=planned['submission_command'],space_free_bytes=shutil.disk_usage(ROOT).free),
        ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
