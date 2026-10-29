"""Check numerical results and actual paths after retiring the EXP125 backend."""
import argparse
import datetime
import hashlib
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


def check_switch(cache):
    selected = re.search(r'^ROCFFT_CC_REAL_FUSION:(?:BOOL|UNINITIALIZED)=(ON|OFF)$', cache, re.M)
    mgr.require(selected and selected[1] == 'ON', 'CC real fusion must be enabled')


def trace_case(binary, case, func, env, folder, kind='fused'):
    n = case['N']
    profile, metadata = folder/'profile', folder/'metadata'
    harness = profile/'harness'
    for path in (harness, profile/'data', metadata):
        path.mkdir(parents=True)
    selected = dict(env, FFT_TEST_OUT=str(harness), ROCFFT_LAYER='40',
                    ROCFFT_LOG_PLAN_PATH=str(metadata/'plan.txt'),
                    ROCFFT_LOG_RTC_PATH=str(metadata/'rtc.txt'))
    run([mgr.DTK+'/bin/hipprof', '--hip-trace', '--trace-args', '--output-type', '0',
         '-o', profile/'trace', '-d', profile/'data', binary, n, 1, func], selected, profile, 'trace')
    child = re.search(r'exited with status:\s*(\d+)', (profile/'trace.err').read_text())
    numerical = read_numerical_outputs(harness, n, func, int(child[1]) if child else None)
    try:
        plan = (metadata/'plan.txt').read_text()
        source_text = (metadata/'rtc.txt').read_text() if (metadata/'rtc.txt').exists() else ''
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
                                  source_text, re.M | re.S))
        launches, checked = inspect_dispatch(plan,
            json.loads((profile/'trace.json').read_text())['traceEvents'], func)
        names = [item['name'] for item in launches]
        mgr.require(names, 'no actual FFT kernels found')
        if kind == 'fused':
            c, q = case['C'], case['Q']
            roles = (4, 5) if func == 'z2d_1d' else (6, 7)
            mgr.require(len(names) == 2 and all(
                '_cc_local_v6_role%d_C%d_Q%d_' % (role, c, q) in name
                for role, name in zip(roles, names)), 'expected CC boundary adapters did not execute')
            mgr.require(all(name in sources for name in names), 'actual fused kernel source missing')
        else:
            retired = ('_cc_local_', '_local_real_rows', '_local_real_columns', '_paired_post_rows')
            mgr.require(all(not any(tag in name for tag in retired) for name in names),
                        'ordinary path executed a real boundary adapter')
            if kind == 'ordinary':
                mgr.require('CS_L1D_CC' in plan, 'ordinary regression must use the default CC path')
    except Exception as error:
        raise CaseError('dispatch', str(error)) from error
    dispatched = dict(N=n, func=func, kind=kind, actual_names=names, dispatch=checked,
        source_sha256={name: hashlib.sha256(sources[name].encode()).hexdigest()
                       for name in names if name in sources})
    if kind == 'fused':
        dispatched.update(C=case['C'], Q=case['Q'])
    return dict(N=n, func=func, check=numerical), dispatched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    settings = mgr.load(args.config)['validation']
    mgr.require(settings['profile'] == 'cc-legacy-retirement-two-checks', 'wrong validation profile')
    built = json.loads(args.build_record.read_text())
    mgr.require(built['complete'], 'build incomplete')
    check_switch((args.build/'CMakeCache.txt').read_text())
    coverage = mgr.inside(settings['coverage'])
    by_n = {item['N']: item for item in json.loads(coverage.read_text())['public']}
    mgr.require(set(settings['sample_N']) <= by_n.keys(), 'representative missing from matrix')
    install = mgr.inside(built['arm']['install'])
    library = install/'lib/librocfft.so.0.1'
    folder = mgr.inside(args.run)/'measurement-validation'
    folder.mkdir()
    helpers = mgr.inside(args.cache)/'helpers'
    helpers.mkdir()
    env = mgr.environment(mgr.inside(args.cache))
    env['FFT_TEST_ITERS'] = '30'
    selected = dict(env, LD_PRELOAD=str(library),
                    LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started = time.monotonic()
    record = dict(complete=False, formal=False, profile=settings['profile'],
        source_commit=built['arm']['source_commit'], library_sha256=built['arm']['library_sha256'],
        coverage_sha256=mgr.common.sha(coverage), scope=settings['scope'], numerical=[], dispatch=[],
        failures=[], callbacks_enabled=False, scales=[1.],
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write(args.run/'legacy-retirement-validation.json', record)

    def operation(n, func):
        return trace_case(binary, by_n[n], func, selected, folder/(str(n)+'-'+func))

    def extra(n, func, kind):
        try:
            numerical, dispatched = trace_case(binary, dict(N=n), func, selected,
                folder/(str(n)+'-'+func), kind)
            record['numerical'].append(numerical)
            record['dispatch'].append(dispatched)
            print('EXTRA_CHECK_PASS', n, func, kind, flush=True)
        except Exception as error:
            record['failures'].append(dict(N=n, func=func, smoke=False,
                stage=getattr(error, 'stage', 'case'), error=type(error).__name__,
                message=str(error), returncode=getattr(error, 'returncode', None)))
            print('EXTRA_CHECK_FAIL', n, func, kind, str(error), flush=True)
        save()

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
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936'
                    and re.fullmatch('[0-9a-f]{32}', gpu['uuid']) and int(gpu['uuid'], 16),
                    'single gfx936 required')
        record['gpu'] = gpu
        try:
            check_cases(record, settings['sample_N'], settings['smoke_N'], operation, save)
        except Exception:
            if not record['failures'] or any(item.get('smoke') for item in record['failures']):
                raise
        for n in settings['fallback_N']:
            for func in ('z2d_1d', 'd2z_1d'):
                extra(n, func, 'fallback')
        for n in settings['ordinary_N']:
            extra(n, 'z2z_1d', 'ordinary')
        expected = 2*(len(settings['sample_N'])+len(settings['fallback_N']))+len(settings['ordinary_N'])
        mgr.require(not record['failures']
                    and len(record['numerical']) == len(record['dispatch']) == expected,
                    'numerical/path failures: '+str(record['failures']))
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
