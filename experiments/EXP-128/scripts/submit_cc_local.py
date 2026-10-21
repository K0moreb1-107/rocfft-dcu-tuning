"""Submit OFF validation, ON validation, then a measurement requiring both."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr


def write(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    mgr.require(branch=='exp-128-cc-local-real','wrong submission branch')
    record=ROOT/'experiments/EXP-128/records/implementation-20261021'
    config_dir=ROOT/'configs/experiments'
    receipts={};previews={}
    def save():write(record/'submission.json',dict(source_commit=commit,branch=branch,receipts=receipts))
    def submit(task,path,key):
        preview=subprocess.check_output([mgr.PYTHON,str(ROOT/'manage.py'),task,'--config',str(path)],
                                        cwd=ROOT,text=True)
        previews[key]=json.loads(preview)
        write(record/'submission-previews.json',previews)
        receipt=json.loads(subprocess.check_output([mgr.PYTHON,str(ROOT/'manage.py'),task,
            '--config',str(path),'--execute'],cwd=ROOT,text=True))
        receipts[key]=receipt;save();return receipt
    for mode in ('off','on'):
        path=config_dir/('EXP-128-cc-local-'+mode+'-build-20261021.json')
        value=json.loads(path.read_text());value['build']['source_commit']=commit
        # Hashes record what is submitted; the manager does not freeze sources.
        hook=value['post_build_validation'];hook['sha256']=mgr.common.sha(mgr.inside(hook['script']))
        for item in hook['inputs']:item['sha256']=mgr.common.sha(mgr.inside(item['path']))
        if mode=='on':value['resources']['dependency']='afterok:'+receipts['off']['job'].split(';')[0]
        write(path,value);submit('build',path,mode)
    measurement_path=config_dir/'EXP-128-cc-local-performance-20261021.json'
    measurement=json.loads(measurement_path.read_text())
    jobs=[receipts[x]['job'].split(';')[0] for x in ('off','on')]
    submitted={x:Path(receipts[x]['run'])/'submit-manifest.json' for x in ('off','on')}
    queue=dict(schema_version=1,experiment='EXP-128',run_id='EXP-128-cc-local-queue-20261021',
        gpu_arch='gfx936',resources=dict(measurement['resources'],dependency='afterok:'+':'.join(jobs)),
        deferred_measurement=dict(reason='User requested performance to be queued now, strictly after both complete build-and-validation jobs succeed.',
            measurement_config=str(measurement_path),measurement_config_sha256=mgr.common.sha(measurement_path),
            build_config=str(submitted['on']),build_config_sha256=mgr.common.sha(submitted['on']),
            build_job_id=jobs[1],required_success_jobs=jobs,
            reference_builds=dict(previous=dict(build_config=str(submitted['off']),
                build_config_sha256=mgr.common.sha(submitted['off']),build_job_id=jobs[0]))))
    queue_path=config_dir/'EXP-128-cc-local-queue-20261021.json';write(queue_path,queue)
    submit('measure',queue_path,'performance')
    print(json.dumps(dict(source_commit=commit,branch=branch,receipts=receipts,
        performance_dependency=queue['resources']['dependency'],
        cases=len(measurement['cases']),processes=2*len(measurement['cases']),
        result_inspection='not performed; stop after submission'),indent=2))


if __name__=='__main__':main()
