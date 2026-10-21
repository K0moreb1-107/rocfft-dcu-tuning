"""Submit candidate validation, then paired timing against the retained EXP125 library."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

STEM = 'EXP-128-cc-local-exp125'
DATE = '20261021'


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def queue_config(measurement_path, measurement, submitted_build, job):
    """Only the candidate is pending; EXP125 has no new prerequisite job."""
    return dict(schema_version=1, experiment='EXP-128', run_id=STEM+'-queue-'+DATE,
        gpu_arch='gfx936',
        resources=dict(measurement['resources'], dependency='afterok:'+job),
        deferred_measurement=dict(
            reason='User selected the validated EXP125 installation as reference; queue timing after this candidate alone passes its build and complete validation.',
            measurement_config=str(measurement_path),
            measurement_config_sha256=mgr.common.sha(measurement_path),
            build_config=str(submitted_build),
            build_config_sha256=mgr.common.sha(submitted_build),
            build_job_id=job, required_success_jobs=[job]))


def main():
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    mgr.require(branch == 'exp-128-cc-local-real', 'wrong submission branch')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    record = ROOT/'experiments/EXP-128/records/exp125-reference-20261021'
    record.mkdir(parents=True, exist_ok=True)
    mgr.require(not (record/'submission.json').exists(), 'submission receipt already exists; do not resubmit')
    config_dir = ROOT/'configs/experiments'
    build_path = config_dir/(STEM+'-on-build-'+DATE+'.json')
    measurement_path = config_dir/(STEM+'-performance-'+DATE+'.json')
    build = json.loads(build_path.read_text())
    measurement = json.loads(measurement_path.read_text())
    mgr.require('dependency' not in build['resources'], 'candidate build must be independent')
    mgr.require('previous_build_record' not in build['validation'], 'validation depends on old control')
    mgr.require(measurement['arms']['previous'] == {'registry_id': 'EXP-125-pre-memory-i'},
                'reference must be the retained EXP125 installation')
    mgr.require(measurement['arms']['candidate'] == {
        'build_record': str(mgr.locations(build, 'build')['run']/'build-provenance.json')},
        'measurement must select this candidate')
    # Resolve and record the existing reference before submitting any job.
    reference = mgr.registry()['installations']['EXP-125-pre-memory-i']
    mgr.require(reference['role'] == 'previous' and reference['eligible_formal_arm'], 'ineligible EXP125 reference')
    mgr.require(mgr.common.sha(mgr.inside(reference['path'])/'lib/librocfft.so.0.1') ==
                reference['arm']['library_sha256'], 'EXP125 library identity mismatch')
    build['build']['source_commit'] = commit
    hook = build['post_build_validation']
    hook['sha256'] = mgr.common.sha(mgr.inside(hook['script']))
    for entry in hook['inputs']:
        entry['sha256'] = mgr.common.sha(mgr.inside(entry['path']))
    write(build_path, build)
    receipts = {}
    previews = {}

    def submit(task, path, name):
        argv = [mgr.PYTHON, str(ROOT/'manage.py'), task, '--config', str(path)]
        previews[name] = json.loads(subprocess.check_output(argv, cwd=ROOT, text=True))
        write(record/'submission-previews.json', previews)
        receipt = json.loads(subprocess.check_output(argv+['--execute'], cwd=ROOT, text=True))
        receipts[name] = receipt
        write(record/'submission.json', dict(source_commit=commit, branch=branch,
            reference=reference['arm'], receipts=receipts,
            result_inspection='not performed; stop after submission'))
        return receipt

    built = submit('build', build_path, 'candidate')
    job = built['job'].split(';')[0]
    submitted = Path(built['run'])/'submit-manifest.json'
    queue = queue_config(measurement_path, measurement, submitted, job)
    queue_path = config_dir/(STEM+'-queue-'+DATE+'.json')
    write(queue_path, queue)
    submit('measure', queue_path, 'performance')
    print(json.dumps(dict(source_commit=commit, receipts=receipts,
        performance_dependency=queue['resources']['dependency'],
        reference_installation='EXP-125-pre-memory-i',
        cases=len(measurement['cases']), processes=2*len(measurement['cases']),
        result_inspection='not performed; stop after submission'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
