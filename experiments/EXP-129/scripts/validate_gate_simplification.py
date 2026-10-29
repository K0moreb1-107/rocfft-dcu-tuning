"""Validate EXP129 numerical results and actual real/ordinary FFT dispatches."""
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
sys.path[:0] = [str(ROOT), str(ROOT/'tools/fft_measurement'),
                str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from cc_dispatch import inspect_dispatch
from validate_cc_local_boundary import build_switches
from validate_cc_local_grouped import CaseError, run, read_numerical_outputs, check_cases, write
import cufft261012_contract as contract


def row_features(name, source, c, q, func):
    lanes = int(re.search(r'_tpt_(\d+)', name)[1])
    wgs = int(re.search(r'_wgs_(\d+)', name)[1])
    factors = list(map(int, re.search(r'_factors_([0-9_]+)_wgs_', name)[1].split('_')))
    rows = wgs//lanes
    mgr.require(rows*lanes == wgs, 'invalid row workgroup geometry')
    direct = rows == 1 and lanes == q//factors[-1]
    global_body = source[source.index('extern "C" __global__'):]
    mgr.require('const bool direct_store_from_reg = '+('true;' if direct else 'false;')
                in global_body, 'output register selection differs from its generic geometry rule')
    result = dict(threads_per_transform=lanes, rows_per_block=rows, direct_output=direct)
    if func == 'z2d_1d':
        packed = c % 2 == 0 and rows % 2 == 0 and c % rows == 0
        if direct:
            mgr.require('cc_direct_row' in global_body and 'cc_output_first' not in global_body,
                        'single-row real output missing')
            result['output_strategy'] = 'register_real_components'
        elif packed:
            mgr.require(all(x in global_body for x in ('cc_packed_slot', 'cc_packed_component', 'cc_packed_pair'))
                        and 'cc_output_first' not in global_body, 'packed output changed')
            result['output_strategy'] = 'packed_lds'
        else:
            mgr.require('cc_output_p0' in global_body, 'multirow output missing')
            if c % rows == 0:
                mgr.require('const unsigned int cc_output_valid = '+str(rows)+';' in global_body,
                            'full row group still has dynamic valid count')
            for offset in re.findall(r'if\(cc_output_p0 \+ (\d+) < '+str(q)+r'\)', global_body):
                mgr.require(int(offset)+lanes > q, 'unnecessary full frequency guard')
            result['output_strategy'] = 'classified_lds'
        return dict(result, packed_output=packed)

    mgr.require(name.endswith('_reg'), 'd2z direct register input is required')
    count = q//factors[0]
    start = source.index('// load global into registers\n')
    end = source.index('// calc the thread_in_device', start)
    region = source[start:end]
    dense = re.sub(r'\s+', '', region)
    recurrent = q > count+min(count, lanes)
    groups = (factors[0]+1)//2 if lanes > count else 1
    mgr.require(dense.count('if(cc_input_row==0)') == groups, 'native input classification changed')
    if lanes > count:
        mgr.require('if(threadIdx.x%'+str(lanes)+'<'+str(count)+')' in dense, 'active-lane guard missing')
    queries = 1+(count+lanes-1)//lanes if recurrent else factors[0]*((count+lanes-1)//lanes)
    mgr.require(region.count('TW_NSteps<') == queries and ('cc_phase_delta' in region) == recurrent,
                'input phase recurrence changed')
    if direct:
        mgr.require('if(cc_direct_row != 0)' in global_body and 'cc_terminal_j' in global_body
                    and 'cc_spectrum_p0' not in global_body, 'ordinary/terminal single-row output missing')
        result['output_strategy'] = 'register_ordinary_terminal_lds'
    else:
        mgr.require('cc_spectrum_p0' in global_body, 'folded LDS output missing')
        result['output_strategy'] = 'folded_lds'
    return dict(result, phase_recurrence=recurrent, source_phase_lookups=queries)


def validate_names(names, c, q, func):
    roles = (4, 5) if func == 'z2d_1d' else (6, 7)
    mgr.require(len(names) == 2 and all('_cc_local_v6_role%d_C%d_Q%d_' % (role, c, q) in name
                for role, name in zip(roles, names)), 'both generic v6 adapters must execute')


def trace_case(binary, case, func, env, folder):
    n, c, q = (case[k] for k in ('N', 'C', 'Q'))
    profile, data = folder/'profile', folder/'metadata'
    harness = profile/'harness'
    for path in (harness, profile/'data', data):
        path.mkdir(parents=True)
    selected = dict(env, FFT_TEST_OUT=str(harness), ROCFFT_LAYER='40',
                    ROCFFT_LOG_PLAN_PATH=str(data/'plan.txt'), ROCFFT_LOG_RTC_PATH=str(data/'rtc.txt'))
    run([mgr.DTK+'/bin/hipprof', '--hip-trace', '--trace-args', '--output-type', '0',
         '-o', profile/'trace', '-d', profile/'data', binary, n, 1, func], selected, profile, 'trace')
    child = re.search(r'exited with status:\s*(\d+)', (profile/'trace.err').read_text())
    numerical = read_numerical_outputs(harness, n, func, int(child[1]) if child else None)
    try:
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
                       ((data/'rtc.txt').read_text() if (data/'rtc.txt').exists() else ''), re.M | re.S))
        launches, checked = inspect_dispatch((data/'plan.txt').read_text(),
                            json.loads((profile/'trace.json').read_text())['traceEvents'], func)
        names = [x['name'] for x in launches]
        if func == 'z2z_1d':
            mgr.require(len(names) == 2 and all('_cc_local_' not in name for name in names),
                        'ordinary CC execution must not use real adapters')
            mgr.require('CS_L1D_CC' in (data/'plan.txt').read_text(),
                        'ordinary regression did not select the expected CC plan')
            features = dict(output_strategy='ordinary_complex_CC',
                            twiddle_recurrence=any('_ordtwrec128k' in name for name in names))
        else:
            mgr.require(all(name in sources for name in names), 'actual FFT source missing')
            validate_names(names, c, q, func)
            features = row_features(names[1], sources[names[1]], c, q, func)
    except Exception as error:
        raise CaseError('dispatch', str(error)) from error
    dispatched = dict(N=n, func=func, row_features=features, actual_names=names,
        dispatch=checked, source_sha256={name: hashlib.sha256(sources[name].encode()).hexdigest()
                                        for name in names if name in sources})
    if func != 'z2z_1d':
        dispatched.update(C=c, Q=q)
    return dict(N=n, func=func, check=numerical), dispatched


