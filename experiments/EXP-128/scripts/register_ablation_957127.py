"""Register and preview the prepared diagnostic; submission remains a separate command."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

SCRIPTS = Path('experiments/EXP-128/scripts')
RECORD = Path('experiments/EXP-128/records/regression-955252-20261022')
ABLATION = RECORD/'ablation-957127'
CONFIG = Path('configs/experiments/EXP-128-cc-regression-ablation-20261022.json')
RUN_ID = 'EXP-128-cc-regression-ablation-20261022'


def read(path):
    return json.loads((ROOT/path).read_text())


def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def save(path, value):
    (ROOT/path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def main():
    selected = read(ABLATION/'selection.json')
    host = read(ABLATION/'host-interposition-test.json')
    mgr.require(host['returncode'] == 0, 'host interposition test failed')
    mgr.require(len(selected['cases']) == 20 and selected['measured_processes'] == 79
                and selected['metadata_processes'] == 16 and len(selected['trials']) == 95,
                'unexpected ablation process coverage')
    mgr.require(not (ROOT/'experiments/EXP-128/runs'/RUN_ID).exists(), 'run already reserved')
    free = shutil.disk_usage(ROOT).free
    mgr.require(free > 5*1024**3, 'insufficient diagnostic disk headroom')
    shim = selected['shim']
    mgr.require(sha(mgr.inside(shim['binary'])) == shim['sha256'], 'host shim identity differs')
    owned_scripts = [SCRIPTS/name for name in (
        'summarize_regression_957127.py', 'inspect_cc_rtc_957127.py', 'isa_cc_957127.py',
        'prototype_cc_957127.py', 'bound_cc_957127.py', 'io_hoist_cc_957127.py',
        'rtc_source_diagnostic.cpp', 'ablate_cc_957127.py', 'register_ablation_957127.py')]
    records = [RECORD/'analysis-957127'/name for name in (
        'counter-summary.json', 'source-comparison.json', 'isa-summary.json',
        'prototype-summary.json', 'bounded-summary.json', 'io-hoist-summary.json',
        '原因核对与候选方案.md', '全部44项原因核对.csv')]
    owned = owned_scripts + records + [ABLATION/'selection.json', ABLATION/'host-interposition-test.json']
    mgr.require(all((ROOT/path).is_file() for path in owned), 'owned diagnostic input missing')
    for path in owned_scripts:
        if path.suffix == '.py':
            compile((ROOT/path).read_text(), str(path), 'exec')
    subprocess.run(['git', 'add', '--', *map(str, owned)], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '--only', '-m',
                    'EXP128: record regression evidence and prepare controlled RTC ablations',
                    '--', *map(str, owned)], cwd=ROOT, check=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()

    original = read(Path('experiments/EXP-128/runs/EXP-128-cc-regression-955252-diagnostic-20261022/preregistration.json'))
    cfg = {key:copy.deepcopy(original[key]) for key in (
        'schema_version', 'policy', 'experiment', 'gpu_arch', 'event_iterations',
        'timing_warmups', 'timing_source_sha256', 'timing_support_sha256',
        'a100_reference', 'diagnostic_program')}
    current = copy.deepcopy(original['arms']['candidate'])
    cfg.update(run_id=RUN_ID, cases=selected['cases'], rtc_ablation=selected,
        arms=dict(previous=copy.deepcopy(current), candidate=current),
        arm_labels=dict(previous='当前原始代码', candidate='同库受控替换代码'),
        comparison_kind='same_library_controlled_rtc_ablation',
        comparison_description='同一已验证库、默认计划及内核参数，仅替换登记的运行时编译源码；用于因果诊断。',
        resources=dict(partition='hx1hdnormal01', cpus=8, time_limit='00:20:00',
                       nodelist='a01r4n01', node_exclusive=True),
        case_scope='20 cases: shared class transformations, three C1024 z2d cases, four Q169 d2z cases, power-of-two and odd endpoints.',
        acceptance='Diagnostic only: exact v3 numerical checks and registered RTC source substitution must pass. Preserve all failures and samples; no production or stable promotion.',
        source_state_policy='Do not lock or compare production workspace state; record only explicit diagnostic input identities.',
        diagnostic_workload=dict(cases=20, clean_timing_processes=79, metadata_processes=16,
                                 processes=95, timing_samples=2370, metadata_samples=480,
                                 event_iterations=30, timing_warmups=10, formal_samples=0))
    runner = SCRIPTS/'ablate_cc_957127.py'
    inputs = [Path(name) for name in (
        'manage.py', 'jobs/workspace_task.slurm', 'tools/workspace_manager/__init__.py',
        'tools/workspace_manager/manager.py', 'tools/workspace_manager/diagnostics.py',
        'tools/workspace_manager/validation_finish.py', 'tools/fft_measurement/common.py',
        'tools/fft_measurement/sample_contract.py', 'tools/fft_measurement/cufft261012_contract.py')]
    inputs += [SCRIPTS/name for name in ('validate_cc_local_unified.py', 'cc_dispatch.py',
        'prototype_cc_957127.py', 'io_hoist_cc_957127.py', 'isa_cc_957127.py',
        'rtc_source_diagnostic.cpp')]
    inputs += [ABLATION/'selection.json', ABLATION/'host-interposition-test.json']
    cfg['diagnostic'] = dict(script=str(ROOT/runner), sha256=sha(runner),
        inputs=[dict(path=str(ROOT/path), sha256=sha(path)) for path in inputs],
        tool_source_commit=commit,
        reason='Isolate measured regression mechanisms with identical accepted library and RTC-only changes; keep metadata collection outside timing trials.')
    program = cfg['diagnostic_program']
    for key in ('binary', 'identity', 'provenance'):
        mgr.require(sha(mgr.inside(program[key])) == program[key+'_sha256'], 'registered program differs: '+key)
    mgr.require(sha(mgr.inside(current['install'])/'lib/librocfft.so.0.1') == current['library_sha256'],
                'accepted library identity differs')
    save(CONFIG, cfg)
    proc = subprocess.run([mgr.PYTHON, '-B', str(ROOT/'manage.py'), 'diagnose',
                           '--config', str(ROOT/CONFIG)], cwd=ROOT, capture_output=True, text=True)
    save(ABLATION/'preview-process.json', dict(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr))
    mgr.require(proc.returncode == 0, 'unified diagnostic preview failed: '+proc.stderr[-2000:])
    preview = json.loads(proc.stdout)
    mgr.require(preview['formal'] is False and preview['cases'] == 20, 'wrong diagnostic preview')
    save(ABLATION/'preview.json', preview)
    summary = dict(config=str(ROOT/CONFIG), tool_source_commit=commit, run_id=RUN_ID,
        cases=20, processes=95, clean_timing_processes=79, metadata_processes=16,
        timing_samples=2370, metadata_samples=480, formal_samples=0,
        library_sha256=current['library_sha256'], node='a01r4n01', free_bytes=free,
        estimated_additional_bytes=1024**3,
        submission_command=preview['submission_command'],
        submit=[mgr.PYTHON, '-B', str(ROOT/'manage.py'), 'diagnose', '--config', str(ROOT/CONFIG), '--execute'])
    save(ABLATION/'registration.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
