"""Submit EXP129 build, independent validation and dependent performance; stop."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

RECORD = ROOT / 'experiments/EXP-129/records/tasks-20261029'
CONFIGS = ROOT / 'configs/experiments'
PREFIX = 'EXP-129-gate-simplification'
DATE = '20261029'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def commit(paths, message):
    names = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git', 'add', '--', *names], cwd=ROOT, check=True)
    pending = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--', *names],
                                      cwd=ROOT, text=True).strip()
    if pending:
        subprocess.run(['git', 'commit', '--only', '-m', message, '--', *names], cwd=ROOT,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main():
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    mgr.require(branch == 'exp-129-gate-simplification', 'wrong experiment branch')
    receipt_path = RECORD / 'submission.json'
    previous = read(receipt_path) if receipt_path.exists() else {}
    receipts = previous.get('receipts', {})
    previews_path = RECORD / 'submission-previews.json'
    previews = read(previews_path) if previews_path.exists() else {}

    def submit(task, config, name):
        if name in receipts:
            return receipts[name]
        command = [mgr.PYTHON, str(ROOT / 'manage.py'), task, '--config', str(config)]
        previews[name] = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
        write(previews_path, previews)
        result = json.loads(subprocess.check_output(command + ['--execute'], cwd=ROOT, text=True))
        receipts[name] = result
        write(receipt_path, dict(receipts=receipts, reference_installs_rebuilt=False,
                                source_state_freeze=False,
                                result_inspection='not performed; stop after submission'))
        print('SUBMITTED', name, result['job'], flush=True)
        return result

    bp = CONFIGS / (PREFIX + '-build-' + DATE + '.json')
    vp = CONFIGS / (PREFIX + '-validate-' + DATE + '.json')
    mp = CONFIGS / (PREFIX + '-performance-' + DATE + '.json')
    qp = CONFIGS / (PREFIX + '-queue-' + DATE + '.json')
    built = submit('build', bp, 'build')
    build_job = built['job'].split(';')[0]
    manifest = Path(built['run']) / 'submit-manifest.json'
    if 'validation' not in receipts:
        validation = read(vp)
        validation['build'] = read(manifest)['build']
        validation['resources']['dependency'] = 'afterok:' + build_job
        validation['pending_build_validation'] = dict(
            build_config=str(manifest), build_config_sha256=mgr.common.sha(manifest),
            build_job_id=build_job)
        write(vp, validation)
        commit([vp], 'EXP129: record submitted build dependency for independent validation')
    checked = submit('validate', vp, 'validation')
    validation_job = checked['job'].split(';')[0]
    measurement = read(mp)
    if 'performance' not in receipts:
        queue = dict(schema_version=1, experiment='EXP-129',
                     run_id=PREFIX + '-queue-' + DATE, gpu_arch='gfx936',
                     resources=dict(measurement['resources'], dependency='afterok:' + validation_job),
                     revalidated_measurement=dict(
                         validation_config=str(Path(checked['run']) / 'submit-manifest.json'),
                         validation_job_id=validation_job, measurement_config=str(mp),
                         measurement_config_sha256=mgr.common.sha(mp)))
        write(qp, queue)
        commit([qp], 'EXP129: record successful-validation dependency for performance')
    submit('measure', qp, 'performance')
    registration = read(RECORD / 'registration.json')
    registration.update(submission='submitted', job_ids={
        name: item['job'].split(';')[0] for name, item in receipts.items()})
    write(RECORD / 'registration.json', registration)
    block = ('\n\n### EXP129：构建、数值/实际路径验证与性能任务提交（2026-10-29）\n\n'
             + '实现c4de21bc；构建' + registration['job_ids']['build']
             + '，独立验证' + registration['job_ids']['validation']
             + '（afterok构建），性能' + registration['job_ids']['performance']
             + '（afterok验证）。先75000/133100双方向冒烟，后覆盖实数代表类型及五个默认普通复数尺寸，共67项数值/实际派发检查；冒烟失败立即返回，后续独立错误全部汇总。\n\n'
             + '默认15用例全部保留，性能393组合、EXP125固定基线/V6/EXP129三版同一独占单卡相邻交替，1179进程/35370正式样本；10/30，仅用中位数。复用两份已验参考，不重建、不冻结源码，不在窗口中混入profiling。注册与回执见experiments/EXP-129/records/tasks-20261029/。主机9项验证流程与1132份行源码解析通过；提交后停止，尚无本轮构建、数值或性能完成结论，不晋升稳定版。\n')
    log = ROOT / 'VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md'
    if block not in log.read_text():
        with log.open('a') as stream:
            stream.write(block)
    commit([vp, qp, previews_path, receipt_path, RECORD / 'registration.json', log],
           'EXP129: record build validation and performance submissions')
    print(json.dumps(dict(job_ids=registration['job_ids'], validation_cases=67,
                          measurement_cases=393, processes=1179, samples=35370,
                          result_inspection='not performed; stop after submission'),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
