"""Run a complete validation against an existing build; gate timing on its new result."""
import copy
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

from tools.workspace_manager import manager as mgr


def read(path):
    return json.loads(mgr.inside(path).read_text(encoding='utf-8'))


def existing(cfg):
    spec = cfg['existing_build_validation']
    record = mgr.inside(spec['build_record'])
    built = read(record)
    mgr.require(built.get('complete') is True and built.get('component') == 'rocfft'
                and built.get('experiment') == cfg['experiment'], 'existing build incomplete or wrong experiment')
    library = mgr.inside(built['arm']['install'])/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(library) == built['arm']['library_sha256'], 'existing library differs')
    filename = spec['evidence_record']
    mgr.require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json', filename), 'invalid validation evidence filename')
    artifact = mgr.inside(built['plan']['paths']['build'])
    mgr.require((artifact/'CMakeCache.txt').is_file(), 'existing build artifacts missing')
    command = mgr.validation_hook(cfg)
    mgr.require(command is not None, 'full validation script required')
    command = list(command)
    command[command.index('--build-record')+1] = str(record)
    command[command.index('--build')+1] = str(artifact)
    if spec.get('isolated_helpers'):
        command.extend(['--helpers', str(mgr.locations(cfg, 'validate')['build'])])
    return built, library, command, filename


def gate(cfg):
    spec = cfg['revalidated_measurement']
    validation_path = mgr.inside(spec['validation_config'])
    validation = mgr.load(validation_path)
    mgr.require('existing_build_validation' in validation and validation['experiment'] == cfg['experiment'],
                'invalid full-validation prerequisite')
    vp = mgr.locations(validation, 'validate')
    mgr.require(validation_path == vp['run']/'submit-manifest.json', 'use the actually submitted validation config')
    receipt = read(vp['run']/'submission.json')
    job = spec['validation_job_id']
    mgr.require(re.fullmatch(r'[1-9][0-9]*', job or '') and receipt['job'].split(';')[0] == job,
                'validation job differs from submitted receipt')
    mgr.require(cfg['resources'].get('dependency') == 'afterok:'+job,
                'successful validation dependency required')
    measurement_path = mgr.inside(spec['measurement_config'])
    mgr.require(mgr.common.sha(measurement_path) == spec['measurement_config_sha256'],
                'measurement configuration differs from its submitted identity')
    measurement = mgr.load(measurement_path)
    mgr.require(measurement['experiment'] == cfg['experiment'] and measurement['run_id'] != cfg['run_id'],
                'measurement experiment or run differs')
    mgr.require(measurement.get('policy') == 'FFT-event-cufft261012-single-v3',
                'revalidated timing requires the registered v3 protocol')
    built, library, command, filename = existing(validation)
    mgr.require(measurement['arms']['candidate'] == built['arm'], 'measurement selects another existing library')
    planned = mgr.task_plan('measure', measurement)
    mgr.require(planned['node_exclusive'] and cfg['resources'].get('node_exclusive') is True,
                'exclusive formal measurement required')
    mgr.require({k: v for k, v in cfg['resources'].items() if k != 'dependency'} == measurement['resources'],
                'queue changes formal measurement resources')
    return validation, vp, built, command, filename, planned


def plan(task, cfg):
    if 'existing_build_validation' in cfg:
        mgr.require(task == 'validate', 'existing build validation must use validate')
        built, library, command, filename = existing(cfg)
        return dict(task=task, existing_build=True, rebuild_required=False,
                    source_commit=built['arm']['source_commit'], library_sha256=built['arm']['library_sha256'],
                    validation_command=command, evidence_record=filename,
                    submission_command=mgr.submission_command(task, cfg),
                    source_state_freeze=False, validation_scope='complete fresh validation; no reuse of partial passes')
    mgr.require(task == 'measure', 'validation-gated measurement must use measure')
    validation, vp, built, command, filename, planned = gate(cfg)
    mgr.require(not Path(planned['paths']['run']).exists(), 'measurement run identifier already used')
    return dict(task=task, pending_acceptance=True, formal=True, rebuild_required=False,
                measurement_run=planned['paths']['run'], processes=planned['processes'], cases=planned['cases'],
                timing_warmups=planned['timing_warmups'], event_iterations=planned['event_iterations'],
                reference_arms=planned['resolved_preregistration']['arms'],
                submission_command=mgr.submission_command(task, cfg), source_state_freeze=False)


