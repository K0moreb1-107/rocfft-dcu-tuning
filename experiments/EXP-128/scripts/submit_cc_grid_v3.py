"""Submit four v3 table-only builds, geometry validation and gated 10/30 timing."""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

FOLDER=ROOT/'experiments/EXP-128/records/grid-fill-20261027'
CONFIGS=ROOT/'configs/experiments'


class SubmissionCapacityPending(RuntimeError):
    pass


def write(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def main():
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='exp-128-cc-local-real'
    receipt=FOLDER/'submission.json'
    preflight=json.loads((FOLDER/'host-preflight.json').read_text())
    assert preflight['complete'] and preflight['incorrect_table_rejected']
    assert all(item['identity']['all_executable_bytes_identical'] for item in preflight['builds'])
    records=json.loads(receipt.read_text())['receipts'] if receipt.exists() else {}
    preview_path=FOLDER/'submission-previews.json'
    previews=json.loads(preview_path.read_text()) if preview_path.exists() else {}
    owned=[]
    def submit(task,path,key):
        if key in records:
            previous=records[key]
            actual=json.loads((Path(previous['run'])/'submission.json').read_text())
            assert actual['job'].split(';')[0]==previous['job'].split(';')[0]
            assert Path(previous['run'])==mgr.locations(mgr.load(path),task)['run']
            return previous
        qos=subprocess.run(['squeue','--noheader','--user=zhangkewei','--format=%q'],
                           cwd=ROOT,capture_output=True,text=True)
        assert qos.returncode==0, qos.stderr
        used=sum(line.strip()=='user_zhangkewei' for line in qos.stdout.splitlines())
        required=2 if task=='validate' and key.replace('-validation','-performance') not in records else 1
        if used+required>10:
            pending=dict(complete=False,reason='QOSMaxSubmitJobPerUserLimit',limit=10,used=used,
                required_slots=required,next_step=key,config=str(path),recorded_receipts=records,
                action='Stop; resume missing steps at the next user-requested inspection.')
            write(FOLDER/'submission-state.json',pending)
            raise SubmissionCapacityPending(json.dumps(pending,ensure_ascii=False))
        cfg=mgr.load(path)
        run=mgr.locations(cfg,task)['run']
        if run.exists():
            actual=run/'submission.json'
            if actual.exists():
                records[key]=dict(job=json.loads(actual.read_text())['job'],run=str(run))
                write(receipt,dict(receipts=records,inspection='submission recovery only; not a runtime poll',
                    cells=84,cases=168,versions=2,processes=336,samples=10080))
                return records[key]
            assert (run/'submission-failed.json').exists(), 'unknown reserved submission; inspect it'
            for retry in range(1,20):
                candidate=dict(cfg,run_id=cfg['run_id']+'-retry%d'%retry)
                if not mgr.locations(candidate,task)['run'].exists():
                    write(path,candidate)
                    break
            else:
                raise RuntimeError('too many preserved submission failures')
        argv=[mgr.PYTHON,str(ROOT/'manage.py'),task,'--config',str(path)]
        previews[key]=json.loads(subprocess.check_output(argv,cwd=ROOT,text=True))
        write(FOLDER/'submission-previews.json',previews)
        result=json.loads(subprocess.check_output(argv+['--execute'],cwd=ROOT,text=True))
        records[key]=result
        write(receipt,dict(receipts=records,inspection='not performed; stop after submission',
            base_v3_implementation='8da0abb02ae6f5591e448d3e10adef8919aae40f',
            reference_installs_rebuilt=False,cells=84,cases=168,versions=2,processes=336,samples=10080))
        return result
    for index in range(4):
        label='EXP-128-cc-local-grid-g%d'%index
        build_path=CONFIGS/(label+'-build-20261027.json')
        validation_path=CONFIGS/(label+'-validate-20261027.json')
        measure_path=CONFIGS/(label+'-performance-20261027.json')
        build=submit('build',build_path,'g%d-build'%index)
        build_job=build['job'].split(';')[0]
        submitted_build=Path(build['run'])/'submit-manifest.json'
        cfg=json.loads(validation_path.read_text())
        cfg['build']=json.loads(submitted_build.read_text())['build']
        build_record=Path(build['run'])/'build-provenance.json'
        measurement=json.loads(measure_path.read_text())
        registered_validation=records.get('g%d-validation'%index)
        validation_run=Path(registered_validation['run']) if registered_validation else mgr.locations(cfg,'validate')['run']
        if registered_validation or (validation_run/'submission.json').exists():
            # A resumed sender must preserve the exact already-submitted gate.
            cfg=json.loads((validation_run/'submit-manifest.json').read_text())
            if 'pending_build_validation' in cfg:
                measurement['arms']['candidate']=dict(build_record=str(build_record))
            else:
                built=json.loads(build_record.read_text())
                measurement['arms']['candidate']=built['arm']
        elif build_record.exists():
            built=json.loads(build_record.read_text())
            assert built['complete'] and built['job_id']==build_job
            assert mgr.common.sha(Path(built['arm']['install'])/'lib/librocfft.so.0.1')==built['arm']['library_sha256']
            cfg['resources'].pop('dependency',None)
            cfg.pop('pending_build_validation',None)
            cfg['successful_existing_build']=dict(job_id=build_job,record=str(build_record),
                reason='Completed build reused; no pending build remains to depend on.')
            measurement['arms']['candidate']=built['arm']
        else:
            cfg['resources']['dependency']='afterok:'+build_job
            cfg['pending_build_validation']=dict(build_config=str(submitted_build),
                build_config_sha256=mgr.common.sha(submitted_build),build_job_id=build_job)
            measurement['arms']['candidate']=dict(build_record=str(build_record))
        write(validation_path,cfg)
        write(measure_path,measurement)
        validation=submit('validate',validation_path,'g%d-validation'%index)
        validation_job=validation['job'].split(';')[0]
        queue=dict(schema_version=1,experiment='EXP-128',run_id=label+'-queue-20261027',gpu_arch='gfx936',
            resources=dict(measurement['resources'],dependency='afterok:'+validation_job),
            revalidated_measurement=dict(validation_config=str(Path(validation['run'])/'submit-manifest.json'),
                validation_job_id=validation_job,measurement_config=str(measure_path),
                measurement_config_sha256=mgr.common.sha(measure_path)))
        queue_path=CONFIGS/(label+'-queue-20261027.json')
        write(queue_path,queue)
        submit('measure',queue_path,'g%d-performance'%index)
        owned.extend([validation_path,measure_path,queue_path])
    owned.extend([FOLDER/'submission.json',FOLDER/'submission-previews.json'])
    write(FOLDER/'submission-state.json',dict(complete=True,receipts=records,cells=84,cases=168,
        processes=336,samples=10080,inspection='not performed; stop after submission'))
    owned.append(FOLDER/'submission-state.json')
    rel=[str(path.relative_to(ROOT)) for path in owned]
    subprocess.run(['git','add','--',*rel],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record four controlled v3 heatmap supplement chains','--',*rel],
                   cwd=ROOT,capture_output=True,check=True)
    print(json.dumps(dict(complete=True,receipts=records,cells=84,cases=168,processes=336,samples=10080,
                         runtime_status_inspected=False),ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:
        main()
    except SubmissionCapacityPending as error:
        print(str(error))
        sys.exit(3)
