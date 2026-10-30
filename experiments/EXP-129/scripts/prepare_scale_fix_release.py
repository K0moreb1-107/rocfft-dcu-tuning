"""Record the complete failed release audit and register the generic repairs."""
from collections import Counter
from pathlib import Path
import copy
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts')]
from submit_gate_simplification import read, write, commit

RECORD = ROOT/'experiments/EXP-129/records/stable-scale-fix-20261030'
OLD = ROOT/'experiments/EXP-129/runs/EXP-129-stable-release-full-validate-20261030'
CONFIGS = ROOT/'configs/experiments'
PREFIX = 'EXP-129-stable-scale-fix'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert read(RECORD/'host-preflight.json')['complete']
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT,
        text=True).strip() == 'exp-129-gate-simplification'
    old = read(OLD/'full-release-validation.json')
    assert len(old['numerical']) == len(old['dispatch']) == 401
    assert all(item['check']['check'] == 'PASS' for item in old['numerical'])
    failed = []
    for item in old['failures']:
        mode = item['stage'].split('/')[-1]
        folder = OLD/'full-release'/('guard-'+str(item['N'])+'-'+item['func']+'-'+mode)
        rtc, stderr = folder/'rtc.txt', folder/'stderr.txt'
        text = rtc.read_text(errors='replace')+stderr.read_text(errors='replace')
        diagnostics = re.findall(r'^.*error: ([^\n]+)', text, re.M)
        if any('redefinition of parameter' in line for line in diagnostics):
            root = 'duplicate_bluestein_scale_parameter'
        elif any('expected' in line and 'after expression' in line for line in diagnostics):
            root = 'untyped_complex_initializer_in_scaled_store'
        else:
            root = 'unclassified'
        entry = dict(N=item['N'], func=item['func'], mode=mode, root=root,
            reporting_error=item['error'], evidence=str(folder.relative_to(ROOT)),
            rtc_sha256=sha(rtc), compiler_errors=dict(Counter(diagnostics)))
        if item['error'] == 'UnicodeDecodeError':
            trace = folder/'trace.json'
            entry['trace_sha256'] = sha(trace)
            try:
                trace.read_bytes().decode('utf8')
            except UnicodeDecodeError as error:
                entry['invalid_utf8_offset'] = error.start
        failed.append(entry)
    assert len(failed) == 70 and all(item['root'] != 'unclassified' for item in failed)
    groups = Counter((item['func'], item['complete']) for item in old['guards'])
    audit = dict(validation_job='1001788', cancelled_performance_job='1001789',
        full_validation_complete=False, elapsed_seconds=old['elapsed_seconds'],
        numerical_and_actual_paths_passed=401, guard_groups_attempted=320,
        guard_group_records=314, guard_groups_passed=250,
        d2z_guard_groups_passed=groups[('d2z_1d', True)],
        z2d_guard_groups_passed=groups[('z2d_1d', True)],
        failures=len(failed), root_counts=dict(Counter(item['root'] for item in failed)),
        failed_sizes=sorted({item['N'] for item in failed}),
        full_evidence=str((OLD/'full-release-validation.json').relative_to(ROOT)),
        full_evidence_sha256=sha(OLD/'full-release-validation.json'),
        failed_groups=failed, promotion_performed=False,
        changes='Type complex literals before scaling; let common store ops own the Bluestein scale argument; '
                'retain execution failure before decoding compiler traces; smoke all four scales.')
    write(RECORD/'failure-audit-1001788.json', audit)
    (RECORD/'README.md').write_text('''# 稳定发布完整验证修正

原验证1001788运行75分16秒后失败，性能1001789因依赖失败取消。401项基础数值和实际路径全部通过；320组扩展检查均已尝试，250组通过，70组失败。d2z的160组全部通过。完整原始证据留在原运行目录。

## 根因与修正

- 17个融合尺寸的非单位缩放：复数初始化列表直接参加缩放乘法，生成代码无法编译。公共存储生成器先赋予复数类型再乘缩放系数，覆盖全部同类写出。
- 65534、65538的卷积回退：内核手工添加缩放参数，共用存储操作又追加一次。删除手工声明，由共用操作统一生成，与参数打包逻辑一致。
- 六处跟踪文件含无效编码，均伴随上述编译失败。验证先保留程序退出码和用例失败，仅在执行成功后解析实际路径；不把坏记录解码成成功。
- 两个代表尺寸的冒烟阶段改为同时检查1、0.5、-1、0四种缩放；主矩阵与数值误差要求保留。

源码仅修改两份公共生成文件，增加三行、删除两行，不添加尺寸例外。2264份单位缩放CC生成代码与已保留版本逐字相同；2264份生成检查包含1132份带缩放行端代码；192项卷积参数组合通过；48份代表设备源码语法编译通过。四项验证脚本回归检查通过。以上是主机检查，设备完整验收仍待新任务。

## 重新提交

新构建、完整验证、正式性能分别提交并显式依赖前一阶段成功；性能仍为393组合、三版本1179进程35370样本，原始10／30，中位数。复用EXP125保留版及清理前EXP129参考库。完整验收通过前不晋升稳定分支、不创建稳定标签、不推送云端。

失败分类、证据路径与摘要见failure-audit-1001788.json；主机检查见host-preflight.json；新任务号见submission-summary.json。用户已取消自动检查；提交后停止，等待用户检查。
''')
    source = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src'
    scripts = ROOT/'experiments/EXP-129/scripts'
    paths = [source/'load_store_ops_gen.cpp', source/'rtc_bluestein_gen.cpp',
        *(scripts/name for name in ['validate_full_release_scale_fix.py', 'generate_scale_regression.cpp',
            'preflight_scale_fix.py', 'prepare_scale_fix_release.py', 'submit_scale_fix_release.py']),
        *(RECORD/name for name in ['scale-generation.patch', 'host-preflight.json',
            'validation-host-tests.json', 'failure-audit-1001788.json', 'README.md'])]
    commit(paths, 'EXP129: repair scaled complex stores and fallback kernel signatures')
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    build = read(CONFIGS/'EXP-129-legacy-retirement-build-20261029.json')
    build['run_id'] = PREFIX+'-build-20261030'
    build['build']['build_id'] = PREFIX+'-20261030'
    build['build']['source_commit'] = source_commit
    build['acceptance'] = 'Compile the general scaling fixes; independent complete release validation follows.'
    build['reference_policy'] = 'Reuse EXP125 and pre-cleanup EXP129 references; do not rebuild them.'
    validation = read(CONFIGS/'EXP-129-stable-release-full-validate-20261030.json')
    validation['run_id'] = PREFIX+'-validate-20261030'
    validation['build'] = copy.deepcopy(build['build'])
    hook = validation['post_build_validation']
    hook['script'] = str(scripts/'validate_full_release_scale_fix.py')
    hook['sha256'] = sha(scripts/'validate_full_release_scale_fix.py')
    validation['existing_build_validation']['build_record'] = str(ROOT/'experiments/EXP-129/runs'/
        build['run_id']/'build-provenance.json')
    validation['reference_policy'] = 'Fresh full acceptance of the corrected build; no reuse of partial passes.'
    measurement = read(CONFIGS/'EXP-129-stable-release-performance-20261030.json')
    measurement['run_id'] = PREFIX+'-performance-20261030'
    measurement['arms']['candidate'] = dict(build_record=validation['existing_build_validation']['build_record'])
    previous_record = ROOT/'experiments/EXP-129/runs/EXP-129-gate-simplification-build-20261029/build-provenance.json'
    measurement['arms']['previous'] = read(previous_record)['arm']
    measurement['arm_labels']['candidate'] = 'EXP129旧后端清理及缩放修正候选'
    measurement['measurement_conditions']['reference'] = 'Retained EXP125 baseline, pre-cleanup EXP129, '
    measurement['measurement_conditions']['reference'] += 'cleaned EXP129 with generic scaling fixes; 393 cases, 1179 processes, 35370 samples.'
    outputs = [(PREFIX+'-build-20261030.json', build), (PREFIX+'-validate-20261030.json', validation),
               (PREFIX+'-performance-20261030.json', measurement)]
    for name, value in outputs:
        write(CONFIGS/name, value)
    write(RECORD/'repair-source.json', dict(source_commit=source_commit,
        production_files=['load_store_ops_gen.cpp', 'rtc_bluestein_gen.cpp'],
        previous_build_commit='48d6c750669c96cbdc17acc4e3443da8ab95b344',
        no_dimension_special_cases=True, formal_performance_not_run=True))
    commit([*(CONFIGS/name for name, _ in outputs), RECORD/'repair-source.json'],
        'EXP129: register corrected stable release build validation and formal timing')
    print(json.dumps(dict(source_commit=source_commit, failed_groups=len(failed),
        root_counts=audit['root_counts'], d2z_groups_passed=audit['d2z_guard_groups_passed'],
        configs=[name for name, _ in outputs]), ensure_ascii=False))


if __name__ == '__main__':
    main()