def verify_acceptance(vp, built, command, filename, job):
    accepted = read(vp['run']/'post-build-validation.json')
    evidence = read(vp['run']/filename)
    arm = built['arm']
    mgr.require(accepted.get('complete') is True and evidence.get('complete') is True
                and accepted.get('job_id') == job and accepted.get('command') == command,
                'full revalidation did not complete or used another command')
    for key in ('source_commit', 'library_sha256'):
        mgr.require(accepted.get(key) == evidence.get(key) == arm[key], 'accepted library identity differs: '+key)
    mgr.require(accepted.get('gpu') == evidence.get('gpu') and evidence.get('gpu', {}).get('count') == 1,
                'validation device evidence differs')
    mgr.require(mgr.common.sha(vp['logs']/'post-build-validation.txt') == accepted.get('log_sha256')
                and mgr.common.sha(vp['run']/filename) == accepted.get('evidence_sha256'),
                'validation evidence differs from acceptance record')
    mgr.require(mgr.common.sha(mgr.inside(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256'],
                'accepted library differs')
    return dict(run=str(vp['run']), job_id=job, record_sha256=mgr.common.sha(vp['run']/'post-build-validation.json'),
                evidence_record=filename, evidence_sha256=accepted['evidence_sha256'],
                source_commit=arm['source_commit'], library_sha256=arm['library_sha256'])


def validate(cfg):
    built, library, command, filename = existing(cfg)
    p = mgr.claim(cfg, 'validate')
    mgr.dumps(p['run']/'preregistration.json', cfg)
    result = dict(complete=False, job_id=os.environ['SLURM_JOB_ID'], command=command,
                  source_commit=built['arm']['source_commit'], library_sha256=built['arm']['library_sha256'],
                  original_build_record=cfg['existing_build_validation']['build_record'], rebuild_required=False,
                  validation_script_sha256=mgr.common.sha(mgr.inside(cfg['post_build_validation']['script'])),
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    log = p['logs']/'post-build-validation.txt'
    try:
        with log.open('xb') as stream:
            subprocess.run(command, env=mgr.environment(p['cache']), cwd=mgr.ROOT,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        evidence = read(p['run']/filename)
        mgr.require(evidence.get('complete') is True, 'full validator did not complete')
        for key in ('source_commit', 'library_sha256'):
            mgr.require(evidence.get(key) == result[key], 'validator used another library: '+key)
        mgr.require(mgr.common.sha(library) == result['library_sha256'], 'validation library differs')
        result.update(complete=True, gpu=evidence['gpu'], evidence_sha256=mgr.common.sha(p['run']/filename))
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        result.update(log_sha256=mgr.common.sha(log) if log.exists() else None,
                      ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        mgr.dumps(p['run']/'post-build-validation.json', result)
    print(json.dumps(result))


def measure(cfg):
    validation, vp, built, command, filename, planned = gate(cfg)
    q = mgr.claim(cfg, 'measure')
    result = dict(complete=False, formal=False, measurement_run=planned['paths']['run'])
    try:
        acceptance = verify_acceptance(vp, built, command, filename,
                                       cfg['revalidated_measurement']['validation_job_id'])
        measurement = copy.deepcopy(planned['resolved_preregistration'])
        measurement['validation_acceptance'] = acceptance
        measurement['queued_submission'] = dict(queue_run=str(q['run']), validation_job_id=acceptance['job_id'])
        p = mgr.allocate(measurement, 'measure')
        for name in ('submission-command.json', 'submission.json'):
            mgr.dumps(p['run']/name, read(q['run']/name))
        mgr.dumps(q['run']/'resolution.json', dict(measurement_run=str(p['run']), validation_acceptance=acceptance))
        import run_cufft261012 as worker
        mgr.require(measurement['policy'] == worker.POLICY, 'revalidated queue requires the registered v3 protocol')
        worker.execute(measurement)
        result['complete'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        mgr.dumps(q['run']/'completion.json', result)


def execute(task, cfg):
    plan(task, cfg)
    return validate(cfg) if task == 'validate' else measure(cfg)
