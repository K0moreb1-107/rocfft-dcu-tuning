"""Retry existing row-simplification validation and success-gated timing, without a build."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

OLD = 'EXP-128-cc-local-rowsimplify'
PREFIX = OLD + '-retry1'
DATE = '20261022'
CONFIGS = ROOT / 'configs/experiments'
RECORD = ROOT / 'experiments/EXP-128/records/rowsimplify-retry1-20261022'
VALIDATION = CONFIGS / (PREFIX + '-validate-' + DATE + '.json')
MEASUREMENT = CONFIGS / (PREFIX + '-performance-' + DATE + '.json')
QUEUE = CONFIGS / (PREFIX + '-queue-' + DATE + '.json')
EXPECTED_LIBRARY = 'f97365bba962f3be72a1336b67b5d4d6a93dd8d63f2500172730f639bb5cf3ea'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def commit(paths, message):
    relative = [str(path.relative_to(ROOT)) for path in paths]
    subprocess.run(['git', 'add', '--', *relative], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '--only', '-m', message, '--', *relative], cwd=ROOT, check=True)


def check_command(command, dependency=None):
    mgr.require('--exclude=a01r4n05' in command, 'failed node not excluded')
    mgr.require(not any(part.startswith('--nodelist=') for part in command), 'fixed node binding reintroduced')
    if dependency:
        mgr.require('--dependency=' + dependency in command, 'missing explicit successful-validation dependency')


def prepare():
    mgr.require(not RECORD.exists() and not any(p.exists() for p in (VALIDATION, MEASUREMENT, QUEUE)),
                'retry already prepared; inspect its records')
    validation = read(CONFIGS / (OLD + '-validate-' + DATE + '.json'))
    measurement = read(CONFIGS / (OLD + '-performance-' + DATE + '.json'))
    built = read(Path(validation['existing_build_validation']['build_record']))
    mgr.require(built.get('complete') is True and built['arm']['library_sha256'] == EXPECTED_LIBRARY,
                'successful build identity differs')
    mgr.require(mgr.common.sha(Path(built['arm']['install']) / 'lib/librocfft.so.0.1') == EXPECTED_LIBRARY,
                'existing candidate library differs')
    validation['run_id'] = PREFIX + '-validate-' + DATE
    validation.pop('pending_build_validation', None)
    validation['resources'].pop('dependency', None)
    validation['resources'].pop('nodelist', None)
    validation['resources']['exclude'] = 'a01r4n05'
    measurement['run_id'] = PREFIX + '-performance-' + DATE
    measurement['resources'].pop('nodelist', None)
    measurement['resources'].pop('dependency', None)
    measurement['resources']['exclude'] = 'a01r4n05'
    measurement['arms']['candidate'] = copy.deepcopy(built['arm'])
    for key in ('validation_acceptance', 'queued_submission'):
        measurement.pop(key, None)
    mgr.require(len(validation['validation']['sample_N']) == 26, 'validation coverage changed')
    mgr.require(len(measurement['cases']) == 388 and len({c['N'] for c in measurement['cases']}) == 194,
                'performance coverage changed')
    RECORD.mkdir()
    write(VALIDATION, validation)
    write(MEASUREMENT, measurement)
    preview = mgr.task_plan('validate', mgr.load(VALIDATION))
    check_command(preview['submission_command'])
    mgr.require(preview['existing_build'] and not preview['rebuild_required'] and not preview['pending_build'],
                'retry unexpectedly requires a build')
    timing = mgr.task_plan('measure', mgr.measurement(mgr.load(MEASUREMENT)))
    check_command(timing['submission_command'])
    mgr.require(timing['processes'] == 1164, 'timing process count changed')
    write(RECORD / 'preparation-preview.json', {'validation': preview, 'measurement_after_acceptance': timing})
    write(RECORD / 'decisions.json', dict(
        original_jobs=dict(build='960028', validation='960029', performance='960030'),
        reason='Validation stopped at device identification on a01r4n05 before any numerical or dispatch case.',
        exclude='a01r4n05', fixed_node=False, rebuild=False, source_state_freeze=False,
        candidate_sha256=EXPECTED_LIBRARY,
        reused_build_record=validation['existing_build_validation']['build_record'],
        validation_N=26, performance_N=194, cases=388, processes=1164, samples=34920,
        protocol='FFT-event-cufft261012-single-v3', warmups=10, measured_samples=30,
        references=['EXP125 retained', 'accepted generic CC v2', 'generic row simplification v3'],
        production_source_modified=False, stop_after_submission=True))
    commit([ROOT / 'tools/workspace_manager/manager.py', Path(__file__), VALIDATION, MEASUREMENT,
            RECORD / 'preparation-preview.json', RECORD / 'decisions.json'],
           'Register row validation retry using existing build and explicit node exclusion')
    print(json.dumps(dict(prepared=True, validation=preview, processes=timing['processes'],
                          samples=34920, performance_run=measurement['run_id']), ensure_ascii=False))


def submit():
    receipt_path = RECORD / 'submission.json'
    mgr.require(not receipt_path.exists(), 'retry already submitted or partially submitted; inspect receipts')
    receipts, previews = {}, {}

    def launch(task, config, label, dependency=None):
        argv = [mgr.PYTHON, str(ROOT / 'manage.py'), task, '--config', str(config)]
        preview = json.loads(subprocess.check_output(argv, cwd=ROOT, text=True))
        check_command(preview['submission_command'], dependency)
        previews[label] = preview
        write(RECORD / 'submission-previews.json', previews)
        result = json.loads(subprocess.check_output(argv + ['--execute'], cwd=ROOT, text=True))
        receipts[label] = result
        write(receipt_path, dict(receipts=receipts, rebuilt=False,
                                reused_build_job='960028', result_inspection='not performed; stop after submission'))
        return result

    validation = launch('validate', VALIDATION, 'validation')
    job = validation['job'].split(';')[0]
    measurement = mgr.load(MEASUREMENT)
    dependency = 'afterok:' + job
    queue = dict(schema_version=1, experiment='EXP-128', run_id=PREFIX + '-queue-' + DATE,
                 gpu_arch='gfx936', resources=dict(measurement['resources'], dependency=dependency),
                 revalidated_measurement=dict(
                     validation_config=str(Path(validation['run']) / 'submit-manifest.json'),
                     validation_job_id=job, measurement_config=str(MEASUREMENT),
                     measurement_config_sha256=mgr.common.sha(MEASUREMENT)))
    mgr.require(not QUEUE.exists(), 'retry queue already exists')
    write(QUEUE, queue)
    launch('measure', QUEUE, 'performance', dependency)
    commit([QUEUE, receipt_path, RECORD / 'submission-previews.json'],
           'Record existing-build row validation retry and success-gated timing jobs')
    print(json.dumps(dict(receipts=receipts, reused_build_job='960028', rebuilt=False,
                         performance_dependency=dependency, exclude='a01r4n05', fixed_node=False,
                         N=194, cases=388, processes=1164, samples=34920,
                         result_inspection='not performed; stop after submission'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    args = parser.parse_args()
    mgr.require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
                == 'exp-128-cc-local-real', 'wrong experiment branch')
    submit() if args.submit else prepare()
