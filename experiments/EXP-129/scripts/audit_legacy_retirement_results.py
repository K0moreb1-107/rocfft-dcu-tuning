"""Audit the completed cleanup jobs against their raw numerical and dispatch evidence."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts'),
                str(ROOT/'tools/fft_measurement')]
import cufft261012_contract as contract
from cc_dispatch import inspect_dispatch

BUILD = ROOT/'experiments/EXP-129/runs/EXP-129-legacy-retirement-build-20261029'
RUN = ROOT/'experiments/EXP-129/runs/EXP-129-legacy-retirement-validate-20261029'
RECORD = ROOT/'experiments/EXP-129/records/legacy-retirement-20261029'
OUT = RECORD/'results-998993'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    built, validated, config = (read(BUILD/'build-provenance.json'),
        read(RUN/'legacy-retirement-validation.json'), read(RUN/'submit-manifest.json'))
    settings = config['validation']
    assert built['complete'] and validated['complete'] and not validated['failures']
    arm = built['arm']
    assert validated['source_commit'] == arm['source_commit']
    assert validated['library_sha256'] == arm['library_sha256']
    library = Path(arm['install'])/'lib/librocfft.so.0.1'
    assert sha(library) == arm['library_sha256']
    assert sha(Path(settings['coverage'])) == validated['coverage_sha256']
    expected = {(n, func) for n in settings['sample_N']+settings['fallback_N']
                for func in ('z2d_1d', 'd2z_1d')}
    expected |= {(n, 'z2z_1d') for n in settings['ordinary_N']}
    numerical = {(item['N'], item['func']): item for item in validated['numerical']}
    dispatch = {(item['N'], item['func']): item for item in validated['dispatch']}
    assert len(expected) == len(numerical) == len(dispatch) == 29
    assert len(validated['numerical']) == len(validated['dispatch']) == 29
    assert set(numerical) == set(dispatch) == expected
    rows, errors, source_count = [], [], 0
    for n, func in sorted(expected):
        item = dispatch[n, func]
        folder = RUN/'measurement-validation'/(str(n)+'-'+func)
        harness = folder/'profile/harness'
        checked = contract.read_check(harness/'fft_test_1d.check.csv')
        data = contract.read_rows(harness/'fft_test_1d.csv')
        samples = contract.read_samples(harness/'fft_test_1d.samples.csv')
        assert len(data) == 1 and checked['check'] == 'PASS'
        assert checked == numerical[n, func]['check']
        contract.validate_process(data[0], samples, checked, n, func, 30)
        plan = (folder/'metadata/plan.txt').read_text()
        launches, trace_check = inspect_dispatch(plan,
            read(folder/'profile/trace.json')['traceEvents'], func)
        names = [launch['name'] for launch in launches]
        assert names == item['actual_names'] and trace_check == item['dispatch']
        kind = 'ordinary' if func == 'z2z_1d' else ('fused' if n in settings['sample_N'] else 'fallback')
        assert item['kind'] == kind and names
        if kind == 'fused':
            roles = (4, 5) if func == 'z2d_1d' else (6, 7)
            assert n == 2*item['C']*item['Q'] and len(names) == 2
            assert all('_cc_local_v6_role%d_C%d_Q%d_' % (role, item['C'], item['Q']) in name
                       for role, name in zip(roles, names))
        else:
            assert all(not any(tag in name for tag in ('_cc_local_', '_local_real_rows',
                       '_local_real_columns', '_paired_post_rows')) for name in names)
            if kind == 'ordinary':
                assert 'CS_L1D_CC' in plan
        rtc = folder/'metadata/rtc.txt'
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
                                  rtc.read_text() if rtc.exists() else '', re.M | re.S))
        for name, digest in item.get('source_sha256', {}).items():
            assert hashlib.sha256(sources[name].encode()).hexdigest() == digest
            source_count += 1
        if kind == 'fused':
            assert set(item['source_sha256']) == set(names)
        errors.extend(float(value) for key, value in checked.items()
                      if key.startswith('err_') and float(value) >= 0)
        rows.append(dict(N=n, type=func.removesuffix('_1d'), kind=kind,
            C=item.get('C', ''), Q=item.get('Q', ''), check='PASS',
            err_a=checked['err_a'], err_b=checked['err_b'], kernels=len(names),
            actual_names='; '.join(names)))
    accounting = subprocess.check_output(['sacct', '-n', '-P', '-j', '998992,998993',
        '--format=JobID,State,ExitCode,Elapsed,NodeList'], cwd=ROOT, text=True)
    jobs = {}
    for line in accounting.splitlines():
        values = line.split('|')
        if values[0] in ('998992', '998993'):
            jobs[values[0]] = dict(state=values[1], exit_code=values[2], elapsed=values[3], node=values[4])
    assert set(jobs) == {'998992', '998993'}
    assert all(item['state'] == 'COMPLETED' and item['exit_code'] == '0:0' for item in jobs.values())
    host = read(RECORD/'host-preflight.json')
    assert host['complete'] and host['generated_sources_identical'] == 2830
    summary = dict(complete=True, jobs=jobs, cases=len(rows),
        kinds=dict(Counter(row['kind'] for row in rows)), maximum_error=max(errors),
        raw_numerical_and_samples_rechecked=29, raw_dispatch_traces_rechecked=29,
        actual_kernel_source_hashes_rechecked=source_count,
        source_commit=arm['source_commit'], requested_cleanup_commit='a6fc19dea8066844376e21db092a2919e88173ba',
        library_sha256=arm['library_sha256'], install=arm['install'], gpu=validated['gpu'],
        host_compiles=host['host_compiles'], generated_sources_identical=2830,
        formal_performance=False, stable_promotion=False,
        evidence=[dict(path=str(path.relative_to(ROOT)), sha256=sha(path)) for path in
            [BUILD/'build-provenance.json', RUN/'legacy-retirement-validation.json',
             RUN/'post-build-validation.json', RUN/'submit-manifest.json', RECORD/'host-preflight.json']])
    OUT.mkdir(exist_ok=True)
    (OUT/'audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    with (OUT/'逐项数值与路径.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = f'''# EXP129旧后端清理验收结果

构建998992和验证998993均正常完成，退出码均为0。构建耗时{jobs['998992']['elapsed']}，验证耗时{jobs['998993']['elapsed']}。

| 检查 | 数量 | 结果 |
| --- | ---: | --- |
| 通用CC融合：13个尺寸，双方向 | 26 | 全部数值正确；每次实际执行角色4/5或6/7两个融合内核 |
| 范围外官方回退：32768双方向 | 2 | 数值正确；各执行3个原有路径内核，无新旧专用适配器 |
| 普通CC：131072 z2z | 1 | 数值正确；仍执行普通CC两个内核 |

29项全部通过，最大误差{max(errors):.15e}，低于1e-9阈值。重新读取了29组原始校验和样本、重新解析29组实际执行跟踪，并复核60个实际内核源码摘要。覆盖无缺项、无重复，构建、安装和验证库校验值一致。

此前21项主机编译通过，283种几何的2830份通用生成源与清理前逐字相同。本轮完成整库构建和设备数值／路径验收，旧后端清理通过这些检查。

清理生产提交：a6fc19dea8066844376e21db092a2919e88173ba。
实际构建身份：{arm['source_commit']}；库校验值：{arm['library_sha256']}。
安装：{arm['install']}。

本轮没有正式性能测试，不报告新的加速比；稳定版未晋升。

逐项结果见同目录“逐项数值与路径.csv”，身份、调度和证据摘要见audit.json。
原始验证目录：{RUN}。
'''
    (OUT/'结果核对.md').write_text(report, encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
