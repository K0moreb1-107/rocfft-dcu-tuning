"""One fresh process per case/version, all event samples retained; no legacy changes."""
import argparse
import datetime
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from common import ROOT, inside, reference, require, cases, sha, single_gpu_allocation, write_json
from sample_contract import POLICY, SOURCE_SHA, SOURCE_NAME, arms, iterations, manifest, schedule, read_samples, validate_process
from summarize_samples import report

HERE = Path(__file__).resolve().parent
DTK = Path('/public/software/compiler/dtk-26.04')

def command(args, env=None):
    return subprocess.check_output([str(a) for a in args], env=env, stderr=subprocess.STDOUT, text=True)

def plan(m):
    return dict(policy=POLICY, run_id=m['run_id'], cases=len(cases(m)), rounds=1, processes=len(schedule(m)), processes_per_case_arm=1, events_per_case_arm=iterations(m), schedule=schedule(m))

def execute(m):
    selected = arms(m)
    allocation = single_gpu_allocation(os.environ)
    require(sha(HERE / SOURCE_NAME) == SOURCE_SHA, 'frozen source changed')
    reference()
    for arm in selected:
        a = m['arms'][arm]
        require(command(['git', '-C', a['source_repo'], 'rev-parse', a['source_commit'] + '^{commit}']).strip() == a['source_commit'], 'source commit unavailable')
        lib = inside(Path(a['install']) / 'lib/librocfft.so.0.1')
        require(sha(lib) == a['library_sha256'], arm + ': install hash mismatch')
    from common import prepare_measurement_paths
    run, build, logs, cache = prepare_measurement_paths(m)
    write_json(run / 'preregistration.json', m)
    write_json(run / 'plan.json', plan(m))
    env = os.environ.copy()
    env.update(HIP_PATH=str(DTK), ROCM_PATH=str(DTK), HIP_PLATFORM='amd', PATH=str(DTK / 'bin') + ':' + env.get('PATH', ''), FFT_TEST_ITERS=str(iterations(m)), ROCFFT_RTC_CACHE_READ_DISABLE='1', ROCFFT_RTC_CACHE_WRITE_DISABLE='1')
    # Do not inherit another user's preload, profile/solution overrides, or loader debug.
    for key in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_DEBUG', 'LD_DEBUG_OUTPUT', 'FFT_TEST_OUT'):
        env.pop(key, None)
    require(not any(k.startswith('ROCFFT_') and k not in ('ROCFFT_RTC_CACHE_READ_DISABLE', 'ROCFFT_RTC_CACHE_WRITE_DISABLE') for k in env), 'unexpected ROCFFT environment override; resolve before running')
    env['LD_LIBRARY_PATH'] = ':'.join(str(p) for p in (DTK/'hip/lib', DTK/'dcc/comgr/lib64', DTK/'lib'))
    env['MPLCONFIGDIR'] = str(cache / 'matplotlib')
    os.environ['MPLCONFIGDIR'] = env['MPLCONFIGDIR']
    # Fail before GPU sampling if plotting is unavailable. No plot work while timing.
    import matplotlib
    identity = build / 'device_identity'
    compile_identity = [DTK/'bin/hipcc', '-O3', '-std=c++17', HERE/'device_identity.cpp', '-o', identity]
    (logs / 'compile_identity.txt').write_text(command(compile_identity, env), encoding='utf-8')
    gpu = json.loads(command([identity], env))
    require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == m['gpu_arch'], 'GPU does not match preregistration')
    require(re.fullmatch('[0-9a-f]{32}', gpu['uuid']) is not None and int(gpu['uuid'], 16) != 0, 'invalid GPU UUID')
    provenance = dict(policy=POLICY, source_sha256=SOURCE_SHA, source_origin='EXP-123 event loop with preallocated per-event samples', event_iterations=iterations(m), timing_warmups=3, plotting_version=matplotlib.__version__, job_id=os.environ['SLURM_JOB_ID'], allocation_gpu=os.environ['SLURM_JOB_GPUS'], host=socket.gethostname(), gpu=gpu, start=datetime.datetime.now(datetime.timezone.utc).isoformat(), complete=False, compiler_version=command([DTK/'bin/hipcc', '--version'], env), environment={k:v for k,v in env.items() if k.startswith(('HIP', 'ROCM', 'ROCFFT', 'ROCR', 'CUDA', 'SLURM', 'FFT_TEST'))}, arms={})
    provenance.update(allocation)
    binaries = {}
    arm_env = {}
    # Compile once against a declared reference ABI, preload each exact arm library.
    binary = build / 'fft_test_1d'
    official = Path(m['arms'][selected[0]]['install'])
    compile_fft = [DTK/'bin/hipcc', '-O3', '-std=c++17', HERE/SOURCE_NAME, '-I'+str(official/'include'), '-L'+str(official/'lib'), '-Wl,-rpath,'+str(official/'lib'), '-lrocfft', '-o', binary]
    (logs / 'compile_fft.txt').write_text(command(compile_fft, env), encoding='utf-8')
    provenance['compile_commands'] = [[str(v) for v in c] for c in (compile_identity, compile_fft)]
    provenance['identity_binary_sha256'] = sha(identity)
    for arm in selected:
        a = m['arms'][arm]
        install = Path(a['install'])
        lib = inside(install/'lib/librocfft.so.0.1')
        arm_env[arm] = dict(env, LD_PRELOAD=str(lib), LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
        ldd = command(['ldd', binary], arm_env[arm])
        require('not found' not in ldd, 'unresolved runtime library')
        loaded = []
        for line in ldd.splitlines():
            if 'librocfft.so' in line:
                path = line.strip().split('=>')[-1].strip().split(' ')[0]
                loaded.append(inside(path))
        require(len(set(loaded)) == 1 and loaded[0] == lib, 'actual linked rocFFT is not declared library')
        (logs / (arm+'_ldd.txt')).write_text(ldd, encoding='utf-8')
        provenance['arms'][arm] = dict(a, actual_library=str(lib), binary_sha256=sha(binary), source_head=command(['git','-C',a['source_repo'],'rev-parse','HEAD']).strip(), source_status=command(['git','-C',a['source_repo'],'status','--porcelain=v1','--untracked-files=no']))
        binaries[arm] = binary
    tool_names = ('common.py', 'sample_contract.py', 'run_samples.py', 'summarize_samples.py', 'plot_samples.py', SOURCE_NAME, 'device_identity.cpp')
    provenance['tools_sha256'] = {name: sha(HERE/name) for name in tool_names}
    entries = []
    write_json(run / 'provenance.json', provenance)
    try:
        for item in schedule(m):
            arm = item['arm']
            a = m['arms'][arm]
            lib = Path(provenance['arms'][arm]['actual_library'])
            require(sha(lib) == a['library_sha256'], 'library changed during run')
            require(sha(binary) == provenance['arms'][arm]['binary_sha256'], 'measurement executable changed during run')
            require(sha(identity) == provenance['identity_binary_sha256'], 'identity executable changed')
            process_gpu = json.loads(command([identity], env))
            require(process_gpu == gpu, 'GPU/runtime identity changed during run')
            label = '%04d_%d_%s_r%d_s%d_%s' % (item['index'], item['N'], item['func'], item['round'], item['slot'], arm)
            case = run / 'processes' / label
            case.mkdir(parents=True)
            tmp = cache / 'tmp' / label
            tmp.mkdir(parents=True)
            process_env = dict(arm_env[arm], FFT_TEST_OUT=str(case), TMPDIR=str(tmp))
            args = [str(binaries[arm]), str(item['N']), '1', item['func'], '1']
            started = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with (case/'stdout.txt').open('xb') as out, (case/'stderr.txt').open('xb') as err:
                rc = subprocess.run(args, env=process_env, cwd=str(HERE), stdout=out, stderr=err).returncode
            entry = dict(item, start=started, end=datetime.datetime.now(datetime.timezone.utc).isoformat(), argv=args, returncode=rc, gpu=process_gpu, job_id=provenance['job_id'], host=provenance['host'], library_sha256=sha(lib))
            for key, filename in (('csv','fft_test_1d.csv'),('samples','fft_test_1d.samples.csv'),('stdout','stdout.txt'),('stderr','stderr.txt')):
                entry[key] = str((case/filename).relative_to(run))
                if (case/filename).is_file():
                    entry[key+'_sha256'] = sha(case/filename)
            entries.append(entry)
            require(rc == 0, 'correctness/process failure: ' + label)
            # Reject a bad row immediately, retaining all partial evidence.
            from common import read_rows
            rows = read_rows(case/'fft_test_1d.csv')
            require(len(rows) == 1, 'unexpected process row count')
            validate_process(rows[0], read_samples(case/'fft_test_1d.samples.csv'), item['N'], item['func'], iterations(m))
        for arm in selected:
            require(sha(provenance['arms'][arm]['actual_library']) == m['arms'][arm]['library_sha256'], 'library changed at completion')
        require(json.loads(command([identity], env)) == gpu, 'GPU changed at completion')
        require(all(sha(HERE/name) == digest for name, digest in provenance['tools_sha256'].items()), 'measurement tools changed during run')
        provenance['complete'] = True
    finally:
        provenance['end'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (run/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n', encoding='utf-8')
        write_json(run/'processes.json', entries)
    report(run)
    print(run / 'comparison.md')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest', type=Path)
    ap.add_argument('--execute', action='store_true', help='run only in a one-GPU Slurm allocation')
    args = ap.parse_args()
    try:
        if args.execute:
            inside(args.manifest)
        m = manifest(args.manifest)
        if args.execute:
            execute(m)
        else:
            print(json.dumps(plan(m), indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        ap.exit(1, 'measurement rejected: %s\n' % e)
