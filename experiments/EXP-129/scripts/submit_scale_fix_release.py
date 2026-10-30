"""Submit the corrected build, full release acceptance and dependent timing; then stop."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts')]
from tools.workspace_manager import manager as mgr
from submit_gate_simplification import read, write, commit

RECORD = ROOT/'experiments/EXP-129/records/stable-scale-fix-20261030'
CONFIGS = ROOT/'configs/experiments'
PREFIX = 'EXP-129-stable-scale-fix'
DATE = '20261030'


def main():
    assert read(RECORD/'host-preflight.json')['complete']
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT,
        text=True).strip() == 'exp-129-gate-simplification'
    receipts_file, previews_file = RECORD/'submission.json', RECORD/'submission-previews.json'
    receipts = read(receipts_file).get('receipts', {}) if receipts_file.exists() else {}
    previews = read(previews_file) if previews_file.exists() else {}

    def submit(task, config, name):
        if name not in receipts:
            command = [mgr.PYTHON, str(ROOT/'manage.py'), task, '--config', str(config)]
            previews[name] = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
            write(previews_file, previews)
            receipts[name] = json.loads(subprocess.check_output(command+['--execute'], cwd=ROOT, text=True))
            write(receipts_file, dict(receipts=receipts, reference_installs_rebuilt=False,
                automation=False, inspection='not performed; await user request'))
            print('SUBMITTED', name, receipts[name]['job'], flush=True)
        return receipts[name]

    bp = CONFIGS/(PREFIX+'-build-'+DATE+'.json')
    vp = CONFIGS/(PREFIX+'-validate-'+DATE+'.json')
    mp = CONFIGS/(PREFIX+'-performance-'+DATE+'.json')
    qp = CONFIGS/(PREFIX+'-queue-'+DATE+'.json')
    built = submit('build', bp, 'build')
    build_job = built['job'].split(';')[0]
    manifest = Path(built['run'])/'submit-manifest.json'
    if 'full_validation' not in receipts:
        validation = read(vp)
        validation['build'] = read(manifest)['build']
        validation['resources']['dependency'] = 'afterok:'+build_job
        validation['pending_build_validation'] = dict(build_config=str(manifest),
            build_config_sha256=mgr.common.sha(manifest), build_job_id=build_job)
        write(vp, validation)
        commit([vp], 'EXP129: require corrected build before full release acceptance')
    checked = submit('validate', vp, 'full_validation')
    validation_job = checked['job'].split(';')[0]
    if 'performance' not in receipts:
        measurement = read(mp)
        queue = dict(schema_version=1, experiment='EXP-129',
            run_id=PREFIX+'-queue-'+DATE, gpu_arch='gfx936',
            resources=dict(measurement['resources'], dependency='afterok:'+validation_job),
            revalidated_measurement=dict(
                validation_config=str(Path(checked['run'])/'submit-manifest.json'),
                validation_job_id=validation_job, measurement_config=str(mp),
                measurement_config_sha256=mgr.common.sha(mp)))
        write(qp, queue)
        commit([qp], 'EXP129: require corrected full release acceptance before timing')
    performance = submit('measure', qp, 'performance')
    summary = dict(build_job=build_job, full_validation_job=validation_job,
        performance_job=performance['job'].split(';')[0], previous_failed_validation='1001788',
        previous_cancelled_performance='1001789', numerical_path_cases=401,
        main_guard_groups=320, guard_reference_cases=3840, smoke_groups=8, smoke_reference_cases=32,
        performance_cases=393, performance_processes=1179, performance_samples=35370,
        automation=False, references_rebuilt=False, user_approved_server_and_cloud_promotion=True,
        inspection='not performed; await user request')
    write(RECORD/'submission-summary.json', summary)
    log = ROOT/'VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md'
    block = ('\n\n### EXP129：稳定发布完整验收缩放修正（2026-10-30）\n\n'
        '原验证1001788已跑完：401项基础数值／路径通过，320组扩展检查全部尝试，'
        'z2d非单位缩放存在两类生成编译错误：复数列表缺少类型、卷积回退重复缩放参数；'
        '六条无效跟踪编码随编译失败出现，改为优先保留执行错误。通用修正两处生成代码，'
        '不添加尺寸特例；两尺寸冒烟加入四种缩放。修正构建'+build_job+'，完整验证'+validation_job
        +'，依赖成功后的三版性能'+summary['performance_job']+'。复用EXP125和清理前EXP129参考安装。'
        '记录：experiments/EXP-129/records/stable-scale-fix-20261030/。提交后停止，等待用户检查，'
        '无定时任务；验收通过前不更新稳定分支、标签或云端。\n')
    if block not in log.read_text():
        with log.open('a') as stream:
            stream.write(block)
    commit([bp, vp, qp, receipts_file, previews_file, RECORD/'submission-summary.json', log],
        'EXP129: record corrected stable release acceptance and timing submissions')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
