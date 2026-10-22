"""Recheck original diagnostic outputs and summarize median comparisons without GPU work."""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT/'tools/fft_measurement'))
import cufft261012_contract as contract

RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-regression-ablation-20261022'
OUT = ROOT/'experiments/EXP-128/records/regression-955252-20261022/ablation-957127/results-957932'
LABELS = dict(original='本轮原代码', identity='源码不变的入口对照', column_merge='合并列边界',
              row_hoist='行端分类与索引简化', pre_mirror='前处理单边镜像交换', combined='三项组合',
              column_restore='恢复旧列端写出', input_restore='恢复旧共享存储加载')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def stats(values):
    return dict(median_us=statistics.median(values), p25_us=contract.percentile(values, .25),
                p75_us=contract.percentile(values, .75), min_us=min(values), max_us=max(values))


def compare(base, candidate):
    b, c = stats(base), stats(candidate)
    separation = ('中间50%区间分离，候选较快' if c['p75_us'] < b['p25_us'] else
                  '中间50%区间分离，候选较慢' if c['p25_us'] > b['p75_us'] else
                  '区间重叠，差异不明确')
    return dict(speedup=b['median_us']/c['median_us'],
                reduction_percent=(b['median_us']-c['median_us'])/b['median_us']*100,
                distribution=separation,
                early10_speedup=statistics.median(base[:10])/statistics.median(candidate[:10]),
                late10_speedup=statistics.median(base[-10:])/statistics.median(candidate[-10:]))


