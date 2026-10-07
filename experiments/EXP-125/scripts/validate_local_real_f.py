#!/usr/bin/env python3
"""EXP-125 f: managed clean build, then correctness and executed-fusion evidence."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

def run_logged(argv, env, directory):
    directory.mkdir(parents=True, exist_ok=False)
    with (directory/'stdout.txt').open('xb') as out, (directory/'stderr.txt').open('xb') as err:
        subprocess.run(argv, env=env, stdout=out, stderr=err, check=True)

def main():
    build_cfg = mgr.load(Path(sys.argv[1]))
    cfg = mgr.load(Path(sys.argv[2]))
    mgr.require(os.environ.get('SLURM_JOB_ID') and os.environ.get('SLURM_JOB_GPUS')
                and len(os.environ['SLURM_JOB_GPUS'].split(',')) == 1, 'one GPU allocation required')
    mgr.execute_build(build_cfg)
    built = json.loads(Path(cfg['candidate_build_record']).read_text())
    mgr.require(built['complete'], 'candidate build did not complete')
    mgr.require(built['arm']['source_commit'] == cfg['source_commit'], 'candidate source mismatch')
    paths = mgr.claim(cfg, 'validate')
    env = mgr.environment(paths['cache'])
    candidate = mgr.inside(built['arm']['install'])
    lib = candidate/'lib/librocfft.so.0.1'
    sha = built['arm']['library_sha256']
    frozen = ROOT/'tools/fft_measurement/fft_test_1d.cpp'
    mgr.require(mgr.common.sha(frozen) == mgr.common.SOURCE_SHA == cfg['measurement_source_sha256'],
                'frozen correctness program changed')
    special = ROOT/cfg['spectral_guard_source']
    mgr.require(mgr.common.sha(special) == cfg['spectral_guard_source_sha256'], 'guard program changed')
    official = mgr.inside(cfg['official_install'])
    mgr.require(mgr.common.sha(official/'lib/librocfft.so.0.1') == cfg['official_library_sha256'],
                'official identity changed')
    identity = paths['build']/'device_identity'
    binary = paths['build']/'fft_test_1d'
    spectral = paths['build']/'spectral_guard_f'
    commands = [
        [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++17', str(ROOT/'tools/fft_measurement/device_identity.cpp'), '-o', str(identity)],
        [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++17', str(frozen), '-I'+str(official/'include'),
         '-L'+str(official/'lib'), '-Wl,-rpath,'+str(official/'lib'), '-lrocfft', '-o', str(binary)],
        [mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', str(special), '-I'+str(candidate/'include'),
         '-L'+str(candidate/'lib'), '-Wl,-rpath,'+str(candidate/'lib'), '-lrocfft', '-o', str(spectral)],
    ]
    for i, command in enumerate(commands):
        with (paths['logs']/('compile-%d.txt'%i)).open('xb') as output:
            subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
    gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
    mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == cfg['gpu_arch']
                and re.fullmatch('[0-9a-f]{32}', gpu['uuid']) and int(gpu['uuid'],16), 'GPU identity mismatch')
    env.update(LD_PRELOAD=str(lib), LD_LIBRARY_PATH=str(candidate/'lib')+':'+env['LD_LIBRARY_PATH'])
    binary_shas = {str(p):mgr.common.sha(p) for p in (binary, spectral, identity)}
    for program in (binary, spectral):
        linked = subprocess.check_output(['ldd', str(program)], env=env, text=True)
        loaded = [Path(line.strip().split('=>')[-1].strip().split(' ')[0]).resolve()
                  for line in linked.splitlines() if 'librocfft.so' in line]
        mgr.require('not found' not in linked and set(loaded) == {lib.resolve()}, 'loaded candidate mismatch')
        (paths['logs']/('ldd-'+program.name+'.txt')).write_text(linked)
    record = {'complete':False, 'formal':False, 'experiment':'EXP-125', 'candidate':'local-real-f',
              'job_id':os.environ['SLURM_JOB_ID'], 'gpu':gpu, 'source_commit':cfg['source_commit'],
              'baseline_commit':cfg['baseline_commit'], 'library_sha256':sha,
              'binaries':binary_shas, 'compile_commands':commands, 'checks':[], 'fusion_evidence':[],
              'start':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    mgr.dumps(paths['run']/'preregistration.json', cfg)
    def identity_check():
        mgr.require(mgr.common.sha(lib) == sha, 'candidate library changed')
        mgr.require(all(mgr.common.sha(Path(p)) == s for p,s in binary_shas.items()), 'binary changed')
        mgr.require(json.loads(subprocess.check_output([str(identity)], env=mgr.environment(paths['cache']), text=True)) == gpu, 'GPU changed')
    try:
        # Unchanged 15-case program, plus all five z2d cases in the LDS mode.
        for mode in ('registers', 'lds'):
            funcs = mgr.common.FUNCS if mode == 'registers' else ('z2d_1d',)
            for n in mgr.common.SIZES:
                for function in funcs:
                    identity_check()
                    case = paths['run']/'processes'/mode/('%d_%s'%(n,function))
                    case_env = dict(env, ROCFFT_EXP125_LOCAL_REAL_LOAD=mode, FFT_TEST_OUT=str(case))
                    run_logged([str(binary),str(n),'1',function,'1'],case_env,case)
                    rows=mgr.common.read_rows(case/'fft_test_1d.csv')
                    mgr.require(len(rows)==1,'wrong frozen quick-check row count')
                    mgr.common.validate_row(rows[0],n,function)
                    record['checks'].append({'mode':mode,'N':n,'func':function,'status':'PASS',
                                             'csv_sha256':mgr.common.sha(case/'fft_test_1d.csv')})
            # Six independent analytic spectra per size. Profile logging observes
            # the executed leaves; RTC logging independently preserves their source.
            for n in mgr.common.SIZES:
                identity_check()
                case = paths['run']/'spectral'/mode/str(n)
                case_env = dict(env, ROCFFT_EXP125_LOCAL_REAL_LOAD=mode, ROCFFT_LAYER='44',
                    ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'), ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'),
                    ROCFFT_LOG_PROFILE_PATH=str(case/'profile.txt'))
                run_logged([str(spectral),str(n)],case_env,case)
                stdout=(case/'stdout.txt').read_text(errors='replace')
                rtc=(case/'rtc.txt').read_text(errors='replace')
                plan=(case/'plan.txt').read_text(errors='replace') + stdout
                profile=(case/'profile.txt').read_text(errors='replace')
                mgr.require(stdout.count('status=PASS')==6 and 'LOCAL_REAL_ALL_PASS' in stdout,
                            'spectral/guard checks incomplete')
                mgr.require('EXP125 local real: folded Hermitian columns' in plan
                            and 'EXP125 local real: paired rows and adjacent real stores' in plan
                            and 'CS_KERNEL_CMPLX_TO_R' not in plan,'wrong real transform tree')
                names=set(re.findall(r'fft_rtc_[A-Za-z0-9_]+',rtc))
                names={name for name in names if '_local_real_' in name}
                mgr.require(any('_local_real_columns_N%d_%s'%(n,'reg' if mode=='registers' else 'lds') in name for name in names)
                            and any('_local_real_rows_N%d_%s'%(n,'reg' if mode=='registers' else 'lds') in name for name in names),
                            'specialized RTC kernels missing')
                schemes=re.findall(r'CS_KERNEL_[A-Z0-9_]+', profile)
                mgr.require(len(schemes)==12 and schemes.count('CS_KERNEL_STOCKHAM_BLOCK_CC')==6
                            and schemes.count('CS_KERNEL_STOCKHAM_BLOCK_RC')==6,
                            'execution did not use exactly two fused leaves per transform')
                record['fusion_evidence'].append({'mode':mode,'N':n,'spectral_cases':6,'guards':'PASS',
                    'input_unchanged':'PASS','executed_leaves_per_transform':2,'kernel_names':sorted(names),
                    'plan_sha256':mgr.common.sha(case/'plan.txt'), 'rtc_sha256':mgr.common.sha(case/'rtc.txt'),
                    'profile_sha256':mgr.common.sha(case/'profile.txt')})
        identity_check()
        mgr.require(mgr.source_identity(build_cfg)==built['plan']['source_identity'],'source changed during validation')
        record['complete']=True
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        mgr.dumps(paths['run']/'local-real-validation.json',record)
    print(paths['run']/'local-real-validation.json')

if __name__ == '__main__':
    main()
