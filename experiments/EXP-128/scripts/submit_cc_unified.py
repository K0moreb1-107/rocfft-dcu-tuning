"""Submit a pure build, independent validation, then success-gated three-version timing."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

CONFIGS = ROOT/'configs/experiments'


def write(path,value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', default='unified-20261021')
    args = parser.parse_args()
    mgr.require(re.fullmatch(r'[a-z][a-z0-9-]{0,49}', args.series), 'invalid submission series')
    folder = ROOT/'experiments/EXP-128/records'/args.series
    prefix = 'EXP-128-cc-local-'+args.series
    branch = subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    mgr.require(branch=='exp-128-cc-local-real','wrong branch')
    receipt_path = folder/'submission.json'
    mgr.require(not receipt_path.exists(),'submission already recorded; inspect its receipts before resubmitting')
    receipts,previews = {},{}
    label, date = prefix.rsplit('-', 1)
    build_path = CONFIGS/(label+'-build-'+date+'.json')
    validation_path = CONFIGS/(label+'-validate-'+date+'.json')
    measure_path = CONFIGS/(label+'-performance-'+date+'.json')

    def submit(task,path,name):
        argv = [mgr.PYTHON,str(ROOT/'manage.py'),task,'--config',str(path)]
        previews[name] = json.loads(subprocess.check_output(argv,cwd=ROOT,text=True))
        write(folder/'submission-previews.json',previews)
        result = json.loads(subprocess.check_output(argv+['--execute'],cwd=ROOT,text=True))
        receipts[name] = result
        write(receipt_path,dict(receipts=receipts,inspection='not performed; stop after submission',
            prior_installs_rebuilt=False,source_state_freeze=False))
        return result

    build = submit('build',build_path,'build')
    build_job = build['job'].split(';')[0]
    submitted_build = Path(build['run'])/'submit-manifest.json'
    cfg = json.loads(validation_path.read_text())
    cfg['build'] = json.loads(submitted_build.read_text())['build']
    cfg['resources']['dependency'] = 'afterok:'+build_job
    cfg['pending_build_validation'] = dict(build_config=str(submitted_build),
        build_config_sha256=mgr.common.sha(submitted_build),build_job_id=build_job)
    write(validation_path,cfg)
    validation = submit('validate',validation_path,'validation')
    validation_job = validation['job'].split(';')[0]
    measurement = json.loads(measure_path.read_text())
    queue = dict(schema_version=1,experiment='EXP-128',run_id=label+'-queue-'+date,
        gpu_arch='gfx936',resources=dict(measurement['resources'],dependency='afterok:'+validation_job),
        revalidated_measurement=dict(validation_config=str(Path(validation['run'])/'submit-manifest.json'),
            validation_job_id=validation_job,measurement_config=str(measure_path),
            measurement_config_sha256=mgr.common.sha(measure_path)))
    queue_path = CONFIGS/(label+'-queue-'+date+'.json')
    write(queue_path,queue)
    submit('measure',queue_path,'performance')
    files = [validation_path,queue_path,folder/'submission-previews.json',receipt_path]
    subprocess.run(['git','add','--',*(str(x.relative_to(ROOT)) for x in files)],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record independent EXP128 '+args.series+' submissions',
                    '--',*(str(x.relative_to(ROOT)) for x in files)],
                   cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    print(json.dumps(dict(receipts=receipts,dependencies=dict(validation='afterok:'+build_job,
        performance='afterok:'+validation_job),N=len({x['N'] for x in measurement['cases']}),cases=len(measurement['cases']),
        versions=['EXP125','measured EXP128','new candidate'],processes=3*len(measurement['cases']),
        events=90*len(measurement['cases']),result_inspection='not performed; stop after submission'),
        ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
