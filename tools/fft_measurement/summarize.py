"""Reject incomplete formal runs, then write 15-case three-arm/A100 report."""
import argparse
import csv
import json
import statistics
from pathlib import Path
from common import ARMS, FUNCS, POLICY, SIZES, SOURCE_SHA, manifest, read_rows, reference, require, schedule, sha, validate_row, write_json

def aggregate(run, reference_path=None):
    run = Path(run)
    m = manifest(run / 'preregistration.json')
    p = json.loads((run / 'provenance.json').read_text(encoding='utf-8'))
    require(p.get('policy') == POLICY and p.get('source_sha256') == SOURCE_SHA, 'wrong timing source/policy')
    require(p.get('complete') is True, 'run not completed')
    require(p.get('job_id') and p.get('host') and p.get('gpu', {}).get('uuid'), 'missing allocation/device provenance')
    require(p['gpu'].get('count') == 1 and p['gpu'].get('arch', '').split(':')[0] == m['gpu_arch'], 'GPU visibility/architecture mismatch')
    require(set(p.get('arms', {})) == set(ARMS), 'missing library provenance')
    for arm in ARMS:
        a = p['arms'][arm]
        require(a.get('library_sha256') == m['arms'][arm]['library_sha256'], 'loaded library hash mismatch')
        require(a.get('source_commit') == m['arms'][arm]['source_commit'], 'source provenance mismatch')
        require(a.get('actual_library') and a.get('binary_sha256'), 'missing actual library/binary evidence')
    expected = schedule()
    entries = json.loads((run / 'processes.json').read_text(encoding='utf-8'))
    require(len(entries) == 720, 'formal run requires exactly 720 processes')
    groups = {(n, f, a): [] for n in SIZES for f in FUNCS for a in ARMS}
    for e, planned in zip(entries, expected):
        require(all(e.get(k) == v for k, v in planned.items()), 'schedule/order mismatch')
        require(e.get('returncode') == 0, 'nonzero process exit')
        require(e.get('gpu') == p['gpu'] and e.get('job_id') == p['job_id'] and e.get('host') == p['host'], 'different GPU/allocation/environment')
        arm = planned['arm']
        require(e.get('library_sha256') == m['arms'][arm]['library_sha256'], 'process library hash mismatch')
        for key in ('csv', 'stdout', 'stderr'):
            path = run / e[key]
            require(run.resolve() in path.resolve().parents, 'evidence path escapes run')
            require(sha(path) == e[key + '_sha256'], 'changed process evidence: ' + key)
        rows = read_rows(run / e['csv'])
        require(len(rows) == 1, 'exactly one row per fresh process required')
        values = validate_row(rows[0], planned['N'], planned['func'])
        groups[(planned['N'], planned['func'], arm)].append(values)
    a100 = reference(reference_path) if reference_path else reference()
    out = []
    for n in SIZES:
        for f in FUNCS:
            row = {'func': f, 'N': n, 'batch': 1, 'iters_per_process': 50, 'processes_per_arm': 16, 'events_per_arm': 800, 'check': 'PASS'}
            for arm in ARMS:
                values = groups[(n, f, arm)]
                require(len(values) == 16, 'each arm needs 16 process means')
                means = [v['mean_ms'] for v in values]
                row[arm + '_mean_ms'] = statistics.mean(means)
                row[arm + '_process_median_ms'] = statistics.median(means)
                row[arm + '_event_min_ms'] = min(v['min_ms'] for v in values)
                row[arm + '_event_max_ms'] = max(v['max_ms'] for v in values)
                row[arm + '_process_stdev_ms'] = statistics.stdev(means)
            candidate = row['candidate_mean_ms']
            row.update(speedup_previous=row['previous_mean_ms']/candidate, speedup_official=row['official_mean_ms']/candidate, a100_mean_ms=a100[(n, f)], a100_performance_percent=a100[(n, f)]/candidate*100)
            out.append(row)
    return m, p, out

def report(run, reference_path=None):
    m, p, rows = aggregate(run, reference_path)
    run = Path(run)
    with (run / 'comparison.csv').open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    lines = ['# ' + m['experiment'] + ' formal event measurement', '', 'Policy: ' + POLICY, '', 'Preregistered acceptance: ' + m['acceptance'], '', 'Correctness: all 720 fresh processes PASS. No outlier removal. All values in ms; each arm uses the arithmetic mean of 16 process means (800 events).', '', '| Function | N | Official ms | Previous ms | Candidate ms | Previous speedup | Official speedup | A100 Performance |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append('| %s | %d | %.12g | %.12g | %.12g | %.9gx | %.9gx | %.9g%% |' % (r['func'], r['N'], r['official_mean_ms'], r['previous_mean_ms'], r['candidate_mean_ms'], r['speedup_previous'], r['speedup_official'], r['a100_performance_percent']))
    lines += ['', 'A100 is a fixed historical cross-hardware reference, not a same-allocation control. Raw CSV/provenance and unrounded comparison.csv remain authoritative. Performance >100% means the candidate is faster than the matched A100 reference.', '', 'plan_ms/first_ms and per_tf_ms remain diagnostic; no hipprof N+1 divisor or kernel subtraction applies. Acceptance decision must be recorded against preregistered experiment-specific criteria; this report does not automatically promote a version.', '']
    (run / 'comparison.md').write_text('\n'.join(lines), encoding='utf-8')
    write_json(run / 'summary.json', dict(policy=POLICY, experiment=m['experiment'], job_id=p['job_id'], gpu=p['gpu'], processes=720, rows=rows))
    return rows

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run', type=Path)
    args = ap.parse_args()
    try:
        report(args.run)
    except (ValueError, OSError, KeyError, TypeError) as e:
        ap.exit(1, 'measurement rejected: %s\n' % e)
