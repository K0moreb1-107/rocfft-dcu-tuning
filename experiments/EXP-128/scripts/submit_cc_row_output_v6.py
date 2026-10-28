"""Submit one candidate build, validation, then dependent four-arm performance; stop."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

DATE = '20261028'
PREFIX = 'EXP-128-cc-local-row-output-v6'
RECORD = ROOT/'experiments/EXP-128/records/row-output-v6-20261028'
CONFIGS = ROOT/'configs/experiments'


def write(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def main():
    receipt_path = RECORD/'submission.json'
    mgr.require(not receipt_path.exists(), 'receipts already exist; inspect before any resubmission')
    mgr.require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
                == 'exp-128-cc-local-real', 'wrong branch')
    receipts, previews = {}, {}

    def submit(task, path, name):
        argv = [mgr.PYTHON, str(ROOT/'manage.py'), task, '--config', str(path)]
        previews[name] = json.loads(subprocess.check_output(argv, cwd=ROOT, text=True))
        write(RECORD/'submission-previews.json', previews)
        result = json.loads(subprocess.check_output(argv+['--execute'], cwd=ROOT, text=True))
        receipts[name] = result
        write(receipt_path, dict(receipts=receipts, reference_installs_rebuilt=False,
              source_state_freeze=False, result_inspection='not performed; stop after submission'))
        return result

    bp = CONFIGS/(PREFIX+'-build-'+DATE+'.json')
    vp = CONFIGS/(PREFIX+'-validate-'+DATE+'.json')
    mp = CONFIGS/(PREFIX+'-performance-'+DATE+'.json')
    built = submit('build', bp, 'build')
    build_job = built['job'].split(';')[0]
    submitted = Path(built['run'])/'submit-manifest.json'
    validation = json.loads(vp.read_text())
    validation['build'] = json.loads(submitted.read_text())['build']
    validation['resources']['dependency'] = 'afterok:'+build_job
    validation['pending_build_validation'] = dict(build_config=str(submitted),
        build_config_sha256=mgr.common.sha(submitted), build_job_id=build_job)
    write(vp, validation)
    checked = submit('validate', vp, 'validation')
    validation_job = checked['job'].split(';')[0]
    measurement = json.loads(mp.read_text())
    queue = dict(schema_version=1, experiment='EXP-128', run_id=PREFIX+'-queue-'+DATE,
        gpu_arch='gfx936', resources=dict(measurement['resources'], dependency='afterok:'+validation_job),
        revalidated_measurement=dict(validation_config=str(Path(checked['run'])/'submit-manifest.json'),
            validation_job_id=validation_job, measurement_config=str(mp),
            measurement_config_sha256=mgr.common.sha(mp)))
    qp = CONFIGS/(PREFIX+'-queue-'+DATE+'.json')
    mgr.require(not qp.exists(), 'queue config already exists')
    write(qp, queue)
    submit('measure', qp, 'performance')
    files = [vp, qp, RECORD/'submission-previews.json', receipt_path]
    relative = [str(p.relative_to(ROOT)) for p in files]
    subprocess.run(['git', 'add', '--', *relative], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '--only', '-m', '记录EXP128第六版单候选依赖提交', '--', *relative],
                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    print(json.dumps(dict(receipts=receipts, performance_dependency=queue['resources']['dependency'],
        N=194, cases=388, versions=['EXP125', 'v5', 'same CC unfused repaired', 'v6'],
        processes=1552, samples=46560, result_inspection='not performed; stop after submission'),
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
