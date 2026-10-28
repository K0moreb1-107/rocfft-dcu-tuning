"""Prepare one small current-vs-EXP125 diagnosis; preview only, no submission."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT / 'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from cc_v5_regression_common import rtc_sources
from prototype_exp125_power2_schedule import transform

RECORD = ROOT / 'experiments/EXP-128/records/exp125-power2-recheck-20261028'
SCRIPTS = ROOT / 'experiments/EXP-128/scripts'
RUN = 'EXP-128-exp125-power2-z2d-diagnostic-20261028'
CONFIG = ROOT / 'configs/experiments' / (RUN + '.json')
ORIGIN = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-performance-20261028'


def read(p):
    return json.loads(p.read_text())


def write(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def commit(paths, message):
    relative = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git', 'add', '--', *relative], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '--only', '-m', message, '--', *relative], cwd=ROOT, check=True)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def main():
    mgr.require(not CONFIG.exists(), 'already registered; read the existing registration')
    mgr.require(not (ROOT / 'experiments/EXP-128/runs' / RUN).exists(), 'run already reserved')
    mgr.require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
                == 'exp-128-cc-local-real', 'wrong branch')
    mgr.require(shutil.disk_usage(ROOT).free > 5 * 1024**3, 'insufficient free space')
    audit = read(RECORD / 'current-vs-exp125-static.json')
    prototype = read(RECORD / 'phase-order-prototypes.json')
    mgr.require(audit['complete'] and prototype['complete'], 'offline preflight failed')
    selected = [x for x in audit['kernels'] if x['version'] != 'exp125' and x['position'] == 1]
    mgr.require(len(selected) == 5, 'five power-of-two rows required')
    expected, geometry, variants, inputs = {}, {}, {}, []
    for row in selected:
        n = row['N']
        c, q = map(int, __import__('re').search(r'_C(\d+)_Q(\d+)_', row['name']).groups())
        geometry[str(n)] = dict(C=c, Q=q)
        expected[str(n)] = {}
        for arm, old in [('baseline', True), ('candidate', False)]:
            kernels = sorted([x for x in audit['kernels'] if x['N'] == n
                              and (x['version'] == 'exp125') == old], key=lambda x: x['position'])
            mgr.require(len(kernels) == 2, 'ambiguous source pair')
            entries = []
            for item in kernels:
                name = item['name']
                source = rtc_sources(Path(item['evidence']).read_text())[name]
                if not old:
                    source = source.replace('_cc_local_v5_', '_cc_local_v6_')
                    name = name.replace('_cc_local_v5_', '_cc_local_v6_')
                entries.append(dict(name=name, sha256=sha_text(source), evidence=item['evidence']))
                if not old and item['position'] == 1:
                    current_name, current_source = name, source
            expected[str(n)][arm] = entries
        folder = RECORD / 'rtc-rules' / str(n)
        folder.mkdir(parents=True)
        original = folder / 'original.cpp'
        original.write_text(current_source)
        phase_source = transform(current_source, q)
        phase = folder / 'phase-order-only.cpp'
        phase.write_text(phase_source)
        # Match the separately compiled prototype including its RTC logger newline.
        proto = next(x for x in prototype['kernels'] if x['N'] == n)
        compiled = Path(proto['source']).read_text().removeprefix('#include <hip/hip_runtime.h>\n')
        mgr.require(compiled.replace('_cc_local_v5_', '_cc_local_v6_').strip() == phase_source.strip(),
                    'registered phase intervention differs from compiled prototype')
        variants[n] = {}
        for label, replacement in [('phase_order', phase), ('identity', original)]:
            rule = dict(name=current_name, original=str(original), replacement=str(replacement),
                        original_sha256=mgr.common.sha(original), replacement_sha256=mgr.common.sha(replacement))
            manifest = folder / (label + '.tsv')
            manifest.write_text(current_name + '\t' + str(original) + '\t' + str(replacement) + '\n')
            variants[n][label] = dict(N=n, func='z2d_1d', arm='candidate', variant=label,
                                     rules=[rule], rules_manifest=str(manifest),
                                     rules_manifest_sha256=mgr.common.sha(manifest),
                                     required_source_names=[current_name])
            inputs.append(manifest)
        inputs += [original, phase]
    schedule, traces, counters = [], [], []
    for i, n in enumerate(sorted(variants)):
        group = [dict(N=n, func='z2d_1d', arm='baseline', variant='original'),
                 dict(N=n, func='z2d_1d', arm='candidate', variant='original'),
                 variants[n]['identity'], variants[n]['phase_order']]
        if i % 2:
            group.reverse()
        for item in group:
            schedule.append(dict(item, index=len(schedule)))
        for arm in (['baseline', 'candidate'] if i % 2 == 0 else ['candidate', 'baseline']):
            traces.append(dict(index=len(traces), N=n, func='z2d_1d', arm=arm, variant='original'))
    for n in (131072, 1048576):
        for arm in ('baseline', 'candidate'):
            for mode in ('general', 'read', 'write'):
                counters.append(dict(index=len(counters), N=n, func='z2d_1d', arm=arm,
                                     variant='original', mode=mode))
        for mode in ('general', 'read'):
            counters.append(dict(variants[n]['phase_order'], index=len(counters), mode=mode))
    selection = dict(clean_schedule=schedule, trace_schedule=traces,
                     counter_schedule=counters, expected_sources=expected,
                     interpretation='Five old EXP125 powers, same-card matched data; phase intervention changes only load order in V6 rows. Padding and packed endpoints are unchanged by the intervention.')
    assert (len(schedule), len(traces), len(counters)) == (20, 10, 16)
    write(RECORD / 'device-selection.json', selection)
    cfg = read(ORIGIN / 'preregistration.json')
    template = read(ROOT / 'configs/experiments/EXP-128-cc-v5-regression-diagnostic-20261027.json')
    for key in ('validation_acceptance', 'validation_acceptances', 'queued_submission',
                'coverage_path', 'coverage_sha256'):
        cfg.pop(key, None)
    cfg.update(run_id=RUN, cases=[dict(N=n, func='z2d_1d') for n in sorted(variants)],
               arms={k:copy.deepcopy(cfg['arms'][k]) for k in ('baseline', 'candidate')},
               arm_labels=dict(baseline='EXP125保留版', candidate='当前第六版及同库相位顺序对照'),
               comparison_kind='exp125_v6_power2_z2d_diagnostic',
               comparison_description='核对旧五个二次幂的列端和行端耗时、读写等待；隔离恢复EXP125相位读取顺序的作用。',
               case_scope='z2d only: N=65536,131072,262144,524288,1048576; both already fused, default decompositions.',
               acceptance='Diagnostic only: strict numerical and actual-fused-source checks; preserve every failure, sample and timestamp warning. No production FFT changes or replacement of formal measurement 991869.',
               geometry=geometry, kernel_versions=dict(candidate=6), power2_selection=selection,
               diagnostic_program=copy.deepcopy(template['diagnostic_program']),
               rtc_shim=copy.deepcopy(template['rtc_shim']),
               resources=dict(partition='hx1hdnormal01', cpus=8, time_limit='00:45:00',
                              node_exclusive=True, exclude='a01r4n05'),
               diagnostic_workload=dict(cases=5, clean_timing_processes=20, clean_samples=600,
                                        metadata_processes=10, trace_processes=10,
                                        counter_processes=16, total_processes=56,
                                        formal_samples=0, warmups=10, event_iterations=30,
                                        expected_peak_additional_bytes=2*1024**3))
    for arm in cfg['arms'].values():
        mgr.require(mgr.common.sha(Path(arm['install']) / 'lib/librocfft.so.0.1') == arm['library_sha256'],
                    'registered measured library differs')
    for key in ('binary', 'identity', 'provenance'):
        mgr.require(mgr.common.sha(Path(cfg['diagnostic_program'][key]))
                    == cfg['diagnostic_program'][key + '_sha256'], 'program provenance differs')
    mgr.require(mgr.common.sha(Path(cfg['rtc_shim']['binary'])) == cfg['rtc_shim']['sha256'],
                'validated interposer differs')
    owned = [SCRIPTS / n for n in ('recheck_exp125_power2_z2d.py', 'prototype_exp125_power2_schedule.py',
                                  'diagnose_exp125_power2_z2d.py', 'register_exp125_power2_z2d.py')]
    owned += [RECORD / n for n in ('current-vs-exp125-static.json', 'phase-order-prototypes.json',
                                  'native-and-planning-evidence.json', 'old-diagnostic-stage-summary.json',
                                  'device-selection.json', 'v5-to-v6-production.diff')]
    owned += inputs
    for path in owned:
        if path.suffix == '.py':
            compile(path.read_text(), str(path), 'exec')
    revision = commit(list(dict.fromkeys(owned)), 'Audit EXP125 versus V6 powers and prepare isolated z2d phase-order diagnosis')
    dependencies = [ROOT / n for n in ('manage.py', 'jobs/workspace_task.slurm',
        'tools/workspace_manager/manager.py', 'tools/workspace_manager/diagnostics.py',
        'tools/fft_measurement/common.py', 'tools/fft_measurement/sample_contract.py',
        'tools/fft_measurement/cufft261012_contract.py',
        'experiments/EXP-128/scripts/diagnose_rows_v3_regression.py',
        'experiments/EXP-128/scripts/diagnose_cc_v5_regressions.py',
        'experiments/EXP-128/scripts/cc_v5_regression_common.py',
        'experiments/EXP-128/scripts/cc_regression_evidence.py',
        'experiments/EXP-128/scripts/validate_cc_local_unified.py',
        'experiments/EXP-128/scripts/validate_cc_local_boundary.py',
        'experiments/EXP-128/scripts/cc_dispatch.py')]
    dependencies += inputs + [RECORD / 'device-selection.json']
    runner = SCRIPTS / 'diagnose_exp125_power2_z2d.py'
    cfg['diagnostic'] = dict(script=str(runner), sha256=mgr.common.sha(runner),
                             inputs=[dict(path=str(p), sha256=mgr.common.sha(p))
                                     for p in dict.fromkeys(dependencies)],
                             tool_source_commit=revision,
                             reason='Separate current V6 stages from EXP125 and isolate the lost phase-load schedule without changing decomposition, packed layout or production source.')
    write(CONFIG, cfg)
    proc = subprocess.run([mgr.PYTHON, str(ROOT / 'manage.py'), 'diagnose', '--config', str(CONFIG)],
                          cwd=ROOT, capture_output=True, text=True)
    write(RECORD / 'preview-process.json', dict(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr))
    mgr.require(proc.returncode == 0, 'preview failed: ' + proc.stderr[-2000:])
    preview = json.loads(proc.stdout)
    mgr.require(preview['cases'] == 5 and not preview['formal'], 'incorrect diagnostic preview')
    mgr.require(not any(x.startswith('--nodelist=') for x in preview['submission_command']), 'fixed node unexpectedly present')
    write(RECORD / 'preview.json', preview)
    registration = dict(config=str(CONFIG), run_id=RUN, tool_source_commit=revision,
                         submission_command=preview['submission_command'], workload=cfg['diagnostic_workload'],
                         status='Reviewed preview; not submitted')
    write(RECORD / 'registration.json', registration)
    commit([CONFIG, RECORD / 'preview.json', RECORD / 'preview-process.json', RECORD / 'registration.json'],
           'Register one five-size EXP125/V6 z2d stage and phase-order diagnostic')
    print(json.dumps(registration, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
