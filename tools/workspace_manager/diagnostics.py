"""Frozen diagnostic scripts on one GPU; their timings are never formal results."""
import datetime
import hashlib
import json
import re
import subprocess

from tools.workspace_manager import manager as mgr


def command(cfg):
    spec = cfg['diagnostic']
    mgr.require(set(spec) == {'script', 'sha256', 'inputs', 'tool_source_commit', 'reason'},
                'invalid diagnostic registration')
    mgr.require(isinstance(spec['reason'], str) and len(spec['reason'].strip()) >= 10,
                'explain diagnostic purpose')
    commit = spec['tool_source_commit']
    mgr.require(re.fullmatch('[0-9a-f]{40}', commit or ''), 'freeze diagnostic tool commit')
    mgr.require(isinstance(spec['inputs'], list), 'diagnostic inputs must be a list')
    base = mgr.inside(mgr.ROOT/'experiments'/cfg['experiment'])
    script = mgr.inside(spec['script'], base)
    mgr.require(script.suffix == '.py', 'diagnostic must be a Python script')
    files = [dict(path=str(script), sha256=spec['sha256'])] + spec['inputs']
    names = set()
    for entry in files:
        mgr.require(set(entry) == {'path', 'sha256'}, 'invalid diagnostic input')
        path = mgr.inside(entry['path'])
        mgr.require(path not in names, 'duplicate diagnostic input')
        names.add(path)
        digest = entry['sha256']
        mgr.require(re.fullmatch('[0-9a-f]{64}', digest or ''), 'freeze diagnostic input checksum')
        mgr.require(mgr.common.sha(path) == digest, 'diagnostic input changed: '+str(path))
        blob = subprocess.check_output(['git', '-C', str(mgr.ROOT), 'show',
                                        commit+':'+str(path.relative_to(mgr.ROOT))])
        mgr.require(hashlib.sha256(blob).hexdigest() == digest, 'uncommitted diagnostic input')
    required = {mgr.ROOT/n for n in ('manage.py', 'jobs/workspace_task.slurm',
                 'tools/workspace_manager/manager.py', 'tools/workspace_manager/diagnostics.py')}
    mgr.require(required <= names, 'freeze diagnostic entry tools')
    paths = mgr.locations(cfg, 'diagnose')
    return [mgr.PYTHON, str(script), '--config', str(paths['run']/'submit-manifest.json'),
            '--run', str(paths['run']), '--build', str(paths['build']), '--cache', str(paths['cache'])]


def plan(cfg):
    mgr.require('deferred_measurement' not in cfg, 'diagnostics require resolved libraries')
    m = mgr.measurement(cfg)
    mgr.require(m.get('resources', {}).get('node_exclusive') is True,
                'diagnostics require exclusive node allocation')
    for name, arm in m['arms'].items():
        lib = mgr.inside(arm['install'])/'lib/librocfft.so.0.1'
        mgr.require(mgr.common.sha(lib) == arm['library_sha256'], name+': library changed')
    return dict(task='diagnose', formal=False, resolved_preregistration=m,
                paths={k:str(v) for k,v in mgr.locations(m, 'diagnose').items()},
                command=command(m), submission_command=mgr.submission_command('diagnose', m),
                cases=len(mgr.common.cases(m)), node_exclusive=True,
                notice='Diagnostic instrumentation only; retain original formal measurements unchanged.')


def execute(cfg):
    planned = plan(cfg)
    m = planned['resolved_preregistration']
    paths = mgr.claim(m, 'diagnose')
    env = mgr.environment(paths['cache'])
    mgr.dumps(paths['run']/'preregistration.json', m)
    mgr.dumps(paths['run']/'plan.json', planned)
    log = paths['logs']/'diagnostic.txt'
    result = dict(complete=False, formal=False, job_id=env['SLURM_JOB_ID'],
                  command=planned['command'], started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        with log.open('xb') as stream:
            subprocess.run(planned['command'], cwd=mgr.ROOT, env=env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        mgr.require(command(m) == planned['command'], 'diagnostic inputs changed during execution')
        result['complete'] = True
    finally:
        result['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if log.exists(): result['log_sha256'] = mgr.common.sha(log)
        mgr.dumps(paths['run']/'diagnostic-validation.json', result)
    print(paths['run']/'diagnostic-validation.json')
