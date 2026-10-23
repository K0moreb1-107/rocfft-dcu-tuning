"""Trace all selected regressions and collect matched counter evidence; never formal timing."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
import cufft261012_contract as contract
from validate_cc_local_unified import read_numerical_outputs
from cc_regression_evidence import trace_evidence, actual_sources, pmc_blocks, select_pmc_windows


def write(path, data):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def launch(argv, env, folder, label, timeout=300):
    argv = list(map(str,argv))
    with (folder/(label+'.out')).open('xb') as out, (folder/(label+'.err')).open('xb') as err:
        try:
            proc = subprocess.run(argv,env=env,cwd=folder,stdout=out,stderr=err,timeout=timeout)
            result = dict(command=argv,returncode=proc.returncode)
        except (OSError,subprocess.TimeoutExpired) as error:
            result = dict(command=argv,returncode=None,error=str(error))
    write(folder/(label+'-command.json'),result)
    return result


def check_process(folder, label, output, n, func, result):
    status = re.search(r'exited with status:\s*(\d+)',(folder/(label+'.err')).read_text(errors='replace'))
    child = int(status.group(1)) if status else result['returncode']
    numerical = read_numerical_outputs(output,n,func,child)
    mgr.require(result['returncode'] == 0,'process/profiler did not complete: '+str(result))
    return numerical


def case_environment(a,cfg,item,env,gpu):
    arm = cfg['arms'][item['arm']]
    library = mgr.inside(arm['install'])/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(library) == arm['library_sha256'],'diagnostic library differs')
    binary = mgr.inside(cfg['diagnostic_program']['binary'])
    mgr.require(mgr.common.sha(binary) == cfg['diagnostic_program']['binary_sha256'],'diagnostic binary differs')
    identity = mgr.inside(cfg['diagnostic_program']['identity'])
    actual = json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(actual == gpu,'diagnostic GPU changed')
    selected = dict(env,LD_PRELOAD=str(library),LD_LIBRARY_PATH=str(library.parent)+':'+env['LD_LIBRARY_PATH'])
    if item.get('rules_manifest'):
        apply_rules(selected,cfg,item)
    linked = subprocess.check_output(['ldd',str(binary)],env=selected,text=True)
    loaded = [mgr.inside(line.strip().split('=>')[-1].strip().split()[0])
              for line in linked.splitlines() if 'librocfft.so' in line]
    mgr.require('not found' not in linked and len(set(loaded)) == 1 and loaded[0] == library,
                'loader did not select the registered library')
    return selected,binary,arm,linked


def trace_case(a,cfg,item,env,gpu):
    n,func,arm = item['N'],item['func'],item['arm']
    folder = a.run/'profiles'/('%04d_%d_%s_%s'%(item['index'],n,func,arm))
    folder.mkdir(parents=True)
    entry = dict(item,valid=False,formal=False,folder=str(folder))
    try:
        selected,binary,identity,linked = case_environment(a,cfg,item,env,gpu)
        (folder/'ldd.txt').write_text(linked)
        entry['library_sha256'] = identity['library_sha256']
        meta,profile = folder/'metadata',folder/'profile'
        for path in (meta,meta/'harness',profile,profile/'harness',profile/'data'):
            path.mkdir()
        meta_env = dict(selected,FFT_TEST_OUT=str(meta/'harness'),ROCFFT_LAYER='40',
            ROCFFT_LOG_PLAN_PATH=str(meta/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(meta/'rtc.txt'))
        result = launch([binary,n,1,func],meta_env,meta,'metadata')
        entry['metadata_check'] = check_process(meta,'metadata',meta/'harness',n,func,result)
        # Metadata/occupancy logging is absent from this separate process.
        prof_env = dict(selected,FFT_TEST_OUT=str(profile/'harness'))
        result = launch([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
            '-o',profile/'trace','-d',profile/'data',binary,n,1,func],prof_env,profile,'trace')
        entry['profile_check'] = check_process(profile,'trace',profile/'harness',n,func,result)
        plan = (meta/'plan.txt').read_text()
        events = json.loads((profile/'trace.json').read_text())['traceEvents']
        entry['trace'] = trace_evidence(plan,events,func)
        entry['actual_sources'] = actual_sources((meta/'rtc.txt').read_text(),entry['trace']['kernel_names'])
        if arm in ('previous','candidate'):
            geometry = cfg['geometry'][str(n)]
            c,q = geometry['C'],geometry['Q']
            roles = (4,5) if func == 'z2d_1d' else (6,7)
            names = entry['trace']['kernel_names']
            mgr.require(len(names) == 2 and all('_cc_local_v%d_role%d_C%d_Q%d_'%(cfg['kernel_versions'][arm],role,c,q) in name
                        for role,name in zip(roles,names)), 'candidate did not use generic CC fusion')
            if func == 'd2z_1d':
                mgr.require(names[1].endswith('_reg'),'candidate forward rows not register loaded')
        entry['maximum_active_workgroups'] = list(map(int,re.findall(r'Kernel occupancy:\s*(\d+)',plan)))[-len(names):]
        entry['valid'] = True
    except Exception as error:
        entry['error'] = dict(kind=type(error).__name__,message=str(error),
                              returncode=getattr(error,'returncode',None),stage=getattr(error,'stage',None))
    write(folder/'review.json',entry)
    print('TRACE',n,func,arm,entry['valid'],entry.get('error',''),flush=True)
    return entry


def counter_case(a,cfg,item,env,gpu,traces,mode,formats):
    n,func,arm = item['N'],item['func'],item['arm']
    folder = a.run/'pmc'/('%04d_%d_%s_%s_%s_%s'%(item['index'],n,func,arm,mode,item.get('variant','original')))
    folder.mkdir(parents=True)
    entry = dict(item,mode=mode,formal=False,valid=False,folder=str(folder),attempts=[])
    try:
        reference = traces[(n,func,arm)]
        mgr.require(reference['valid'],'no accepted trace for this exact counter case')
        selected,binary,identity,linked = case_environment(a,cfg,item,env,gpu)
        flag = '--pmc' if mode == 'general' else '--pmc-read'
        for export_type in ([formats[mode]] if mode in formats else [2,0]):
            attempt = folder/('format-'+str(export_type))
            output,data = attempt/'harness',attempt/'data'
            for path in (attempt,output,data):
                path.mkdir()
            selected['FFT_TEST_OUT'] = str(output)
            if item.get('rules_manifest'):
                selected['CC_RTC_DIAG_LOG'] = str(attempt/'source-audit.tsv')
            try:
                result = launch([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
                    flag,'--pmc-type',export_type,'-o',attempt/'counter','-d',data,binary,n,1,func],selected,attempt,'pmc')
                check = check_process(attempt,'pmc',output,n,func,result)
                if item.get('rules_manifest'): check_rule_audit(attempt/'source-audit.tsv',item)
                blocks = pmc_blocks((attempt/'counter.txt').read_text())
                windows = select_pmc_windows(blocks,reference['trace']['kernel_names'])
                fields = sorted({key for window in windows for block in window for key in block['fields']})
                mgr.require(any(re.search(r'SQ_|TCC_|TCP_|cache|bank conflict|processed ALU|memory operation',key,re.I)
                                for key in fields),'counter file has no recognizable performance fields')
                write(folder/'measured-counter-windows.json',dict(mode=mode,export_type=export_type,
                    unit_policy='raw SDK field names and units',windows=windows,
                    setup_and_correctness_excluded=True,timing_warmups=10))
                formats[mode] = export_type
                entry.update(valid=True,check=check,export_type=export_type,
                    library_sha256=identity['library_sha256'],counter_blocks=len(blocks),
                    measured_windows=len(windows),fields=fields)
                entry['attempts'].append(dict(export_type=export_type,valid=True))
                break
            except Exception as error:
                entry['attempts'].append(dict(export_type=export_type,valid=False,error=str(error)))
        mgr.require(entry['valid'],'all allowed counter export formats failed: '+str(entry['attempts']))
    except Exception as error:
        entry['error'] = dict(kind=type(error).__name__,message=str(error),
                              returncode=getattr(error,'returncode',None),stage=getattr(error,'stage',None))
    write(folder/'review.json',entry)
    print('PMC',n,func,arm,mode,entry['valid'],entry.get('error',''),flush=True)
    return entry


def apply_rules(env,cfg,item):
    """Only the copied RTC row body changes; the v3 library/plan and ABI remain fixed."""
    shim=cfg['rtc_shim']
    mgr.require(mgr.common.sha(Path(shim['binary']))==shim['sha256'],'diagnostic source shim differs')
    mgr.require(mgr.common.sha(Path(item['rules_manifest']))==item['rules_manifest_sha256'],'RTC rules differ')
    for rule in item['rules']:
        for key in ('original','replacement'):
            mgr.require(mgr.common.sha(Path(rule[key]))==rule[key+'_sha256'],'RTC rule source differs')
    library=mgr.inside(cfg['arms']['candidate']['install'])/'lib/librocfft.so.0.1'
    env.update(LD_PRELOAD=shim['binary']+':'+str(library),CC_RTC_DIAG_RULES=item['rules_manifest'])


def check_rule_audit(path,item):
    lines=[line.split('\t') for line in path.read_text().splitlines()]
    mgr.require(lines and all(status in ('identity','override') for status,name in lines),'RTC source mismatch')
    hits={name for status,name in lines}
    mgr.require(set(item['required_source_names'])<=hits,'target timing row source was not replaced')
    return lines


def replace_row_parts(current,previous,name,variant):
    """Restore whole generated load/store regions rather than changing indices piecemeal."""
    previous=previous.replace('_cc_local_v2_','_cc_local_v3_')
    def arguments(text):
        begin=text.index(name+'(')+len(name)+1
        return text[begin:text.index(') {',begin)]
    mgr.require(arguments(current)==arguments(previous),'row restore ABI differs')
    for text in (current,previous):
        mgr.require(text.count('extern "C" __global__')==1,'ambiguous RTC entry')
    register=lambda text:re.search(r'scalar_type R\[\d+\]',text[text.index('extern "C" __global__'):])[0]
    mgr.require(register(current)==register(previous),'row restore native register mapping differs')
    if variant in ('restore_input','restore_both'):
        start,end='// load global into registers\n','// calc the thread_in_device'
        a,b=current.index(start),current.index(end,current.index(start))
        x,y=previous.index(start),previous.index(end,previous.index(start))
        current=current[:a]+previous[x:y]+current[b:]
    if variant in ('restore_output','restore_both'):
        marker='// call a post-store from registers to lds (if necessary)'
        a=current.index('if(direct_store_from_reg) {',current.index(marker))
        b=previous.index('if(direct_store_from_reg) {',previous.index(marker))
        current=current[:a]+previous[b:]
    return current


def source_rules(a,cfg,item,traces):
    n,func=item['N'],item['func']
    target=traces[n,func,'candidate'];older=traces[n,func,'previous']
    mgr.require(target['valid'] and older['valid'],'row restoration lacks a matched accepted trace')
    def sources(entry):
        text=(Path(entry['folder'])/'metadata/rtc.txt').read_text()
        # rocFFT's RTC log adds one newline before its end delimiter.
        return {name:source[:-1] for name,source in re.findall(
            r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S)}
    current,previous=sources(target),sources(older)
    role=5 if func=='z2d_1d' else 7
    folder=a.run/'rtc-restorations'/('%d-%s-%s'%(n,func,item['variant']))
    folder.mkdir(parents=True)
    rules,manifest=[],[]
    for index,(name,source) in enumerate(current.items()):
        if '_cc_local_v3_role%d_'%role not in name: continue
        old_name=name.replace('_cc_local_v3_','_cc_local_v2_')
        mgr.require(old_name in previous,'previous RTC source missing for '+name)
        changed=replace_row_parts(source,previous[old_name],name,item['variant'])
        original,replacement=folder/(str(index)+'-original.cpp'),folder/(str(index)+'-replacement.cpp')
        original.write_text(source);replacement.write_text(changed)
        manifest.append(name+'\t'+str(original)+'\t'+str(replacement))
        rules.append(dict(name=name,original=str(original),replacement=str(replacement),
            original_sha256=mgr.common.sha(original),replacement_sha256=mgr.common.sha(replacement)))
    required=[target['trace']['kernel_names'][1]]
    mgr.require(set(required)<={rule['name'] for rule in rules},'no timing row source rule')
    path=folder/'rules.tsv';path.write_text('\n'.join(manifest)+'\n')
    return dict(item,arm='candidate',rules=rules,rules_manifest=str(path),
                rules_manifest_sha256=mgr.common.sha(path),required_source_names=required)


def timing_case(a,cfg,item,env,gpu,label,metadata=False):
    folder=a.run/'timings'/('%04d_%d_%s_%s_%s'%(item['index'],item['N'],item['func'],item['arm'],label))
    folder.mkdir(parents=True);output=folder/'harness';output.mkdir()
    entry=dict(item,formal=False,valid=False,phase=label,metadata=metadata,folder=str(folder))
    try:
        selected,binary,identity,linked=case_environment(a,cfg,item,env,gpu)
        selected.update(FFT_TEST_OUT=str(output),TMPDIR=str(folder))
        if metadata: selected.update(ROCFFT_LAYER='8',ROCFFT_LOG_PLAN_PATH=str(folder/'plan.txt'))
        if item.get('rules_manifest'): selected['CC_RTC_DIAG_LOG']=str(folder/'source-audit.tsv')
        result=launch([binary,item['N'],1,item['func']],selected,folder,'timing')
        check=check_process(folder,'timing',output,item['N'],item['func'],result)
        values=contract.validate_process(contract.read_rows(output/'fft_test_1d.csv')[0],
            contract.read_samples(output/'fft_test_1d.samples.csv'),check,item['N'],item['func'],30)
        entry.update(check=check,samples_ms=values,statistics_ms=contract.statistics_for(values),
            library_sha256=identity['library_sha256'])
        if item.get('rules_manifest'):
            entry['source_audit']=check_rule_audit(folder/'source-audit.tsv',item)
        if metadata:
            occupancy=list(map(int,re.findall(r'Kernel occupancy:\s*(\d+)',(folder/'plan.txt').read_text())))
            mgr.require(len(occupancy)>=80 and occupancy[-80:]==occupancy[-2:]*40,'incomplete capacity metadata')
            entry['maximum_active_workgroups']=occupancy[-2:]
        entry['valid']=True
    except Exception as error:
        entry['error']=dict(kind=type(error).__name__,message=str(error))
    write(folder/'review.json',entry)
    print('TIMING',label,item['N'],item['func'],item['arm'],entry['valid'],entry.get('error',''),flush=True)
    return entry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','run','build','cache'): parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();cfg=mgr.load(a.config)
    for name in ('run','build','cache'): setattr(a,name,mgr.inside(getattr(a,name)))
    mgr.common.single_gpu_allocation(os.environ)
    program=cfg['diagnostic_program']
    original=json.loads(mgr.inside(program['provenance']).read_text())
    mgr.require(original['complete'] and original['job_id']=='960099','wrong original timing evidence')
    mgr.require(mgr.common.sha(Path(program['provenance']))==program['provenance_sha256'],'original provenance differs')
    for key in ('binary','identity'):
        mgr.require(mgr.common.sha(Path(program[key]))==program[key+'_sha256'],'registered measurement executable differs')
    env=mgr.environment(a.cache);env['FFT_TEST_ITERS']='30'
    gpu=json.loads(subprocess.check_output([program['identity']],env=env,text=True))
    mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936','one gfx936 required')
    mgr.require(re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16)>0,'invalid GPU identity')
    record=dict(complete=False,formal=False,gpu=gpu,job_id=os.environ['SLURM_JOB_ID'],host=socket.gethostname(),
        original_formal_job='960099',start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        timing=[],traces=[],pmc=[],ablations=[],anchors=[],failures=[])
    def save():
        record['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        write(a.run/'diagnostic-result.json',record)
    def accept(kind,entry):
        record[kind].append(entry)
        if not entry['valid']: record['failures'].append(dict(stage=kind,N=entry['N'],func=entry['func'],
            arm=entry.get('arm'),variant=entry.get('variant'),error=entry['error']))
        save()
    traces,formats={},{}
    try:
        schedule=contract.schedule(cfg)
        for item in schedule: accept('timing',timing_case(a,cfg,item,env,gpu,'before'))
        for item in schedule:
            entry=trace_case(a,cfg,item,env,gpu)
            traces[item['N'],item['func'],item['arm']]=entry;accept('traces',entry)
        for item in cfg['pmc_cases']:
            for mode in item['modes']: accept('pmc',counter_case(a,cfg,item,env,gpu,traces,mode,formats))
        prepared={}
        for index,seed in enumerate(cfg['ablations']):
            try:
                item=source_rules(a,cfg,dict(seed,index=index),traces)
                prepared.setdefault((seed['N'],seed['func']),[]).append(item)
            except Exception as error:
                record['failures'].append(dict(stage='ablation-preparation',**seed,error=str(error)));save()
        successful=[]
        for group_index,((n,func),items) in enumerate(prepared.items()):
            anchor=dict(index=group_index,N=n,func=func)
            order=('previous','candidate') if group_index%2==0 else ('candidate','previous')
            for arm in order:
                accept('anchors',timing_case(a,cfg,dict(anchor,arm=arm),env,gpu,'ablation-before'))
            for item in items if group_index%2==0 else reversed(items):
                entry=timing_case(a,cfg,item,env,gpu,item['variant'])
                accept('ablations',entry)
                if entry['valid']: successful.append(item)
            accept('anchors',timing_case(a,cfg,dict(anchor,arm='candidate'),env,gpu,'ablation-after'))
        # Profilers run after the adjacent clean restoration comparisons.
        for item in successful:
            if item['pmc_modes']:
                accept('ablations',timing_case(a,cfg,item,env,gpu,item['variant']+'-metadata',metadata=True))
                for mode in item['pmc_modes']:
                    accept('pmc',counter_case(a,cfg,item,env,gpu,traces,mode,formats))
        severe={(x['N'],x['func']) for x in cfg['selection'] if 'all 24 ratios below 0.95' in x['reasons']}
        # Reverse the within-pair order to expose process-order effects.
        pairs=[schedule[i:i+2] for i in range(0,len(schedule),2)]
        for pair in pairs:
            if (pair[0]['N'],pair[0]['func']) in severe:
                for item in reversed(pair): accept('timing',timing_case(a,cfg,item,env,gpu,'after'))
        mgr.require(json.loads(subprocess.check_output([program['identity']],env=env,text=True))==gpu,'GPU changed at completion')
        record['counter_formats']=formats
        record['complete']=not record['failures']
    finally:
        save()
    mgr.require(record['complete'],'independent diagnostic failures collected; inspect diagnostic-result.json')


if __name__=='__main__': main()

