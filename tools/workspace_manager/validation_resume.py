"""Finish a proven final-check failure without rebuilding or rerunning passed cases.

Original failed runs stay immutable. A separate acceptance record gates the normal
formal measurement worker. No source snapshots or workspace-state comparisons.
"""
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tools.workspace_manager import manager as mgr


def read(path):
    return json.loads(mgr.inside(path).read_text())


def checked_cases(record, coverage, model):
    mgr.require(record.get('complete') is False, 'resume only an incomplete validation')
    failures=record.get('failures', [])
    mgr.require(len(failures)==1 and failures[0].get('type')=='FileNotFoundError'
                and "'passed_default': 172" in failures[0].get('message',''),
                'not the registered final device-check variable collision')
    defaults=record.get('default_cases', [])
    mgr.require([(x['N'],x['func']) for x in defaults]==
                [(x['N'],x['func']) for x in coverage['cases']], 'default coverage incomplete')
    mgr.require(all(len(x['guard']['references'])==14 for x in defaults), 'default guards incomplete')
    boundaries=record.get('boundary_cases', [])
    mgr.require(len(boundaries)==model['cases']+model['configurations']
                and len({x['id'] for x in boundaries})==len(boundaries), 'boundary coverage incomplete')
    mgr.require(all(x['exchange']=='direct_scalar' and 0<=x['max_error']<1e-9 for x in boundaries),
                'boundary backend or accuracy invalid')
    mgr.require([(x['N'],x['func']) for x in record.get('controls', [])]==
                [(x['N'],x['func']) for x in coverage['controls']], 'control coverage incomplete')
    wanted=[(x['N'],load) for x in coverage['folded'] for load in ('registers','lds')]
    mgr.require([(x['N'],x['load']) for x in record.get('folded_regressions', [])]==wanted,
                'folded regression coverage incomplete')
    mgr.require(record.get('negative_control',{}).get('expected_returncode')==1
                and record.get('retained_validation_sha256'), 'final-stage prerequisites missing')


def existing(cfg):
    spec=cfg['validation_resume']
    mgr.require(cfg['experiment']=='EXP-127', 'this resume recipe is specific to EXP-127 CC validation')
    old=mgr.inside(spec['failed_run'])
    built=read(old/'build-provenance.json');original=read(old/'submit-manifest.json')
    record=read(old/'cc-all-io-validation.json');post=read(old/'post-build-validation.json')
    v=original['validation'];coverage=read(v['coverage']);model=read(v['coordinate_proof'])
    mgr.require(built.get('complete') is True and built['component']=='rocfft'
                and original['experiment']==cfg['experiment'] and v['policy']=='direct-scalar',
                'wrong or incomplete existing build')
    mgr.require(post.get('complete') is False and post['source_commit']==record['source_commit']==built['arm']['source_commit']
                and post['library_sha256']==record['library_sha256']==built['arm']['library_sha256'],
                'failed validation and built library do not match')
    log=old/'logs/post-build-validation.txt'
    mgr.require(mgr.common.sha(log)==post['log_sha256']
                and 'str(identity)' in log.read_text() and 'FileNotFoundError' in log.read_text(),
                'failure was not at the known final check')
    lib=mgr.inside(built['arm']['install'])/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(lib)==built['arm']['library_sha256'], 'existing library differs')
    checked_cases(record,coverage,model)
    # Verify test definitions used to interpret the saved evidence, not current source state.
    registered=original['build']['task_input_sha256']
    for name in ('coverage','coordinate_proof','host_expected'):
        path=mgr.inside(v[name])
        mgr.require(mgr.common.sha(path)==registered[str(path)], 'saved test definition differs: '+name)
    return old,built,v,record,coverage,model,lib


def gate(cfg):
    spec=cfg['validated_measurement']
    resumed=mgr.load(mgr.inside(spec['resume_config']))
    mgr.require('validation_resume' in resumed and resumed['experiment']==cfg['experiment'], 'invalid resume prerequisite')
    rp=mgr.locations(resumed,'validate');receipt=read(rp['run']/'submission.json')
    job=spec['resume_job_id']
    mgr.require(re.fullmatch('[1-9][0-9]*',job or '') and receipt['job'].split(';')[0]==job,
                'resume job differs from actual submission')
    mgr.require(cfg['resources'].get('dependency')=='afterok:'+job, 'successful resume dependency required')
    m=mgr.load(mgr.inside(spec['measurement_config']))
    mgr.require(m['experiment']==cfg['experiment'] and m['run_id']!=cfg['run_id'], 'measurement scope mismatch')
    old,built,*_=existing(resumed)
    mgr.require(m['arms']['candidate']==built['arm'], 'measurement does not select the validated existing library')
    planned=mgr.task_plan('measure',m)
    mgr.require(planned['node_exclusive'] and cfg['resources'].get('node_exclusive') is True,
                'exclusive measurement required')
    mgr.require({k:v for k,v in cfg['resources'].items() if k!='dependency'}==m['resources'],
                'queue changes formal measurement resources')
    return resumed,rp,m,planned


