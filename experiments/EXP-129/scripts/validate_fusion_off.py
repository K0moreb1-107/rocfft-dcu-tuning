"""Check numerical results and actual unfused three-stage CC execution."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts'),
               str(ROOT/'tools/fft_measurement')]
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from cc_dispatch import inspect_dispatch
from gate_validation_support import CaseError, run, read_numerical_outputs, check_cases, write
import cufft261012_contract as contract


def validate_names(names, c, q, func):
    mgr.require(len(names) == 3, 'unfused CC must execute exactly three stages')
    forbidden = ('_cc_local_', '_local_real_columns', '_local_real_rows', '_paired_post_rows')
    mgr.require(not any(token in name for name in names for token in forbidden),
                'unfused control executed fusion')
    boundary = names[0] if func == 'z2d_1d' else names[-1]
    prefix = 'c2r_even_pre_' if func == 'z2d_1d' else 'r2c_even_post_'
    mgr.require(boundary.startswith(prefix), 'independent boundary missing or misplaced')
    fft = names[1:] if func == 'z2d_1d' else names[:2]
    for name, length, scheme in zip(fft, (c, q), ('sbcc', 'sbrc')):
        mgr.require('_len_'+str(length)+'_' in name and '_'+scheme+'_' in name,
                    'unfused CC decomposition differs: '+name)


def trace_case(binary, case, func, env, folder):
    n, c, q = (case[k] for k in ('N', 'C', 'Q'))
    profile, data = folder/'profile', folder/'metadata'
    harness = profile/'harness'
    for path in (harness, profile/'data', data):
        path.mkdir(parents=True)
    selected = dict(env, FFT_TEST_OUT=str(harness), ROCFFT_LAYER='8',
                    ROCFFT_LOG_PLAN_PATH=str(data/'plan.txt'))
    run([mgr.DTK+'/bin/hipprof', '--hip-trace', '--trace-args', '--output-type', '0',
         '-o', profile/'trace', '-d', profile/'data', binary, n, 1, func],
        selected, profile, 'trace')
    child = re.search(r'exited with status:\s*(\d+)', (profile/'trace.err').read_text())
    numerical = read_numerical_outputs(harness, n, func, int(child[1]) if child else None)
    try:
        plan = (data/'plan.txt').read_text()
        mgr.require('CS_L1D_CC' in plan, 'CC plan missing')
        launches, checked = inspect_dispatch(plan,
            json.loads((profile/'trace.json').read_text())['traceEvents'], func)
        names = [e['name'] for e in launches]
        validate_names(names, c, q, func)
    except Exception as error:
        raise CaseError('dispatch', str(error)) from error
    return dict(N=n, func=func, check=numerical), dict(N=n, func=func, C=c, Q=q,
        actual_names=names, dispatch=checked, fusion=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+key, type=Path, required=True)
    a = parser.parse_args()
    settings = mgr.load(a.config)['validation']
    mgr.require(settings['profile'] == 'fusion-off-two-checks', 'wrong validation profile')
    built = json.loads(a.build_record.read_text())
    cache = (a.build/'CMakeCache.txt').read_text()
    mgr.require(re.search(r'^ROCFFT_CC_REAL_FUSION:BOOL=OFF$', cache, re.M), 'OFF build required')
    coverage = mgr.inside(settings['coverage'])
    mgr.require(mgr.common.sha(coverage) == settings['coverage_sha256'], 'coverage changed')
    cases = {x['N']: x for x in json.loads(coverage.read_text())['public']}
    install = mgr.inside(built['arm']['install'])
    library = install/'lib/librocfft.so.0.1'
    folder = a.run/'measurement-validation'
    folder.mkdir()
    helpers = a.cache/'helpers'
    helpers.mkdir()
    env = mgr.environment(a.cache)
    env['FFT_TEST_ITERS'] = '30'
    selected = dict(env, LD_PRELOAD=str(library),
                    LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started = time.monotonic()
    record = dict(complete=False, formal=False, profile=settings['profile'],
        source_commit=built['arm']['source_commit'], library_sha256=built['arm']['library_sha256'],
        coverage_sha256=mgr.common.sha(coverage), numerical=[], dispatch=[], failures=[],
        callbacks_enabled=False, scales=[1.], start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write(a.run/'fusion-off-validation.json', record)

    try:
        identity, binary = helpers/'device-identity', helpers/'measurement-v3'
        for output, source, flags in [
            (identity, ROOT/'tools/fft_measurement/device_identity.cpp', []),
            (binary, ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,
             ['-I'+str(install/'include'), '-L'+str(install/'lib'),
              '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-lstdc++fs'])]:
            run([mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936', '-mcumode',
                 source, *flags, '-o', output], env, folder, 'compile-'+output.name)
        gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936', 'single gfx936 required')
        record['gpu'] = gpu
        check_cases(record, settings['sample_N'], settings['smoke_N'],
                    lambda n, func: trace_case(binary, cases[n], func, selected,
                                               folder/(str(n)+'-'+func)), save)
        finish(record, built, gpu, env, library, identity)
    except Exception as error:
        record['failure'] = dict(error=type(error).__name__, message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True, numerical=len(record['numerical']),
                         dispatch=len(record['dispatch']), elapsed_seconds=record['elapsed_seconds'])))


if __name__ == '__main__':
    main()
