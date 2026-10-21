"""Audit completed three-version evidence and describe median performance by CC family."""
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools/fft_measurement'))
from summarize_cufft261012 import aggregate
from sample_contract import percentile
from cufft261012_contract import read_check
from tools.workspace_manager import manager as mgr, revalidate

RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-phasefix-performance-20261022'
VALIDATION = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-phasefix-validate-20261022'
OUT = ROOT/'experiments/EXP-128/records/phasefix-20261022/results-955252'
ARMS = ('baseline', 'previous', 'candidate')


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def write_csv(name, rows):
    with (OUT/name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def order_effect(values):
    first, last = values[:15], values[15:]
    disjoint = (percentile(first, .75) < percentile(last, .25)
                or percentile(last, .75) < percentile(first, .25))
    return dict(flag=disjoint, first_half_median_us=1000*statistics.median(first),
                last_half_median_us=1000*statistics.median(last))


def summarize(rows, reference):
    ratios = [row['speedup_'+reference] for row in rows]
    return dict(cases=len(rows), faster=sum(value > 1 for value in ratios),
        equal=sum(value == 1 for value in ratios), slower=sum(value < 1 for value in ratios),
        median_case_speedup=statistics.median(ratios), min_speedup=min(ratios), max_speedup=max(ratios),
        clear_faster=sum(row['assessment_'+reference] == '更快' for row in rows),
        clear_slower=sum(row['assessment_'+reference] == '更慢' for row in rows),
        unclear=sum(row['assessment_'+reference] == '差异不明确' for row in rows),
        iqr_overlap=sum(row['overlap_'+reference] for row in rows),
        order_effect=sum(row['order_effect_'+reference] for row in rows))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, provenance, original_rows, samples = aggregate(RUN)
    assert original_rows == read(RUN/'summary.json')['rows']
    assert len(original_rows) == 388 and len(samples) == 1164
    assert sum(map(len, samples.values())) == 34920
    validation_cfg = mgr.load(VALIDATION/'submit-manifest.json')
    built, library, command, filename = revalidate.existing(validation_cfg)
    acceptance = revalidate.verify_acceptance(mgr.locations(validation_cfg, 'validate'),
                                             built, command, filename, '955251')
    assert acceptance == manifest['validation_acceptance']
    validation = read(VALIDATION/filename)
    assert validation['complete'] and not validation['failures']
    assert len(validation['numerical']) == len(validation['dispatch']) == 24
    assert validation['gpu'] == provenance['gpu']
    coverage_path = ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    coverage = read(coverage_path)
    by_n = {row['N']:row for row in coverage['public']}
    assert set(by_n) == {row['N'] for row in original_rows}
    for row in validation['dispatch']:
        expected = (4, 5) if row['func'] == 'z2d_1d' else (6, 7)
        assert len(row['actual_names']) == 2
        assert all('_cc_local_v2_role%d_C%d_Q%d_' % (role, row['C'], row['Q']) in name
                   for role, name in zip(expected, row['actual_names']))
        if row['func'] == 'd2z_1d':
            assert row['actual_names'][1].endswith('_reg')
    rows, exported = [], []
    for original in original_rows:
        n, func = original['N'], original['func']
        geometry = by_n[n]
        c, q = geometry['C'], geometry['Q']
        row = dict(N=n, type=func.removesuffix('_1d'), C=c, Q=q,
            parity=('奇' if c % 2 else '偶')+'×'+('奇' if q % 2 else '偶'),
            power_of_two=(n & (n-1)) == 0)
        effects = {}
        for arm in ARMS:
            row[arm+'_us'] = 1000*original[arm+'_median_ms']
            row[arm+'_p25_us'] = 1000*original[arm+'_p25_ms']
            row[arm+'_p75_us'] = 1000*original[arm+'_p75_ms']
            effects[arm] = order_effect(samples[(n, func, arm)])
            row[arm+'_order_effect'] = effects[arm]['flag']
        for reference in ('baseline', 'previous'):
            row['speedup_'+reference] = row[reference+'_us']/row['candidate_us']
            row['reduction_'+reference+'_percent'] = 100*(1-row['candidate_us']/row[reference+'_us'])
            row['overlap_'+reference] = not (
                row[reference+'_p25_us'] > row['candidate_p75_us']
                or row['candidate_p25_us'] > row[reference+'_p75_us'])
            row['order_effect_'+reference] = effects[reference]['flag'] or effects['candidate']['flag']
            row['assessment_'+reference] = ('差异不明确' if row['overlap_'+reference]
                or row['order_effect_'+reference] else ('更快' if row['speedup_'+reference] > 1 else '更慢'))
        row['a100_us'] = (1000*original['a100_median_ms']
                          if original['a100_median_ms'] is not None else None)
        row['a100_performance_percent'] = original['a100_performance_median_percent']
        rows.append(row)
        exported.append(dict(row, samples_us={arm:[value*1000 for value in samples[(n,func,arm)]]
                                             for arm in ARMS}, order_effect_details=effects))
    groups = []
    dimensions = [('全部', 'all', lambda row:'all'), ('列长', 'C', lambda row:row['C']),
                  ('行长', 'Q', lambda row:row['Q']), ('奇偶', 'parity', lambda row:row['parity']),
                  ('二次幂', 'power_of_two', lambda row:row['power_of_two'])]
    for label, field, get in dimensions:
        for value in sorted({get(row) for row in rows}, key=str):
            for func in ('z2d', 'd2z'):
                selected = [row for row in rows if row['type'] == func and get(row) == value]
                for reference in ('baseline', 'previous'):
                    groups.append(dict(dimension=label, value=value, type=func, reference=reference,
                                       **summarize(selected, reference)))
    historical_path = ROOT/'experiments/EXP-128/records/regression-analysis-953997-20261021/全部退化项.csv'
    historical = list(csv.DictReader(historical_path.open(encoding='utf-8-sig')))
    historical_keys = {(int(row['N']), row['类型']) for row in historical}
    old_slower = [row for row in rows if (row['N'], row['type']) in historical_keys]
    assert len(old_slower) == 60
    checks = [dict(arm=entry['arm'], **read_check(RUN/entry['correctness']))
              for entry in read(RUN/'processes.json')]
    assert len(checks) == 1164 and all(row['check'] == 'PASS' for row in checks)
    audit = dict(complete=True, formal=True, job_id='955252', validation_job='955251',
        validation_cases=24, validation_seconds=validation['elapsed_seconds'],
        correctness_processes=len(samples), numerical_checks='all PASS; strict <1e-9 outside timing',
        max_numerical_error=max(float(row['err_a']) for row in checks),
        Ns=len(by_n), cases=len(rows), processes=len(samples), samples=sum(map(len,samples.values())),
        GPU=provenance['gpu'], host=provenance['host'],
        first=provenance['start'], last=provenance['end'], policy=provenance['policy'],
        coverage=dict(columns=len({row['C'] for row in rows}), rows=len({row['Q'] for row in rows}),
                      parity_counts={p:sum(row['parity'] == p for row in rows)//2
                                     for p in sorted({row['parity'] for row in rows})}),
        arms={arm:dict(source_commit=provenance['arms'][arm]['source_commit'],
                      library_sha256=provenance['arms'][arm]['library_sha256'],
                      install=provenance['arms'][arm]['install']) for arm in ARMS},
        validation_acceptance=acceptance,
        all={func:{ref:summarize([row for row in rows if row['type'] == func],ref)
                   for ref in ('baseline','previous')} for func in ('z2d','d2z')},
        formerly_slower={ref:summarize(old_slower,ref) for ref in ('baseline','previous')},
        all_reference_sha256={str(path.relative_to(ROOT)):mgr.common.sha(path) for path in
            (RUN/'preregistration.json',RUN/'provenance.json',RUN/'processes.json',RUN/'summary.json',
             VALIDATION/'post-build-validation.json',VALIDATION/'cc-local-validation.json',coverage_path)},
        assessments='IQR overlap or a first-half/last-half disjoint IQR is marked inconclusive; descriptive, not a significance test.',
        modifications='Two generic changes together plus inclusive 65536 boundary; no legacy priority, no isolated mechanism timing.')
    write('audit-and-statistics.json', audit)
    write('all-samples-and-statistics.json', exported)
    write_csv('全部尺寸.csv', rows)
    write_csv('类型汇总.csv', groups)
    write_csv('此前退化项复测.csv', old_slower)
    write_csv('相对上一版退化.csv', [row for row in rows if row['speedup_previous'] < 1])
    write_csv('相对EXP125退化.csv', [row for row in rows if row['speedup_baseline'] < 1])
    write_csv('重点类型.csv', [row for row in rows if row['C'] == 289 or row['Q'] == 289
                             or row['N'] == 142688 or row['power_of_two']])
    write_csv('独立正确性表.csv', checks)
    with (OUT/'原始逐次样本.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['N','type','arm','sample_index','elapsed_ms'])
        for (n, func, arm), values in samples.items():
            writer.writerows((n,func.removesuffix('_1d'),arm,index,value)
                             for index,value in enumerate(values,1))
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print('KEY_FAMILIES', json.dumps([group for group in groups if
        (group['dimension'] == '列长' and group['value'] == 289)
        or (group['dimension'] == '行长' and group['value'] in (121,169,289,343,1331))
        or group['dimension'] == '二次幂'], ensure_ascii=False))


if __name__ == '__main__':
    main()
