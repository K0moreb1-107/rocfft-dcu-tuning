"""Use one unchanged v3 executable for cross-version and same-version controls."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts'),
                str(ROOT/'tools/fft_measurement'), str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from gate_validation_support import run, read_numerical_outputs, write
from cufft261012_contract import read_samples
from cc_regression_evidence import stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    a = parser.parse_args()
    cfg = mgr.load(a.config)
    settings = cfg['controls']
    folder = a.run/'controls'
    folder.mkdir()
    binary, identity = (mgr.inside(settings[key]['path']) for key in ('binary', 'identity'))
    for key, path in (('binary', binary), ('identity', identity)):
        mgr.require(mgr.common.sha(path) == settings[key]['sha256'], 'changed control helper: '+key)
    gpu = json.loads(subprocess.check_output([str(identity)], env=mgr.environment(a.cache), text=True))
    mgr.require(gpu['count'] == 1 and gpu['uuid'] == settings['gpu_uuid'], 'control GPU changed')
    environments = {}
    for arm, spec in cfg['arms'].items():
        install = mgr.inside(spec['install'])
        lib = install/'lib/librocfft.so.0.1'
        mgr.require(mgr.common.sha(lib) == spec['library_sha256'], 'control library changed: '+arm)
        temporary = a.cache/arm
        temporary.mkdir()
        env = mgr.environment(temporary)
        env.update(FFT_TEST_ITERS='30', LD_PRELOAD=str(lib),
                   LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
        linked = subprocess.check_output(['ldd', str(binary)], env=env, text=True)
        (folder/('ldd-'+arm+'.txt')).write_text(linked)
        resolved = [Path(line.split('=>')[-1].split()[0]).resolve() for line in linked.splitlines() if 'librocfft.so' in line]
        mgr.require(resolved and all(path == lib.resolve() for path in resolved), 'wrong control library')
        environments[arm] = env
    record = dict(complete=False, formal=False, gpu=gpu, binary_sha256=settings['binary']['sha256'],
                  design='Four blocks per case: V6/current/current/V6 and two fresh-process A/A pairs, one per library. Rotate mode order by block. Every process uses the unchanged v3 10/30 loop.',
                  interpretation='Diagnostic controls only. A/A reveals process/order variability; it does not establish a hardware or software cause.',
                  processes=[], pairs=[], failures=[])
    save = lambda: write(folder/'control-results.json', record)
    save()
    for case in cfg['cases']:
        n, func = case['N'], case['func']
        for block in range(4):
            modes = [('cross', ['previous', 'candidate', 'candidate', 'previous']),
                     ('same_v6', ['previous', 'previous']),
                     ('same_current', ['candidate', 'candidate'])]
            modes = modes[block % 3:]+modes[:block % 3]
            for mode, order in modes:
                entries = []
                for slot, arm in enumerate(order):
                    destination = folder/('%d-%s/b%d-%s-%d' % (n, func, block, mode, slot))
                    harness = destination/'harness'
                    harness.mkdir(parents=True)
                    env = dict(environments[arm], FFT_TEST_OUT=str(harness))
                    try:
                        run([binary, n, 1, func], env, destination, 'measurement')
                        numerical = read_numerical_outputs(harness, n, func)
                        samples = [1000*float(row['elapsed_ms']) for row in read_samples(harness/'fft_test_1d.samples.csv')]
                        mgr.require(len(samples) == 30, 'incomplete control sample sequence')
                        entry = dict(N=n, func=func, block=block, mode=mode, slot=slot, arm=arm,
                            path=str(destination), samples_us=samples, stats_us=stats(samples), numerical=numerical,
                            library_sha256=cfg['arms'][arm]['library_sha256'],
                            evidence_sha256={p.name:mgr.common.sha(p) for p in harness.iterdir() if p.is_file()})
                        record['processes'].append(entry)
                        entries.append(entry)
                    except Exception as error:
                        entries.append(None)
                        record['failures'].append(dict(N=n, func=func, block=block, mode=mode, slot=slot,
                            arm=arm, error=type(error).__name__, message=str(error)))
                    save()
                for first, second in zip(entries[::2], entries[1::2]):
                    if first is None or second is None:
                        continue
                    if mode == 'cross':
                        previous, current = (first, second) if first['arm'] == 'previous' else (second, first)
                        ratio = previous['stats_us']['median']/current['stats_us']['median']
                        label = 'V6/current'
                    else:
                        ratio = first['stats_us']['median']/second['stats_us']['median']
                        label = 'same-library first/second'
                    record['pairs'].append(dict(N=n, func=func, block=block, mode=mode,
                        first_arm=first['arm'], ratio=ratio, ratio_definition=label,
                        paths=[first['path'], second['path']]))
                save()
                print('CONTROL', n, func, block, mode, 'failures', len(record['failures']), flush=True)
    summaries = []
    for case in cfg['cases']:
        for mode in ('cross', 'same_v6', 'same_current'):
            pairs = [p for p in record['pairs'] if p['N'] == case['N'] and p['func'] == case['func'] and p['mode'] == mode]
            if not pairs:
                continue
            ratios = [p['ratio'] for p in pairs]
            summaries.append(dict(**case, mode=mode, pairs=len(pairs), ratios=ratios, stats=stats(ratios),
                below_095=sum(r < .95 for r in ratios), above_105=sum(r > 1.05 for r in ratios),
                ratios_by_first_arm={arm:[p['ratio'] for p in pairs if p['first_arm'] == arm] for arm in cfg['arms']}))
    record['summary'] = summaries
    record['complete'] = not record['failures'] and len(record['processes']) == 32*len(cfg['cases'])
    save()
    mgr.require(record['complete'], 'control failures; see control-results.json')


if __name__ == '__main__':
    main()
