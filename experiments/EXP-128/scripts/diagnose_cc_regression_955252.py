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
        if arm == 'candidate':
            geometry = cfg['geometry'][str(n)]
            c,q = geometry['C'],geometry['Q']
            roles = (4,5) if func == 'z2d_1d' else (6,7)
            names = entry['trace']['kernel_names']
            mgr.require(len(names) == 2 and all('_cc_local_v2_role%d_C%d_Q%d_'%(role,c,q) in name
                        for role,name in zip(roles,names)), 'candidate did not use generic CC fusion')
            if func == 'd2z_1d':
                mgr.require(names[1].endswith('_reg'),'candidate forward rows not register loaded')
        entry['valid'] = True
    except Exception as error:
        entry['error'] = dict(kind=type(error).__name__,message=str(error),
                              returncode=getattr(error,'returncode',None),stage=getattr(error,'stage',None))
    write(folder/'review.json',entry)
    print('TRACE',n,func,arm,entry['valid'],entry.get('error',''),flush=True)
    return entry


def counter_case(a,cfg,item,env,gpu,traces,mode,formats):
    n,func,arm = item['N'],item['func'],item['arm']
    folder = a.run/'pmc'/('%04d_%d_%s_%s_%s'%(item['index'],n,func,arm,mode))
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
            try:
                result = launch([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
                    flag,'--pmc-type',export_type,'-o',attempt/'counter','-d',data,binary,n,1,func],selected,attempt,'pmc')
                check = check_process(attempt,'pmc',output,n,func,result)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config','run','build','cache'):
        parser.add_argument('--'+name,type=Path,required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    for name in ('run','build','cache'):
        setattr(a,name,mgr.inside(getattr(a,name)))
    mgr.common.single_gpu_allocation(os.environ)
    program = cfg['diagnostic_program']
    original = json.loads(mgr.inside(program['provenance']).read_text())
    mgr.require(original['complete'] and original['job_id'] == '955252','wrong original performance run')
    mgr.require(mgr.common.sha(mgr.inside(program['provenance'])) == program['provenance_sha256'],
                'original performance provenance differs')
    for key,digest in [('binary',program['binary_sha256']),('identity',program['identity_sha256'])]:
        mgr.require(mgr.common.sha(mgr.inside(program[key])) == digest,'registered executable differs')
    mgr.require(all(arm['binary_sha256'] == program['binary_sha256'] for arm in original['arms'].values()),
                'diagnostic does not reuse the measured executable')
    env = mgr.environment(a.cache)
    env['FFT_TEST_ITERS'] = '30'
    gpu = json.loads(subprocess.check_output([program['identity']],env=env,text=True))
    mgr.require(gpu == program['gpu'],'diagnostic must use the original GPU/runtime')
    record = dict(complete=False,formal=False,gpu=gpu,job_id=os.environ['SLURM_JOB_ID'],host=socket.gethostname(),
        start=datetime.datetime.now(datetime.timezone.utc).isoformat(),traces=[],pmc=[],failures=[])
    def save():
        record['end'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write(a.run/'diagnostic-result.json',record)
    traces,formats = {},{}
    try:
        for item in contract.schedule(cfg):
            entry = trace_case(a,cfg,item,env,gpu)
            traces[(item['N'],item['func'],item['arm'])] = entry
            record['traces'].append(entry)
            if not entry['valid']:
                record['failures'].append(dict(kind='trace',**item,error=entry['error']))
            save()
        for item in cfg['pmc_cases']:
            for mode in item['modes']:
                entry = counter_case(a,cfg,item,env,gpu,traces,mode,formats)
                record['pmc'].append(entry)
                if not entry['valid']:
                    record['failures'].append(dict(kind='pmc',mode=mode,**item,error=entry['error']))
                save()
        record['complete'] = (not record['failures'] and len(record['traces']) == len(contract.schedule(cfg))
            and len(record['pmc']) == sum(len(item['modes']) for item in cfg['pmc_cases']))
        record['counter_formats'] = formats
    finally:
        save()
    mgr.require(record['complete'],'independent diagnostic failures collected; inspect diagnostic-result.json')


if __name__ == '__main__':
    main()
