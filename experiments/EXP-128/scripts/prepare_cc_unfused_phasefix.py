"""Repair the general CC phase-range guard; register only the twenty missing four-arm cases."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr,revalidate
RECORD=ROOT/'experiments/EXP-128/records/unfused-phasefix-20261027'
CONFIGS=ROOT/'configs/experiments'
PREFIX='EXP-128-cc-local-unfused-phasefix'
CANDIDATE='EXP-128-cc-local-boundary-v5-tail'
DATE='20261027'
OLD_RUN=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-boundary-v5-performance-20261027'


def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def commit(paths,message):
    files=[str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m',message,'--',*files],cwd=ROOT,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def main():
    mgr.require(subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
                =='exp-128-cc-local-real','wrong branch')
    proof=read(RECORD/'phase-selector-model.json')
    mgr.require(proof['complete'] and proof['original_368_cases_unchanged'],'phase-range model failed')
    parser=read(RECORD/'validator-parser-preflight.json')
    mgr.require(parser['complete'] and parser['actual_dispatch_cases']==24 and parser['negative_cases']==48,
                'actual phase-name parser preflight failed')
    old=read(OLD_RUN/'preregistration.json')
    previous_record=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/inspection-983952'
    audit=read(previous_record/'audit.json');rows=read(previous_record/'valid-four-arm-cases.json')
    missing={(r['N'],r['type']+'_1d') for r in audit['missing_cases']}
    cases=[x for x in old['cases'] if (x['N'],x['func']) in missing]
    mgr.require(len(cases)==20 and len({x['N'] for x in cases})==10,'unexpected remaining matrix')
    mgr.require(len(rows)==368 and len(cases)+len(rows)==388,'incomplete matrix partition')
    changed={x['N'] for x in proof['affected']}
    mgr.require(not changed&{x['N'] for x in rows},'repair affects a completed case')
    free=shutil.disk_usage(ROOT).free;mgr.require(free>16*1024**3,'insufficient independent build headroom')
    old_validation=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-boundary-v5-validate-20261027'
    cfg=mgr.load(old_validation/'submit-manifest.json')
    built,lib,cmd,filename=revalidate.existing(cfg)
    accepted=revalidate.verify_acceptance(mgr.locations(cfg,'validate'),built,cmd,filename,'983949')
    mgr.require(accepted==old['validation_acceptances']['candidate'],'retained candidate acceptance differs')
    decisions=dict(reason='Native small phase table is limited to 64^3; general SBCC guard now honors that range.',
        affected_N=sorted(changed),failed_N=702464,unchanged_completed_cases=368,remaining_cases=cases,
        candidate_rebuilt=False,reference_installs_rebuilt=False,new_build='same-CC unfused only',
        candidate_validation_N=sorted(changed),
        measurement_processes=80,event_samples=2400,
        prior_run=str(OLD_RUN),prior_complete_subset=str(previous_record),free_bytes=free,
        source_state_freeze=False,
        merge_policy='Preserve the failed original run. Report two independent measurement segments; compare arms only within each case/segment. Never claim one allocation or one unfused library hash for both segments.')
    write(RECORD/'decisions.json',decisions)
    paths=[ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/tree_node_1D.cpp']
    paths += [ROOT/'experiments/EXP-128/scripts'/n for n in ('preflight_cc_unfused_phasefix.py',
        'validate_cc_unfused_phasefix.py','prepare_cc_unfused_phasefix.py','submit_cc_unfused_phasefix.py')]
    paths += [RECORD/n for n in ('phase-selector-model.json','validator-parser-preflight.json','decisions.json','修复说明.md')]
    source_commit=commit(paths,'EXP128: apply the SBCC three-step phase capacity guard to every role')
    build=read(CONFIGS/'EXP-128-cc-local-unfused-cc-build-20261027.json')
    build.update(run_id=PREFIX+'-build-'+DATE)
    build['build'].update(build_id=PREFIX+'-'+DATE,source_commit=source_commit)
    build['acceptance']='Only rebuild same-CC unfused control with the general capacity guard; retained fusion installs are reused.'
    new_record=str(mgr.locations(build,'build')['run']/'build-provenance.json')
    validations={}
    for arm,prefix in [('candidate',CANDIDATE),('unfused_cc',PREFIX)]:
        v=read(CONFIGS/('EXP-128-cc-local-'+('boundary-v5' if arm=='candidate' else 'unfused-cc')+'-validate-'+DATE+'.json'))
        v.update(run_id=prefix+'-validate-'+DATE)
        for key in ('pending_build_validation','validation_acceptance','validation_acceptances','queued_submission'):v.pop(key,None)
        v['resources'].pop('dependency',None);v['resources'].pop('nodelist',None)
        if arm=='candidate':
            v['validation']['sample_N']=sorted(changed);v['validation']['smoke_N']=[702464,769318]
            v['validation']['scope']='Check retained v5 on the three previously unmeasured phase-capacity geometries; no candidate rebuild.'
        else:
            v['build']=copy.deepcopy(build['build']);v['existing_build_validation']['build_record']=new_record
            v['validation']['sample_N']=sorted(set(v['validation']['sample_N'])|{x['N'] for x in cases})
            v['validation']['smoke_N']=[702464,769318]
            v['validation']['scope']='Numerical, exact three-stage CC execution, and actual phase base/steps; include all three capacity failures and all missing N.'
            script=ROOT/'experiments/EXP-128/scripts/validate_cc_unfused_phasefix.py'
            inputs=v['post_build_validation']['inputs']+[
                dict(path=str(ROOT/'experiments/EXP-128/scripts/validate_cc_local_boundary.py'),sha256=mgr.common.sha(ROOT/'experiments/EXP-128/scripts/validate_cc_local_boundary.py')),
                dict(path=str(RECORD/'phase-selector-model.json'),sha256=mgr.common.sha(RECORD/'phase-selector-model.json'))]
            v['post_build_validation']=dict(script=str(script),sha256=mgr.common.sha(script),inputs=inputs)
        v['acceptance']='Numerical and actual path only; stop on a representative smoke failure, then aggregate independent remaining failures.'
        validations[arm]=v
    measure=copy.deepcopy(old)
    for key in ('validation_acceptance','validation_acceptances','queued_submission','installations_sha256'):measure.pop(key,None)
    measure.update(run_id=PREFIX+'-performance-'+DATE,cases=cases)
    measure['arms']['candidate']=dict(build_record=validations['candidate']['existing_build_validation']['build_record'])
    measure['arms']['unfused_cc']=dict(build_record=new_record)
    measure['comparison_description']='补测原任务983952未完成的20个组合，四版同卡紧邻交替。只修复未融合库的相位容量选择；复用EXP125、第四版与第五版。368个完整旧组合保留为独立测量批次。'
    measure['measurement_conditions']['reference']='20个组合，四版，每组合10/30，共80进程、2400个正式样本；不与旧节点的绝对时间交叉比较。'
    measure['case_scope']='Exactly the twenty incomplete cases from job983952; all four arms repeated per case in this allocation.'
    measure['acceptance']='Both retained-candidate tail path validation and repaired unfused validation must succeed before timing.'
    measure['continuation']=dict(original_run=str(OLD_RUN),original_complete_cases=368,
        original_matrix_N=194,segmented_measurement=True,unfused_repaired_only_for_previously_failing_geometries=True)
    config_paths=[]
    for prefix,task,c in [(PREFIX,'build',build),(CANDIDATE,'validate',validations['candidate']),
                          (PREFIX,'validate',validations['unfused_cc']),(PREFIX,'performance',measure)]:
        path=CONFIGS/(prefix+'-'+task+'-'+DATE+'.json');mgr.require(not path.exists(),'config exists: '+str(path))
        write(path,c);mgr.load(path);config_paths.append(path)
    preview=mgr.task_plan('build',build);write(RECORD/'build-preview.json',preview);config_paths.append(RECORD/'build-preview.json')
    preview=mgr.task_plan('validate',validations['candidate']);write(RECORD/'candidate-tail-preview.json',preview);config_paths.append(RECORD/'candidate-tail-preview.json')
    commit(config_paths,'Register one repaired unfused build and twenty-case four-arm continuation')
    print(json.dumps(dict(source_commit=source_commit,builds=1,candidate_validation_N=3,
        unfused_validation_N=len(validations['unfused_cc']['validation']['sample_N']),
        performance_cases=20,processes=80,samples=2400,reused_complete_cases=368),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
