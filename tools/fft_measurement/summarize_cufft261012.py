"""Strict v3 evidence aggregation; all analysis and plots use sample medians."""
import argparse
import csv
import json
from pathlib import Path
from common import cases, require, sha, write_json
from cufft261012_contract import (POLICY, SOURCE_SHA, SOURCE_FILES, ORIGIN_SHA, WARMUPS, arms,
    iterations, manifest, read_samples, read_rows, read_check, reference, schedule, statistics_for, validate_process)

def aggregate(run, reference_path=None):
    run = Path(run)
    m = manifest(run/'preregistration.json')
    p = json.loads((run/'provenance.json').read_text(encoding='utf-8'))
    selected = arms(m)
    count = iterations(m)
    require(p.get('policy') == POLICY and p.get('source_sha256') == SOURCE_SHA,
            'wrong timing source/policy')
    require(p.get('source_files_sha256') == SOURCE_FILES and p.get('timing_origin_sha256') == ORIGIN_SHA, 'source/header/origin mismatch')
    require(p.get('complete') is True, 'run not completed')
    require(p.get('event_iterations') == count and p.get('timing_warmups') == WARMUPS,
            'iteration/warmup provenance mismatch')
    require(p.get('job_id') and p.get('host') and p.get('gpu', {}).get('uuid'),
            'missing allocation/device provenance')
    require(p['gpu'].get('count') == 1 and p['gpu'].get('arch', '').split(':')[0] == m['gpu_arch'],
            'GPU visibility/architecture mismatch')
    require(set(p.get('arms', {})) == set(selected), 'missing library provenance')
    for arm in selected:
        a = p['arms'][arm]
        require(a.get('library_sha256') == m['arms'][arm]['library_sha256']
                and a.get('source_commit') == m['arms'][arm]['source_commit'],
                'library/source provenance mismatch')
        require(a.get('actual_library') and a.get('binary_sha256'), 'missing library/binary evidence')
    expected = schedule(m)
    entries = json.loads((run/'processes.json').read_text(encoding='utf-8'))
    require(len(entries) == len(expected), 'incomplete preregistered schedule')
    samples = {}
    evidence_paths = set()
    for entry, planned in zip(entries, expected):
        require(all(entry.get(key) == value for key, value in planned.items()), 'schedule/order mismatch')
        require(entry.get('returncode') == 0, 'nonzero process exit')
        require(entry.get('gpu') == p['gpu'] and entry.get('job_id') == p['job_id']
                and entry.get('host') == p['host'], 'different GPU/allocation/environment')
        require(entry.get('library_sha256') == m['arms'][planned['arm']]['library_sha256'],
                'process library hash mismatch')
        for key in ('csv', 'samples', 'correctness', 'stdout', 'stderr'):
            path = (run/entry[key]).resolve()
            require(run.resolve() in path.parents, 'evidence path escapes run')
            require(path not in evidence_paths, 'reused process evidence')
            evidence_paths.add(path)
            require(sha(path) == entry[key+'_sha256'], 'changed process evidence: '+key)
        rows = read_rows(run/entry['csv'])
        require(len(rows) == 1, 'exactly one summary row per fresh process required')
        key = (planned['N'], planned['func'], planned['arm'])
        require(key not in samples, 'duplicate process for case/arm')
        samples[key] = validate_process(rows[0], read_samples(run/entry['samples']), read_check(run/entry['correctness']),
                                        planned['N'], planned['func'], count)
    require(reference_path is None, 'use the frozen reference, not a report-time override')
    a100 = reference(m)
    rows = []
    for n, func in cases(m):
        row = dict(func=func, N=n, batch=1, processes_per_arm=1, events_per_arm=count, check='PASS')
        for arm in selected:
            row.update({arm+'_'+key: value for key, value in statistics_for(samples[(n, func, arm)]).items()})
        for arm in selected:
            if arm != 'candidate':
                row['speedup_'+arm+'_median'] = row[arm+'_median_ms']/row['candidate_median_ms']
        row['a100_median_ms'] = a100.get((n, func))
        row['a100_performance_median_percent'] = (a100[(n, func)]/row['candidate_median_ms']*100
                                                  if (n, func) in a100 else None)
        rows.append(row)
    return m, p, rows, samples


