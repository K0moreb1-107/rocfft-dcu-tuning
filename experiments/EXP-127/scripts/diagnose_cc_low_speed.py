"""Default-plan CC fusion traces and per-kernel profiles; never formal timing."""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr
sys.path.insert(0, str(ROOT/'tools/fft_measurement'))
import cufft261012_contract as contract


def launch(argv, env, folder, label, timeout=180):
    with (folder/(label+'.out')).open('xb') as out, (folder/(label+'.err')).open('xb') as err:
        try:
            code = subprocess.run(list(map(str, argv)), cwd=folder, env=env, stdout=out,
                                  stderr=err, timeout=timeout).returncode
            result = dict(argv=list(map(str, argv)), returncode=code)
        except subprocess.TimeoutExpired:
            result = dict(argv=list(map(str, argv)), returncode=None, timeout_seconds=timeout)
        except OSError as error:
            result = dict(argv=list(map(str, argv)), returncode=None, error=str(error))
    mgr.dumps(folder/(label+'-command.json'), result)
    return result


def profile_case(args, cfg, target, gpu, base_env, binary, identity, item, pmc=False):
    n, func, arm = item['N'], item['func'], item['arm']
    folder = args.run/('pmc' if pmc else 'profiles')/('%04d_%d_%s_%s'%(item['index'], n, func, arm))
    folder.mkdir(parents=True)
    data = folder/'data'; data.mkdir()
    output = folder/'harness'; output.mkdir()
    temporary = args.cache/(folder.parent.name+'-'+folder.name); temporary.mkdir()
    a = cfg['arms'][arm]
    lib = mgr.inside(a['install'])/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(lib) == a['library_sha256'], 'profile library changed')
    mgr.require(mgr.common.sha(binary) == cfg['diagnostic_program']['binary_sha256'], 'timer binary changed')
    mgr.require(mgr.common.sha(identity) == cfg['diagnostic_program']['identity_sha256'], 'identity binary changed')
    actual = json.loads(subprocess.check_output([str(identity)], env=base_env, text=True))
    mgr.require(actual == gpu, 'diagnostic GPU identity changed')
    env = dict(base_env, LD_PRELOAD=str(lib), LD_LIBRARY_PATH=str(lib.parent)+':'+base_env['LD_LIBRARY_PATH'],
               FFT_TEST_OUT=str(output), TMPDIR=str(temporary))
    linked = subprocess.check_output(['ldd', str(binary)], env=env, text=True)
    loaded = [mgr.inside(line.strip().split('=>')[-1].strip().split()[0])
              for line in linked.splitlines() if 'librocfft.so' in line]
    mgr.require('not found' not in linked and len(set(loaded)) == 1 and loaded[0] == lib,
                'actual rocFFT library differs from registration')
    (folder/'ldd.txt').write_text(linked)
    entry = dict(item, pmc=pmc, formal=False, valid=False, library_sha256=a['library_sha256'])
    if not pmc:
        # Plan logging also queries occupancy on every launch. Keep that
        # instrumentation in a separate process, out of the timing trace.
        metadata = folder/'metadata'; metadata.mkdir()
        meta_output = metadata/'harness'; meta_output.mkdir()
        meta_env = dict(env, FFT_TEST_OUT=str(meta_output), ROCFFT_LAYER='40',
                        ROCFFT_LOG_PLAN_PATH=str(metadata/'plan.txt'),
                        ROCFFT_LOG_RTC_PATH=str(metadata/'rtc.txt'))
        entry['metadata_process'] = launch([binary,str(n),'1',func],meta_env,metadata,'plan')
    profiler = Path(mgr.DTK)/'bin/hipprof'
    # Keep the timeline and API launch arguments. --stats alone suppresses it.
    argv = [profiler, '--hip-trace', '--trace-args', '--output-type', '0']
    if pmc:
        role = 'paired_pre_columns_v2' if func == 'z2d_1d' else 'generic_paired_post_v2'
        argv += ['--pmc', '--kernel-name', role]
    argv += ['-o', folder/('pmc' if pmc else 'profile'), '-d', data, binary, str(n), '1', func]
    entry['process'] = launch(argv, env, folder, 'profile', timeout=300 if pmc else 180)
    try:
        mgr.require(entry['process']['returncode'] == 0, 'profiler/process failed')
        if not pmc:
            mgr.require(entry['metadata_process']['returncode'] == 0, 'plan metadata process failed')
            meta_rows = contract.read_rows(meta_output/'fft_test_1d.csv')
            mgr.require(len(meta_rows) == 1, 'unexpected metadata harness row count')
            contract.validate_process(meta_rows[0],contract.read_samples(meta_output/'fft_test_1d.samples.csv'),
                                      contract.read_check(meta_output/'fft_test_1d.check.csv'),n,func,30)
        rows = contract.read_rows(output/'fft_test_1d.csv')
        mgr.require(len(rows) == 1, 'unexpected harness row count')
        check = contract.read_check(output/'fft_test_1d.check.csv')
        samples = contract.read_samples(output/'fft_test_1d.samples.csv')
        contract.validate_process(rows[0], samples, check, n, func, 30)
        entry['correctness'] = check
        if not pmc:
            summaries = list(folder.glob('*.hipkernel.csv'))
            if not summaries:
                # Export existing trace data on the CPU; never rerun the workload.
                entry['statistics_export'] = launch([profiler, '--hip-trace', '--stats',
                    '--db-path', data, '-d', data, '-o', folder/'statistics'],
                    base_env, folder, 'statistics-export')
                summaries = list(folder.glob('*.hipkernel.csv'))
            mgr.require(len(summaries) == 1, 'missing or ambiguous kernel summary')
            with summaries[0].open(newline='') as stream:
                kernels = list(csv.DictReader(stream))
            mgr.require(kernels and {'Name','Calls','TotalDurationNs'} <= set(kernels[0]),
                        'unexpected kernel summary schema')
            entry['all_kernel_rows'] = kernels
            if arm == 'candidate':
                expected = cfg['expected_boundaries'][str(n)][func]
                matched = [row for row in kernels if expected in row['Name']]
                mgr.require(len(matched) == 1 and int(matched[0]['Calls']) == 41,
                            'fused boundary absent or wrong execute count')
                mgr.require(len([row for row in kernels if row['Calls'].isdigit()
                                 and int(row['Calls']) == 41]) == 2,
                            'candidate does not execute exactly two transform kernels')
                mgr.require(not any(re.search(r'(c2r_even_pre|r2c_even_post)', row['Name'])
                                    for row in kernels), 'standalone real boundary still executes')
                entry['fused_boundary'] = matched[0]
                entry['expected_boundary'] = expected
            entry['timing_interpretation'] = ('41 transforms = 1 correctness + 10 warmups + 30 samples. '
                'Keep all records; use chronological trace to isolate measured launches. '
                'Profiler durations are diagnostics, never replacement formal event times. '
                'Plan/occupancy logging is confined to the independent metadata process.')
        entry['valid'] = True
    except (ValueError, OSError, KeyError, TypeError) as error:
        entry['error'] = str(error)
    entry['files'] = {p.relative_to(folder).as_posix():mgr.common.sha(p)
                      for p in folder.rglob('*') if p.is_file()}
    mgr.dumps(folder/'review.json', entry)
    print(json.dumps(dict(N=n,func=func,arm=arm,pmc=pmc,valid=entry['valid'],error=entry.get('error'))),flush=True)
    target.append(entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config','run','build','cache'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    cfg = mgr.load(args.config)
    for name in ('run','build','cache'): setattr(args, name, mgr.inside(getattr(args,name)))
    mgr.require(json.loads((args.run/'preregistration.json').read_text()) == cfg, 'unfrozen diagnostic config')
    mgr.common.single_gpu_allocation(os.environ)
    program = cfg['diagnostic_program']
    provenance = mgr.inside(program['provenance'])
    mgr.require(mgr.common.sha(provenance) == program['provenance_sha256'], 'original measurement provenance changed')
    original = json.loads(provenance.read_text())
    mgr.require(original['job_id'] == '922865' and original['complete']
                and original['arms']['official']['binary_sha256'] == program['binary_sha256']
                and original['identity_binary_sha256'] == program['identity_sha256'],
                'diagnostic binary is not the measured executable')
    binary = mgr.inside(program['binary']); identity = mgr.inside(program['identity'])
    mgr.require(mgr.common.sha(binary) == program['binary_sha256'], 'use the actual 922865 timing binary')
    mgr.require(mgr.common.sha(identity) == program['identity_sha256'], 'device helper differs')
    for name,digest in contract.SOURCE_FILES.items():
        mgr.require(mgr.common.sha(ROOT/'tools/fft_measurement'/name) == digest, 'v3 source changed')
    env = mgr.environment(args.cache); env['FFT_TEST_ITERS'] = '30'
    gpu = json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(gpu == program['gpu'], 'diagnostic must use the same GPU/runtime as 922865')
    record = dict(complete=False, formal=False, job_id=os.environ['SLURM_JOB_ID'],host=socket.gethostname(),
                  gpu=gpu, program=program, start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  profiles=[], pmc=[])
    try:
        for item in contract.schedule(cfg):
            profile_case(args,cfg,record['profiles'],gpu,env,binary,identity,item)
        for item in cfg['pmc_cases']:
            profile_case(args,cfg,record['pmc'],gpu,env,binary,identity,item,pmc=True)
        record['complete'] = len(record['profiles']) == len(contract.schedule(cfg)) and all(
            item['valid'] for item in record['profiles'])
        record['pmc_complete'] = all(item['valid'] for item in record['pmc'])
    finally:
        record['end'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        mgr.dumps(args.run/'diagnostic-result.json',record)
    mgr.require(record['complete'], 'one or more diagnostic traces failed; partial evidence retained')


if __name__ == '__main__': main()
