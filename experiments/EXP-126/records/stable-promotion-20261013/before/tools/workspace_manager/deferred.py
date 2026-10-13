"""Queue formal measurement by frozen build identity; resolve its library after validation."""
import copy
import datetime
import json
import re
from pathlib import Path

from tools.workspace_manager import manager as mgr


def hashed_json(path, digest):
    path = mgr.inside(path)
    mgr.require(re.fullmatch(r'[0-9a-f]{64}', digest or ''), 'explicit input checksum required')
    mgr.require(mgr.common.sha(path) == digest, 'queued input changed: ' + str(path))
    return mgr.load(path)


def inputs(cfg):
    spec = cfg['deferred_measurement']
    mgr.require(isinstance(spec, dict), 'invalid deferred measurement')
    mgr.require(isinstance(spec.get('reason'), str) and len(spec['reason'].strip()) >= 10,
                'record reason for early submission')
    tools = spec.get('tools_sha256', {})
    required = {'manage.py', 'jobs/workspace_task.slurm',
                'tools/workspace_manager/manager.py', 'tools/workspace_manager/deferred.py'}
    mgr.require(isinstance(tools, dict) and required <= set(tools), 'freeze queued entry tools')
    for name, digest in tools.items():
        mgr.require(mgr.common.sha(mgr.inside(name)) == digest, 'queued tool changed: ' + name)
    m = hashed_json(spec['measurement_config'], spec['measurement_config_sha256'])
    b = hashed_json(spec['build_config'], spec['build_config_sha256'])
    mgr.require(m['experiment'] == b['experiment'] == cfg['experiment'], 'queue experiment mismatch')
    mgr.require(m['run_id'] != cfg['run_id'], 'queue and measurement need independent run IDs')
    import sample_contract as protocol
    mgr.require(m.get('policy') == protocol.POLICY, 'early queue requires sample protocol v2')
    mgr.require(m.get('gpu_arch') == 'gfx936', 'unsupported queue GPU profile')
    mgr.require(m.get('timing_source_sha256') == protocol.SOURCE_SHA, 'timing source mismatch')
    mgr.require(isinstance(m.get('acceptance'), str) and len(m['acceptance'].strip()) >= 10,
                'measurement acceptance required')
    protocol.iterations(m)
    protocol.arms(m)
    mgr.common.cases(m)
    for name, digest in m.get('measurement_tools_sha256', {}).items():
        mgr.require(mgr.common.sha(mgr.inside('tools/fft_measurement/' + name)) == digest,
                    'measurement tool changed: ' + name)
    if m.get('coverage_path'):
        mgr.require(mgr.common.sha(mgr.inside(m['coverage_path'])) == m['coverage_sha256'],
                    'measurement coverage changed')
    bp = mgr.locations(b, 'build')
    mgr.require(mgr.inside(spec['build_config']) == bp['run'] / 'submit-manifest.json',
                'use actual submitted build manifest')
    mgr.require(m['arms']['candidate'] == {'build_record': str(bp['run'] / 'build-provenance.json')},
                'candidate must select exactly the registered pending build')
    mgr.require(b['build'].get('component', 'rocfft') == 'rocfft'
                and b.get('post_build_validation'), 'declared post-build validation required')
    hook = mgr.validation_hook(b)
    receipt = json.loads((bp['run'] / 'submission.json').read_text())
    job = spec.get('build_job_id', '')
    mgr.require(re.fullmatch(r'[1-9][0-9]*', job or '')
                and receipt['job'].split(';')[0] == job, 'pending build job identity mismatch')
    jobs = spec.get('required_success_jobs')
    mgr.require(isinstance(jobs, list) and jobs and len(jobs) == len(set(jobs))
                and all(isinstance(j, str) and re.fullmatch(r'[1-9][0-9]*', j) for j in jobs)
                and job in jobs, 'required successful build dependency missing')
    dependency = cfg.get('resources', {}).get('dependency', '')
    mgr.require(re.fullmatch(r'afterok:[1-9][0-9]*(?::[1-9][0-9]*)*', dependency),
                'early queue needs explicit successful dependencies')
    mgr.require(set(jobs) <= set(dependency.split(':')[1:]), 'queue omits successful prerequisites')
    expected_resources = dict(m.get('resources', {}), dependency=dependency)
    mgr.require(cfg['resources'] == expected_resources and expected_resources.get('node_exclusive') is True,
                'queue must preserve exclusive measurement resources')
    return m, b, bp, hook


