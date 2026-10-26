"""Recheck original samples and acceptance for the grouped-input candidate."""
import csv
import json
import runpy
import statistics
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
SERIES = ROOT/'experiments/EXP-128/records/grouped-20261026'
RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-grouped-performance-20261026'
VALIDATION = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-grouped-validate-20261026'
OUT = SERIES/'results-979273'
HELPERS = runpy.run_path(str(ROOT/'experiments/EXP-128/scripts/analyze_cc_rows_results.py'))
aggregate = HELPERS['aggregate']
order_effect = HELPERS['order_effect']
summarize = HELPERS['summarize']
read_check = HELPERS['read_check']
mgr, revalidate = HELPERS['mgr'], HELPERS['revalidate']
ARMS = ('baseline', 'previous', 'candidate')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def write_csv(name, rows, fields=None):
    with (OUT/name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, provenance, original_rows, samples = aggregate(RUN)
    assert original_rows == read(RUN/'summary.json')['rows']
    assert len(original_rows) == 388 and len(samples) == 1164
    assert all(len(values) == 30 for values in samples.values())
    assert sum(map(len, samples.values())) == 34920

    validation_cfg = mgr.load(VALIDATION/'submit-manifest.json')
    built, library, command, filename = revalidate.existing(validation_cfg)
    acceptance = revalidate.verify_acceptance(mgr.locations(validation_cfg, 'validate'),
                                             built, command, filename, '979272')
    assert acceptance == manifest['validation_acceptance']
    validation = read(VALIDATION/filename)
    assert validation['complete'] and not validation['failures']
    assert validation['profile'] == 'cc-local-grouped-two-checks-v4'
    assert len(validation['numerical']) == len(validation['dispatch']) == 58
    assert all(entry['check']['check'] == 'PASS' for entry in validation['numerical'])
    assert validation['gpu'] == provenance['gpu']
    for entry in validation['dispatch']:
        roles = (4, 5) if entry['func'] == 'z2d_1d' else (6, 7)
        assert len(entry['actual_names']) == 2
        for role, name in zip(roles, entry['actual_names']):
            assert '_cc_local_v4_role%d_C%d_Q%d_' % (role, entry['C'], entry['Q']) in name
        if entry['func'] == 'd2z_1d':
            assert entry['actual_names'][1].endswith('_reg')
        grouped = entry['grouped_input']
        if grouped['enabled']:
            assert entry['func'] == 'd2z_1d'
            count = entry['Q']//grouped['first_factor']
            assert grouped['active_first_lanes'] == count
            assert grouped['threads_per_transform'] > count
            assert grouped['classification_groups'] == (grouped['first_factor']+1)//2

    coverage_path = ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    geometry = {entry['N']: entry for entry in read(coverage_path)['public']}
    assert set(geometry) == {row['N'] for row in original_rows}
    changed_pairs = {(entry['C'], entry['Q']) for entry in read(SERIES/'host-preflight.json')['changed_sources']}
    rows, exported = [], []
    for original in original_rows:
        n, func = original['N'], original['func']
        c, q = geometry[n]['C'], geometry[n]['Q']
        row = dict(N=n, type=func.removesuffix('_1d'), C=c, Q=q,
                   parity=('奇' if c % 2 else '偶')+'×'+('奇' if q % 2 else '偶'),
                   power_of_two=(n & (n-1)) == 0,
                   input_changed=func == 'd2z_1d' and (c, q) in changed_pairs)
        effects = {}
        for arm in ARMS:
            row[arm+'_us'] = original[arm+'_median_ms']*1000
            row[arm+'_p25_us'] = original[arm+'_p25_ms']*1000
            row[arm+'_p75_us'] = original[arm+'_p75_ms']*1000
            effects[arm] = order_effect(samples[(n, func, arm)])
            row[arm+'_order_effect'] = effects[arm]['flag']
        for reference in ('baseline', 'previous'):
            row['speedup_'+reference] = row[reference+'_us']/row['candidate_us']
            row['reduction_'+reference+'_percent'] = 100*(1-row['candidate_us']/row[reference+'_us'])
            row['overlap_'+reference] = not (row[reference+'_p25_us'] > row['candidate_p75_us']
                or row['candidate_p25_us'] > row[reference+'_p75_us'])
            row['order_effect_'+reference] = effects[reference]['flag'] or effects['candidate']['flag']
            row['assessment_'+reference] = ('差异不明确' if row['overlap_'+reference]
                or row['order_effect_'+reference] else ('更快' if row['speedup_'+reference] > 1 else '更慢'))
        row['a100_us'] = original['a100_median_ms']*1000 if original['a100_median_ms'] is not None else None
        row['a100_performance_percent'] = original['a100_performance_median_percent']
        rows.append(row)
        exported.append(dict(row, samples_us={arm:[v*1000 for v in samples[(n, func, arm)]] for arm in ARMS},
                             order_effect_details=effects))
    assert sum(row['input_changed'] for row in rows) == 30
    assert {row['Q'] for row in rows if row['input_changed']} == {100, 200, 512}

    groups = []
    for label, get in [('全部', lambda row:'all'), ('列长', lambda row:row['C']),
                       ('行长', lambda row:row['Q']), ('奇偶', lambda row:row['parity']),
                       ('二次幂', lambda row:row['power_of_two'])]:
        for value in sorted({get(row) for row in rows}, key=str):
            for func in ('z2d', 'd2z'):
                selected = [row for row in rows if row['type'] == func and get(row) == value]
                for ref in ('baseline', 'previous'):
                    groups.append(dict(dimension=label, value=value, type=func, reference=ref,
                                       **summarize(selected, ref)))
    entries = read(RUN/'processes.json')
    checks = [dict(arm=entry['arm'], **read_check(RUN/entry['correctness'])) for entry in entries]
    assert len(checks) == 1164 and all(check['check'] == 'PASS' for check in checks)
    max_error = max(max(float(check['err_a']), float(check['err_b'])) for check in checks)
    assert max_error < 1e-9
    prior_path = ROOT/'experiments/EXP-128/records/rowsimplify-retry1-20261022/results-960099/all-samples-and-statistics.json'
    old_rows = read(prior_path)
    old_severe_keys = {(row['N'], row['type']) for row in old_rows if row['speedup_previous'] < .95}
    old_severe = [row for row in rows if (row['N'], row['type']) in old_severe_keys]
    assert len(old_severe) == len(old_severe_keys) == 24
    base_previous = [row for row in rows if row['baseline_us']/row['previous_us'] < .95]
    base_candidate = [row for row in rows if row['speedup_baseline'] < .95]
    base_previous_keys = {(row['N'], row['type']) for row in base_previous}
    base_candidate_keys = {(row['N'], row['type']) for row in base_candidate}
    affected = [row for row in rows if row['input_changed']]
    unaffected = [row for row in rows if not row['input_changed']]
    audit = dict(complete=True, formal=True, job_id='979273', validation_job='979272',
        build_job='979271', Ns=len(geometry), cases=len(rows), processes=len(samples),
        samples=sum(map(len, samples.values())), max_numerical_error=max_error,
        validation_cases=58, validation_seconds=validation['elapsed_seconds'],
        grouped_validation_cases=sum(row['grouped_input']['enabled'] for row in validation['dispatch']),
        GPU=provenance['gpu'], host=provenance['host'], policy=provenance['policy'],
        first=provenance['start'], last=provenance['end'],
        arms={arm:{key:provenance['arms'][arm][key] for key in ('source_commit','library_sha256','install')}
              for arm in ARMS},
        validation_acceptance=acceptance,
        all={func:{ref:summarize([row for row in rows if row['type'] == func], ref)
                   for ref in ('baseline','previous')} for func in ('z2d','d2z')},
        changed_input={ref:summarize(affected, ref) for ref in ('baseline','previous')},
        unchanged_input={ref:summarize(unaffected, ref) for ref in ('baseline','previous')},
        changed_families={str(q):{ref:summarize([row for row in affected if row['Q'] == q], ref)
                                  for ref in ('baseline','previous')} for q in (100,200,512)},
        previous_formal_24_severe={ref:summarize(old_severe, ref) for ref in ('baseline','previous')},
        same_run_severe_transition=dict(previous_vs_EXP125=len(base_previous),
            candidate_vs_EXP125=len(base_candidate), repaired=len(base_previous_keys-base_candidate_keys),
            newly_below_095=len(base_candidate_keys-base_previous_keys)),
        severe_vs_v3_changed=sum(row['input_changed'] and row['speedup_previous'] < .95 for row in rows),
        severe_vs_v3_unchanged=sum(not row['input_changed'] and row['speedup_previous'] < .95 for row in rows),
        previous_24_changed=sum(row['input_changed'] for row in old_severe),
        all_reference_sha256={str(path.relative_to(ROOT)):mgr.common.sha(path) for path in
            (RUN/'preregistration.json', RUN/'provenance.json', RUN/'processes.json', RUN/'summary.json',
             VALIDATION/'post-build-validation.json', VALIDATION/'cc-local-validation.json',
             coverage_path, SERIES/'host-preflight.json', prior_path)},
        assessments='IQR overlap or disjoint first/last half IQR is inconclusive; descriptive, not a significance test.',
        modifications='Only partial-lane native first-pass d2z input grouping; no CC plan changes.')
    write('audit-and-statistics.json', audit)
    write('all-samples-and-statistics.json', exported)
    write_csv('全部尺寸.csv', rows)
    write_csv('类型汇总.csv', groups)
    write_csv('本轮实际修改的30项.csv', affected)
    write_csv('此前24项退化复测.csv', old_severe)
    fields = list(rows[0])
    for ref, label in [('previous','上一版'), ('baseline','EXP125')]:
        write_csv('相对'+label+'低于095.csv', sorted((row for row in rows if row['speedup_'+ref] < .95),
                   key=lambda row:row['speedup_'+ref]), fields)
    write_csv('独立正确性表.csv', checks)
    with (OUT/'原始逐次样本.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['N','type','arm','sample_index','elapsed_ms'])
        for (n, func, arm), values in samples.items():
            writer.writerows((n,func.removesuffix('_1d'),arm,index,value) for index,value in enumerate(values,1))
    print(json.dumps({key:audit[key] for key in ('complete','Ns','cases','processes','samples',
        'max_numerical_error','all','changed_input','changed_families','same_run_severe_transition',
        'severe_vs_v3_changed','severe_vs_v3_unchanged')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
