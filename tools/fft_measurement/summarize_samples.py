"""Validate every v2 event sample, then report separate mean/median ratios."""
import argparse
import csv
import json
from pathlib import Path

from common import cases, read_rows, reference, require, sha, write_json
from sample_contract import (POLICY, SOURCE_SHA, arms, iterations, manifest,
                             read_samples, schedule, statistics_for, validate_process)


def aggregate(run, reference_path=None):
    run = Path(run)
    m = manifest(run/'preregistration.json')
    p = json.loads((run/'provenance.json').read_text(encoding='utf-8'))
    selected = arms(m)
    count = iterations(m)
    require(p.get('policy') == POLICY and p.get('source_sha256') == SOURCE_SHA,
            'wrong timing source/policy')
    require(p.get('complete') is True, 'run not completed')
    require(p.get('event_iterations') == count and p.get('timing_warmups') == 3,
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
        for key in ('csv', 'samples', 'stdout', 'stderr'):
            path = (run/entry[key]).resolve()
            require(run.resolve() in path.parents, 'evidence path escapes run')
            require(path not in evidence_paths, 'reused process evidence')
            evidence_paths.add(path)
            require(sha(path) == entry[key+'_sha256'], 'changed process evidence: '+key)
        rows = read_rows(run/entry['csv'])
        require(len(rows) == 1, 'exactly one summary row per fresh process required')
        key = (planned['N'], planned['func'], planned['arm'])
        require(key not in samples, 'duplicate process for case/arm')
        samples[key] = validate_process(rows[0], read_samples(run/entry['samples']),
                                        planned['N'], planned['func'], count)
    a100 = reference(reference_path) if reference_path else reference()
    rows = []
    for n, func in cases(m):
        row = dict(func=func, N=n, batch=1, processes_per_arm=1, events_per_arm=count, check='PASS')
        for arm in selected:
            row.update({arm+'_'+key: value for key, value in statistics_for(samples[(n, func, arm)]).items()})
        for arm in selected:
            if arm != 'candidate':
                for statistic in ('mean', 'median'):
                    row['speedup_'+arm+'_'+statistic] = row[arm+'_'+statistic+'_ms']/row['candidate_'+statistic+'_ms']
        row['a100_mean_ms'] = a100.get((n, func))
        row['a100_performance_mean_percent'] = (a100[(n, func)]/row['candidate_mean_ms']*100
                                                 if (n, func) in a100 else None)
        rows.append(row)
    return m, p, rows, samples


def report(run, reference_path=None):
    m, p, rows, samples = aggregate(run, reference_path)
    run = Path(run)
    with (run/'comparison.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    selected = arms(m)
    labels = {'official': '官方基线', 'previous': '稳定对照', 'candidate': '当前版本'}
    count = iterations(m)
    lines = ['# '+m['experiment']+' 性能测量', '', '测量协议：`'+POLICY+'`。', '',
             '每个尺寸、类型、版本一个独立进程；批量为一，预热三次，正式计时%d次。全部样本保留，正确性全部通过。'%count,
             '均值与中位数分别由单次耗时计算；加速比为对照耗时除以当前耗时，大于一表示加速。', '',
             '登记的验收要求：'+m['acceptance'], '']
    columns = ['尺寸／类型']
    for arm in selected:
        columns.extend([labels[arm]+'均值（微秒）', labels[arm]+'中位数（微秒）'])
    for arm in selected:
        if arm != 'candidate':
            columns.extend(['对'+labels[arm]+'均值加速比', '对'+labels[arm]+'中位数加速比'])
    columns.extend(['散点／顺序图', 'A100相对性能（均值）'])
    lines.extend(['| '+' | '.join(columns)+' |', '| '+' | '.join(['---']+['---:']*(len(columns)-1))+' |'])
    from plot_samples import render
    plots = render(run, m, samples)
    for row, plot in zip(rows, plots):
        fields = [str(row['N'])+' '+row['func'].removesuffix('_1d')]
        for arm in selected:
            fields.extend('%.6f'%(row[arm+'_'+statistic+'_ms']*1000) for statistic in ('mean','median'))
        for arm in selected:
            if arm != 'candidate':
                fields.extend('%.6f倍'%row['speedup_'+arm+'_'+statistic] for statistic in ('mean','median'))
        fields.extend(['[查看图]('+plot+')', '%.2f%%'%row['a100_performance_mean_percent']
                       if row['a100_performance_mean_percent'] is not None else '—'])
        lines.append('| '+' | '.join(fields)+' |')
    lines.extend(['', '散点图显示全部单次耗时、均值、中位数及中间50%的样本区间；顺序图显示各版本内的测量先后，横轴相同序号不代表两版本同步测量。',
                  '一组连续样本反映当次运行内的波动，图形重叠或顺序漂移时应标注差异不明确；图形本身不构成跨运行稳定性的证明。',
                  '原始逐次记录、源程序／库校验值和未舍入的比较表为依据。计划创建、首次执行及最小耗时仅作诊断，不作内核扣除或额外次数除法。',
                  'A100仅使用历史匹配的均值；无匹配尺寸留空，缺少逐次记录时不构造中位数相对性能。不自动推广或重新测量。', ''])
    with (run/'comparison.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))
    write_json(run/'summary.json', dict(policy=POLICY, experiment=m['experiment'], job_id=p['job_id'],
                                       gpu=p['gpu'], processes=len(schedule(m)), events_per_arm=count, rows=rows))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    try:
        report(args.run)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, 'measurement rejected: %s\n'%error)
