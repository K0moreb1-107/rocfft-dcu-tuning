"""Audit and describe the completed previous/V6 comparison without rerunning timing."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'tools/fft_measurement'),
               str(ROOT/'experiments/EXP-128/scripts')]
from summarize_cufft261012 import aggregate
from cufft261012_contract import read_check
from analyze_cc_rows_results import order_effect

RUN = ROOT/'experiments/EXP-129/runs/EXP-129-fusion-only-performance-20261031'
RECORD = ROOT/'experiments/EXP-129/records/fusion-only-20261031'
OUT = RECORD/'results-1009320'
ARMS = ('previous', 'candidate')
IDENTITIES = {
    'previous': ('e7340de4d5d59122d6cf85e7fd76bae529652705',
                 '540224bb0da0e49d13468291902e2ab6fd92db60f973a244082e7352624db803'),
    'candidate': ('842b98916033e212ca9fe0e327381e6d33eb8080',
                  '974f5a4f1acfd471b751849277a8a949b2c4e59466b907ea9078ee4fb65ae0b3'),
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def csv_file(name, rows, fields=None):
    with (OUT/name).open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    ratios = [r['speedup'] for r in rows]
    return dict(cases=len(rows), faster=sum(x > 1 for x in ratios),
                equal=sum(x == 1 for x in ratios), slower=sum(x < 1 for x in ratios),
                median_case_speedup=statistics.median(ratios),
                min_speedup=min(ratios), max_speedup=max(ratios),
                below_095=sum(x < .95 for x in ratios),
                within_095_105=sum(.95 <= x <= 1.05 for x in ratios),
                above_105=sum(x > 1.05 for x in ratios),
                clear_faster=sum(r['assessment'] == '更快' for r in rows),
                clear_slower=sum(r['assessment'] == '更慢' for r in rows),
                unclear=sum(r['assessment'] == '差异不明确' for r in rows),
                iqr_overlap=sum(r['iqr_overlap'] for r in rows),
                order_effect=sum(r['order_effect'] for r in rows))


def table(rows, flag=False):
    lines = ['| size／类型 | baseline（微秒） | A100（微秒） | 当前（微秒） | 加速比 | performance |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:
        a100 = '—' if r['a100_us'] is None else '%.6f' % r['a100_us']
        performance = '—' if r['performance_percent'] is None else '%.2f%%' % r['performance_percent']
        ratio = '%.6f' % r['speedup']
        if flag and r['assessment'] == '差异不明确':
            ratio += '†'
        lines.append('| %d %s | %.6f | %s | %.6f | %s | %s |' %
                     (r['N'], r['type'], r['previous_us'], a100,
                      r['candidate_us'], ratio, performance))
    return lines


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, provenance, original, samples = aggregate(RUN)
    assert manifest.get('comparison_kind') == 'real_boundary_fusion'
    assert original == read(RUN/'summary.json')['rows']
    assert tuple(manifest['arms']) == ARMS
    assert len(original) == 388 and len(samples) == 776
    assert sum(map(len, samples.values())) == 23280
    assert provenance['job_id'] == '1009320'
    assert provenance['timing_warmups'] == 10 and provenance['event_iterations'] == 30
    assert provenance['gpu']['count'] == 1
    for arm, (commit, checksum) in IDENTITIES.items():
        assert provenance['arms'][arm]['source_commit'] == commit
        assert provenance['arms'][arm]['library_sha256'] == checksum
    coverage_path = ROOT/'experiments/EXP-129/records/fusion-only-20261031/coverage.json'
    assert sha(coverage_path) == manifest['coverage_sha256']
    ns = {x['N'] for x in read(coverage_path)['public']}
    assert len(ns) == 194 and (min(ns), max(ns)) == (65536, 2725888)
    assert {(r['N'], r['func']) for r in original} == {
        (n, f) for n in ns for f in ('z2d_1d', 'd2z_1d')}
    model_path = ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027/mapping-model.json'
    geometry = {x['N']: x for x in read(model_path)['cases']}
    assert set(geometry) == ns
    entries = read(RUN/'processes.json')
    checks = [dict(arm=e['arm'], **read_check(RUN/e['correctness'])) for e in entries]
    assert len(checks) == 776 and all(c['check'] == 'PASS' for c in checks)
    errors = [float(c[k]) for c in checks for k in ('err_a', 'err_b') if float(c[k]) >= 0]
    assert max(errors) < 1e-9
    for i in range(388):
        a, b = entries[2*i:2*i+2]
        assert (a['N'], a['func']) == (b['N'], b['func'])
        assert [a['arm'], b['arm']] == (list(ARMS) if i % 2 == 0 else list(reversed(ARMS)))
    rows, exported = [], []
    for x in original:
        n, func = x['N'], x['func']
        g = geometry[n]
        row = dict(N=n, type=func.removesuffix('_1d'), C=g['C'], Q=g['Q'],
                   power_of_two=(n & (n-1)) == 0)
        effects = {}
        for arm in ARMS:
            for stat in ('median', 'p25', 'p75', 'min', 'max'):
                row[arm+('_us' if stat == 'median' else '_'+stat+'_us')] = x[arm+'_'+stat+'_ms']*1000
            effects[arm] = order_effect(samples[n, func, arm])
        row['speedup'] = row['previous_us']/row['candidate_us']
        assert row['speedup'] == x['speedup_previous_median']
        row['iqr_overlap'] = not (row['previous_p25_us'] > row['candidate_p75_us'] or
                                  row['candidate_p25_us'] > row['previous_p75_us'])
        row['order_effect'] = effects['previous']['flag'] or effects['candidate']['flag']
        row['assessment'] = ('差异不明确' if row['iqr_overlap'] or row['order_effect'] else
                             '更快' if row['speedup'] > 1 else '更慢')
        row['a100_us'] = None if x['a100_median_ms'] is None else x['a100_median_ms']*1000
        row['performance_percent'] = x['a100_performance_median_percent']
        rows.append(row)
        exported.append(dict(row, samples_us={a: [v*1000 for v in samples[n, func, a]] for a in ARMS},
                             order_effect_details=effects))
    rows.sort(key=lambda r: (r['N'], r['type']))
    exported.sort(key=lambda r: (r['N'], r['type']))
    groups = []
    for dimension, getter in [('全部', lambda r: '全部'), ('二次幂', lambda r: r['power_of_two']),
                               ('行长', lambda r: r['Q']), ('列长', lambda r: r['C'])]:
        for value in sorted({getter(r) for r in rows}, key=str):
            for func in ('z2d', 'd2z'):
                selected = [r for r in rows if getter(r) == value and r['type'] == func]
                if selected:
                    groups.append(dict(dimension=dimension, value=value, type=func, **summarize(selected)))
    severe = sorted((r for r in rows if r['speedup'] < .95), key=lambda r: r['speedup'])
    audit = dict(complete=True, job_id='1009320', N=194, cases=388, processes=776,
                 formal_samples=23280, timing_warmups=10, samples_per_process=30,
                 max_numerical_error=max(errors), host=provenance['host'], gpu=provenance['gpu'],
                 policy=provenance['policy'], start=provenance['start'], end=provenance['end'],
                 original_39_columns_and_all_raw_evidence_verified=True,
                 adjacent_alternating_schedule_verified=True,
                 references={a: {k: provenance['arms'][a][k] for k in
                             ('install', 'source_commit', 'library_sha256')} for a in ARMS},
                 all={f: summarize([r for r in rows if r['type'] == f]) for f in ('z2d', 'd2z')},
                 overall=summarize(rows), severe=severe,
                 power_of_two=[r for r in rows if r['power_of_two']],
                 a100_exact_matches=sum(r['a100_us'] is not None for r in rows),
                 assessment_rule='IQR overlap or disjoint first/last 15-sample IQR => inconclusive; descriptive, not a significance test.',
                 comparison='Same production source and CC decomposition, fusion OFF versus ON; ratio OFF median / ON median.',
                 evidence_sha256={str(p.relative_to(ROOT)): sha(p) for p in
                    (RUN/'preregistration.json', RUN/'provenance.json', RUN/'processes.json',
                     RUN/'summary.json', coverage_path, model_path, Path(__file__))})
    save('audit-and-statistics.json', audit)
    save('all-samples-and-statistics.json', exported)
    csv_file('全部尺寸.csv', rows)
    csv_file('类型汇总.csv', groups)
    csv_file('独立正确性表.csv', checks)
    csv_file('低于095.csv', severe, list(rows[0]))
    csv_file('六列表格.csv', [dict(size_type=str(r['N'])+' '+r['type'], baseline_us=r['previous_us'],
        A100_us=r['a100_us'], current_us=r['candidate_us'], speedup=r['speedup'],
        performance_percent=r['performance_percent']) for r in rows])
    with (OUT/'原始逐次样本.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['N', 'type', 'arm', 'sample_index', 'elapsed_us'])
        for r in exported:
            for arm in ARMS:
                w.writerows((r['N'], r['type'], arm, i, v) for i, v in enumerate(r['samples_us'][arm], 1))
    lines = ['# 同源未融合版与融合版性能结果', '',
        '任务1009320完成，退出码为0；194个N、388个组合、776个进程和23280个正式样本全部齐全，独立数值校验全部通过。', '',
        '对照为同源未融合版，候选为EXP129稳定融合版。两版在'+provenance['host']+
        '的同一张gfx936显卡上相邻、交替先后测量。双精度、一维、批量一、非原位、默认计划；每版10次预热、30次计时。', '',
        '加速比＝未融合中位数／当前中位数。以下总体数值是各组合加速比的中位数，不代表合并所有样本后的耗时比。', '',
        '| 类型 | 组合数 | 加速比中位数 | 大于1 | 小于1 | 低于0.95 | 明确更快 | 明确更慢 | 差异不明确 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for func, s in audit['all'].items():
        lines.append('| %s | %d | %.4f | %d | %d | %d | %d | %d | %d |' %
            (func, s['cases'], s['median_case_speedup'], s['faster'], s['slower'], s['below_095'],
             s['clear_faster'], s['clear_slower'], s['unclear']))
    lines += ['', '差异判定沿用既有规则：两版中间50%区间重叠，或任一版前后15次样本的中间50%区间分离，标为“差异不明确”。这是分布描述。全部慢点和异常点保留。', '',
              '本次固定相同生产源码、CC分解和构建参数，只改变前后处理融合开关，测量融合流水的整体净收益，含其布局、配对、同步和资源开销。', '',
              '## 低于0.95的组合', '']
    lines += table(severe, True) if severe else ['无。']
    lines += ['', '## 二次幂', ''] + table(audit['power_of_two'], True)
    lines += ['', '## 全部组合', '',
              'baseline为同源未融合版；A100只使用已登记数据集的精确尺寸与类型匹配。performance＝A100中位数／当前中位数×100%。',
              '加速比后的†表示差异不明确；每项标记和两版四分位区间见“全部尺寸.csv”与交互图。', '']
    lines += table(rows, True)
    lines += ['', '## 证据', '',
              '- 运行目录：`'+str(RUN)+'`。',
              '- 原始39列汇总、逐次样本、独立正确性表及进程输出保留在运行目录；分析器重新核对全部进程证据校验值、顺序、设备与库身份。',
              '- 未融合源码提交：`'+IDENTITIES['previous'][0]+'`；融合版构建源码提交：`'+IDENTITIES['candidate'][0]+'`。',
              '- 最大数值误差：`'+str(max(errors))+'`；阈值严格小于`1e-9`。',
              '- 统计审计：`audit-and-statistics.json`；逐项统计和全部样本：`all-samples-and-statistics.json`。']
    (OUT/'结果分析.md').write_text('\n'.join(lines)+'\n')
    save('analysis-index.json', dict(job_id='1009320', source_run=str(RUN),
        files={p.name:dict(bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(OUT.iterdir())
               if p.is_file() and p.name != 'analysis-index.json'}))
    print(json.dumps({k: audit[k] for k in ('complete', 'host', 'N', 'cases', 'processes',
          'formal_samples', 'max_numerical_error', 'all', 'overall', 'severe', 'power_of_two',
          'a100_exact_matches')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
