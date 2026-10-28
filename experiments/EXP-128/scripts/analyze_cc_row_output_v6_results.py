"""Audit completed v6 raw evidence and report medians by actual output geometry."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'tools/fft_measurement'), str(ROOT/'experiments/EXP-128/scripts')]
from summarize_cufft261012 import aggregate
from cufft261012_contract import read_check
from analyze_cc_rows_results import order_effect, summarize
from tools.workspace_manager import manager as mgr, revalidate

RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-performance-20261028'
VALIDATION = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-validate-20261028'
RECORD = ROOT/'experiments/EXP-128/records/row-output-v6-20261028'
OUT = RECORD/'results-991869'
ARMS = ('baseline', 'previous', 'unfused_cc', 'candidate')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def csv_file(name, rows, fields=None):
    with (OUT/name).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    manifest, provenance, original, samples = aggregate(RUN)
    assert original == read(RUN/'summary.json')['rows']
    assert len(original) == 388 and len(samples) == 1552 and sum(map(len, samples.values())) == 46560
    cfg = mgr.load(VALIDATION/'submit-manifest.json')
    built, lib, command, filename = revalidate.existing(cfg)
    acceptance = revalidate.verify_acceptance(mgr.locations(cfg, 'validate'), built, command, filename, '991868')
    assert acceptance == manifest['validation_acceptance']
    validation = read(VALIDATION/filename)
    assert validation['complete'] and not validation['failures']
    assert len(validation['numerical']) == len(validation['dispatch']) == 56
    assert all(x['check']['check'] == 'PASS' for x in validation['numerical'])
    features = {}
    for d in validation['dispatch']:
        roles = (4, 5) if d['func'] == 'z2d_1d' else (6, 7)
        assert len(d['actual_names']) == 2
        assert all('_cc_local_v6_role%d_C%d_Q%d_' % (role, d['C'], d['Q']) in name
                   for role, name in zip(roles, d['actual_names']))
        key = d['row_features']['output_strategy']
        features[key] = features.get(key, 0)+1
    model_path = ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027/mapping-model.json'
    geometry = {x['N']: x for x in read(model_path)['cases']}
    assert set(geometry) == {x['N'] for x in original}
    proof = read(RECORD/'host-preflight.json')
    assert proof['complete'] and not proof['failures'] and not proof['input_changed'] and not proof['column_changed']
    rows, exported = [], []
    for x in original:
        n, func = x['N'], x['func']
        g = geometry[n]
        direct = g['R'] == 1 and g['T'] == g['Q']//g['factors'][-1]
        changed = direct or (func == 'z2d_1d' and not g['packed'])
        group = '单行寄存器直写' if direct else '多行输出分类简化' if changed else '未改输出'
        row = dict(N=n, type=func.removesuffix('_1d'), C=g['C'], Q=g['Q'],
                   T=g['T'], R=g['R'], output_group=group, output_changed=changed,
                   power_of_two=(n & (n-1)) == 0)
        effects = {}
        for arm in ARMS:
            for stat in ('median', 'p25', 'p75'):
                row[arm+('_us' if stat == 'median' else '_'+stat+'_us')] = x[arm+'_'+stat+'_ms']*1000
            effects[arm] = order_effect(samples[n, func, arm])
        for ref in ARMS[:-1]:
            row['speedup_'+ref] = row[ref+'_us']/row['candidate_us']
            row['overlap_'+ref] = not (row[ref+'_p25_us'] > row['candidate_p75_us'] or
                                      row['candidate_p25_us'] > row[ref+'_p75_us'])
            row['order_effect_'+ref] = effects[ref]['flag'] or effects['candidate']['flag']
            row['assessment_'+ref] = ('差异不明确' if row['overlap_'+ref] or row['order_effect_'+ref]
                                      else '更快' if row['speedup_'+ref] > 1 else '更慢')
        row['previous_speedup_unfused_cc'] = row['unfused_cc_us']/row['previous_us']
        row['previous_speedup_baseline'] = row['baseline_us']/row['previous_us']
        row['a100_us'] = x['a100_median_ms']*1000 if x['a100_median_ms'] is not None else None
        row['a100_performance_percent'] = x['a100_performance_median_percent']
        rows.append(row)
        exported.append(dict(row, samples_us={a: [v*1000 for v in samples[n, func, a]] for a in ARMS},
                             order_effect_details=effects, measurement_job='991869', host=provenance['host']))
    rows.sort(key=lambda x: (x['N'], x['type']))
    exported.sort(key=lambda x: (x['N'], x['type']))
    assert sum(x['output_changed'] for x in rows) == 197
    groups = []
    for dimension, get in [('全部', lambda x: 'all'), ('输出类型', lambda x: x['output_group']),
                           ('行长', lambda x: x['Q']), ('列长', lambda x: x['C']),
                           ('二次幂', lambda x: x['power_of_two'])]:
        for value in sorted({get(x) for x in rows}, key=str):
            for func in ('z2d', 'd2z'):
                selected = [x for x in rows if x['type'] == func and get(x) == value]
                if not selected:
                    continue
                for ref in ARMS[:-1]:
                    groups.append(dict(dimension=dimension, value=value, type=func, reference=ref,
                                       **summarize(selected, ref)))
    entries = read(RUN/'processes.json')
    checks = [dict(arm=x['arm'], **read_check(RUN/x['correctness'])) for x in entries]
    assert len(checks) == 1552 and all(x['check'] == 'PASS' for x in checks)
    errors = [float(x[k]) for x in checks for k in ('err_a', 'err_b') if float(x[k]) >= 0]
    assert max(errors) < 1e-9
    transitions = {}
    for func in ('z2d', 'd2z'):
        selected = [x for x in rows if x['type'] == func]
        before = {x['N'] for x in selected if x['previous_speedup_unfused_cc'] < .95}
        after = {x['N'] for x in selected if x['speedup_unfused_cc'] < .95}
        transitions[func] = dict(v5_below_095=len(before), v6_below_095=len(after),
                                 recovered_N=sorted(before-after), new_N=sorted(after-before))
    audit = dict(complete=True, formal=True, job_id='991869', validation_job='991868',
        N=194, cases=388, processes=1552, formal_samples=46560, warmups=10, samples_per_process=30,
        max_numerical_error=max(errors), validation_seconds=validation['elapsed_seconds'],
        validation_features=features, validation_acceptance=acceptance, policy=provenance['policy'],
        host=provenance['host'], gpu=provenance['gpu'], start=provenance['start'], end=provenance['end'],
        references={a: {k: manifest['arms'][a][k] for k in ('install', 'source_commit', 'library_sha256')} for a in ARMS},
        all={func: {ref: summarize([x for x in rows if x['type'] == func], ref) for ref in ARMS[:-1]}
             for func in ('z2d', 'd2z')},
        output_groups=[x for x in groups if x['dimension'] == '输出类型'],
        same_CC_severe_transition=transitions,
        power_of_two=[x for x in rows if x['power_of_two']],
        severe_previous=[x for x in rows if x['speedup_previous'] < .95],
        known_stable_unfused_losses=[x for x in rows if x['type'] == 'z2d' and x['N'] in
                                    (97104, 255552, 425920, 646866, 681472, 1362944, 2725888)],
        assessments='IQR overlap or disjoint first/last 15-sample IQR => inconclusive; descriptive, not a significance test. One fresh process per case/arm, no cross-run stability claim.',
        evidence_sha256={str(p.relative_to(ROOT)): sha(p) for p in
            (RUN/'preregistration.json', RUN/'provenance.json', RUN/'processes.json', RUN/'summary.json',
             VALIDATION/filename, VALIDATION/'post-build-validation.json', RECORD/'host-preflight.json', model_path)})
    write('audit-and-statistics.json', audit)
    write('all-samples-and-statistics.json', exported)
    csv_file('全部尺寸.csv', rows)
    csv_file('类型汇总.csv', groups)
    csv_file('独立正确性表.csv', checks)
    for ref in ARMS[:-1]:
        csv_file('低于095-'+ref+'.csv', sorted([x for x in rows if x['speedup_'+ref] < .95],
                 key=lambda x: x['speedup_'+ref]), list(rows[0]))
    with (OUT/'原始逐次样本.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['N', 'type', 'arm', 'sample_index', 'elapsed_us'])
        for x in exported:
            for arm in ARMS:
                w.writerows((x['N'], x['type'], arm, i, value) for i, value in enumerate(x['samples_us'][arm], 1))
    print(json.dumps({k: audit[k] for k in ('complete', 'N', 'cases', 'processes', 'formal_samples',
        'max_numerical_error', 'all', 'output_groups', 'same_CC_severe_transition', 'severe_previous',
        'known_stable_unfused_losses')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
