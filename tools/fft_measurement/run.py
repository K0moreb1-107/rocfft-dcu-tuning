"""Plan by default; --execute performs one preregistered formal Slurm run."""
import argparse
import datetime
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from common import ARMS, POLICY, ROOT, SOURCE_SHA, inside, manifest, reference, require, schedule, sha, write_json
from summarize import report

HERE = Path(__file__).resolve().parent
DTK = Path('/public/software/compiler/dtk-26.04')

def command(args, env=None):
    return subprocess.check_output([str(a) for a in args], env=env, stderr=subprocess.STDOUT, text=True)

def plan(m):
    return dict(policy=POLICY, run_id=m['run_id'], cases=15, rounds=8, processes=720, processes_per_case_arm=16, events_per_case_arm=800, schedule=schedule())

def execute(m):
    require(os.environ.get('SLURM_JOB_ID') and os.environ.get('SLURM_JOB_GPUS'), 'execute requires a Slurm GPU allocation')
    require(os.environ.get('SLURM_JOB_NUM_NODES', '1') == '1', 'one-node allocation required')
    job_gpus = os.environ['SLURM_JOB_GPUS'].split(',')
    require(len(job_gpus) == 1 and job_gpus[0].strip(), 'exactly one allocated GPU required')
    require(sha(HERE / 'fft_test_1d.cpp') == SOURCE_SHA, 'frozen source changed')
    reference()
    for arm in ARMS:
        a = m['arms'][arm]
        require(command(['git', '-C', a['source_repo'], 'rev-parse', a['source_commit'] + '^{commit}']).strip() == a['source_commit'], 'source commit unavailable')
        lib = inside(Path(a['install']) / 'lib/librocfft.so.0.1')
        require(sha(lib) == a['library_sha256'], arm + ': install hash mismatch')
    run = ROOT / 'results/fft_measurement' / m['run_id']
    build = ROOT / 'build/fft_measurement' / m['run_id']
    logs = ROOT / 'logs/fft_measurement' / m['run_id']
    for directory in (run, build, logs):
        require(not directory.exists(), 'run_id already used: ' + str(directory))
    for directory in (run, build, logs):
        directory.mkdir(parents=True)
    write_json(run / 'preregistration.json', m)
    write_json(run / 'plan.json', plan(m))
    env = os.environ.copy()
    env.update(HIP_PATH=str(DTK), ROCM_PATH=str(DTK), HIP_PLATFORM='amd', PATH=str(DTK / 'bin') + ':' + env.get('PATH', ''), FFT_TEST_ITERS='50', ROCFFT_RTC_CACHE_READ_DISABLE='1', ROCFFT_RTC_CACHE_WRITE_DISABLE='1')
    # Do not inherit another user's preload, profile/solution overrides, or loader debug.
    for key in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_DEBUG', 'LD_DEBUG_OUTPUT', 'FFT_TEST_OUT'):
        env.pop(key, None)
    require(not any(k.startswith('ROCFFT_') and k not in ('ROCFFT_RTC_CACHE_READ_DISABLE', 'ROCFFT_RTC_CACHE_WRITE_DISABLE') for k in env), 'unexpected ROCFFT environment override; resolve before running')
    env['LD_LIBRARY_PATH'] = ':'.join(str(p) for p in (DTK/'hip/lib', DTK/'dcc/comgr/lib64', DTK/'lib'))
    identity = build / 'device_identity'
    compile_identity = [DTK/'bin/hipcc', '-O3', '-std=c++17', HERE/'device_identity.cpp', '-o', identity]
    (logs / 'compile_identity.txt').write_text(command(compile_identity, env), encoding='utf-8')
    gpu = json.loads(command([identity], env))
    require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == m['gpu_arch'], 'GPU does not match preregistration')
    require(re.fullmatch('[0-9a-f]{32}', gpu['uuid']) is not None and int(gpu['uuid'], 16) != 0, 'invalid GPU UUID')
    provenance = dict(policy=POLICY, source_sha256=SOURCE_SHA, source_origin='EXP-123 frozen fft_test_1d.cpp', job_id=os.environ['SLURM_JOB_ID'], allocation_gpu=os.environ['SLURM_JOB_GPUS'], host=socket.gethostname(), gpu=gpu, start=datetime.datetime.now(datetime.timezone.utc).isoformat(), complete=False, compiler_version=command([DTK/'bin/hipcc', '--version'], env), environment={k:v for k,v in env.items() if k.startswith(('HIP', 'ROCM', 'ROCFFT', 'ROCR', 'CUDA', 'SLURM', 'FFT_TEST'))}, arms={})
    binaries = {}
    arm_env = {}
    # As in the original retest, compile once against the official ABI, preload the exact arm library.
    binary = build / 'fft_test_1d'
    official = Path(m['arms']['official']['install'])
    compile_fft = [DTK/'bin/hipcc', '-O3', '-std=c++17', HERE/'fft_test_1d.cpp', '-I'+str(official/'include'), '-L'+str(official/'lib'), '-Wl,-rpath,'+str(official/'lib'), '-lrocfft', '-o', binary]
    (logs / 'compile_fft.txt').write_text(command(compile_fft, env), encoding='utf-8')
    provenance['compile_commands'] = [[str(v) for v in c] for c in (compile_identity, compile_fft)]
    provenance['identity_binary_sha256'] = sha(identity)
    for arm in ARMS:
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
    entries = []
    write_json(run / 'provenance.json', provenance)
    try:
        for item in schedule():
            arm = item['arm']
            a = m['arms'][arm]
            lib = Path(provenance['arms'][arm]['actual_library'])
            require(sha(lib) == a['library_sha256'], 'library changed during run')
            require(sha(binary) == provenance['arms'][arm]['binary_sha256'], 'measurement executable changed during run')
            process_gpu = json.loads(command([identity], env))
            require(process_gpu == gpu, 'GPU/runtime identity changed during run')
            label = '%04d_%d_%s_r%d_s%d_%s' % (item['index'], item['N'], item['func'], item['round'], item['slot'], arm)
            case = run / 'processes' / label
            case.mkdir(parents=True)
            tmp = build / 'tmp' / label
            tmp.mkdir(parents=True)
            process_env = dict(arm_env[arm], FFT_TEST_OUT=str(case), TMPDIR=str(tmp))
            args = [str(binaries[arm]), str(item['N']), '1', item['func'], '1']
            with (case/'stdout.txt').open('xb') as out, (case/'stderr.txt').open('xb') as err:
                rc = subprocess.run(args, env=process_env, cwd=str(HERE), stdout=out, stderr=err).returncode
            entry = dict(item, argv=args, returncode=rc, gpu=process_gpu, job_id=provenance['job_id'], host=provenance['host'], library_sha256=sha(lib))
            for key, filename in (('csv','fft_test_1d.csv'),('stdout','stdout.txt'),('stderr','stderr.txt')):
                entry[key] = str((case/filename).relative_to(run))
                entry[key+'_sha256'] = sha(case/filename)
            entries.append(entry)
            require(rc == 0, 'correctness/process failure: ' + label)
            # Reject a bad row immediately, retaining all partial evidence.
            from common import read_rows, validate_row
            rows = read_rows(case/'fft_test_1d.csv')
            require(len(rows) == 1, 'unexpected process row count')
            validate_row(rows[0], item['N'], item['func'])
        for arm in ARMS:
            require(sha(provenance['arms'][arm]['actual_library']) == m['arms'][arm]['library_sha256'], 'library changed at completion')
        require(json.loads(command([identity], env)) == gpu, 'GPU changed at completion')
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
        m = manifest(args.manifest)
        if args.execute:
            execute(m)
        else:
            print(json.dumps(plan(m), indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        ap.exit(1, 'measurement rejected: %s\n' % e)
