"""Submit two-check validation and dependent timing, using the already installed candidate."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr, revalidate


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    mgr.require(branch=='exp-128-cc-local-real','wrong branch')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    folder=ROOT/'experiments/EXP-128/records/default-scope-20261021'
    mgr.require(not (folder/'submission.json').exists(),'submission already recorded; do not duplicate tasks')
    directory=ROOT/'configs/experiments'
    validation_path=directory/'EXP-128-cc-local-default-validate-20261021.json'
    measurement_path=directory/'EXP-128-cc-local-default-performance-20261021.json'
    cfg=json.loads(validation_path.read_text())
    mgr.require(cfg['validation'].get('profile')=='measurement-default-two-checks', 'wrong measurement acceptance profile')
    cfg['operations_source_commit']=commit
    hook=cfg['post_build_validation'];hook['sha256']=mgr.common.sha(mgr.inside(hook['script']))
    for entry in hook['inputs']:entry['sha256']=mgr.common.sha(mgr.inside(entry['path']))
    write(validation_path,cfg)
    built,library,command,filename=revalidate.existing(cfg)
    receipts={};previews={}

    def submit(task,path,name):
        argv=[mgr.PYTHON,str(ROOT/'manage.py'),task,'--config',str(path)]
        previews[name]=json.loads(subprocess.check_output(argv,cwd=ROOT,text=True))
        write(folder/'submission-previews.json',previews)
        receipt=json.loads(subprocess.check_output(argv+['--execute'],cwd=ROOT,text=True))
        receipts[name]=receipt
        write(folder/'submission.json',dict(operations_source_commit=commit,candidate=built['arm'],
            receipts=receipts,rebuild_submitted=False,result_inspection='not performed; stop after submission'))
        return receipt

    validated=submit('validate',validation_path,'validation')
    job=validated['job'].split(';')[0]
    measurement=json.loads(measurement_path.read_text())
    queue=dict(schema_version=1,experiment='EXP-128',run_id='EXP-128-cc-local-default-queue-20261021',
        gpu_arch='gfx936',resources=dict(measurement['resources'],dependency='afterok:'+job),
        revalidated_measurement=dict(validation_config=str(Path(validated['run'])/'submit-manifest.json'),
            validation_job_id=job,measurement_config=str(measurement_path),
            measurement_config_sha256=mgr.common.sha(measurement_path)))
    queue_path=directory/'EXP-128-cc-local-default-queue-20261021.json';write(queue_path,queue)
    submit('measure',queue_path,'performance')
    print(json.dumps(dict(receipts=receipts,performance_dependency=queue['resources']['dependency'],
        reused_build_job='953518',candidate_library_sha256=built['arm']['library_sha256'],
        rebuild_submitted=False,cases=len(measurement['cases']),processes=2*len(measurement['cases']),
        result_inspection='not performed; stop after submission'),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
