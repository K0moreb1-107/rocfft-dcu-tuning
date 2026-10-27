"""Submit two independent builds/validations, then four-arm timing after both successes."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
RECORD=ROOT/'experiments/EXP-128/records/boundary-v5-20261027'
CONFIGS=ROOT/'configs/experiments'
PREFIX='EXP-128-cc-local-boundary-v5'
OFF='EXP-128-cc-local-unfused-cc'
DATE='20261027'


def write(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def main():
    receipt_path=RECORD/'submission.json'
    mgr.require(not receipt_path.exists(),'receipts already exist; inspect before any resubmission')
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
                =='exp-128-cc-local-real','wrong branch')
    receipts,previews={},{}
    def submit(task,path,name):
        argv=[mgr.PYTHON,str(ROOT/'manage.py'),task,'--config',str(path)]
        previews[name]=json.loads(subprocess.check_output(argv,cwd=ROOT,text=True))
        write(RECORD/'submission-previews.json',previews)
        result=json.loads(subprocess.check_output(argv+['--execute'],cwd=ROOT,text=True))
        receipts[name]=result
        write(receipt_path,dict(receipts=receipts,result_inspection='not performed; stop after submission',
            reference_installs_rebuilt=False,source_state_freeze=False))
        return result
    validations={};changed=[]
    for name,prefix in [('candidate',PREFIX),('unfused_cc',OFF)]:
        bp=CONFIGS/(prefix+'-build-'+DATE+'.json');vp=CONFIGS/(prefix+'-validate-'+DATE+'.json')
        b=submit('build',bp,name+'_build');job=b['job'].split(';')[0]
        submitted=Path(b['run'])/'submit-manifest.json'
        cfg=json.loads(vp.read_text());cfg['build']=json.loads(submitted.read_text())['build']
        cfg['resources']['dependency']='afterok:'+job
        cfg['pending_build_validation']=dict(build_config=str(submitted),build_config_sha256=mgr.common.sha(submitted),build_job_id=job)
        write(vp,cfg);changed.append(vp)
        validations[name]=submit('validate',vp,name+'_validation')
    mp=CONFIGS/(PREFIX+'-performance-'+DATE+'.json');measurement=json.loads(mp.read_text())
    deps={name:result['job'].split(';')[0] for name,result in validations.items()}
    def validation_spec(name):
        return dict(validation_config=str(Path(validations[name]['run'])/'submit-manifest.json'),validation_job_id=deps[name])
    queue=dict(schema_version=1,experiment='EXP-128',run_id=PREFIX+'-queue-'+DATE,gpu_arch='gfx936',
        resources=dict(measurement['resources'],dependency='afterok:'+deps['candidate']+':'+deps['unfused_cc']),
        revalidated_measurement=dict(validation_spec('candidate'),measurement_config=str(mp),measurement_config_sha256=mgr.common.sha(mp),
            reference_validations=dict(unfused_cc=validation_spec('unfused_cc'))))
    qp=CONFIGS/(PREFIX+'-queue-'+DATE+'.json');write(qp,queue);changed.append(qp)
    submit('measure',qp,'performance')
    changed += [RECORD/'submission-previews.json',receipt_path]
    relative=[str(p.relative_to(ROOT)) for p in changed]
    subprocess.run(['git','add','--',*relative],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record EXP128 boundary v5 independent submissions and dual success gate','--',*relative],
        cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    print(json.dumps(dict(receipts=receipts,performance_dependency=queue['resources']['dependency'],
        N=194,cases=388,versions=['EXP125','v4','same CC unfused','v5'],processes=1552,samples=46560,
        result_inspection='not performed; stop after submission'),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
