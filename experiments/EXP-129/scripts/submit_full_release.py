"""Submit full release acceptance and dependent timing; wait for the user afterwards."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts')]
from tools.workspace_manager import manager as mgr
from submit_gate_simplification import read, write, commit

RECORD = ROOT/'experiments/EXP-129/records/stable-release-20261030'
CONFIGS = ROOT/'configs/experiments'


def main():
    receipts_file = RECORD/'submission.json'
    previews_file = RECORD/'submission-previews.json'
    receipts = read(receipts_file).get('receipts', {}) if receipts_file.exists() else {}
    previews = read(previews_file) if previews_file.exists() else {}

    def submit(task, config, name):
        if name not in receipts:
            command = [mgr.PYTHON, str(ROOT/'manage.py'), task, '--config', str(config)]
            previews[name] = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
            write(previews_file, previews)
            receipts[name] = json.loads(subprocess.check_output(command+['--execute'], cwd=ROOT, text=True))
            write(receipts_file, dict(receipts=receipts, rebuilt=False,
                automation=False, inspection='not performed; await user request'))
            print('SUBMITTED', name, receipts[name]['job'], flush=True)
        return receipts[name]

    validation_config = CONFIGS/'EXP-129-stable-release-full-validate-20261030.json'
    measured = CONFIGS/'EXP-129-stable-release-performance-20261030.json'
    queue_path = CONFIGS/'EXP-129-stable-release-performance-queue-20261030.json'
    validation = submit('validate', validation_config, 'full_validation')
    job = validation['job'].split(';')[0]
    if 'performance' not in receipts:
        measurement = read(measured)
        queue = dict(schema_version=1, experiment='EXP-129',
            run_id='EXP-129-stable-release-performance-queue-20261030', gpu_arch='gfx936',
            resources=dict(measurement['resources'], dependency='afterok:'+job),
            revalidated_measurement=dict(
                validation_config=str(Path(validation['run'])/'submit-manifest.json'),
                validation_job_id=job, measurement_config=str(measured),
                measurement_config_sha256=mgr.common.sha(measured)))
        write(queue_path, queue)
        commit([queue_path], 'EXP129: require full release validation before formal performance')
    performance = submit('measure', queue_path, 'performance')
    summary = dict(full_validation_job=job, performance_job=performance['job'].split(';')[0],
        numerical_path_cases=401, main_guard_groups=320, guard_reference_cases=3840,
        callback_guard_sizes=39, performance_cases=393, performance_processes=1179,
        performance_samples=35370, automation=False, references_rebuilt=False,
        current_install='experiments/EXP-129/artifacts/install/EXP-129-legacy-retirement-20261029',
        user_approved_server_and_cloud_promotion=True,
        inspection='not performed; await user request')
    write(RECORD/'submission-summary.json', summary)
    log = ROOT/'VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md'
    block = ('\n\n### EXP129：稳定发布前完整验证任务提交（2026-10-30）\n\n'
        '复用清理后安装，完整验证'+job+'，正式性能'+summary['performance_job']
        +'（显式afterok完整验证）。401项数值／实际路径，39个代表尺寸的实数／复数回调、'
        '独占计数、输入输出及工作区保护、端点与中点、四种缩放；加范围外边界共320组3840个参考用例。'
        '默认15例保留，194个实数N双向覆盖。性能393组合、三版本1179进程35370样本，原始10／30、中位数。'
        '用户已取消定时检查，提交后等待用户检查；完整验收通过后才晋升服务器并推送云端。'
        '记录：experiments/EXP-129/records/stable-release-20261030/。\n')
    if block not in log.read_text():
        with log.open('a') as stream:
            stream.write(block)
    commit([queue_path, receipts_file, previews_file, RECORD/'submission-summary.json', log],
           'EXP129: record full release validation and dependent performance submissions')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