def check_gate_cases(record, settings, operation, save):
    try:
        check_cases(record, settings['sample_N'], settings['smoke_N'],
                    operation, save)
    except Exception:
        # Smoke failures stop immediately; later independent failures are aggregated.
        if not record['failures'] or any(item.get('smoke') for item in record['failures']):
            raise
    for n in settings['ordinary_N']:
        func = 'z2z_1d'
        try:
            numerical, dispatch = operation(n, func)
            record['numerical'].append(numerical)
            record['dispatch'].append(dispatch)
            print('ORDINARY_CHECK_PASS', n, func, flush=True)
        except Exception as error:
            record['failures'].append(dict(N=n, func=func, smoke=False,
                stage=getattr(error, 'stage', 'case'), error=type(error).__name__,
                message=str(error), returncode=getattr(error, 'returncode', None)))
            print('ORDINARY_CHECK_FAIL', n, func, str(error), flush=True)
        save()
    expected = 2*len(settings['sample_N']) + len(settings['ordinary_N'])
    mgr.require(not record['failures']
                and len(record['numerical']) == len(record['dispatch']) == expected,
                'numerical/path failures; all post-smoke independent cases attempted: '
                + str(record['failures']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    a = parser.parse_args()
    settings = mgr.load(a.config)['validation']
    mgr.require(settings['profile'] == 'gate-simplification-two-checks', 'wrong validation profile')
    built = json.loads(a.build_record.read_text())
    mgr.require(built['complete'], 'build incomplete')
    build_switches((a.build/'CMakeCache.txt').read_text(), True)
    coverage_path = mgr.inside(settings['coverage'])
    by_n = {x['N']: x for x in json.loads(coverage_path.read_text())['public']}
    mgr.require(set(settings['sample_N']) <= by_n.keys(), 'representative missing from matrix')
    install = mgr.inside(built['arm']['install'])
    library = install/'lib/librocfft.so.0.1'
    folder = mgr.inside(a.run)/'measurement-validation'
    folder.mkdir()
    helpers = mgr.inside(a.cache)/'helpers'
    helpers.mkdir()
    env = mgr.environment(mgr.inside(a.cache))
    env['FFT_TEST_ITERS'] = '30'
    selected = dict(env, LD_PRELOAD=str(library), LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started = time.monotonic()
    record = dict(complete=False, formal=False, profile=settings['profile'],
        source_commit=built['arm']['source_commit'], library_sha256=built['arm']['library_sha256'],
        coverage_sha256=mgr.common.sha(coverage_path), scope=settings['scope'], numerical=[], dispatch=[], failures=[],
        callbacks_enabled=False, scales=[1.], start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write(a.run/'gate-simplification-validation.json', record)

    try:
        identity, binary = helpers/'device-identity', helpers/'measurement-v3'
        for output, source, flags in [
            (identity, ROOT/'tools/fft_measurement/device_identity.cpp', []),
            (binary, ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,
             ['-I'+str(install/'include'), '-L'+str(install/'lib'), '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-lstdc++fs'])]:
            run([mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936', '-mcumode',
                 source, *flags, '-o', output], env, folder, 'compile-'+output.name)
        gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936'
                    and re.fullmatch('[0-9a-f]{32}', gpu['uuid']) and int(gpu['uuid'], 16), 'single gfx936 required')
        record['gpu'] = gpu
        check_gate_cases(record, settings,
                         lambda n, func: trace_case(binary, by_n.get(n, dict(N=n, C=0, Q=0)),
                                                   func, selected, folder/(str(n)+'-'+func)), save)
        finish(record, built, gpu, env, library, identity)
    except Exception as error:
        record['failure'] = dict(error=type(error).__name__, message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True, numerical=len(record['numerical']), dispatch=len(record['dispatch']),
                          elapsed_seconds=record['elapsed_seconds'])))


if __name__ == '__main__':
    main()
