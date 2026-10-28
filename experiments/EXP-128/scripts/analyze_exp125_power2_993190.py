"""Audit and summarize completed EXP125/V6 z2d diagnosis. No device execution."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/fft_measurement'),
               str(ROOT / 'experiments/EXP-128/scripts')]
import cufft261012_contract as contract
from collect_v5_regression_evidence import numeric, stat
from analyze_cc_rows_results import order_effect
from cc_v5_regression_common import rtc_sources

RUN = ROOT / 'experiments/EXP-128/runs/EXP-128-exp125-power2-z2d-diagnostic-20261028'
OUT = ROOT / 'experiments/EXP-128/records/exp125-power2-recheck-20261028/results-993190'


def read(path):
    assert path.resolve().is_relative_to(ROOT)
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def write_csv(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def compare(reference, candidate):
    a, b = reference['statistics_us'], candidate['statistics_us']
    overlap = not (a['p75'] < b['p25'] or b['p75'] < a['p25'])
    drift = reference['order_effect']['flag'] or candidate['order_effect']['flag']
    return dict(speedup=a['median'] / b['median'], iqr_overlap=overlap,
                order_effect=drift,
                assessment='差异不明确' if overlap or drift else '更快' if a['median'] > b['median'] else '更慢')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = read(RUN / 'diagnostic-result.json')
    gate = read(RUN / 'diagnostic-validation.json')
    cfg = read(RUN / 'submit-manifest.json')
    assert result['complete'] and gate['complete'] and not result['failures']
    assert result['job_id'] == gate['job_id'] == '993190' and not result['timestamp_warnings']
    assert {k:len(result[k]) for k in ('timing', 'traces', 'pmc')} == dict(timing=20, traces=10, pmc=16)
    assert result['gpu']['count'] == 1 and result['gpu']['arch'].split(':')[0] == 'gfx936'
    for group in ('timing', 'traces', 'pmc'):
        assert all(x['valid'] and x['library_sha256'] == cfg['arms'][x['arm']]['library_sha256'] for x in result[group])
    files = [RUN / n for n in ('diagnostic-result.json', 'diagnostic-validation.json', 'submit-manifest.json')]
    checks, samples, times, source_audits = [], [], [], []
    for kind in ('timing', 'traces', 'pmc'):
        for x in result[kind]:
            for label in ('check', 'metadata_check', 'profile_check'):
                if label not in x:
                    continue
                c = x[label]
                assert c['check'] == 'PASS' and int(c['N']) == x['N'] and int(c['batch']) == 1
                assert c['func'] == 'z2d_1d' and float(c['err_a']) < 1e-9
                checks.append(dict(N=x['N'], arm=x['arm'], variant=x['variant'],
                                   process_kind=kind, check_kind=label, mode=x.get('mode', ''),
                                   error_a=float(c['err_a']), status=c['check']))
            if x.get('rules_manifest'):
                lines = x['source_audit']
                expected = 'identity' if x['variant'] == 'identity' else 'override'
                assert lines and all(status == expected and '_cc_local_v6_role5_' in name
                                     for status, name in lines)
                assert {name for status, name in lines} == set(x['required_source_names'])
                source_audits.append(dict(N=x['N'], variant=x['variant'], process_kind=kind,
                                          mode=x.get('mode', ''), audit=lines))
    assert len(checks) == 56 and len(source_audits) == 14
    for x in result['timing']:
        output = Path(x['folder']) / 'harness'
        csv_path, raw_path = output / 'fft_test_1d.csv', output / 'fft_test_1d.samples.csv'
        values = contract.validate_process(contract.read_rows(csv_path)[0], contract.read_samples(raw_path),
                                          x['check'], x['N'], x['func'], 30)
        assert values == x['samples_ms'] and len(values) == 30
        files += [csv_path, raw_path]
        statistics_us = stat([v * 1000 for v in values])
        entry = dict(N=x['N'], arm=x['arm'], variant=x['variant'], index=x['index'],
                     statistics_us=statistics_us, order_effect=order_effect(values),
                     samples_us=[v * 1000 for v in values])
        times.append(entry)
        for i, v in enumerate(entry['samples_us'], 1):
            samples.append(dict(N=x['N'], arm=x['arm'], variant=x['variant'],
                                process_index=x['index'], sample_index=i, time_us=v))
    by = {(x['N'], x['arm'], x['variant']): x for x in times}
    comparisons = []
    for n in sorted({x['N'] for x in times}):
        old, cur, identity, phase = (by[n, a, v] for a, v in
                                     [('baseline', 'original'), ('candidate', 'original'),
                                      ('candidate', 'identity'), ('candidate', 'phase_order')])
        comparisons.append(dict(N=n, **cfg['geometry'][str(n)],
                                exp125_us=old['statistics_us']['median'],
                                current_us=cur['statistics_us']['median'],
                                identity_us=identity['statistics_us']['median'],
                                phase_order_us=phase['statistics_us']['median'],
                                current_vs_exp125=compare(old, cur),
                                phase_vs_current=compare(cur, phase),
                                phase_vs_identity=compare(identity, phase),
                                identity_vs_current=compare(cur, identity)))
    traces = []
    for x in result['traces']:
        assert x['timing_valid'] and len(x['trace']['kernels']) == 2
        captured_path = Path(x['folder']) / 'metadata/rtc.txt'
        captured = rtc_sources(captured_path.read_text())
        expected = cfg['power2_selection']['expected_sources'][str(x['N'])][x['arm']]
        assert [k['name'] for k in expected] == x['trace']['kernel_names']
        for e in expected:
            assert hashlib.sha256(captured[e['name']].encode()).hexdigest() == e['sha256']
        files += [captured_path, captured_path.with_name('plan.txt'),
                  Path(x['folder']) / 'profile/trace.json']
        kernels = [dict(position=k['position'], name=k['name'], statistics_us=k['stats_us'],
                         samples_us=k['samples_us']) for k in x['trace']['kernels']]
        assert all(len(k['samples_us']) == 30 for k in kernels)
        traces.append(dict(N=x['N'], arm=x['arm'], kernels=kernels,
                           window_sum_us=x['trace']['window_kernel_sum_us'],
                           window_gap_us=x['trace']['window_gap_us'],
                           maximum_active_workgroups=x['occupancy_log_values'][-2:],
                           evidence=x['folder']))
    pmc, flat_counters = [], []
    totals = {'shared memory operation', 'number of L2 cache read requests', 'size of L2 cache read',
              'number of L2 cache write requests', 'size of L2 cache write'}
    for x in result['pmc']:
        path = Path(x['folder']) / 'measured-counter-windows.json'
        files.append(path)
        raw = read(path)
        windows = raw['windows']
        assert len(windows) == 30 and all(len(w) == 2 for w in windows)
        expected = cfg['power2_selection']['expected_sources'][str(x['N'])][x['arm']]
        assert all([b['name'] for b in w] == [b['name'] for b in expected] for w in windows)
        entry = {k:x[k] for k in ('N', 'arm', 'variant', 'mode')}
        entry.update(raw_path=str(path), raw_sha256=sha(path), stages=[], summed_fields={})
        for position in range(2):
            keys = set(windows[0][position]['fields'])
            assert all(set(w[position]['fields']) == keys for w in windows)
            fields = {}
            for key in sorted(keys):
                values = [numeric(w[position]['fields'][key]) for w in windows]
                if any(v is None for v in values):
                    continue
                assert len({v[1] for v in values}) == 1
                info = dict(unit=values[0][1], **stat([v[0] for v in values]))
                fields[key] = info
                flat_counters.append(dict(N=x['N'], arm=x['arm'], variant=x['variant'], mode=x['mode'],
                                           stage='列端' if position == 0 else '行端', field=key, **info))
            entry['stages'].append(dict(position=position, name=windows[0][position]['name'], fields=fields))
        for key in sorted(totals):
            if not all(key in b['fields'] for w in windows for b in w):
                continue
            values = [[numeric(b['fields'][key]) for b in w] for w in windows]
            assert all(v is not None for group in values for v in group)
            assert len({v[1] for group in values for v in group}) == 1
            entry['summed_fields'][key] = dict(unit=values[0][0][1],
                                              **stat([sum(v[0] for v in group) for group in values]))
        pmc.append(entry)
    audit = dict(complete=True, formal=False, job_id='993190', host=result['host'], gpu=result['gpu'],
                 counts=dict(timing_processes=20, clean_samples=600, trace_processes=10,
                             traced_kernel_samples=600, counter_processes=16, counter_windows=480,
                             numerical_checks=56, source_override_processes=14),
                 maximum_numerical_error=max(c['error_a'] for c in checks),
                 original_result_sha256=sha(RUN / 'diagnostic-result.json'),
                 timestamp_warnings=[], production_source_modified=False,
                 counter_units='Raw SDK units; stall percentages are not wait cycles, L2 bytes are not HBM bytes.',
                 sample_policy='Median only; preserve all 30 samples per process. IQR overlap or disjoint first/last 15-sample IQR => inconclusive. Diagnostic, not a replacement of formal job991869.')
    save('evidence-acceptance.json', audit)
    save('analysis.json', dict(audit=audit, timing=times, comparisons=comparisons, traces=traces,
                                source_audits=source_audits))
    save('pmc-summary.json', dict(complete=True, job_id='993190', entries=pmc))
    save('source-index.json', [dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size)
                                for p in dict.fromkeys(files)])
    write_csv('原始计时样本.csv', samples)
    write_csv('独立正确性表.csv', checks)
    write_csv('全部计数器中位数.csv', flat_counters)
    write_csv('计时对照.csv', [dict(N=x['N'], C=x['C'], Q=x['Q'], exp125_us=x['exp125_us'],
                                   current_us=x['current_us'], identity_us=x['identity_us'],
                                   phase_order_us=x['phase_order_us'],
                                   current_speedup=x['current_vs_exp125']['speedup'],
                                   current_assessment=x['current_vs_exp125']['assessment'],
                                   phase_speedup=x['phase_vs_current']['speedup'],
                                   phase_assessment=x['phase_vs_current']['assessment']) for x in comparisons])
    write_csv('实际内核分段.csv', [dict(N=x['N'], arm=x['arm'],
                                       column_us=x['kernels'][0]['statistics_us']['median'],
                                       row_us=x['kernels'][1]['statistics_us']['median'],
                                       column_p25=x['kernels'][0]['statistics_us']['p25'],
                                       column_p75=x['kernels'][0]['statistics_us']['p75'],
                                       row_p25=x['kernels'][1]['statistics_us']['p25'],
                                       row_p75=x['kernels'][1]['statistics_us']['p75'],
                                       window_sum_us=x['window_sum_us']['median']) for x in traces])
    print(json.dumps(audit, ensure_ascii=False))
    print('COMPARISONS', json.dumps(comparisons, ensure_ascii=False))
    for x in pmc:
        print('PMC', x['N'], x['arm'], x['variant'], x['mode'],
              json.dumps([dict(position=s['position'], fields={k:v['median'] for k,v in s['fields'].items()
                          if k in {'vgpr count', 'sgpr count', 'shared memory size', 'scratch size',
                                   'shared memory operation', 'shared memory bank conflict',
                                   'L1 cache unit is stalled', 'L2 cache hit rate',
                                   'size of L2 cache read', 'number of L2 cache read requests',
                                   'size of L2 cache write', 'number of L2 cache write requests'}})
                          for s in x['stages']], ensure_ascii=False))


if __name__ == '__main__':
    main()
