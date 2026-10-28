"""Matched EXP125/V6 stages and phase-order-only interventions on five powers of two."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/fft_measurement'),
               str(ROOT / 'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from diagnose_rows_v3_regression import launch, check_process, case_environment
from diagnose_cc_v5_regressions import timing, counter, temporary, cleanup, write
from cc_v5_regression_common import rtc_sources, profile_evidence
from cc_regression_evidence import actual_sources


def trace(a, cfg, item, env, gpu):
    label = '%04d_%d_%s' % (item['index'], item['N'], item['arm'])
    folder = a.run / 'profiles' / label
    folder.mkdir(parents=True)
    meta, profile = folder / 'metadata', folder / 'profile'
    for p in (meta, meta / 'harness', profile, profile / 'harness', profile / 'data'):
        p.mkdir()
    tmp = temporary(a, 'trace-' + label)
    e = dict(item, valid=False, formal=False, folder=str(folder), timing_valid=False)
    try:
        selected, binary, identity, linked = case_environment(a, cfg, item, env, gpu)
        selected['TMPDIR'] = str(tmp)
        (folder / 'ldd.txt').write_text(linked)
        m_env = dict(selected, FFT_TEST_OUT=str(meta / 'harness'), ROCFFT_LAYER='40',
                     ROCFFT_LOG_PLAN_PATH=str(meta / 'plan.txt'),
                     ROCFFT_LOG_RTC_PATH=str(meta / 'rtc.txt'))
        result = launch([binary, item['N'], 1, item['func']], m_env, meta, 'metadata')
        e['metadata_check'] = check_process(meta, 'metadata', meta / 'harness',
                                             item['N'], item['func'], result)
        result = launch([mgr.DTK + '/bin/hipprof', '--hip-trace', '--trace-args',
                         '--output-type', '0', '-o', profile / 'trace', '-d', profile / 'data',
                         binary, item['N'], 1, item['func']],
                        dict(selected, FFT_TEST_OUT=str(profile / 'harness')), profile, 'trace')
        e['profile_check'] = check_process(profile, 'trace', profile / 'harness',
                                            item['N'], item['func'], result)
        plan = (meta / 'plan.txt').read_text()
        events = json.loads((profile / 'trace.json').read_text())['traceEvents']
        e['trace'], warning = profile_evidence(plan, events, item['func'])
        names = e['trace']['kernel_names']
        expected = cfg['power2_selection']['expected_sources'][str(item['N'])][item['arm']]
        mgr.require(names == [x['name'] for x in expected], 'actual FFT stages differ')
        captured = rtc_sources((meta / 'rtc.txt').read_text())
        for x in expected:
            mgr.require(x['name'] in captured and hashlib.sha256(
                captured[x['name']].encode()).hexdigest() == x['sha256'],
                'actual source differs from the registered measured kernel')
        e['actual_sources'] = actual_sources((meta / 'rtc.txt').read_text(), names)
        e['occupancy_log_values'] = list(map(int, re.findall(r'Kernel occupancy:\s*(\d+)', plan)))
        e['timing_valid'] = warning is None
        if warning:
            e['timestamp_warning'] = warning
        e.update(valid=True, library_sha256=identity['library_sha256'])
    except Exception as error:
        e['error'] = dict(kind=type(error).__name__, message=str(error))
    finally:
        e['temporary_bytes_removed'] = cleanup(a, tmp)
    write(folder / 'review.json', e)
    print('TRACE', item['N'], item['arm'], e['valid'], e['timing_valid'], flush=True)
    return e


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'run', 'build', 'cache'):
        parser.add_argument('--' + name, type=Path, required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    for name in ('run', 'build', 'cache'):
        setattr(a, name, mgr.inside(getattr(a, name)))
    mgr.common.single_gpu_allocation(os.environ)
    env = mgr.environment(a.cache)
    env['FFT_TEST_ITERS'] = '30'
    program = cfg['diagnostic_program']
    for name in ('binary', 'identity', 'provenance'):
        mgr.require(mgr.common.sha(Path(program[name])) == program[name + '_sha256'],
                    'diagnostic program input differs: ' + name)
    gpu = json.loads(subprocess.check_output([program['identity']], env=env, text=True))
    mgr.require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936',
                'single gfx936 required')
    selection = cfg['power2_selection']
    result = dict(complete=False, formal=False, job_id=os.environ['SLURM_JOB_ID'],
                  start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  gpu=gpu, host=socket.gethostname(), timing=[], traces=[], pmc=[],
                  failures=[], timestamp_warnings=[], production_source_modified=False,
                  original_formal_measurement='991869')

    def save():
        result['updated_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write(a.run / 'diagnostic-result.json', result)

    def accept(kind, entry):
        result[kind].append(entry)
        if not entry['valid']:
            result['failures'].append(dict(stage=kind, N=entry['N'], arm=entry['arm'],
                                           variant=entry.get('variant'), error=entry['error']))
        if entry.get('timestamp_warning'):
            result['timestamp_warnings'].append(dict(N=entry['N'], arm=entry['arm'],
                                                      warning=entry['timestamp_warning']))
        save()

    try:
        for item in selection['clean_schedule']:
            accept('timing', timing(a, cfg, item, env, gpu, item['variant']))
        traces = {}
        for item in selection['trace_schedule']:
            entry = trace(a, cfg, item, env, gpu)
            traces[item['N'], item['func'], item['arm']] = entry
            accept('traces', entry)
        for item in selection['counter_schedule']:
            accept('pmc', counter(a, cfg, item, env, gpu, traces, item['mode']))
        result['complete'] = (not result['failures']
                              and len(result['timing']) == 20
                              and len(result['traces']) == 10
                              and len(result['pmc']) == 16)
    finally:
        result['end'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    mgr.require(result['complete'], 'independent errors retained in diagnostic-result.json')


if __name__ == '__main__':
    main()
