"""Full EXP129 publication checks using the accepted library and public API."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts'),
                str(ROOT/'tools/fft_measurement')]
import numpy as np
import cufft261012_contract as contract
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from gate_validation_support import run, write, check_cases
from validate_legacy_retirement import trace_case, check_switch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def references(n, func, mode, folder, coverage, smoke=False):
    folder.mkdir()
    assert shutil.disk_usage(folder).free > 384*(1 << 20)+20*n*8, 'insufficient reference workspace'
    indices = np.arange(n)
    rng = np.random.default_rng(129000+n)
    patterns = ['mixed'] if smoke else coverage['patterns']
    scales = [1.] if smoke else coverage['scales']
    metadata, lines = [], []
    load, store = mode in ('load', 'callbacks'), mode in ('store', 'callbacks')
    for pattern in patterns:
        if func == 'd2z_1d':
            if pattern == 'mixed':
                original = rng.standard_normal(n)
            elif pattern == 'endpoints':
                original = np.ones(n)+0.25*np.where(indices % 2, -1., 1.)
            else:
                original = np.cos(2*np.pi*(n//4)*indices/n)
        else:
            original = np.zeros(n//2+1, dtype=np.complex128)
            if pattern == 'mixed':
                original = np.fft.rfft(rng.standard_normal(n))
            elif pattern == 'endpoints':
                original[0], original[-1] = 1.5, -0.75
            else:
                original[n//4] = 0.75+0.5j
        input_file = folder/('input-'+pattern+'.bin')
        original.tofile(input_file)
        transformed = original.copy()
        if load:
            positions = np.arange(len(transformed))
            transformed *= 0.75
            if func == 'd2z_1d':
                transformed += (positions % 7)*0.03125
            else:
                transformed.real += (positions % 7)*0.03125
                transformed.imag[1:-1] += (positions[1:-1] % 11)*0.015625
        fft = (np.fft.rfft(transformed) if func == 'd2z_1d'
               else np.fft.irfft(transformed, n=n)*n)
        metadata.append(dict(path=str(input_file), sha256=sha(input_file), bytes=input_file.stat().st_size))
        for index, scale in enumerate(scales):
            expected = fft*scale
            if store:
                positions = np.arange(len(expected))
                expected *= 1.125
                if func == 'd2z_1d':
                    expected.real += (positions % 5)*0.015625
                    expected.imag += (positions % 3+1)*0.03125
                else:
                    expected += (positions % 5)*0.015625
            path = folder/(pattern+'-scale-'+str(index)+'.bin')
            expected.tofile(path)
            metadata.append(dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size))
            lines.append(f'{pattern} {scale:.17g} {input_file} {path}')
    manifest = folder/'cases.txt'
    manifest.write_text('\n'.join(lines)+'\n')
    write(folder.parent/'reference-manifest.json', dict(files=metadata, numpy_version=np.__version__,
        seed=129000+n, N=n, func=func, mode=mode, cases=len(lines)))
    return manifest, metadata, len(lines)


def guard_group(binary, case, func, mode, env, folder, coverage, smoke=False):
    folder.mkdir()
    refs = folder/'references'
    manifest, temporary, expected = references(case['N'], func, mode, refs, coverage, smoke)
    selected = dict(env, ROCFFT_LAYER='40', ROCFFT_LOG_PLAN_PATH=str(folder/'plan.txt'),
                    ROCFFT_LOG_RTC_PATH=str(folder/'rtc.txt'))
    command = [str(binary), str(case['N']), func.removesuffix('_1d'), str(manifest), mode]
    profiled = mode == 'callbacks'
    if profiled:
        (folder/'profile-data').mkdir()
        command = [mgr.DTK+'/bin/hipprof', '--hip-trace', '--trace-args', '--output-type', '0',
            '-o', str(folder/'trace'), '-d', str(folder/'profile-data'), *command]
    try:
        with (folder/'stdout.txt').open('wb') as out, (folder/'stderr.txt').open('wb') as err:
            process = subprocess.run(command, cwd=folder, env=selected, stdout=out, stderr=err, timeout=900)
        output = (folder/'stdout.txt').read_text(errors='replace')
        error = (folder/'stderr.txt').read_text(errors='replace')
        passed = re.findall(r'^EVEN_CC_GUARD_PASS .*$', output, re.M)
        failures = re.findall(r'^FULL_RELEASE_CASE_FAIL .*$', output, re.M)
        end = re.search(r'^FULL_RELEASE_GROUP_END cases=(\d+) failures=(\d+)$', output, re.M)
        child = re.search(r'exited with status:\s*(\d+)', error)
        result = dict(N=case['N'], func=func, mode=mode, expected=expected, passed=len(passed),
            failures=failures, returncode=process.returncode,
            child_returncode=int(child[1]) if child else None, profiled=profiled,
            complete=bool(process.returncode == 0 and not (child and int(child[1])) and end
                          and int(end[1]) == expected and int(end[2]) == 0
                          and len(passed) == expected and not failures))
        if profiled:
            events = json.loads((folder/'trace.json').read_text())['traceEvents']
            names = [event['name'] for event in events
                     if event.get('cat') == 'HIPOPS' and 'fft_rtc_' in event.get('name', '')]
            roles = (4, 5) if func == 'z2d_1d' else (6, 7)
            expected_tags = ['_cc_local_v6_role%d_C%d_Q%d_' % (role, case['C'], case['Q'])
                             for role in roles]
            path_ok = bool(names) and all(any(tag in name for tag in expected_tags) for name in names)
            path_ok = path_ok and all(any(tag in name for name in names) for tag in expected_tags)
            if result['complete']:
                path_ok = path_ok and len(names) == expected*2*2
            result.update(actual_names=sorted(set(names)), actual_fft_launches=len(names),
                          actual_path_passed=path_ok, complete=result['complete'] and path_ok)
        write(folder/'result.json', result)
        return result
    finally:
        # Only the explicitly recorded reference arrays are temporary.
        for item in temporary:
            path = Path(item['path']).resolve()
            assert path.is_relative_to(refs.resolve())
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    settings = mgr.load(args.config)['validation']
    coverage_path = mgr.inside(settings['coverage'])
    coverage = json.loads(coverage_path.read_text())
    by_n = {item['N']: item for item in coverage['public']}
    built = json.loads(args.build_record.read_text())
    check_switch((args.build/'CMakeCache.txt').read_text())
    install = mgr.inside(built['arm']['install'])
    library = install/'lib/librocfft.so.0.1'
    assert sha(library) == built['arm']['library_sha256']
    folder, helpers = mgr.inside(args.run)/'full-release', mgr.inside(args.cache)/'helpers'
    folder.mkdir()
    helpers.mkdir()
    env = mgr.environment(mgr.inside(args.cache))
    env['FFT_TEST_ITERS'] = '30'
    selected = dict(env, LD_PRELOAD=str(library),
                    LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started = time.monotonic()
    record = dict(complete=False, formal=False, profile='full-stable-release', numerical=[], dispatch=[],
        guards=[], smoke_guards=[], failures=[], source_commit=built['arm']['source_commit'],
        library_sha256=built['arm']['library_sha256'], coverage_sha256=sha(coverage_path),
        callbacks_enabled=True, scales=coverage['scales'], numpy_version=np.__version__,
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write(args.run/'full-release-validation.json', record)

    def add_failure(n, func, stage, error):
        record['failures'].append(dict(N=n, func=func, stage=stage,
            error=type(error).__name__, message=str(error), returncode=getattr(error, 'returncode', None)))

    def operation(n, func):
        kind = 'ordinary' if func == 'z2z_1d' else ('fused' if n in by_n else 'fallback')
        return trace_case(timer, by_n.get(n, dict(N=n)), func, selected,
                          folder/('dispatch-'+str(n)+'-'+func), kind)

    try:
        identity, timer, guard = helpers/'device-identity', helpers/'measurement-v3', helpers/'full-release-guard'
        link = ['-I'+str(install/'include'), '-L'+str(install/'lib'),
                '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-lstdc++fs']
        for output, source, flags in [
            (identity, ROOT/'tools/fft_measurement/device_identity.cpp', []),
            (timer, ROOT/'tools/fft_measurement'/contract.SOURCE_NAME, link),
            (guard, Path(settings['guard_source']), [*link,
                '-I'+str(ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/shared')])]:
            run([mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936', '-mcumode',
                 source, *flags, '-o', output], env, folder, 'compile-'+output.name)
        gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936', 'single gfx936 required')
        record['gpu'] = gpu
        smoke = coverage['smoke_N']
        for n in smoke:
            for func in ('z2d_1d', 'd2z_1d'):
                for mode in ('none', 'callbacks'):
                    result = guard_group(guard, by_n[n], func, mode, selected,
                        folder/('smoke-guard-'+str(n)+'-'+func+'-'+mode), coverage, smoke=True)
                    record['smoke_guards'].append(result)
                    save()
                    mgr.require(result['complete'], 'public API guard smoke failed: '+json.dumps(result))
        try:
            check_cases(record, sorted(by_n), smoke, operation, save)
        except Exception:
            if not record['failures'] or any(item.get('smoke') for item in record['failures']):
                raise
        for n, func in ([(n, f) for n in coverage['fallback_N'] for f in ('z2d_1d', 'd2z_1d')]
                        + [(n, 'z2z_1d') for n in coverage['ordinary_N']]):
            try:
                numeric, dispatch = operation(n, func)
                record['numerical'].append(numeric)
                record['dispatch'].append(dispatch)
            except Exception as error:
                add_failure(n, func, 'numerical/path', error)
            save()
        for n in coverage['guard_N']+coverage['fallback_N']:
            for func in ('z2d_1d', 'd2z_1d'):
                modes = coverage['callback_modes'] if n in by_n else ['boundary']
                for mode in modes:
                    try:
                        result = guard_group(guard, by_n.get(n, dict(N=n)), func, mode, selected,
                            folder/('guard-'+str(n)+'-'+func+'-'+mode), coverage)
                        record['guards'].append(result)
                        if not result['complete']:
                            add_failure(n, func, 'guard/'+mode, RuntimeError(json.dumps(result)))
                        print('GUARD_GROUP', n, func, mode, result['complete'], flush=True)
                    except Exception as error:
                        add_failure(n, func, 'guard/'+mode, error)
                    save()
        expected_dispatch = len(by_n)*2+len(coverage['fallback_N'])*2+len(coverage['ordinary_N'])
        expected_guards = len(coverage['guard_N'])*2*4+len(coverage['fallback_N'])*2
        record['expected_dispatch'], record['expected_guard_groups'] = expected_dispatch, expected_guards
        mgr.require(not record['failures'] and len(record['numerical']) == len(record['dispatch'])
                    == expected_dispatch and len(record['guards']) == expected_guards,
                    'full release failures; all independent post-smoke cases attempted: '+str(len(record['failures'])))
        finish(record, built, gpu, env, library, identity)
    except Exception as error:
        record['failure'] = dict(error=type(error).__name__, message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True, numerical=len(record['numerical']), guards=len(record['guards']),
                          elapsed_seconds=record['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
