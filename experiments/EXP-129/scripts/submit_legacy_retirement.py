"""Submit the cleanup build and dependent numerical/path validation, then stop."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts')]
from tools.workspace_manager import manager as mgr
from submit_gate_simplification import read, write, commit

RECORD = ROOT/'experiments/EXP-129/records/legacy-retirement-20261029'
PREFIX = 'EXP-129-legacy-retirement'
CONFIGS = ROOT/'configs/experiments'


def main():
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    mgr.require(branch == 'exp-129-gate-simplification', 'wrong experiment branch')
    receipt_path, previews_path = RECORD/'submission.json', RECORD/'submission-previews.json'
    receipts = read(receipt_path).get('receipts', {}) if receipt_path.exists() else {}
    previews = read(previews_path) if previews_path.exists() else {}

    def submit(task, path, name):
        if name not in receipts:
            command = [mgr.PYTHON, str(ROOT/'manage.py'), task, '--config', str(path)]
            previews[name] = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
            write(previews_path, previews)
            receipts[name] = json.loads(subprocess.check_output(command+['--execute'], cwd=ROOT, text=True))
            write(receipt_path, dict(receipts=receipts, reference_installs_rebuilt=False,
                performance_submitted=False, result_inspection='not performed; stop after submission'))
            print('SUBMITTED', name, receipts[name]['job'], flush=True)
        return receipts[name]

    build_config = CONFIGS/(PREFIX+'-build-20261029.json')
    validation_config = CONFIGS/(PREFIX+'-validate-20261029.json')
    built = submit('build', build_config, 'build')
    build_job = built['job'].split(';')[0]
    manifest = Path(built['run'])/'submit-manifest.json'
    if 'validation' not in receipts:
        validation = read(validation_config)
        validation['build'] = read(manifest)['build']
        validation['resources']['dependency'] = 'afterok:'+build_job
        validation['pending_build_validation'] = dict(build_config=str(manifest),
            build_config_sha256=mgr.common.sha(manifest), build_job_id=build_job)
        write(validation_config, validation)
        commit([validation_config], 'EXP129: register cleanup validation after its submitted build')
    checked = submit('validate', validation_config, 'validation')
    jobs = dict(build=build_job, validation=checked['job'].split(';')[0])
    summary = dict(job_ids=jobs, cleanup_source_commit='a6fc19dea8066844376e21db092a2919e88173ba',
        validation_processes=29, generated_sources_identical=2830, host_compiles=21,
        performance_submitted=False, references_rebuilt=False,
        result_inspection='not performed; stop after submission')
    write(RECORD/'submission-summary.json', summary)
    log = ROOT/'VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md'
    block = ('\n\n### EXP129：旧后端清理任务提交（2026-10-29）\n\n'
             '源码a6fc19de；构建'+jobs['build']+'，验证'+jobs['validation']
             +'（显式afterok构建）。主机21项编译、2830份通用生成源码逐字对照通过；'
             '设备待验29项数值／实际路径。仅提交这两项，不提交正式性能、不重建参考；'
             '提交后停止，等待用户检查。回执：experiments/EXP-129/records/legacy-retirement-20261029/。\n')
    if block not in log.read_text():
        with log.open('a') as stream:
            stream.write(block)
    commit([build_config, validation_config, receipt_path, previews_path,
            RECORD/'submission-summary.json', log], 'EXP129: record cleanup build and validation submissions')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
