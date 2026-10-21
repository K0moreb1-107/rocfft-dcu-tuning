"""Numerical correctness and actual generic CC dispatch; no release regressions."""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from cc_dispatch import inspect_dispatch
import cufft261012_contract as contract


class CaseError(RuntimeError):
    def __init__(self, stage, message, returncode=None):
        super().__init__(message)
        self.stage = stage
        self.returncode = returncode


def write(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def run(command, env, folder, label):
    folder.mkdir(parents=True, exist_ok=True)
    command = list(map(str, command))
    with (folder/(label+'.out')).open('wb') as out, (folder/(label+'.err')).open('wb') as err:
        proc = subprocess.run(command, env=env, cwd=folder, stdout=out, stderr=err, timeout=900)
    write(folder/(label+'-command.json'), dict(command=command, returncode=proc.returncode))
    if proc.returncode:
        raise CaseError(label, 'nonzero process exit; see '+str(folder/(label+'.err')), proc.returncode)


def trace_case(binary, case, func, env, folder):
    n,c,q = (case[key] for key in ('N','C','Q'))
    profile = folder/'profile'
    harness = profile/'harness'
    data = folder/'metadata'
    for path in (harness, profile/'data', data):
        path.mkdir(parents=True)
    selected = dict(env, FFT_TEST_OUT=str(harness), ROCFFT_LAYER='40',
        ROCFFT_LOG_PLAN_PATH=str(data/'plan.txt'), ROCFFT_LOG_RTC_PATH=str(data/'rtc.txt'))
    run([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
         '-o',profile/'trace','-d',profile/'data',binary,n,1,func], selected,profile,'trace')
    try:
        numerical = contract.read_check(harness/'fft_test_1d.check.csv')
        row = contract.read_rows(harness/'fft_test_1d.csv')[0]
        contract.validate_process(row,contract.read_samples(harness/'fft_test_1d.samples.csv'),
                                  numerical,n,func,30)
    except Exception as error:
        raise CaseError('numerical', str(error)) from error
    try:
        plan = (data/'plan.txt').read_text()
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
                                  (data/'rtc.txt').read_text(),re.M|re.S))
        launches,checked = inspect_dispatch(plan,json.loads((profile/'trace.json').read_text())['traceEvents'],func)
        names = [x['name'] for x in launches]
        roles = (4,5) if func == 'z2d_1d' else (6,7)
        mgr.require(len(names) == 2 and all('_cc_local_v2_role%d_C%d_Q%d_'%(role,c,q) in name
                    for role,name in zip(roles,names)), 'default did not execute both generic v2 adapters')
        mgr.require(all(name in sources for name in names), 'actual RTC source missing')
        if func == 'd2z_1d':
            mgr.require(names[1].endswith('_reg'), 'forward native register input not selected')
    except Exception as error:
        raise CaseError('dispatch', str(error)) from error
    return dict(N=n,func=func,check=numerical),dict(N=n,func=func,C=c,Q=q,
        actual_names=names,dispatch=checked,source_sha256={name:hashlib.sha256(sources[name].encode()).hexdigest()
                                                        for name in names})


def check_cases(record, sample_n, smoke_n, operation, save):
    """Smoke fails fast; independent main-matrix cases report every failure."""
    mgr.require(sample_n and len(sample_n) == len(set(sample_n)) and smoke_n
                and len(smoke_n) <= 2 and set(smoke_n) <= set(sample_n), 'invalid representative matrix')
    sequence = [(n,True) for n in smoke_n]+[(n,False) for n in sample_n if n not in smoke_n]
    for n,smoke in sequence:
        for func in ('z2d_1d','d2z_1d'):
            try:
                numerical,dispatch = operation(n,func)
                record['numerical'].append(numerical)
                record['dispatch'].append(dispatch)
                print('UNIFIED_CHECK_PASS',n,func,flush=True)
            except Exception as error:
                record['failures'].append(dict(N=n,func=func,smoke=smoke,
                    stage=getattr(error,'stage','case'),error=type(error).__name__,
                    message=str(error),returncode=getattr(error,'returncode',None)))
                print('UNIFIED_CHECK_FAIL',n,func,str(error),flush=True)
                if smoke:
                    save()
                    raise RuntimeError('representative smoke failed; no main matrix attempted') from error
            save()
    expected = 2*len(sample_n)
    mgr.require(not record['failures'] and len(record['numerical']) == len(record['dispatch']) == expected,
                'independent representative failures; all main-matrix cases attempted: '+str(record['failures']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config','build-record','run','build','cache'):
        parser.add_argument('--'+name,type=Path,required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    settings = cfg['validation']
    mgr.require(settings['profile'] == 'cc-local-unified-two-checks-v2'
                and settings['expected_cc_local_version'] == 2, 'wrong validation profile')
    built = json.loads(a.build_record.read_text())
    mgr.require(built['complete'], 'candidate build incomplete')
    coverage = json.loads(mgr.inside(settings['coverage']).read_text())
    by_n = {x['N']:x for x in coverage['public']}
    mgr.require(set(settings['sample_N']) <= by_n.keys(), 'representative absent from coverage')
    install = mgr.inside(built['arm']['install'])
    library = install/'lib/librocfft.so.0.1'
    folder = mgr.inside(a.run)/'measurement-validation'
    folder.mkdir()
    helpers = mgr.inside(a.cache)/'helpers'
    helpers.mkdir()
    env = mgr.environment(mgr.inside(a.cache))
    env['FFT_TEST_ITERS'] = '30'
    selected = dict(env,LD_PRELOAD=str(library),LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started = time.monotonic()
    record = dict(complete=False,formal=False,profile=settings['profile'],
        source_commit=built['arm']['source_commit'],library_sha256=built['arm']['library_sha256'],
        coverage_sha256=mgr.common.sha(mgr.inside(settings['coverage'])),scope=settings['scope'],
        numerical=[],dispatch=[],failures=[],callbacks_enabled=False,scales=[1.],
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write(a.run/'cc-local-validation.json',record)

    try:
        identity,binary = helpers/'device-identity',helpers/'measurement-v3'
        for output,source,flags in [
            (identity,ROOT/'tools/fft_measurement/device_identity.cpp',[]),
            (binary,ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,
             ['-I'+str(install/'include'),'-L'+str(install/'lib'),
              '-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-lstdc++fs'])]:
            run([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',
                 '-mcumode',source,*flags,'-o',output],env,folder,'compile-'+output.name)
        gpu = json.loads(subprocess.check_output([str(identity)],env=env,text=True))
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936'
                    and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16),
                    'single gfx936 required')
        record['gpu'] = gpu
        check_cases(record,settings['sample_N'],settings['smoke_N'],
            lambda n,func:trace_case(binary,by_n[n],func,selected,folder/(str(n)+'-'+func)),save)
        finish(record,built,gpu,env,library,identity)
    except Exception as error:
        record['failure'] = dict(error=type(error).__name__,message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True,numerical=len(record['numerical']),dispatch=len(record['dispatch']),
                         elapsed_seconds=record['elapsed_seconds'])))


if __name__ == '__main__':
    main()
