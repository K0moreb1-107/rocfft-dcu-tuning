"""Host-only compile and exact generated-source comparison against the saved V6."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

ART = ROOT / 'experiments/EXP-129/artifacts/host-equivalence-20261029'
RECORD = ROOT / 'experiments/EXP-129/records/implementation-20261029'
BUILD = ROOT / 'experiments/EXP-128/artifacts/build/EXP-128-cc-local-boundary-v5-20261027'
BASE = ROOT / 'experiments/EXP-128/artifacts/preflight/row-output-v6-20261028'
MATRIX = ROOT / 'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'


def run(args, label, cwd):
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=mgr.environment(ART),
                            capture_output=True, timeout=240)
    (ART / (label + '.out')).write_bytes(result.stdout)
    (ART / (label + '.err')).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(label + ': ' + result.stderr.decode(errors='replace')[-3000:])
    return result.stdout.decode()


def main():
    started = time.monotonic()
    ART.mkdir(parents=True, exist_ok=False)
    RECORD.mkdir(parents=True, exist_ok=True)
    commands = json.loads((BUILD / 'compile_commands.json').read_text())
    driver = ART / 'generate.cpp'
    driver.write_text((BASE / 'generate.cpp').read_text().replace(
        'RealBlockIO::CanRegisterInput(q, specs.factors, rp, rp * rt)',
        'RealBlockIO::CanRegisterInput(rp, rp * rt)'))
    compilation = []
    for unit in ('rtc_stockham_gen.cpp', 'rtc_stockham_kernel.cpp',
                 'node_factory.cpp', 'tree_node_real.cpp'):
        entry = next(x for x in commands if x['file'].endswith('/' + unit))
        args = shlex.split(entry['command']) + ['--offload-arch=gfx936', '-mcumode']
        args[args.index('-o') + 1] = str(ART / (unit + '.o'))
        compilation.append((args, 'compile-' + unit, entry['directory']))
        if unit == 'rtc_stockham_gen.cpp':
            other = list(args)
            other[other.index('-o') + 1] = str(ART / 'driver.o')
            other[other.index('-c') + 1] = str(driver)
            compilation.append((other, 'compile-driver', entry['directory']))
        if unit == 'tree_node_real.cpp':
            for total, local in ((0, 0), (0, 1), (1, 0)):
                other = [x for x in args if not x.startswith('-DROCFFT_CC_REAL_FUSION=')
                         and not x.startswith('-DROCFFT_CC_LOCAL_REAL_FUSION=')]
                other += ['-DROCFFT_CC_REAL_FUSION=' + str(total),
                          '-DROCFFT_CC_LOCAL_REAL_FUSION=' + str(local)]
                other[other.index('-o') + 1] = str(ART / ('tree-' + str(total) + str(local) + '.o'))
                compilation.append((other, 'compile-tree-' + str(total) + str(local),
                                    entry['directory']))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda item: run(*item), compilation))
    print('HOST_COMPILES_PASS', len(compilation), flush=True)
    objects = [x for x in (BUILD / 'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o')
               if x.name != 'rtc_stockham_gen.cpp.o']
    objects += list((BUILD / 'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects += list((BUILD / 'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    run([mgr.DTK + '/bin/hipcc', '--offload-arch=gfx936', '-mcumode', ART / 'driver.o',
         ART / 'rtc_stockham_gen.cpp.o', *objects, '-pthread', '-ldl', '-lstdc++fs',
         '-o', ART / 'generate'], 'link-generator', ART)
    checks = []
    for mode, extra, count in (('default', [], 2264), ('retained-lds', ['lds'], 566)):
        olddir, newdir = ART / ('v6-' + mode), ART / ('candidate-' + mode)
        olddir.mkdir()
        newdir.mkdir()
        oldlines = run([BASE / 'generate', MATRIX, olddir, *extra], 'v6-' + mode, ART)
        newlines = run([ART / 'generate', MATRIX, newdir, *extra], 'candidate-' + mode, ART)
        if oldlines != newlines:
            raise RuntimeError(mode + ': RTC names, counts, or sizes differ')
        names = {x.name for x in olddir.glob('*.cpp')}
        if len(names) != count or names != {x.name for x in newdir.glob('*.cpp')}:
            raise RuntimeError(mode + ': incomplete source matrix')
        for name in sorted(names):
            old, new = (olddir / name).read_bytes(), (newdir / name).read_bytes()
            if old != new:
                raise RuntimeError(mode + ': generated GPU code differs: ' + name)
            checks.append({'mode': mode, 'file': name, 'sha256': hashlib.sha256(new).hexdigest()})
        print('EXACT_GENERATION_PASS', mode, count, flush=True)
    report = {'complete': True, 'device_execution': False, 'host_compiles': len(compilation),
              'compile_units': [x[1] for x in compilation], 'geometries': 283,
              'generated_sources_identical': len(checks), 'rtc_names_identical': True,
              'comparison': 'byte-for-byte against freshly rerun saved V6 generator; no normalization',
              'matrix_sha256': hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
              'elapsed_seconds': time.monotonic() - started, 'sources': checks}
    (RECORD / 'host-equivalence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'sources'}), flush=True)


if __name__ == '__main__':
    main()