def report(run):
    m, p, rows, samples = aggregate(run)
    run = Path(run)
    with (run/'comparison.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    from plot_cufft261012 import render
    plots = render(run, m, samples)
    selected = arms(m)
    baseline = 'official' if 'official' in selected else 'previous'
    lines = ['# '+m['experiment']+' 性能测量', '', '协议：`'+POLICY+'`。', '',
             '双精度、一维、批量一、非原位、默认计划；每个尺寸／类型／版本一个进程，十次预热、三十次计时。',
             '预热与正式测量共用同一事件循环，每次完整变换后单独同步；输入为递增序列，复数虚部为零。',
             '严格正确性检查在窗口外，随后恢复完整输入；全部逐次样本保留。时间和加速比只用样本中位数。', '',
             '| size／类型 | baseline（微秒） | A100（微秒） | 当前（微秒） | 加速比 | performance |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    fusion_comparison = m.get('comparison_kind') == 'real_boundary_fusion'
    if fusion_comparison:
        require(selected == ('previous', 'candidate'), 'fusion comparison requires just unfused/fused arms')
        lines[-2:] = ['| size／类型 | 未融合（微秒） | 已融合（微秒） | 融合加速比 | 节省时间（微秒） |',
                      '| --- | ---: | ---: | ---: | ---: |']
        lines.insert(4, '同一源码和CC分解，只有新增实数前后处理融合开关不同；未融合对照不是稳定版或官方版。')
    for row in rows:
        if fusion_comparison:
            lines.append('| %d %s | %.6f | %.6f | %.6f | %.6f |' % (
                row['N'], row['func'].removesuffix('_1d'), row['previous_median_ms']*1000,
                row['candidate_median_ms']*1000, row['speedup_previous_median'],
                (row['previous_median_ms']-row['candidate_median_ms'])*1000))
            continue
        value = row['a100_median_ms']; percentage = row['a100_performance_median_percent']
        fields = [str(row['N'])+' '+row['func'].removesuffix('_1d'),
                  '%.6f'%(row[baseline+'_median_ms']*1000), '%.6f'%(value*1000) if value is not None else '—',
                  '%.6f'%(row['candidate_median_ms']*1000), '%.6f'%row['speedup_'+baseline+'_median'],
                  '%.2f%%'%percentage if percentage is not None else '—']
        lines.append('| '+' | '.join(fields)+' |')
    if 'previous' in selected and baseline != 'previous':
        lines.extend(['', '| size／类型 | 稳定中位数（微秒） | 对稳定加速比 |', '| --- | ---: | ---: |'])
        for row in rows:
            lines.append('| %d %s | %.6f | %.6f |'%(row['N'], row['func'].removesuffix('_1d'),
                row['previous_median_ms']*1000, row['speedup_previous_median']))
    if fusion_comparison:
        lines.extend(['', '比值为未融合／已融合的完整事件中位数，计入融合新增的交换、同步与资源成本。',
                      '原五尺寸z2d包含折叠列和布局变化，单列为融合实现整体净收益；不等同于单独显存读写节省。'])
    else:
        lines.extend(['', 'A100按随包记录的10／30条件及精确N和类型匹配；performance＝A100中位数／当前中位数×100%。',
                  '它是跨设备参考，不替代同卡官方对照；随包源码与二进制对应关系缺少构建凭据，数值检查也不在A100记录中。',
        ])
    lines.extend(['CSV保留原包的六位小数格式；另存未舍入的逐次样本及窗口外正确性记录。统计使用未舍入样本，不删除慢点。',
                  '图中每版一列散点及按内部测量序号排列的同一批样本；只标中位数及中间50%区间，相同序号不表示同步测量。',
                  '分布重叠或时间漂移应标注差异不明确，一组样本不证明跨次稳定性；不自动推广或重新测量。', '', '散点及顺序图：'])
    lines.extend('- [%d %s](%s)'%(r['N'], r['func'].removesuffix('_1d'), image) for r, image in zip(rows, plots))
    with (run/'comparison.md').open('x', encoding='utf-8') as stream: stream.write('\n'.join(lines)+'\n')
    write_json(run/'summary.json', dict(policy=POLICY, experiment=m['experiment'], job_id=p['job_id'],
        gpu=p['gpu'], processes=len(schedule(m)), events_per_arm=iterations(m), timing_warmups=WARMUPS,
        a100_reference=m['a100_reference'], rows=rows))
    return rows

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    try: report(args.run)
    except (ValueError, OSError, KeyError, TypeError) as error: parser.exit(1, 'measurement rejected: %s\n'%error)
