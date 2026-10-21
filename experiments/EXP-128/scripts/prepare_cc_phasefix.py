"""Record the boundary phase-table repair and prepare a separate candidate retry."""
import copy
import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
RECORD = ROOT/'experiments/EXP-128/records/phasefix-20261022'
CONFIGS = ROOT/'configs/experiments'
PREFIX = 'EXP-128-cc-local-phasefix'
DATE = '20261022'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def commit(files, message):
    paths = [str(path.relative_to(ROOT)) for path in files]
    subprocess.run(['git', 'add', '--', *paths], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '--only', '-m', message, '--', *paths], cwd=ROOT,
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def main():
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT,
                                   text=True).strip() == 'exp-128-cc-local-real'
    proof = read(RECORD/'phase-table-preflight.json')
    assert proof['complete'] and proof['generated_rows'] == 283
    old_run = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-unified-validate-20261021'
    check_path = old_run/'measurement-validation/65536-d2z_1d/profile/harness/fft_test_1d.check.csv'
    check = list(csv.DictReader(check_path.open()))[0]
    assert check['check'] == 'FAIL' and check['err_a'] == '1'
    write(RECORD/'diagnosis.json', dict(failed_jobs=dict(build='955131', validation='955132', performance='955133'),
        numerical=check, evidence=str(check_path), profiler_child_returncode=2,
        root_cause='Forward boundary lookup read three base-8 segments from a two-segment N=65536 table.',
        masked_error='hipprof returned zero after child exit 2; missing timing CSV hid the failed numerical row.',
        fix='Use the same ceil(ceil(log2(N))/8) rule as TwiddleTableLarge; report correctness before timings.',
        host_coverage=proof['generated_rows'], device_acceptance='pending',
        reference_installs_rebuilt=False, source_state_freeze=False))
    note = '''65536点正变换失败修正

构建955131成功；验证955132在65536点d2z校验失败，相对误差为1；z2d已通过。性能队列955133因依赖失败取消，尚无性能数据。

根因是边界相位表与读取段数不一致。相位表按实数长度N生成，每段256个复数，段数为ceil(ceil(log2(N))/8)。65536只分配512个复数，原代码固定读三段，第三段首地址512已经越界。此前入口排除65536，新增包含边界后才触发。

修正为使用与相位表分配完全相同的段数公式，不按尺寸写特例。已重新生成覆盖清单中全部283种行内核，194个公开尺寸中只有65536需要由三段改为两段，其余保持三段。寄存器直读和通用二次幂接入保留；设备正确性仍待重新验证。

验证脚本同时修正错误报告：先读独立正确性表，再读计时文件；保留分析器报告的子进程退出码，避免校验失败被误报为文件缺失。五项主机测试通过，含新增的两项错误报告测试。

只重建候选，复用EXP125及此前EXP128参考安装。新构建、验证、三版性能分别登记，显式成功依赖。旧日志和失败安装保留，不晋升稳定版本，不推送。
'''
    (RECORD/'修正说明.md').write_text(note)
    files = [ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/rtc_stockham_gen.cpp']
    files += [ROOT/'experiments/EXP-128/scripts'/name for name in
        ('validate_cc_local_unified.py', 'test_cc_unified_validation.py', 'submit_cc_unified.py',
         'preflight_cc_phasefix.py', 'prepare_cc_phasefix.py')]
    files += [RECORD/name for name in ('diagnosis.json', 'phase-table-preflight.json', '修正说明.md')]
    source_commit = commit(files, 'Fix CC boundary phase lookup segments to match allocated tables')
    build = read(CONFIGS/'EXP-128-cc-local-unified-build-20261021.json')
    build.update(run_id=PREFIX+'-build-'+DATE)
    build['build'].update(build_id=PREFIX+'-'+DATE, source_commit=source_commit)
    build_record = ROOT/'experiments/EXP-128/runs'/build['run_id']/'build-provenance.json'
    validation = read(old_run/'submit-manifest.json')
    validation['run_id'] = PREFIX+'-validate-'+DATE
    validation['build'] = copy.deepcopy(build['build'])
    validation.pop('pending_build_validation', None)
    validation['resources'].pop('dependency', None)
    validation['existing_build_validation']['build_record'] = str(build_record)
    script = ROOT/validation['post_build_validation']['script']
    validation['post_build_validation']['sha256'] = hashlib.sha256(script.read_bytes()).hexdigest()
    measure = read(CONFIGS/'EXP-128-cc-local-unified-performance-20261021.json')
    measure['run_id'] = PREFIX+'-performance-'+DATE
    measure['arms']['candidate'] = dict(build_record=str(build_record))
    paths = []
    for kind, cfg in [('build', build), ('validate', validation), ('performance', measure)]:
        path = CONFIGS/(PREFIX+'-'+kind+'-'+DATE+'.json')
        assert not path.exists(), path
        write(path, cfg)
        paths.append(path)
    write(RECORD/'retry-plan.json', dict(source_commit=source_commit, predecessor_validation='955132',
        series='phasefix-20261022', build_record=str(build_record), cases=len(measure['cases']),
        reference_arms={key:value for key,value in measure['arms'].items() if key != 'candidate'},
        auto_check_minutes=20))
    paths.append(RECORD/'retry-plan.json')
    commit(paths, 'Register EXP128 phase-table repair validation and three-version timing')
    print(json.dumps(dict(source_commit=source_commit, configs=list(map(str, paths[:3])),
                         cases=len(measure['cases']), prior_installs_rebuilt=False)))


if __name__ == '__main__':
    main()
