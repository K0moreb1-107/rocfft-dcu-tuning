"""Register output-only v6 and reuse three validated references for four-arm timing."""
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

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr

DATE = '20261028'
PREFIX = 'EXP-128-cc-local-row-output-v6'
RECORD = ROOT/'experiments/EXP-128/records/row-output-v6-20261028'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/row-output-v6-20261028'
CONFIGS = ROOT/'configs/experiments'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def commit(paths, message):
    relative = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git', 'add', '--', *relative], cwd=ROOT, check=True)
    p = subprocess.run(['git', 'commit', '--only', '-m', message, '--', *relative],
                       cwd=ROOT, capture_output=True, text=True)
    mgr.require(p.returncode == 0, p.stdout+p.stderr)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def validation_preflight():
    import validate_cc_row_output_v6 as validator
    import test_cc_unified_validation as flow
    temporary = ART/'test-tmp'
    temporary.mkdir(exist_ok=True)
    tempfile.tempdir = str(temporary)
    flow.validation = validator
    test = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(flow.ValidationFlow))
    mgr.require(test.wasSuccessful(), 'validation numerical-failure/aggregation control flow failed')
    counts = {}
    cases = 0
    for path in (ART/'default').glob('*.cpp'):
        if path.name.endswith('.hip.cpp'):
            continue
        text = path.read_text()
        name = re.search(r'extern "C" __global__.*? void ([^(]+)\(', text)[1]
        match = re.search(r'_cc_local_v6_role([57])_C(\d+)_Q(\d+)_', name)
        if not match:
            continue
        role, c, q = map(int, match.groups())
        func = 'z2d_1d' if role == 5 else 'd2z_1d'
        features = validator.row_features(name, text, c, q, func)
        counts[features['output_strategy']] = counts.get(features['output_strategy'], 0)+1
        cases += 1
    mgr.require(cases == 1132, 'unexpected row parser matrix')
    return dict(complete=True, device_execution=False, flow_tests=test.testsRun,
                generated_row_parser_cases=cases, output_sources=counts)


