"""Matched clean repeats, actual stage traces, counters, and whole-row-region interventions."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path[:0]=[str(ROOT),str(ROOT/'tools/fft_measurement'),str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
import cufft261012_contract as contract
from diagnose_rows_v3_regression import launch,check_process,case_environment,check_rule_audit
from cc_dispatch import inspect_dispatch
from cc_regression_evidence import trace_evidence,actual_sources,pmc_blocks,select_pmc_windows
from cc_v5_regression_common import rtc_sources,restore_row,adaptive_pairs,profile_evidence
from validate_cc_local_boundary import validate_names


def write(path,x):
    p=path.with_name(path.name+'.tmp');p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');p.replace(path)


def temporary(a,label):
    p=a.cache/'process-tmp'/label;p.mkdir(parents=True)
    return p


def cleanup(a,p):
    root=(a.cache/'process-tmp').resolve();resolved=p.resolve()
    mgr.require(resolved!=root and root in resolved.parents,'temporary cleanup outside this diagnostic cache')
    size=sum(x.stat().st_size for x in p.rglob('*') if x.is_file())
    shutil.rmtree(p)
    return size


def timing(a,cfg,item,env,gpu,phase):
    label='%04d_%d_%s_%s_%s'%(item['index'],item['N'],item['func'],item['arm'],phase)
    folder=a.run/'timings'/label;folder.mkdir(parents=True)
    output=folder/'harness';output.mkdir();tmp=temporary(a,label)
    e=dict(item,valid=False,formal=False,phase=phase,folder=str(folder))
    try:
        selected,binary,identity,linked=case_environment(a,cfg,item,env,gpu)
        selected.update(FFT_TEST_OUT=str(output),TMPDIR=str(tmp))
        if item.get('rules_manifest'):selected['CC_RTC_DIAG_LOG']=str(folder/'source-audit.tsv')
        result=launch([binary,item['N'],1,item['func']],selected,folder,'timing')
        check=check_process(folder,'timing',output,item['N'],item['func'],result)
        values=contract.validate_process(contract.read_rows(output/'fft_test_1d.csv')[0],
            contract.read_samples(output/'fft_test_1d.samples.csv'),check,item['N'],item['func'],30)
        if item.get('rules_manifest'):e['source_audit']=check_rule_audit(folder/'source-audit.tsv',item)
        e.update(valid=True,check=check,samples_ms=values,statistics_ms=contract.statistics_for(values),
                 library_sha256=identity['library_sha256'])
    except Exception as error:e['error']=dict(kind=type(error).__name__,message=str(error))
    finally:e['temporary_bytes_removed']=cleanup(a,tmp)
    write(folder/'review.json',e);print('TIMING',phase,item['N'],item['func'],item['arm'],e['valid'],flush=True)
    return e


def trace(a,cfg,item,env,gpu):
    label='%04d_%d_%s_%s'%(item['index'],item['N'],item['func'],item['arm'])
    folder=a.run/'profiles'/label;folder.mkdir(parents=True)
    meta,profile=folder/'metadata',folder/'profile'
    for p in (meta,meta/'harness',profile,profile/'harness',profile/'data'):p.mkdir()
    tmp=temporary(a,'trace-'+label)
    e=dict(item,valid=False,formal=False,folder=str(folder),timing_valid=False)
    try:
        selected,binary,identity,linked=case_environment(a,cfg,item,env,gpu)
        selected['TMPDIR']=str(tmp);(folder/'ldd.txt').write_text(linked)
        m_env=dict(selected,FFT_TEST_OUT=str(meta/'harness'),ROCFFT_LAYER='40',
            ROCFFT_LOG_PLAN_PATH=str(meta/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(meta/'rtc.txt'))
        result=launch([binary,item['N'],1,item['func']],m_env,meta,'metadata')
        e['metadata_check']=check_process(meta,'metadata',meta/'harness',item['N'],item['func'],result)
        result=launch([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
            '-o',profile/'trace','-d',profile/'data',binary,item['N'],1,item['func']],
            dict(selected,FFT_TEST_OUT=str(profile/'harness')),profile,'trace')
        e['profile_check']=check_process(profile,'trace',profile/'harness',item['N'],item['func'],result)
        plan=(meta/'plan.txt').read_text();events=json.loads((profile/'trace.json').read_text())['traceEvents']
        launches,checked=inspect_dispatch(plan,events,item['func']);names=[x['name'] for x in launches]
        c,q=(cfg['geometry'][str(item['N'])][k] for k in ('C','Q'))
        if item['arm']=='unfused_cc':validate_names(names,c,q,item['func'],False)
        else:
            version=cfg['kernel_versions'][item['arm']];roles=(4,5) if item['func']=='z2d_1d' else (6,7)
            mgr.require(len(names)==2 and all('_cc_local_v%d_role%d_C%d_Q%d_'%(version,role,c,q) in name
                        for role,name in zip(roles,names)),'unexpected actual fused geometry/version')
        e['trace']=dict(kernel_names=names,contract=checked)
        e['actual_sources']=actual_sources((meta/'rtc.txt').read_text(),names)
        mgr.require(all(value['available'] for name,value in e['actual_sources'].items() if name.startswith('fft_rtc_')),
                    'actual FFT source missing')
        # Correlation/dispatch validity is independent of the profiler's timestamp quality.
        e['trace'],warning=profile_evidence(plan,events,item['func'])
        e['timing_valid']=warning is None
        if warning:e['timestamp_warning']=warning
        e['occupancy_log_values']=list(map(int,re.findall(r'Kernel occupancy:\s*(\d+)',plan)))
        e.update(valid=True,library_sha256=identity['library_sha256'])
    except Exception as error:e['error']=dict(kind=type(error).__name__,message=str(error))
    finally:e['temporary_bytes_removed']=cleanup(a,tmp)
    write(folder/'review.json',e);print('TRACE',item['N'],item['func'],item['arm'],e['valid'],e['timing_valid'],flush=True)
    return e


def counter(a,cfg,item,env,gpu,traces,mode):
    label='%04d_%d_%s_%s_%s_%s'%(item['index'],item['N'],item['func'],item['arm'],mode,item.get('variant','original'))
    folder=a.run/'pmc'/label;folder.mkdir(parents=True);output=folder/'harness';output.mkdir()
    data=folder/'data';data.mkdir();tmp=temporary(a,'pmc-'+label)
    e=dict(item,mode=mode,valid=False,formal=False,folder=str(folder))
    try:
        reference=traces[item['N'],item['func'],item['arm']]
        mgr.require(reference['valid'],'matching dispatch/source evidence unavailable')
        names=reference['trace']['kernel_names']
        selected,binary,identity,linked=case_environment(a,cfg,item,env,gpu)
        selected.update(FFT_TEST_OUT=str(output),TMPDIR=str(tmp))
        if item.get('rules_manifest'):selected['CC_RTC_DIAG_LOG']=str(folder/'source-audit.tsv')
        flag={'general':'--pmc','read':'--pmc-read','write':'--pmc-write'}[mode]
        result=launch([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
            flag,'--pmc-type','0','-o',folder/'counter','-d',data,binary,item['N'],1,item['func']],selected,folder,'pmc')
        check=check_process(folder,'pmc',output,item['N'],item['func'],result)
        if item.get('rules_manifest'):e['source_audit']=check_rule_audit(folder/'source-audit.tsv',item)
        windows=select_pmc_windows(pmc_blocks((folder/'counter.txt').read_text()),names)
        fields=sorted({k for window in windows for block in window for k in block['fields']})
        mgr.require(any(re.search(r'cache|shared memory|vgpr|SQ_|memory operation',k,re.I) for k in fields),'counter field schema is empty')
        write(folder/'measured-counter-windows.json',dict(mode=mode,export_type=0,
            windows=windows,unit_policy='Raw SDK field names/units. Instrumented kernel time is not clean elapsed time.',
            setup_and_correctness_excluded=True,timing_warmups=10))
        e.update(valid=True,check=check,measured_windows=30,fields=fields,export_type=0,library_sha256=identity['library_sha256'])
    except Exception as error:e['error']=dict(kind=type(error).__name__,message=str(error))
    finally:e['temporary_bytes_removed']=cleanup(a,tmp)
    write(folder/'review.json',e);print('PMC',mode,item['N'],item['func'],item['arm'],e['valid'],flush=True)
    return e


def rules(a,trial,traces,variant):
    n,func=trial['N'],trial['func'];cur=traces[n,func,'candidate'];old=traces[n,func,'previous']
    mgr.require(cur['valid'] and old['valid'],'intervention lacks valid matched default sources')
    name=cur['trace']['kernel_names'][1];older=old['trace']['kernel_names'][1]
    current=rtc_sources((Path(cur['folder'])/'metadata/rtc.txt').read_text())[name]
    previous=rtc_sources((Path(old['folder'])/'metadata/rtc.txt').read_text())[older]
    changed=restore_row(current,previous,variant)
    folder=a.run/'row-interventions'/('%d-%s-%s'%(n,func,variant));folder.mkdir(parents=True)
    original,replacement=folder/'original.cpp',folder/'replacement.cpp'
    original.write_text(current);replacement.write_text(changed)
    path=folder/'rules.tsv';path.write_text(name+'\t'+str(original)+'\t'+str(replacement)+'\n')
    rule=dict(name=name,original=str(original),replacement=str(replacement),
        original_sha256=mgr.common.sha(original),replacement_sha256=mgr.common.sha(replacement))
    return dict(trial,arm='candidate',variant=variant,rules=[rule],rules_manifest=str(path),
        rules_manifest_sha256=mgr.common.sha(path),required_source_names=[name])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('config','run','build','cache'):parser.add_argument('--'+n,type=Path,required=True)
    a=parser.parse_args();cfg=mgr.load(a.config)
    for n in ('run','build','cache'):setattr(a,n,mgr.inside(getattr(a,n)))
    mgr.common.single_gpu_allocation(os.environ)
    env=mgr.environment(a.cache);env['FFT_TEST_ITERS']='30'
    program=cfg['diagnostic_program'];origin=json.loads(Path(program['provenance']).read_text())
    mgr.require(origin['complete'] and origin['job_id']=='984725','reuse the completed continuation executable')
    mgr.require(mgr.common.sha(Path(program['provenance']))==program['provenance_sha256'],'program provenance differs')
    for k in ('binary','identity'):mgr.require(mgr.common.sha(Path(program[k]))==program[k+'_sha256'],'diagnostic executable differs')
    gpu=json.loads(subprocess.check_output([program['identity']],env=env,text=True))
    mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936','single gfx936 required')
    selection=cfg['regression_selection']
    record=dict(complete=False,formal=False,job_id=os.environ['SLURM_JOB_ID'],gpu=gpu,host=socket.gethostname(),
        start=datetime.datetime.now(datetime.timezone.utc).isoformat(),timing=[],traces=[],pmc=[],interventions=[],anchors=[],
        failures=[],timestamp_warnings=[],source_comparisons=[],adaptive_pairs=[])
    def save():
        record['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();write(a.run/'diagnostic-result.json',record)
    def accept(kind,e):
        record[kind].append(e)
        if not e['valid']:record['failures'].append(dict(stage=kind,N=e['N'],func=e['func'],arm=e['arm'],error=e['error']))
        if e.get('timestamp_warning'):record['timestamp_warnings'].append(dict(N=e['N'],func=e['func'],arm=e['arm'],warning=e['timestamp_warning']))
        if len(record[kind])%5==0 or not e['valid']:save()
    try:
        schedule=selection['clean_schedule']
        for repeat,order in [('repeat-1',schedule),('repeat-2',list(reversed(schedule)))]:
            for item in order:accept('timing',timing(a,cfg,item,env,gpu,repeat))
            save()
        adaptive=adaptive_pairs(selection,record['timing']);record['adaptive_pairs']=adaptive
        detailed={(x['N'],x['func'],x['arm']):dict(x) for x in selection['mandatory_detailed']}
        for x in adaptive:
            for arm in (x['reference'],'candidate'):detailed.setdefault((x['N'],x['func'],arm),dict(N=x['N'],func=x['func'],arm=arm))
        # Both arms are required for a source intervention even when a positive control is adaptive.
        for x in selection['ablations']:
            for arm in ('previous','candidate'):detailed.setdefault((x['N'],x['func'],arm),dict(N=x['N'],func=x['func'],arm=arm))
        details=sorted(detailed.values(),key=lambda x:(x['N'],x['func'],x['arm']))
        traces={}
        for i,item in enumerate(details):
            item=dict(item,index=i);e=trace(a,cfg,item,env,gpu);traces[item['N'],item['func'],item['arm']]=e;accept('traces',e)
        save()
        for x in selection['cases']:
            old=traces.get((x['N'],x['func'],'previous'));cur=traces.get((x['N'],x['func'],'candidate'))
            if not old or not cur or not old['valid'] or not cur['valid']:continue
            left=rtc_sources((Path(old['folder'])/'metadata/rtc.txt').read_text());right=rtc_sources((Path(cur['folder'])/'metadata/rtc.txt').read_text())
            pairs=[]
            for stage,(old_name,new_name) in enumerate(zip(old['trace']['kernel_names'],cur['trace']['kernel_names'])):
                same=left[old_name]==right[new_name].replace('_cc_local_v5_','_cc_local_v4_')
                pairs.append(dict(stage=stage,v4=old_name,v5=new_name,equal_except_version_name=same))
            record['source_comparisons'].append(dict(N=x['N'],func=x['func'],stages=pairs))
        save()
        for i,item in enumerate(details):
            item=dict(item,index=i)
            modes=['general','read']+(['write'] if item['func']=='z2d_1d' else [])
            for mode in modes:accept('pmc',counter(a,cfg,item,env,gpu,traces,mode))
        for i,trial in enumerate(selection['ablations']):
            try:
                modified=rules(a,trial,traces,trial['variant']);identity=rules(a,trial,traces,'identity')
                base=dict(N=trial['N'],func=trial['func'],index=i)
                order=[dict(base,arm='previous'),dict(base,arm='candidate'),dict(identity,index=i),dict(modified,index=i),
                       dict(identity,index=i),dict(base,arm='candidate')]
                if i%2:order[2:4]=reversed(order[2:4])
                results=[]
                for position,item in enumerate(order):
                    e=timing(a,cfg,item,env,gpu,'intervention-%d-%d'%(i,position));accept('interventions',e);results.append(e)
                if all(e['valid'] for e in results):
                    for mode in ('general','read')+ (('write',) if trial['func']=='z2d_1d' else ()):
                        accept('pmc',counter(a,cfg,dict(modified,index=len(details)+i),env,gpu,traces,mode))
            except Exception as error:
                record['failures'].append(dict(stage='intervention-preparation',**trial,error=str(error)));save()
        # End anchors test whether the original severe comparisons changed over the diagnostic.
        last=[]
        for x in selection['cases']:
            refs=[ref for ref in x['references'] if x['ratios'][ref]<.95]
            if refs:
                for arm in refs+['candidate']:last.append(dict(index=len(last),N=x['N'],func=x['func'],arm=arm))
        for item in reversed(last):accept('anchors',timing(a,cfg,item,env,gpu,'end-anchor'))
        record['complete']=not record['failures'];record['all_requested_workflows_attempted']=True
        record['removed_temporary_bytes']=sum(e.get('temporary_bytes_removed',0) for k in ('timing','traces','pmc','interventions','anchors') for e in record[k])
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    mgr.require(record['complete'],'diagnostic process/counter failures collected; inspect all case records')


if __name__=='__main__':main()
