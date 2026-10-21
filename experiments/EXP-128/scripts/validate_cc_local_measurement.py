"""Check numerical results and actual fused dispatch for measurement defaults only."""
import argparse
import datetime
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
from validate_cc_local import run, trace_case
import cufft261012_contract as contract

SAMPLE_N = (65856, 67600, 69938, 131072, 100352, 133100)


def write_progress(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    mgr.require(cfg['validation']['profile'] == 'measurement-default-two-checks', 'wrong acceptance scope')
    mgr.require(tuple(cfg['validation']['sample_N']) == SAMPLE_N, 'wrong representative matrix')
    built = json.loads(a.build_record.read_text())
    coverage = json.loads(mgr.inside(cfg['validation']['coverage']).read_text())
    by_n = {case['N']: case for case in coverage['public']}
    install = mgr.inside(built['arm']['install'])
    library = install/'lib/librocfft.so.0.1'
    folder = mgr.inside(a.run)/'measurement-validation'
    folder.mkdir()
    helpers = mgr.inside(a.cache)/'helpers'
    helpers.mkdir()
    env = mgr.environment(mgr.inside(a.cache))
    env['FFT_TEST_ITERS'] = '30'
    selected = dict(env, LD_PRELOAD=str(library),
        LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started = time.monotonic()
    record = dict(complete=False, formal=False, profile=cfg['validation']['profile'],
        source_commit=built['arm']['source_commit'], library_sha256=built['arm']['library_sha256'],
        coverage_sha256=mgr.common.sha(mgr.inside(cfg['validation']['coverage'])),
        scope=cfg['validation']['scope'], callbacks_enabled=False, scales=[1.],
        known_limitations=cfg['validation']['known_limitations'],
        prior_public_evidence='experiments/EXP-128/runs/EXP-128-cc-local-mapfix-validate-20261021/cc-local-validation.json',
        numerical=[], dispatch=[], failures=[],
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write_progress(a.run/'cc-local-validation.json', record)

    try:
        identity = helpers/'device-identity'
        binary = helpers/'measurement-v3'
        for output, source, flags in [
            (identity, ROOT/'tools/fft_measurement/device_identity.cpp', []),
            (binary, ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,
             ['-I'+str(install/'include'), '-L'+str(install/'lib'),
              '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-lstdc++fs'])]:
            run([mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936',
                 '-mcumode', source, *flags, '-o', output], env, folder, 'compile-'+output.name)
        gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936'
            and re.fullmatch('[0-9a-f]{32}', gpu['uuid']) and int(gpu['uuid'], 16), 'single gfx936 required')
        record['gpu'] = gpu
        for n in SAMPLE_N:
            for func in ('z2d_1d', 'd2z_1d'):
                case_folder = folder/(str(n)+'-'+func)
                try:
                    dispatch = trace_case(binary, by_n[n], func, selected, case_folder, True)
                    numerical = contract.read_check(case_folder/'profile/harness/fft_test_1d.check.csv')
                    record['numerical'].append(dict(N=n, func=func, check=numerical))
                    record['dispatch'].append(dispatch)
                    print('MEASUREMENT_CHECK_PASS', n, func, flush=True)
                except Exception as error:
                    record['failures'].append(dict(N=n, func=func, type=type(error).__name__, message=str(error)))
                    print('MEASUREMENT_CHECK_FAIL', n, func, str(error), flush=True)
                save()
        expected = 2*len(SAMPLE_N)
        mgr.require(not record['failures'] and len(record['numerical']) == len(record['dispatch']) == expected,
                    'measurement checks failed; all representative cases were attempted: '+str(record['failures']))
        finish(record, built, gpu, env, library, identity)
    except Exception as error:
        record['failure'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True, numerical=len(record['numerical']),
        dispatch=len(record['dispatch']), elapsed_seconds=record['elapsed_seconds'])))


if __name__ == '__main__':
    main()