def main():
    mgr.require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
                == 'exp-128-cc-local-real', 'wrong branch')
    proof = read(RECORD/'host-preflight.json')
    mgr.require(proof['complete'] and proof['geometries'] == 283 and not proof['failures']
                and not proof['input_changed'] and not proof['column_changed'], 'host generation proof incomplete')
    validators = validation_preflight()
    write(RECORD/'validation-preflight.json', validators)
    coverage_path = ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    public = read(coverage_path)['public']
    by_n = {x['N']: x for x in public}
    original = read(CONFIGS/'EXP-128-cc-local-boundary-v5-performance-20261027.json')
    mgr.require(len(original['cases']) == 388 and len(by_n) == 194, 'wrong formal case matrix')
    baseline = copy.deepcopy(original['arms']['baseline'])
    reference_specs = {
        'previous': ('EXP-128-cc-local-boundary-v5-build-20261027', '2ca09d728a3cd008c631e8b4e5b2b031e5a24faa60e2636d2ca6c1e7adf2fc0d'),
        'unfused_cc': ('EXP-128-cc-local-unfused-phasefix-build-20261027', '43e6ab4835fbc382fced7cf251c00db7c4baf2b04d5a0d4f01b6a46e89f514d0')}
    references = dict(baseline=baseline)
    for name, (run_id, expected) in reference_specs.items():
        built = read(ROOT/'experiments/EXP-128/runs'/run_id/'build-provenance.json')
        mgr.require(built['complete'] and built['arm']['library_sha256'] == expected, 'wrong reference identity')
        references[name] = copy.deepcopy(built['arm'])
    for arm in references.values():
        mgr.require(sha(Path(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256'], 'reference library differs')
    old_validation = read(CONFIGS/'EXP-128-cc-local-boundary-v5-validate-20261027.json')
    features = {}
    selected = {65536, 1048576, 497664, 75000, 133100, max(by_n)}
    for n, case in sorted(by_n.items()):
        c, q = case['C'], case['Q']
        text = (ART/'default'/f'{c}-{q}-5-0.cpp').read_text()
        t = int(re.search(r'uses (\d+) threads per transform', text)[1])
        rows = int(re.search(r'does (\d+) transforms per thread block', text)[1])
        factors = list(map(int, re.search(r'_factors_([0-9_]+)_wgs_', text[text.index('extern "C" __global__'):])[1].split('_')))
        direct = rows == 1 and t == q//factors[-1]
        packed = c % 2 == 0 and rows % 2 == 0 and c % rows == 0
        if direct or not packed:
            # Cover every changed row geometry, column parity and full/tail row group.
            features.setdefault((q, t, rows, c % 2, c % rows == 0), n)
    selected.update(features.values())
    sample = sorted(selected)
    mgr.require(set(sample) <= by_n.keys(), 'validation size missing from registered defaults')
    free = shutil.disk_usage(ROOT).free
    mgr.require(free > 16*1024**3, 'insufficient headroom for one candidate build')
    decisions = dict(scope='1D double batch1 OOP even N>=65536 generic CC, unchanged default plans',
        user_choice='A: output only; keep input-index variants for later',
        changes=['z2d native single-row real output', 'z2d full-group output guard elimination',
                 'd2z native ordinary single-row output with terminal-row LDS retained'],
        input_changed=False, column_changed=False, decomposition_changed=False,
        references=references, reference_installs_rebuilt=False, source_state_freeze=False,
        validation_N=sample, changed_output_classes=[dict(key=k, N=n) for k, n in features.items()],
        validation='Numerical results and actual fusion/output path only',
        performance_N=194, performance_cases=388, processes=1552, event_samples=46560,
        free_bytes=free, reserved_peak_bytes=16*1024**3,
        source_analysis='experiments/EXP-128/records/row-cost-reduction-20261027/分析与具体修改方案.md')
    write(RECORD/'decisions.json', decisions)
    files = [ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'/name for name in
             ('library/src/device/generator/stockham_gen_cc_real_rows.h', 'library/src/rtc_stockham_gen.cpp')]
    files += [ROOT/'experiments/EXP-128/scripts'/name for name in
              ('preflight_cc_row_output_v6.py', 'validate_cc_row_output_v6.py', 'prepare_cc_row_output_v6.py', 'submit_cc_row_output_v6.py')]
    files += [RECORD/name for name in ('host-preflight.json', 'validation-preflight.json', 'decisions.json', '实现说明.md')]
    source_commit = commit(files, 'EXP128：仅简化行端输出并消除单行共享存储中转')

    build = read(CONFIGS/'EXP-128-cc-local-boundary-v5-build-20261027.json')
    build['run_id'] = PREFIX+'-build-'+DATE
    build['build'].update(build_id=PREFIX+'-'+DATE, source_commit=source_commit)
    build['resources'].pop('dependency', None)
    build['resources'].pop('nodelist', None)
    build['acceptance'] = 'Build output-only v6; separate numerical/path validation follows.'
    build['reference_policy'] = 'Reuse EXP125, v5 and repaired same-CC OFF; no reference builds or dependencies.'
    validation = copy.deepcopy(old_validation)
    for key in ('pending_build_validation', 'validation_acceptance', 'queued_submission'):
        validation.pop(key, None)
    validation.update(run_id=PREFIX+'-validate-'+DATE, build=copy.deepcopy(build['build']))
    for key in ('dependency', 'nodelist'):
        validation['resources'].pop(key, None)
    validation['existing_build_validation'] = dict(
        build_record=str(mgr.locations(build, 'build')['run']/'build-provenance.json'),
        evidence_record='cc-row-output-validation.json', isolated_helpers=False)
    script = ROOT/'experiments/EXP-128/scripts/validate_cc_row_output_v6.py'
    inputs = [ROOT/'experiments/EXP-128/scripts'/name for name in
              ('cc_dispatch.py', 'validate_cc_local_grouped.py', 'validate_cc_local_boundary.py')]+[coverage_path]
    validation['post_build_validation'] = dict(script=str(script), sha256=sha(script),
        inputs=[dict(path=str(p), sha256=sha(p)) for p in inputs])
    validation['validation'] = dict(profile='cc-row-output-v6-two-checks', coverage=str(coverage_path),
        smoke_N=[75000, 133100], sample_N=sample,
        scope='Numerical correctness, exact default C/Q, two v6 fusion stages and selected output strategy; no callback/memory release suite.')
    validation['reference_policy'] = build['reference_policy']
    validation['acceptance'] = 'Only numerical and actual-path checks; aggregate all independent main-matrix errors.'
    measure = copy.deepcopy(original)
    for key in ('validation_acceptance', 'validation_acceptances', 'queued_submission',
                'pending_build_validation', 'installations_sha256'):
        measure.pop(key, None)
    measure['run_id'] = PREFIX+'-performance-'+DATE
    measure['arms'] = dict(references, candidate=dict(build_record=str(mgr.locations(build, 'build')['run']/'build-provenance.json')))
    measure['arm_labels'] = dict(baseline='EXP125保留版', previous='通用融合第五版',
                                 unfused_cc='修复后的同CC未融合版', candidate='行端输出第六版')
    for key in ('dependency', 'nodelist'):
        measure['resources'].pop(key, None)
    measure['comparison_description'] = '四版同卡相邻交替：EXP125、第五版、修复同CC未融合版、第六版。仅候选输出改动，默认分解不变。'
    measure['measurement_conditions']['reference'] = '三份参考安装直接复用；194个N、388组合、四版1552进程、46560正式样本，10/30，仅用中位数。'
    measure['acceptance'] = 'Start only after v6 numerical/path validation succeeds; no reference rebuild or prerequisite.'
    config_paths = []
    for kind, config in [('build', build), ('validate', validation), ('performance', measure)]:
        path = CONFIGS/(PREFIX+'-'+kind+'-'+DATE+'.json')
        mgr.require(not path.exists(), 'config already exists: '+str(path))
        write(path, config)
        mgr.load(path)
        config_paths.append(path)
    preview = RECORD/'build-preview.json'
    write(preview, mgr.task_plan('build', build))
    commit(config_paths+[preview], '登记EXP128第六版单候选验证与四版默认性能对照')
    print(json.dumps(dict(source_commit=source_commit, validation_N=len(sample), validation_cases=2*len(sample),
        default_N=194, cases=388, processes=1552, samples=46560,
        reference_installs_rebuilt=False, validation_preflight=validators), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