def plan(task,cfg):
    if 'validation_resume' in cfg:
        mgr.require(task=='validate', 'resume is a validation task')
        old,built,v,record,coverage,model,lib=existing(cfg)
        return dict(task=task,resumed=True,original_run=str(old),source_commit=built['arm']['source_commit'],
                    library_sha256=built['arm']['library_sha256'],compile_commands=[],
                    reused_default_cases=len(record['default_cases']),reused_boundary_cases=len(record['boundary_cases']),
                    pending='Verify saved raw evidence, then rerun shared final verifier on the original GPU UUID.',
                    submission_command=mgr.submission_command(task,cfg),source_state_freeze=False)
    mgr.require(task=='measure', 'validated measurement queue must use measure')
    resumed,rp,m,planned=gate(cfg)
    return dict(task=task,pending_acceptance=True,formal=True,measurement_run=str(mgr.locations(m,'measure')['run']),
                processes=planned['processes'],cases=planned['cases'],timing_warmups=planned['timing_warmups'],
                event_iterations=planned['event_iterations'],reference_arms=m['arms'],
                submission_command=mgr.submission_command(task,cfg),source_state_freeze=False)


def resume(cfg):
    old,built,v,original,coverage,model,lib=existing(cfg)
    p=mgr.claim(cfg,'validate');env=mgr.environment(p['cache'])
    mgr.dumps(p['run']/'preregistration.json',cfg)
    result=dict(complete=False,original_run=str(old),source_commit=built['arm']['source_commit'],
                library_sha256=built['arm']['library_sha256'],job_id=os.environ['SLURM_JOB_ID'],
                original_validation_sha256=mgr.common.sha(old/'cc-all-io-validation.json'),
                original_failure_preserved=True,source_state_freeze=False)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        evidence=old/'cc-all-io-validation'
        for name,digest in original['files'].items():
            path=mgr.inside(evidence/name)
            mgr.require(evidence in path.parents and mgr.common.sha(path)==digest, 'saved raw evidence differs: '+name)
        result['verified_evidence_files']=len(original['files'])
        binary=mgr.inside(v['identity_binary'])
        mgr.require(mgr.common.sha(binary)==v['identity_binary_sha256'], 'device helper differs')
        gpu=json.loads(subprocess.check_output([str(binary)],env=env,text=True))
        mgr.require(gpu==original['gpu'], 'resume requires the original GPU and runtime')
        script=mgr.inside(cfg['validation_resume']['validator'])
        sys.path.insert(0,str(script.parent))
        spec=importlib.util.spec_from_file_location('resumed_cc_validator',script)
        validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
        record=copy.deepcopy(original);record['failures']=[]
        record['resumed_from']=str(old);record['resume_start']=started
        expected=read(v['host_expected'])[str(v['policy_index'])]
        validator.finish_validation(record,v,built,expected,coverage,model,gpu,env,lib,binary)
        mgr.require(record['complete'] is True, 'final verifier did not complete')
        result.update(complete=True,gpu=gpu,validation_script=str(script),
                      validation_script_sha256=mgr.common.sha(script),
                      counts={k:len(record[k]) for k in ('default_cases','boundary_cases','controls','folded_regressions')})
        # Preserve the full historical record by reference; no bulky duplicate fixtures.
        mgr.dumps(p['run']/'cc-all-io-validation.json',dict(complete=True,resumed_from=str(old),
                   reused_validation_sha256=result['original_validation_sha256'],
                   library_sha256=result['library_sha256'],source_commit=result['source_commit'],
                   counts=result['counts'],gpu=gpu,final_verifier_passed=True))
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        result.update(started_utc=started,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        mgr.dumps(p['run']/'post-build-validation.json',result)
    print(json.dumps(result))


def measure(cfg):
    resumed,rp,m,planned=gate(cfg)
    q=mgr.claim(cfg,'measure')
    result=dict(complete=False,formal=False,measurement_run=str(mgr.locations(m,'measure')['run']))
    try:
        accepted=read(rp['run']/'post-build-validation.json')
        evidence=read(rp['run']/'cc-all-io-validation.json')
        arm=m['arms']['candidate']
        mgr.require(accepted.get('complete') is True and evidence.get('complete') is True
                    and accepted['job_id']==cfg['validated_measurement']['resume_job_id']
                    and accepted['source_commit']==arm['source_commit']
                    and accepted['library_sha256']==arm['library_sha256']
                    and evidence.get('final_verifier_passed') is True
                    and evidence['source_commit']==arm['source_commit']
                    and evidence['library_sha256']==arm['library_sha256']
                    and evidence['reused_validation_sha256']==accepted['original_validation_sha256']
                    and mgr.common.sha(mgr.inside(accepted['original_run'])/'cc-all-io-validation.json')
                        ==accepted['original_validation_sha256'], 'resumed validation incomplete or wrong library')
        m=copy.deepcopy(planned['resolved_preregistration'])
        m['validation_acceptance']=dict(run=str(rp['run']),
            record_sha256=mgr.common.sha(rp['run']/'post-build-validation.json'),
            original_run=accepted['original_run'],reused_cases=accepted['counts'])
        m['queued_submission']=dict(queue_run=str(q['run']),validation_job_id=accepted['job_id'])
        p=mgr.allocate(m,'measure')
        for name in ('submission-command.json','submission.json'):
            mgr.dumps(p['run']/name,read(q['run']/name))
        mgr.dumps(q['run']/'resolution.json',dict(measurement_run=str(p['run']),
            validation_acceptance=m['validation_acceptance']))
        import run_cufft261012 as worker
        worker.execute(m)
        result['complete']=True
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        mgr.dumps(q['run']/'completion.json',result)


def execute(task,cfg):
    plan(task,cfg)
    return resume(cfg) if task=='validate' else measure(cfg)
