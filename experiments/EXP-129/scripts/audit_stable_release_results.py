"""Audit full release evidence and all raw v3 samples before stable promotion."""
from collections import Counter
from pathlib import Path
import csv
import hashlib
import json
import re
import statistics
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts'), str(ROOT/'tools/fft_measurement')]
import cufft261012_contract as contract
from cc_dispatch import inspect_dispatch
from summarize_cufft261012 import aggregate

BASE = ROOT/'experiments/EXP-129/runs'
BUILD = BASE/'EXP-129-stable-scale-fix-build-20261030'
VALIDATE = BASE/'EXP-129-stable-scale-fix-validate-20261030'
MEASURE = BASE/'EXP-129-stable-scale-fix-performance-20261030'
OUT = ROOT/'experiments/EXP-129/records/stable-scale-fix-20261030/results-1004433'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classification(row, arm, samples):
    current = samples[row['N'], row['func'], 'candidate']
    reference = samples[row['N'], row['func'], arm]
    drift = lambda values: statistics.median(values[-10:])/statistics.median(values[:10])-1.
    shifts = [drift(reference), drift(current)]
    if any(abs(value) >= 0.05 for value in shifts):
        evidence = '差异不明确：前后十次中位数变化至少5%'
    elif row['candidate_p75_ms'] < row[arm+'_p25_ms']:
        evidence = '当前较快：中间50%区间分离'
    elif row[arm+'_p75_ms'] < row['candidate_p25_ms']:
        evidence = '当前较慢：中间50%区间分离'
    else:
        evidence = '差异不明确：中间50%区间重叠'
    return evidence, shifts


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    built, validated, accepted = (read(BUILD/'build-provenance.json'),
        read(VALIDATE/'full-release-validation.json'), read(VALIDATE/'post-build-validation.json'))
    assert built['complete'] and validated['complete'] and accepted['complete']
    assert not validated['failures']
    arm = built['arm']
    assert sha(Path(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256']
    assert validated['library_sha256'] == accepted['library_sha256'] == arm['library_sha256']
    assert validated['source_commit'] == accepted['source_commit'] == arm['source_commit']
    assert accepted['evidence_sha256'] == sha(VALIDATE/'full-release-validation.json')
    config = read(VALIDATE/'submit-manifest.json')
    coverage = read(Path(config['validation']['coverage']))
    assert sha(Path(config['validation']['coverage'])) == validated['coverage_sha256']
    geometry = {item['N']: item for item in coverage['public']}
    expected = {(n, f) for n in list(geometry)+coverage['fallback_N'] for f in ('z2d_1d', 'd2z_1d')}
    expected |= {(n, 'z2z_1d') for n in coverage['ordinary_N']}
    numeric = {(item['N'], item['func']): item for item in validated['numerical']}
    dispatch = {(item['N'], item['func']): item for item in validated['dispatch']}
    assert len(expected) == len(validated['numerical']) == len(validated['dispatch']) == 401
    assert set(numeric) == set(dispatch) == expected
    rows, errors, source_count = [], [], 0
    for n, func in sorted(expected):
        item = dispatch[n, func]
        folder = VALIDATE/'full-release'/('dispatch-'+str(n)+'-'+func)
        harness = folder/'profile/harness'
        checked = contract.read_check(harness/'fft_test_1d.check.csv')
        raw = contract.read_rows(harness/'fft_test_1d.csv')
        assert len(raw) == 1 and checked == numeric[n, func]['check']
        contract.validate_process(raw[0], contract.read_samples(harness/'fft_test_1d.samples.csv'), checked, n, func, 30)
        plan = (folder/'metadata/plan.txt').read_text()
        launches, checked_dispatch = inspect_dispatch(plan, read(folder/'profile/trace.json')['traceEvents'], func)
        names = [launch['name'] for launch in launches]
        assert names == item['actual_names'] and checked_dispatch == item['dispatch']
        kind = 'ordinary' if func == 'z2z_1d' else ('fused' if n in geometry else 'fallback')
        assert item['kind'] == kind and names
        if kind == 'fused':
            roles = (4, 5) if func == 'z2d_1d' else (6, 7)
            assert len(names) == 2 and item['C'] == geometry[n]['C'] and item['Q'] == geometry[n]['Q']
            assert all('_cc_local_v6_role%d_C%d_Q%d_'%(role, item['C'], item['Q']) in name
                       for role, name in zip(roles, names))
            if func == 'd2z_1d':
                assert '_reg' in names[1]
        else:
            assert all(not any(tag in name for tag in ('_cc_local_', '_local_real_rows',
                '_local_real_columns', '_paired_post_rows')) for name in names)
        rtc = folder/'metadata/rtc.txt'
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
            rtc.read_text() if rtc.exists() else '', re.M | re.S))
        for name, digest in item.get('source_sha256', {}).items():
            assert hashlib.sha256(sources[name].encode()).hexdigest() == digest
            source_count += 1
        errors.extend(float(v) for k, v in checked.items() if k.startswith('err_') and float(v) >= 0)
        rows.append(dict(N=n, type=func.removesuffix('_1d'), kind=kind, C=item.get('C', ''), Q=item.get('Q', ''),
            err_a=checked['err_a'], err_b=checked['err_b'], actual_names='; '.join(names)))
    assert len(validated['guards']) == 320 and len(validated['smoke_guards']) == 8
    guard_cases, guard_error, protected_arrays = 0, [], 0
    for smoke, groups in [(False, validated['guards']), (True, validated['smoke_guards'])]:
        for item in groups:
            n, func, mode = item['N'], item['func'], item['mode']
            folder = VALIDATE/'full-release'/('%sguard-%d-%s-%s'%('smoke-' if smoke else '', n, func, mode))
            actual = read(folder/'result.json')
            count = 4 if smoke else 12
            assert actual == item and actual['complete'] and actual['expected'] == actual['passed'] == count
            assert actual['returncode'] == 0 and actual['child_returncode'] in (0, None) and not actual['failures']
            output = (folder/'stdout.txt').read_text()
            lines = re.findall(r'^EVEN_CC_GUARD_PASS .*$', output, re.M)
            assert len(lines) == count and not re.search(r'^FULL_RELEASE_CASE_FAIL ', output, re.M)
            assert re.search(r'^FULL_RELEASE_GROUP_END cases=%d failures=0$'%count, output, re.M)
            for line in lines:
                assert 'rounds=2' in line and 'guards=1' in line
                value = float(re.search(r' error=([^ ]+)', line)[1])
                assert 0 <= value < 1e-9
                guard_error.append(value)
            refs = read(folder/'reference-manifest.json')
            assert refs['cases'] == count and all(not Path(x['path']).exists() for x in refs['files'])
            protected_arrays += len(refs['files'])
            if actual['profiled']:
                events = read(folder/'trace.json')['traceEvents']
                names = [event['name'] for event in events if event.get('cat') == 'HIPOPS'
                         and 'fft_rtc_' in event.get('name', '')]
                roles = (4, 5) if func == 'z2d_1d' else (6, 7)
                tags = ['_cc_local_v6_role%d_C%d_Q%d_'%(role, geometry[n]['C'], geometry[n]['Q']) for role in roles]
                assert len(names) == actual['actual_fft_launches'] == count*4
                assert all(any(tag in name for tag in tags) for name in names)
                assert all(any(tag in name for name in names) for tag in tags)
                assert actual['actual_path_passed'] and sorted(set(names)) == actual['actual_names']
            guard_cases += count
    assert guard_cases == 3872
    manifest, provenance, perf, samples = aggregate(MEASURE)
    stored = read(MEASURE/'summary.json')
    assert perf == stored['rows'] and len(perf) == 393
    assert len(samples) == 1179 and sum(map(len, samples.values())) == 35370
    assert manifest['arms']['candidate'] == arm
    plots = sorted((MEASURE/'plots').glob('*.svg'))
    assert len(plots) == 393
    annotated, grouped = [], []
    for row in perf:
        record = {k: v for k, v in row.items() if '_mean_' not in k}
        for reference in ('baseline', 'previous'):
            conclusion, shifts = classification(row, reference, samples)
            record[reference+'_distribution'] = conclusion
            record[reference+'_sequence_drift'] = shifts[0]
            record['candidate_sequence_drift'] = shifts[1]
        annotated.append(record)
    for func in ('z2d_1d', 'd2z_1d', 'z2z_1d'):
        selected = [row for row in annotated if row['func'] == func]
        for reference in ('baseline', 'previous'):
            ratios = [row['speedup_'+reference+'_median'] for row in selected]
            grouped.append(dict(type=func.removesuffix('_1d'), reference=reference, cases=len(selected),
                median_of_case_speedups=statistics.median(ratios), minimum=min(ratios), maximum=max(ratios),
                below_095=sum(x < 0.95 for x in ratios), above_105=sum(x > 1.05 for x in ratios),
                between_095_105=sum(0.95 <= x <= 1.05 for x in ratios),
                distribution_counts=dict(Counter(row[reference+'_distribution'] for row in selected))))
    for filename, data in [('逐项数值与实际路径.csv', rows), ('逐项性能与分布.csv', annotated), ('分类型性能汇总.csv', grouped)]:
        with (OUT/filename).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    (OUT/'raw-samples.json').write_text(json.dumps(dict(policy=manifest['policy'], gpu=provenance['gpu'],
        arms=manifest['arm_labels'], rows=[dict(N=row['N'], func=row['func'],
        samples={a: samples[row['N'], row['func'], a] for a in ('baseline', 'previous', 'candidate')})
        for row in annotated]), ensure_ascii=False, separators=(',', ':')))
    jobs = {}
    account = subprocess.check_output(['sacct', '-n', '-P', '-j', '1004430,1004431,1004433',
        '--format=JobID,State,ExitCode,Elapsed,NodeList'], cwd=ROOT, text=True)
    for line in account.splitlines():
        item = line.split('|')
        if item[0] in ('1004430', '1004431', '1004433'):
            jobs[item[0]] = dict(state=item[1], exit_code=item[2], elapsed=item[3], node=item[4])
    assert len(jobs) == 3 and all(x['state'] == 'COMPLETED' and x['exit_code'] == '0:0' for x in jobs.values())
    audit = dict(complete=True, jobs=jobs, numerical_actual_path_cases=401, source_hashes=source_count,
        maximum_basic_error=max(errors), main_guard_groups=320, main_guard_reference_cases=3840,
        smoke_groups=8, smoke_reference_cases=32, guard_reference_cases_rechecked=guard_cases,
        maximum_guard_error=max(guard_error), per_guard_execution_rounds=2,
        temporary_reference_arrays_cleaned=protected_arrays,
        performance_cases=393, performance_processes=1179, performance_samples=35370,
        raw_evidence_files_rehashed=1179*5, plots=393, policy=manifest['policy'],
        candidate=arm, validation_gpu=validated['gpu'], performance_gpu=provenance['gpu'],
        full_performance_single_gpu_all_versions=True, summary=grouped,
        distribution_rule='Use middle 50% separation; overlap or absolute first-ten/last-ten median drift >=5% is inconclusive. '
            'This is descriptive, not a confidence test. No samples removed.',
        formal_acceptance_complete=True, stable_promotion=False,
        evidence=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in
            [BUILD/'build-provenance.json', VALIDATE/'full-release-validation.json', VALIDATE/'post-build-validation.json',
             MEASURE/'provenance.json', MEASURE/'processes.json', MEASURE/'summary.json', MEASURE/'comparison.csv']])
    (OUT/'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    lines = ['# EXP129完整验收及性能核对', '',
        '构建1004430、完整验证1004431、性能1004433全部正常完成。', '',
        f'401项基础数值与实际路径全部通过，最大误差{max(errors):.15e}。320组扩展检查、3840个参考用例全部通过；'
        f'另有8组32个冒烟用例。每例执行两轮，覆盖内存保护、四种回调模式、端点／中点、四种缩放。最大参考误差{max(guard_error):.15e}。', '',
        '正式性能393个尺寸／类型组合、三版1179进程、35370个样本均完整，同一独占显卡、原始10／30计时，'
        '已重读原始39列数据、独立校验和未舍入样本，重新核对全部汇总。EXP125是保留对照；上一版是清理前EXP129。', '',
        '| 类型 | 对照 | 组合数 | 各组合加速比的中位数 | 低于0.95 | 高于1.05 |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    for row in grouped:
        lines.append('| %s | %s | %d | %.6f | %d | %d |'%(row['type'],
            'EXP125保留版' if row['reference']=='baseline' else '清理前EXP129', row['cases'],
            row['median_of_case_speedups'], row['below_095'], row['above_105']))
    lines += ['', '上表为逐组合中位数比值再取中位数，不表示所有尺寸都同幅度变化。分布重叠或序列前后十次中位数相差至少5%时标注差异不明确；'
        '这是描述性标记，不是置信度检验。全部慢点保留。逐项耗时、比值、四分位区间与漂移见逐项性能与分布.csv；'
        '原始散点与顺序图保留在正式运行目录的plots/。', '',
        '本次清理与缩放修正不新增性能优化。2264份单位缩放CC生成代码此前已逐字对照；'
        '剩余相对EXP125的退化不在本轮继续修改，原始证据与差异保留。', '',
        '计算源码：'+arm['source_commit']+'；库校验值：'+arm['library_sha256']+'。',
        '安装：'+arm['install']+'。', '',
        '验收已完成；稳定晋升状态以同实验stable-promotion-20261031/中的发布记录为准。']
    (OUT/'结果核对.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k: v for k, v in audit.items() if k not in ('candidate', 'evidence')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
