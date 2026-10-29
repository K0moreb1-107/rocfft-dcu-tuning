"""EXP128 bounded device checks for an explicitly registered validation profile.

The measurement profile checks N>65536, unit scale and no user callbacks.
The extended profile retains the separate legacy compatibility regressions.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from cc_fusion_ab_references import references, PATTERNS
from audit_cc_coverage import parse_mapping, validate_coverage

# Parity, row tail, both load backends, scalar column storage and long row.
SAMPLE_N = (65856, 67600, 69938, 131072, 100352, 133100)
BUDGET_SECONDS = 300


def write_progress(path, record):
    # Progress is updated repeatedly within this run; submission records stay exclusive.
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def worker():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    profile = cfg['validation'].get('profile', 'extended-regression')
    mgr.require(profile in ('extended-regression', 'measurement-default'), 'unknown validation profile')
    measurement_default = profile == 'measurement-default'
    modes = ('plain',) if measurement_default else ('callbacks', 'plain')
    patterns = PATTERNS if measurement_default else ('impulse', 'random')
    scales = (1.,) if measurement_default else (1., .375)
    mgr.require(cfg['validation'].get('budget_seconds') == BUDGET_SECONDS
        and tuple(cfg['validation'].get('sample_N', ())) == SAMPLE_N, 'bounded regression config mismatch')
    built = json.loads(a.build_record.read_text())
    mgr.require(built['complete'], 'build incomplete')
    coverage_path = mgr.inside(cfg['validation']['coverage'])
    coverage = json.loads(coverage_path.read_text())
    source = mgr.inside(cfg['build']['source_dir'])
    recorded_map = subprocess.check_output(['git', '-C', built['arm']['source_repo'], 'show',
        built['arm']['source_commit']+':rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/node_factory.cpp'], text=True)
    audit = validate_coverage(coverage, parse_mapping(recorded_map))
    by_n = {c['N']: c for c in coverage['public']}
    mgr.require(set(SAMPLE_N) <= by_n.keys(), 'regression sample not in audited default manifest')
    install = mgr.inside(built['arm']['install'])
    lib = install/'lib/librocfft.so.0.1'
    build = mgr.inside(a.build)
    folder = mgr.inside(a.run)/'cc-local-fast-validation'
    folder.mkdir()
    helpers = folder/'helpers'
    helpers.mkdir()
    env = mgr.environment(mgr.inside(a.cache))
    selected = dict(env, LD_PRELOAD=str(lib),
        LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    here = Path(__file__).resolve().parent
    record = dict(complete=False, formal=False, scope=cfg['validation'].get('scope', '300-second targeted regression'),
        profile=profile, callbacks_enabled=not measurement_default, scales=scales,
        known_limitations=cfg['validation'].get('known_limitations', []),
        budget_seconds=BUDGET_SECONDS, source_commit=built['arm']['source_commit'],
        library_sha256=built['arm']['library_sha256'], coverage_sha256=mgr.common.sha(coverage_path),
        coverage_audit=audit, controls=[], public=[],
        omitted=['279 internal geometries', '193-size repeated full matrix', '78 profiler launches'],
        prior_public_evidence='experiments/EXP-128/runs/EXP-128-cc-local-mapfix-validate-20261021/cc-local-validation.json',
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def save():
        record['elapsed_seconds'] = time.monotonic()-started
        write_progress(a.run/'cc-local-validation.json', record)

    def run(command, directory, label, selected_env=env):
        directory.mkdir(parents=True, exist_ok=True)
        command = list(map(str, command))
        t = time.monotonic()
        remaining = 288-(t-started)
        mgr.require(remaining > 0, 'regression budget exhausted')
        with (directory/(label+'.out')).open('wb') as out, (directory/(label+'.err')).open('wb') as err:
            proc = subprocess.run(command, env=selected_env, cwd=directory,
                                  stdout=out, stderr=err, timeout=remaining)
        mgr.dumps(directory/(label+'-command.json'), dict(command=command,
            returncode=proc.returncode, elapsed_seconds=time.monotonic()-t))
        mgr.require(proc.returncode == 0, label+' failed: '+str(directory))

    def check(case, direction, mode, control=False):
        n = case['N']
        callback = True if mode == 'callbacks' else False if mode == 'plain' else mode
        key = '%d-%s-%s'%(n, direction, mode)
        scratch = mgr.inside(a.cache)/'fast-references'/key
        scratch.mkdir(parents=True)
        log = folder/key
        try:
            manifest, meta = references(n, direction, callback, scratch,
                patterns, scales)
            run([guard, n, direction, manifest, mode], log, 'guard', dict(selected,
                ROCFFT_LAYER='40', ROCFFT_LOG_PLAN_PATH=str(log/'plan.txt'),
                ROCFFT_LOG_RTC_PATH=str(log/'rtc.txt')))
            output = (log/'guard.out').read_text()
            mgr.require(output.count('EVEN_CC_GUARD_PASS ') == len(meta), 'incomplete regression guard')
            generated = (log/'rtc.txt').read_text()
            if control and direction == 'z2d' and mode in ('callbacks', 'load'):
                mgr.require('_unique_load_v1' in generated, 'legacy unique-load repair not selected')
            if not control:
                roles = (4, 5) if direction == 'z2d' else (6, 7)
                for role in roles:
                    mgr.require('_cc_local_v1_role%d_C%d_Q%d_'%(role, case['C'], case['Q']) in generated,
                                'unexpected default CC adapter/decomposition')
            record['controls' if control else 'public'].append(dict(case, direction=direction,
                callbacks=callback, references=meta, elapsed_seconds=json.loads(
                    (log/'guard-command.json').read_text())['elapsed_seconds']))
            save()
            print('REGRESSION_PASS', key, flush=True)
        finally:
            shutil.rmtree(scratch)

    try:
        guard = helpers/'public-guard'
        identity = helpers/'device-identity'
        for output, src, flags in [
            (guard, here/'cc_fusion_ab_guard.cpp', ['-I'+str(source/'shared'),
             '-I'+str(install/'include'), '-L'+str(install/'lib'),
             '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-lstdc++fs']),
            (identity, ROOT/'tools/fft_measurement/device_identity.cpp', [])]:
            run([mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936',
                 '-mcumode', src, *flags, '-o', output], folder, 'compile-'+output.name)
        gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True, timeout=10))
        mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936'
            and re.fullmatch('[0-9a-f]{32}', gpu['uuid']) and int(gpu['uuid'], 16), 'single gfx936 required')
        record['gpu'] = gpu
        linked = subprocess.check_output(['ldd', str(guard)], env=selected, text=True, timeout=10)
        loaded = [mgr.inside(x.split('=>')[-1].strip().split()[0])
                  for x in linked.splitlines() if 'librocfft.so' in x]
        mgr.require('not found' not in linked and loaded == [lib.resolve()], 'wrong actual library')
        (folder/'ldd.txt').write_text(linked)
        text = (build/'CMakeCache.txt').read_text()
        mgr.require('ROCFFT_CC_REAL_FUSION:BOOL=ON' in text
            and 'ROCFFT_CC_LOCAL_REAL_FUSION:BOOL=ON' in text, 'wrong fusion switches')
        # Legacy compatibility is separate from an explicitly registered measurement scope.
        if not measurement_default:
            for direction in ('z2d', 'd2z'):
                for mode in ('callbacks', 'load', 'store', 'plain'):
                    check({'N': 65536}, direction, mode, True)
        for n in SAMPLE_N:
            for direction in ('z2d', 'd2z'):
                for mode in modes:
                    check(by_n[n], direction, mode)
        mgr.require(len(record['controls']) == (0 if measurement_default else 8)
            and len(record['public']) == len(SAMPLE_N)*2*len(modes),
                    'targeted matrix incomplete')
        finish(record, built, gpu, env, lib, identity)
    except Exception as error:
        record['failure'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True, scope=record['scope'],
        controls=len(record['controls']), public=len(record['public']), elapsed_seconds=record['elapsed_seconds'])))


def main():
    # A separate process group bounds the entire gate, including compiler children.
    process = subprocess.Popen([sys.executable, '-B', __file__, '--worker', *sys.argv[1:]],
                               start_new_session=True)
    try:
        code = process.wait(timeout=290)
        if code:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return code
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        run_path = Path(sys.argv[sys.argv.index('--run')+1])
        path = run_path/'cc-local-validation.json'
        record = json.loads(path.read_text()) if path.exists() else {}
        record.update(complete=False, failure=dict(type='ValidationTimeout',
            message='300-second regression budget exhausted'), budget_seconds=BUDGET_SECONDS)
        write_progress(path, record)
        print('Validation stopped within the 300-second budget', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.argv.remove('--worker')
        worker()
    else:
        sys.exit(main())
