"""Register and preview fresh official/V6 timing on the unchanged 194-size list."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr, revalidate

RUN_ID = 'EXP-128-cc-local-v6-official-performance-20261029'
CONFIG = ROOT / 'configs/experiments' / (RUN_ID + '.json')
RECORD = ROOT / 'experiments/EXP-128/records/official-v6-remeasure-20261029'
ORIGIN = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-performance-20261028'
VALIDATION = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-validate-20261028'
OFFICIAL_ID = 'install-exp096-official'
OFFICIAL_SHA = '3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5'
V6_SHA = 'bd45afb7a95cfc80fccc0aae80f7bedf684d7468c11c735cdcd0049af72364e4'


def read(path):
    return json.loads(path.read_text())


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def commit(paths, message):
    args = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git', 'add', '--', *args], cwd=ROOT, check=True, capture_output=True)
    p = subprocess.run(['git', 'commit', '--only', '-m', message, '--', *args],
                       cwd=ROOT, capture_output=True, text=True)
    mgr.require(p.returncode == 0, p.stdout + p.stderr)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def main():
    mgr.require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT,
                                       text=True).strip() == 'exp-128-cc-local-real', 'wrong branch')
    mgr.require(not CONFIG.exists(), 'registration already exists; inspect it before retrying')
    mgr.require(not (ROOT / 'experiments/EXP-128/runs' / RUN_ID).exists(), 'run already reserved')
    RECORD.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(ROOT).free
    mgr.require(free > 4 * 1024**3, 'insufficient measurement storage headroom')
    cfg = read(ORIGIN / 'preregistration.json')
    candidate = copy.deepcopy(cfg['arms']['candidate'])
    mgr.require(candidate['library_sha256'] == V6_SHA, 'not the accepted V6 library')
    vcfg = mgr.load(VALIDATION / 'submit-manifest.json')
    built, library, command, filename = revalidate.existing(vcfg)
    accepted = revalidate.verify_acceptance(mgr.locations(vcfg, 'validate'), built, command, filename, '991868')
    mgr.require(accepted == cfg['validation_acceptance'] and candidate == built['arm'],
                'candidate does not match accepted numerical/path evidence')
    evidence = read(VALIDATION / filename)
    mgr.require(evidence['complete'] and not evidence['failures']
                and len(evidence['numerical']) == len(evidence['dispatch']) == 56,
                'accepted V6 evidence is incomplete')
    registry = mgr.registry()
    mgr.require(registry['aliases']['official'] == OFFICIAL_ID, 'official alias differs')
    official_record = registry['installations'][OFFICIAL_ID]
    mgr.require(official_record['role'] == 'official' and official_record['eligible_formal_arm'],
                'registered library is not an approved official arm')
    official = official_record['arm']
    mgr.require(official['library_sha256'] == OFFICIAL_SHA, 'official library mapping differs')
    for arm in (official, candidate):
        mgr.require(mgr.common.sha(Path(arm['install']) / 'lib/librocfft.so.0.1') == arm['library_sha256'],
                    'measured library differs from approved identity')
    coverage = ROOT / 'experiments/EXP-128/records/unified-20261021/coverage.json'
    mgr.require(mgr.common.sha(coverage) == cfg['coverage_sha256'], 'original coverage differs')
    ns = sorted(x['N'] for x in read(coverage)['public'])
    pairs = {(x['N'], x['func']) for x in cfg['cases']}
    mgr.require(len(ns) == len(set(ns)) == 194 and (min(ns), max(ns)) == (65536, 2725888),
                'wrong size list')
    mgr.require(len(cfg['cases']) == len(pairs) == 388
                and pairs == {(n, f) for n in ns for f in ('z2d_1d', 'd2z_1d')},
                'wrong size/direction coverage')
    for key in ('queued_submission', 'deferred_measurement', 'revalidated_measurement',
                'validated_measurement', 'pending_build_validation', 'installations_sha256'):
        cfg.pop(key, None)
    cfg.update(run_id=RUN_ID, arms=dict(official=dict(registry_id=OFFICIAL_ID), candidate=candidate),
               arm_labels=dict(official='官方rocFFT原版', candidate='通用CC融合第六版'),
               comparison_kind='version_comparison',
               case_scope='Unchanged 194 default sizes, both z2d/d2z, even N>=65536 through 2725888; official and accepted V6 only.',
               comparison_description='官方默认计划与当前第六版默认计划同卡紧邻交替重测；衡量当前版本整体性能，不将EXP125作为官方基线，也不强制官方改用CC。',
               validation_acceptance=accepted, validation_acceptances=dict(candidate=accepted),
               acceptance='Reuse the accepted V6 numerical/path validation and approved official library. Each original v3 timing process must pass its independent numerical check; retain every 30-sample trace and all failures. No rebuild, forced load path, phase-order prototype or stable promotion.')
    for key in ('dependency', 'nodelist'):
        cfg['resources'].pop(key, None)
    cfg['resources']['node_exclusive'] = True
    cfg['measurement_conditions']['reference'] = '两份现成库复用；官方与第六版同一独占单卡，各组合相邻、交替先后。194个N、388组合、776进程、23280个计时样本，10/30，仅用中位数。'
    cfg['measurement_conditions']['load_path'] = 'default'
    cfg['source_state_policy'] = 'Do not freeze or compare workspace/build source state. Record selected libraries and original timing protocol identities only.'
    cfg = mgr.measurement(cfg)
    protocol = mgr.measurement_protocol(cfg)
    schedule = protocol.schedule(cfg)
    mgr.require(tuple(protocol.arms(cfg)) == ('official', 'candidate'), 'unexpected comparison arms')
    mgr.require(len(schedule) == 776 and protocol.iterations(cfg) == 30
                and cfg['timing_warmups'] == 10, 'wrong process/sample count')
    seen = set()
    for i in range(388):
        a, b = schedule[2*i:2*i+2]
        key = (int(a['N']), a['func'])
        mgr.require(key == (int(b['N']), b['func']) and key not in seen,
                    'comparison versions are not adjacent for every unique case')
        seen.add(key)
        expected = ['official', 'candidate'] if i % 2 == 0 else ['candidate', 'official']
        mgr.require([a['arm'], b['arm']] == expected, 'comparison order does not alternate')
    mgr.require(seen == pairs, 'scheduler lost a case')
    selection = dict(user_choice='A: 194 N, z2d and d2z, 388 combinations; scope and submission flow confirmed.',
                     official_registry_id=OFFICIAL_ID, arms=cfg['arms'],
                     coverage=dict(path=str(coverage), sha256=mgr.common.sha(coverage),
                                   sizes=194, cases=388, minimum=65536, maximum=2725888),
                     protocol=cfg['policy'], timing_warmups=10, samples_per_process=30,
                     processes=776, event_samples=23280, schedule_first_four=schedule[:4],
                     schedule_adjacency_and_alternation_verified=True,
                     candidate_validation=accepted, accepted_numerical_cases=56, accepted_actual_path_cases=56,
                     official_default_plan=True, forced_CC_or_load_path=False,
                     official_historical_v3_full_scope_evidence='Not found in bounded historical lookup; each fresh v3 measurement process independently checks numerical results.',
                     references_rebuilt=False, production_source_modified=False,
                     new_validation_jobs=False, source_state_freeze=False, free_bytes=free,
                     analysis='Official median / current median; keep raw samples, IQR, all points and order plots. No cross-run sample mixing.',
                     stop_policy='Stop after submission receipt; no scheduler or result polling until requested.')
    write(CONFIG, cfg)
    write(RECORD / 'selection-and-identities.json', selection)
    write(RECORD / 'process-schedule.json', schedule)
    process = subprocess.run([mgr.PYTHON, str(ROOT / 'manage.py'), 'measure', '--config', str(CONFIG)],
                             cwd=ROOT, capture_output=True, text=True)
    write(RECORD / 'preview-process.json', dict(returncode=process.returncode,
                                               stdout=process.stdout, stderr=process.stderr))
    mgr.require(process.returncode == 0, 'unified preview failed: ' + process.stderr[-2000:])
    preview = json.loads(process.stdout)
    mgr.require(preview['processes'] == 776 and preview['cases'] == 388 and preview['formal'],
                'preview workload differs')
    mgr.require(not any(x.startswith(('--dependency=', '--nodelist=')) for x in preview['submission_command']),
                'unexpected old dependency or fixed node')
    write(RECORD / 'preview.json', preview)
    paths = [Path(__file__), CONFIG] + [RECORD / n for n in
             ('selection-and-identities.json', 'process-schedule.json', 'preview-process.json', 'preview.json')]
    revision = commit(paths, 'Register fresh official versus accepted V6 timing for all 194 real CC sizes')
    registration = dict(config=str(CONFIG), run_id=RUN_ID, record_commit=revision,
                         submission_command=preview['submission_command'], cases=388, sizes=194,
                         processes=776, event_samples=23280,
                         arms={a:dict(install=v['install'], source_commit=v['source_commit'],
                                      library_sha256=v['library_sha256']) for a,v in cfg['arms'].items()},
                         status='Previewed; not submitted')
    write(RECORD / 'registration.json', registration)
    print(json.dumps(registration, ensure_ascii=False))


if __name__ == '__main__':
    main()