def validate_build(spec, b, bp, hook):
    record_path = bp['run'] / 'build-provenance.json'
    built = json.loads(record_path.read_text())
    mgr.require(built.get('complete') is True and built.get('component') == 'rocfft'
                and built.get('experiment') == b['experiment'], 'queued build incomplete or wrong')
    mgr.require(built.get('job_id') == spec['build_job_id'], 'queued build job mismatch')
    a = built['arm']
    mgr.require(a['source_commit'] == b['build']['source_commit']
                and a['source_repo'] == str(mgr.inside(b['build']['source_repo'], allow_root=True))
                and a['install'] == str(bp['install']) and a['build_provenance'] == str(record_path),
                'queued build identity mismatch')
    mgr.require(built['plan']['source_identity']['commit'] == a['source_commit']
                and built['plan']['paths'] == {k: str(v) for k, v in bp.items()}
                and built['plan']['post_build_validation_command'] == hook,
                'queued build plan mismatch')
    mgr.require(mgr.common.sha(bp['install'] / 'lib/librocfft.so.0.1') == a['library_sha256'],
                'queued build library changed')
    validated_path = bp['run'] / 'post-build-validation.json'
    validated = json.loads(validated_path.read_text())
    mgr.require(validated.get('complete') is True and validated.get('command') == hook
                and validated.get('source_commit') == a['source_commit']
                and validated.get('library_sha256') == a['library_sha256'],
                'queued validation incomplete or identity mismatch')
    mgr.require(mgr.common.sha(bp['logs'] / 'post-build-validation.txt') == validated['log_sha256'],
                'queued validation log changed')
    return dict(build_job_id=spec['build_job_id'], build_record_sha256=mgr.common.sha(record_path),
                validation_record_sha256=mgr.common.sha(validated_path),
                library_sha256=a['library_sha256'])


def plan(cfg):
    m, b, bp, hook = inputs(cfg)
    mgr.source_identity(b)
    mgr.require(not mgr.locations(m, 'measure')['run'].exists(), 'measurement run already used')
    import sample_contract as protocol
    references = {}
    for name in protocol.arms(m):
        if name == 'candidate':
            continue
        a = copy.deepcopy(m['arms'][name])
        if a.get('registry_id'):
            r = mgr.registry()['installations'][a['registry_id']]
            mgr.require(r.get('role') == name and r.get('eligible_formal_arm'), 'ineligible reference')
            for field in ('install', 'source_repo', 'source_commit', 'source_state',
                          'library_sha256', 'build_provenance'):
                mgr.require(a.get(field, r['arm'][field]) == r['arm'][field], 'reference identity changed')
                a[field] = r['arm'][field]
            a.pop('registry_id', None)
        mgr.require(mgr.common.sha(mgr.inside(a['install']) / 'lib/librocfft.so.0.1') == a['library_sha256'],
                    'reference library changed')
        references[name] = a
    return dict(task='measure', deferred=True, queue_run=str(mgr.locations(cfg, 'measure')['run']),
                measurement_run=str(mgr.locations(m, 'measure')['run']),
                submission_command=mgr.submission_command('measure', cfg),
                reference_arms=references, pending_candidate=dict(build_job_id=cfg['deferred_measurement']['build_job_id'],
                    source_commit=b['build']['source_commit'], install=str(bp['install']),
                    library_sha256=None, validation_command=hook),
                cases=len(mgr.common.cases(m)), processes=len(protocol.schedule(m)),
                event_iterations=protocol.iterations(m), timing_warmups=3, node_exclusive=True,
                notice='Only scheduling is early. Freeze the real candidate checksum after successful build and validation, before any timing.')


def execute(cfg):
    queue = mgr.locations(cfg, 'measure')['run']
    reservation = json.loads((queue / '.reservation.json').read_text())
    mgr.require(reservation == {'task': 'measure', 'manifest': cfg}, 'queued reservation mismatch')
    mgr.require(json.loads((queue / 'submit-manifest.json').read_text()) == cfg, 'queued manifest mismatch')
    with (queue / '.deferred-execution-lock').open('x') as stream:
        stream.write('single deferred resolution; do not reuse this queue identifier')
    try:
        m, b, bp, hook = inputs(cfg)
        evidence = validate_build(cfg['deferred_measurement'], b, bp, hook)
        m = mgr.measurement(m)
        m['readiness'] = 'build_and_validation_completed_before_resolving_formal_identity'
        m['queued_submission'] = dict(queue_run=str(queue),
            queue_manifest_sha256=mgr.common.sha(queue / 'submit-manifest.json'),
            resolved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), **evidence)
        planned = mgr.task_plan('measure', m)
        mgr.require(planned['resolved_preregistration'] == m, 'resolved manifest changed')
        p = mgr.allocate(m, 'measure')
        # Keep the queue submission intact; the child run holds concrete measurement identities.
        mgr.dumps(p['run'] / 'submission-command.json',
                  json.loads((queue / 'submission-command.json').read_text()))
        mgr.dumps(p['run'] / 'submission.json', dict(
            json.loads((queue / 'submission.json').read_text()), queue_run=str(queue)))
        mgr.dumps(queue / 'resolution.json', dict(measurement_run=str(p['run']),
            resolved_manifest_sha256=mgr.common.sha(p['run'] / 'submit-manifest.json'), **evidence))
        import run_samples
        run_samples.execute(m)
        mgr.dumps(queue / 'completion.json', dict(complete=True, measurement_run=str(p['run'])))
    except Exception as error:
        mgr.dumps(queue / 'execution-failed.json', dict(error=str(error), complete=False))
        raise
