"""Submit one OFF build, two short independent checks, and the missing four-arm cases."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
CONFIGS=ROOT/'configs/experiments';RECORD=ROOT/'experiments/EXP-128/records/unfused-phasefix-20261027'
PREFIX='EXP-128-cc-local-unfused-phasefix';CANDIDATE='EXP-128-cc-local-boundary-v5-tail';DATE='20261027'


def write(path,x):
    tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


def main():
    receipt=RECORD/'submission.json';mgr.require(not receipt.exists(),'submission receipts exist; do not submit twice')
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='exp-128-cc-local-real','wrong branch')
    receipts,previews={},{}
    def submit(task,path,name):
        args=[mgr.PYTHON,str(ROOT/'manage.py'),task,'--config',str(path)]
        previews[name]=json.loads(subprocess.check_output(args,cwd=ROOT,text=True));write(RECORD/'submission-previews.json',previews)
        x=json.loads(subprocess.check_output(args+['--execute'],cwd=ROOT,text=True));receipts[name]=x
        write(receipt,dict(receipts=receipts,result_inspection='not performed; stop after submission',
            source_state_freeze=False,retained_installations_rebuilt=False))
        return x
    build_path=CONFIGS/(PREFIX+'-build-'+DATE+'.json')
    build=submit('build',build_path,'unfused_cc_build');build_job=build['job'].split(';')[0]
    vp=CONFIGS/(PREFIX+'-validate-'+DATE+'.json');v=json.loads(vp.read_text())
    submitted=Path(build['run'])/'submit-manifest.json'
    v['build']=json.loads(submitted.read_text())['build'];v['resources']['dependency']='afterok:'+build_job
    v['pending_build_validation']=dict(build_config=str(submitted),build_config_sha256=mgr.common.sha(submitted),build_job_id=build_job)
    write(vp,v)
    off=submit('validate',vp,'unfused_cc_validation')
    candidate_path=CONFIGS/(CANDIDATE+'-validate-'+DATE+'.json')
    candidate=submit('validate',candidate_path,'candidate_tail_validation')
    mp=CONFIGS/(PREFIX+'-performance-'+DATE+'.json');m=json.loads(mp.read_text())
    def dependency_spec(result):return dict(validation_config=str(Path(result['run'])/'submit-manifest.json'),validation_job_id=result['job'].split(';')[0])
    candidate_spec,off_spec=dependency_spec(candidate),dependency_spec(off)
    queue=dict(schema_version=1,experiment='EXP-128',run_id=PREFIX+'-queue-'+DATE,gpu_arch='gfx936',
        resources=dict(m['resources'],dependency='afterok:'+candidate_spec['validation_job_id']+':'+off_spec['validation_job_id']),
        revalidated_measurement=dict(candidate_spec,measurement_config=str(mp),measurement_config_sha256=mgr.common.sha(mp),
            reference_validations=dict(unfused_cc=off_spec)))
    qp=CONFIGS/(PREFIX+'-queue-'+DATE+'.json');write(qp,queue);submit('measure',qp,'performance')
    files=[vp,qp,receipt,RECORD/'submission-previews.json'];relative=[str(p.relative_to(ROOT)) for p in files]
    subprocess.run(['git','add','--',*relative],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record EXP128 unfused phase-range repair and four-arm continuation submissions','--',*relative],
        cwd=ROOT,capture_output=True,check=True)
    print(json.dumps(dict(receipts=receipts,performance_dependency=queue['resources']['dependency'],
        N=10,cases=20,processes=80,samples=2400,original_complete_cases_reused=368,
        result_inspection='not performed; stop after submission'),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
