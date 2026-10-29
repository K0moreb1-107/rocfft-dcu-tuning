"""Experiment-local copies of the existing numerical/path validation utilities."""
import json
import re
import subprocess
from pathlib import Path
from tools.workspace_manager import manager as mgr
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


def read_numerical_outputs(harness, n, func, child_returncode=None):
    try:
        numerical = contract.read_check(harness/'fft_test_1d.check.csv')
        if numerical['check'] != 'PASS':
            raise CaseError('numerical', 'correctness check failed: '+json.dumps(numerical),
                            child_returncode)
        if child_returncode:
            raise CaseError('trace', 'profiled measurement exited with status '+str(child_returncode),
                            child_returncode)
        row = contract.read_rows(harness/'fft_test_1d.csv')[0]
        contract.validate_process(row, contract.read_samples(harness/'fft_test_1d.samples.csv'),
                                  numerical, n, func, 30)
        return numerical
    except CaseError:
        raise
    except Exception as error:
        raise CaseError('numerical', str(error), child_returncode) from error


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


def build_switches(cache,fused):
    for key in ('ROCFFT_CC_REAL_FUSION','ROCFFT_CC_LOCAL_REAL_FUSION'):
        found=re.search(r'^'+key+r':(?:BOOL|UNINITIALIZED)=(ON|OFF)$',cache,re.M)
        mgr.require(found and found[1]==('ON' if fused else 'OFF'),'wrong build switch: '+key)