def main():
    OUT.mkdir(exist_ok=True)
    result, cfg, validation = map(read, (RUN/'ablation-result.json', RUN/'submit-manifest.json',
                                       RUN/'diagnostic-validation.json'))
    assert validation['complete'] and result['complete'] and not result['failures']
    assert result['job_id'] == validation['job_id'] == '957932'
    assert result['gpu'] == cfg['diagnostic_program']['gpu']
    assert len(result['trials']) == len(cfg['rtc_ablation']['trials']) == 95
    timing, metadata, samples, max_error, audit_count = [], [], [], 0., 0
    for declared, trial in zip(cfg['rtc_ablation']['trials'], result['trials']):
        assert all(trial[key] == value for key, value in declared.items())
        assert trial['valid'] and 'error' not in trial
        folder = Path(trial['folder'])
        harness = folder/'harness'
        check = contract.read_check(harness/'fft_test_1d.check.csv')
        assert check == trial['check']
        original_rows = contract.read_rows(harness/'fft_test_1d.csv')
        assert len(original_rows) == 1
        raw_samples = contract.read_samples(harness/'fft_test_1d.samples.csv')
        values = contract.validate_process(original_rows[0], raw_samples, check,
                                          trial['N'], trial['func'], 30)
        assert values == trial['samples_ms'] and all(math.isfinite(x) and x > 0 for x in values)
        assert statistics.median(values) == trial['statistics_ms']['median_ms']
        max_error = max(max_error, float(check['err_a']))
        if trial['variant'] != 'original':
            actual = [line.split('\t') for line in (folder/'source-audit.tsv').read_text().splitlines()]
            assert actual == trial['source_audit']
            registered = {rule['name']:rule['status'] for rule in trial['rules']}
            assert all(registered.get(name) == status for status, name in actual)
            assert set(trial['required_source_names']) <= {name for status, name in actual}
            audit_count += len(actual)
        seed = cfg['rtc_ablation']['seeds'][str(trial['N'])+'-'+trial['func']]
        c, q = map(int, re.search(r'_C(\d+)_Q(\d+)_', seed['kernel_names'][0]).groups())
        row = dict(index=trial['index'], N=trial['N'], type=trial['func'][:-3], C=c, Q=q,
                   variant=trial['variant'], label=LABELS[trial['variant']],
                   input_path='共享存储' if seed['kernel_names'][1].endswith('_lds') else '寄存器',
                   samples_us=[value*1000 for value in values], raw_folder=trial['folder'])
        row.update(stats(row['samples_us']))
        early, late = stats(row['samples_us'][:10]), stats(row['samples_us'][-10:])
        row.update(early10_median_us=early['median_us'], late10_median_us=late['median_us'],
                   within_process_drift_percent=(late['median_us']/early['median_us']-1)*100,
                   within_process_blocks_separated=(early['p75_us'] < late['p25_us']
                                                    or late['p75_us'] < early['p25_us']))
        if trial['metadata']:
            text = (folder/'plan.txt').read_text()
            last = text.rsplit('ExecPlan:', 1)[1]
            schemes = re.findall(r'^\s*scheme: (\S+)', last, re.M)
            assert schemes == ['CS_REAL_TRANSFORM_EVEN', 'CS_KERNEL_STOCKHAM_BLOCK_CC',
                               'CS_KERNEL_STOCKHAM_BLOCK_RC'], schemes
            occupancy = list(map(int, re.findall(r'Kernel occupancy:\s*(\d+)', text)))
            assert occupancy[-80:] == trial['maximum_active_workgroups']*40
            row.update(maximum_active_workgroups=trial['maximum_active_workgroups'], schemes=schemes,
                       comments=re.findall(r'comment: ([^\n]+)', last),
                       grids=re.findall(r'^  b\[[^\n]+', last, re.M), plan_sha256=digest(folder/'plan.txt'))
            assert len(row['comments']) == len(row['grids']) == 2
            metadata.append(row)
        else:
            timing.append(row)
            samples += [dict(N=row['N'], type=row['type'], variant=row['variant'],
                             sample_index=index, elapsed_ms=value)
                        for index, value in enumerate(values, 1)]
    assert len(timing) == 79 and len(metadata) == 16 and len(samples) == 2370
    originals = {(row['N'],row['type']):row for row in timing if row['variant'] == 'original'}
    assert len(originals) == len(cfg['cases']) == 20
    for row in timing:
        base = originals[row['N'],row['type']]
        row.update(compare(base['samples_us'], row['samples_us']))
    for row in metadata:
        base = next(t for t in metadata if t['N'] == row['N'] and t['type'] == row['type']
                    and t['variant'] == 'original')
        assert row['schemes'] == base['schemes'] and row['grids'] == base['grids']
    groups = []
    for kind, variant in sorted({(row['type'], row['variant']) for row in timing
                                  if row['variant'] not in ('original','identity')}):
        group = [row for row in timing if row['type'] == kind and row['variant'] == variant]
        groups.append(dict(type=kind, variant=variant, cases=len(group),
                           point_estimates_faster=sum(row['speedup'] > 1 for row in group),
                           clear_faster=sum(row['distribution'] == '中间50%区间分离，候选较快' for row in group),
                           clear_slower=sum(row['distribution'] == '中间50%区间分离，候选较慢' for row in group),
                           uncertain=sum(row['distribution'] == '区间重叠，差异不明确' for row in group),
                           minimum_speedup=min(row['speedup'] for row in group),
                           maximum_speedup=max(row['speedup'] for row in group)))
    overview = dict(complete=True, formal=False, job='957932', runtime_seconds=274,
        cases=20, timing_processes=79, timing_samples=2370, metadata_processes=16,
        metadata_samples=480, max_err_a=max_error, audited_source_calls=audit_count,
        protocol=cfg['policy'], gpu=result['gpu'], library_sha256=cfg['arms']['candidate']['library_sha256'],
        tool_source_commit=cfg['diagnostic']['tool_source_commit'], groups=groups,
        files={name:dict(path=str(RUN/name), sha256=digest(RUN/name)) for name in
               ('ablation-result.json','submit-manifest.json','diagnostic-validation.json')},
        caveats=['与本轮同一库原代码比较；不能替换955252正式总表或与历史耗时拼接加速比。',
                 '中间50%区间分离是分布描述，不是独立重复实验的统计显著性检验。',
                 '首十次与末十次只描述进程内变化，不据此猜测频率、温度、缓存原因。',
                 '驻留工作组数是资源允许的上限，不是实测活跃占用率。'])
    save(OUT/'分析数据.json', dict(overview=overview, timing=timing, metadata=metadata))
    save(OUT/'核对摘要.json', overview)
    fields = ['N','type','C','Q','input_path','variant','label','median_us','p25_us','p75_us',
              'speedup','reduction_percent','distribution','early10_median_us','late10_median_us',
              'within_process_drift_percent','early10_speedup','late10_speedup','raw_folder']
    for name, rows, columns in [('全部受控对照.csv',timing,fields),
                                ('全部2370个计时样本.csv',samples,list(samples[0]))]:
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
            writer.writeheader();writer.writerows(rows)
    save(OUT/'路径与驻留上限.json',metadata)
    print(json.dumps(overview, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
