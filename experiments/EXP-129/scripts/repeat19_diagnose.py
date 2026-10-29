"""Audit three independent paired reruns; profile cases that remain slower."""
import argparse
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts'),
                str(ROOT/'tools/fft_measurement'), str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from summarize_cufft261012 import aggregate
from cc_regression_evidence import trace_evidence, actual_sources, stats
from gate_validation_support import run, read_numerical_outputs, write
import cufft261012_contract as contract


def summarize(settings, config, folder):
    rounds = []
    expected = {(x['N'], x['func']) for x in config['cases']}
    for path in settings['runs']:
        manifest, provenance, rows, samples = aggregate(mgr.inside(path))
        mgr.require({(r['N'], r['func']) for r in rows} == expected,
                    'repeat cohort changed')
        mgr.require(set(manifest['arms']) == {'previous', 'candidate'}, 'repeat arms changed')
        mgr.require(provenance['host'] == settings['host']
                    and provenance['gpu']['uuid'] == settings['gpu_uuid'], 'repeat device changed')
        mgr.require(all(manifest['arms'][arm]['library_sha256'] == config['arms'][arm]['library_sha256']
                        for arm in config['arms']), 'repeat library changed')
        rounds.append((provenance, samples))
    mgr.require(len(rounds) == 3 and len({p['job_id'] for p, _ in rounds}) == 3,
                'require three independent successful jobs')
    original_m, original_p, original_rows, original_samples = aggregate(mgr.inside(settings['original_run']))
    mgr.require(all(original_m['arms'][arm]['library_sha256'] == config['arms'][arm]['library_sha256']
                    for arm in config['arms']), 'original library differs')
    cases = []
    for n, func in sorted(expected):
        values = []
        for provenance, samples in rounds:
            pair = {arm: stats([1000*x for x in samples[n, func, arm]]) for arm in config['arms']}
            pair['ratio_v6_current'] = pair['previous']['median']/pair['candidate']['median']
            pair['job_id'] = provenance['job_id']
            pair['iqr_nonoverlap_slower'] = pair['candidate']['p25'] > pair['previous']['p75']
            pair['drift'] = {arm: drift(samples[n, func, arm]) for arm in config['arms']}
            values.append(pair)
        ratios = [p['ratio_v6_current'] for p in values]
        before = statistics.median(original_samples[n, func, 'previous']) / statistics.median(original_samples[n, func, 'candidate'])
        cases.append(dict(N=n, func=func, original_ratio=before, repetitions=values,
                          median_ratio=statistics.median(ratios), slower_rounds=sum(r < 1 for r in ratios),
                          below_095_rounds=sum(r < .95 for r in ratios),
                          selected_for_diagnosis=statistics.median(ratios) < 1))
    result = dict(complete=True, formal=True, aggregation='Each ratio uses one independent 30-sample median per arm; no sample pooling.',
                  jobs=[p['job_id'] for p, _ in rounds], host=settings['host'], gpu_uuid=settings['gpu_uuid'],
                  selection='Median of three V6/current ratios below 1; descriptive selection, not a statistical proof.', cases=cases)
    write(folder/'repeat-summary.json', result)
    lines = ['# 19项复测', '', '比值＝V6中位数／当前版中位数；每轮独立统计，不合并样本。', '',
             '|N|类型|原比值|第1轮|第2轮|第3轮|三轮比值中位数|进入诊断|', '|---:|---|---:|---:|---:|---:|---:|---|']
    for c in cases:
        lines.append('|%d|%s|%.6f|%s|%.6f|%s|' % (c['N'], c['func'], c['original_ratio'],
                     '|'.join('%.6f' % r['ratio_v6_current'] for r in c['repetitions']), c['median_ratio'],
                     '是' if c['selected_for_diagnosis'] else '否'))
    (folder/'repeat-summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return [c for c in cases if c['selected_for_diagnosis']]


def drift(samples):
    first, last = stats(samples[:15]), stats(samples[15:])
    return first['p75'] < last['p25'] or last['p75'] < first['p25']


def profile(binary, n, func, env, folder):
    metadata, profiled = folder/'metadata', folder/'profile'
    for part in (metadata/'harness', profiled/'harness', profiled/'data'):
        part.mkdir(parents=True)
    selected = dict(env, FFT_TEST_OUT=str(metadata/'harness'), ROCFFT_LAYER='40',
                    ROCFFT_LOG_PLAN_PATH=str(metadata/'plan.txt'), ROCFFT_LOG_RTC_PATH=str(metadata/'rtc.txt'))
    run([binary, n, 1, func], selected, metadata, 'metadata')
    numerical = read_numerical_outputs(metadata/'harness', n, func)
    # Collect logs in a separate process so logging cannot enlarge trace gaps.
    selected = dict(env, FFT_TEST_OUT=str(profiled/'harness'))
    run([mgr.DTK+'/bin/hipprof', '--hip-trace', '--trace-args', '--output-type', '0',
         '-o', profiled/'trace', '-d', profiled/'data', binary, n, 1, func], selected, profiled, 'trace')
    child = re.search(r'exited with status:\s*(\d+)', (profiled/'trace.err').read_text())
    profile_check = read_numerical_outputs(profiled/'harness', n, func, int(child[1]) if child else None)
    plan = (metadata/'plan.txt').read_text()
    events = json.loads((profiled/'trace.json').read_text())['traceEvents']
    evidence = trace_evidence(plan, events, func)
    names = evidence['kernel_names']
    evidence['sources'] = actual_sources((metadata/'rtc.txt').read_text(), names)
    mgr.require(all(s['available'] for s in evidence['sources'].values()), 'actual RTC source missing')
    evidence['launch_geometry'] = re.findall(r'GridParams\n(.*?)End GridParams', plan, re.S)[-1].strip()
    evidence['occupancy'] = re.findall(r'Kernel occupancy:\s*(\d+)', plan)[-len(names):] or None
    timers = sorted((e for e in events if e.get('cat') == 'HIP' and e['name'] == 'hipEventRecord'),
                    key=lambda e: int(e['args']['index']))
    thread = (timers[0]['args']['pid'], timers[0]['args']['tid'])
    launches = [e for e in events if e.get('cat') == 'HIP' and 'LaunchKernel' in e['name']
                and (e['args']['pid'], e['args']['tid']) == thread]
    groups = [[e for e in launches if int(start['args']['index']) < int(e['args']['index']) < int(stop['args']['index'])]
              for start, stop in zip(timers[20::2], timers[21::2])]
    groups = [sorted(group, key=lambda e: int(e['args']['index'])) for group in groups]
    evidence['host_launch_api_sum_us'] = stats([sum(float(e['dur']) for e in group) for group in groups])
    evidence['host_submission_span_us'] = stats([float(group[-1]['ts'])+float(group[-1]['dur'])-float(group[0]['ts'])
                                                for group in groups])
    evidence['numerical'] = numerical
    evidence['profile_numerical'] = profile_check
    evidence['paths'] = dict(metadata=str(metadata), profile=str(profiled))
    write(folder/'trace-evidence.json', evidence)
    return evidence


def compare(pair):
    before, after = pair['previous'], pair['candidate']
    names_equal = before['kernel_names'] == after['kernel_names']
    sources_equal = names_equal and before['sources'] == after['sources']
    geometry_equal = before['launch_geometry'] == after['launch_geometry']
    result = dict(same_kernel_sequence=names_equal, same_actual_sources=sources_equal,
                  same_launch_geometry=geometry_equal,
                  same_occupancy=before['occupancy'] == after['occupancy'] if before['occupancy'] and after['occupancy'] else None)
    for key in ('window_kernel_sum_us', 'window_device_span_us', 'window_gap_us',
                'host_launch_api_sum_us', 'host_submission_span_us'):
        result[key] = {arm: pair[arm][key] for arm in pair}
        result[key]['candidate_minus_previous_median_us'] = after[key]['median']-before[key]['median']
    if names_equal:
        result['per_kernel'] = [dict(position=i, name=p['name'], previous=p['stats_us'], candidate=c['stats_us'],
            ratio_v6_current=p['stats_us']['median']/c['stats_us']['median'])
            for i, (p, c) in enumerate(zip(before['kernels'], after['kernels']))]
    if not (names_equal and sources_equal and geometry_equal):
        result['finding'] = 'Observed execution/source/geometry difference; inspect saved plans and RTC source before attributing a cause.'
    else:
        result['finding'] = 'Execution sequence, generated source and geometry match. Compare kernel sums and inter-kernel gaps; profile overhead prevents causal attribution from this trace alone.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('config', 'run', 'build', 'cache'):
        parser.add_argument('--'+field, type=Path, required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    settings = cfg['repeat19']
    folder = mgr.inside(a.run)/'repeat19-analysis'
    folder.mkdir()
    selected = summarize(settings, cfg, folder)
    record = dict(complete=False, formal=False, selected_cases=[dict(N=c['N'], func=c['func']) for c in selected],
                  note='Diagnostic timings are separate from the three formal reruns.', cases=[], failures=[])
    save = lambda: write(folder/'diagnostic-summary.json', record)
    save()
    if not selected:
        record.update(complete=True, decision='No median ratio below 1; detailed profiling skipped.')
        save()
        return
    for part in ('common', *cfg['arms']):
        (a.cache/part).mkdir()
    env = mgr.environment(a.cache/'common')
    env['FFT_TEST_ITERS'] = '30'
    install = mgr.inside(cfg['arms']['candidate']['install'])
    binary, identity = a.build/'measurement-v3', a.build/'device-identity'
    for output, source, flags in [
        (identity, ROOT/'tools/fft_measurement/device_identity.cpp', []),
        (binary, ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,
         ['-I'+str(install/'include'), '-L'+str(install/'lib'), '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-lstdc++fs'])]:
        run([mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936', '-mcumode',
             source, *flags, '-o', output], env, folder, 'compile-'+output.name)
    gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
    mgr.require(gpu['count'] == 1 and gpu['uuid'] == settings['gpu_uuid'], 'diagnostic GPU differs')
    record['gpu'] = gpu
    record['binary_sha256'] = mgr.common.sha(binary)
    record['libraries'] = {}
    arm_env = {}
    for arm, spec in cfg['arms'].items():
        arm_install = mgr.inside(spec['install'])
        lib = arm_install/'lib/librocfft.so.0.1'
        mgr.require(mgr.common.sha(lib) == spec['library_sha256'], 'diagnostic library changed')
        selected_env = mgr.environment(a.cache/arm)
        for key in tuple(selected_env):
            if key == 'ROCFFT_LAYER' or key.startswith('ROCFFT_LOG_'):
                del selected_env[key]
        selected_env.update(FFT_TEST_ITERS='30', LD_PRELOAD=str(lib),
                            LD_LIBRARY_PATH=str(arm_install/'lib')+':'+selected_env['LD_LIBRARY_PATH'])
        output = subprocess.check_output(['ldd', str(binary)], env=selected_env, text=True)
        (folder/('ldd-'+arm+'.txt')).write_text(output)
        resolved = [Path(line.split('=>')[-1].split()[0]).resolve() for line in output.splitlines() if 'librocfft.so' in line]
        mgr.require(resolved and all(path == lib.resolve() for path in resolved), 'loaded wrong diagnostic library')
        record['libraries'][arm] = dict(path=str(lib), sha256=spec['library_sha256'])
        arm_env[arm] = selected_env
    save()
    for i, case in enumerate(selected):
        pair = {}
        order = ('previous', 'candidate') if i % 2 == 0 else ('candidate', 'previous')
        for arm in order:
            try:
                pair[arm] = profile(binary, case['N'], case['func'], arm_env[arm],
                                    folder/(str(case['N'])+'-'+case['func'])/arm)
                print('PROFILE_PASS', case['N'], case['func'], arm, flush=True)
            except Exception as error:
                record['failures'].append(dict(N=case['N'], func=case['func'], arm=arm,
                    stage=getattr(error, 'stage', 'profile'), error=type(error).__name__, message=str(error),
                    returncode=getattr(error, 'returncode', None)))
                print('PROFILE_FAIL', case['N'], case['func'], arm, str(error), flush=True)
            save()
        if len(pair) == 2:
            record['cases'].append(dict(N=case['N'], func=case['func'], comparison=compare(pair)))
            save()
    record['complete'] = not record['failures']
    save()
    mgr.require(record['complete'], 'diagnostic failures; see diagnostic-summary.json')


if __name__ == '__main__':
    main()
