"""Check scaled generators and compile representative device sources without executing a GPU."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

ART = ROOT/'experiments/EXP-129/artifacts/stable-scale-fix-preflight-20261030'
RECORD = ROOT/'experiments/EXP-129/records/stable-scale-fix-20261030'
BUILD = ROOT/'experiments/EXP-129/artifacts/build/EXP-129-legacy-retirement-20261029'
SOURCE = ROOT/'experiments/EXP-129/scripts/generate_scale_regression.cpp'
MATRIX = ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'
REFERENCE = ROOT/'experiments/EXP-129/artifacts/host-equivalence-20261029/candidate-default'


def run(command, label, cwd):
    command = list(map(str, command))
    process = subprocess.run(command, cwd=cwd, env=mgr.environment(ART), capture_output=True, timeout=300)
    (ART/(label+'.out')).write_bytes(process.stdout)
    (ART/(label+'.err')).write_bytes(process.stderr)
    (ART/(label+'-command.json')).write_text(json.dumps(dict(command=command,
        cwd=str(cwd), returncode=process.returncode), indent=2)+'\n')
    if process.returncode:
        raise RuntimeError(label+': '+process.stderr.decode(errors='replace')[-3500:])
    return process.stdout.decode()


def output_path(entry):
    args = shlex.split(entry['command'])
    path = Path(args[args.index('-o')+1])
    return (Path(entry['directory'])/path).resolve()


def main():
    started = time.monotonic()
    ART.mkdir(parents=True, exist_ok=False)
    RECORD.mkdir(parents=True, exist_ok=True)
    report = dict(complete=False, device_execution=False, failures=[])
    try:
        commands = json.loads((BUILD/'compile_commands.json').read_text())
        by_object = {output_path(item): item for item in commands}
        objects = list((BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o'))
        objects += list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
        objects += list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
        assert objects
        replacement = {}
        compilation = []
        for name in ['load_store_ops_gen.cpp', 'rtc_bluestein_gen.cpp', 'rtc_stockham_gen.cpp']:
            old = next(path for path in objects if path.name == name+'.o')
            entry = by_object[old.resolve()]
            command = shlex.split(entry['command'])
            if name == 'rtc_stockham_gen.cpp':
                output = ART/'driver.o'
                command[command.index('-c')+1] = str(SOURCE)
            else:
                output = ART/(name+'.o')
                replacement[old.resolve()] = output
            command[command.index('-o')+1] = str(output)
            compilation.append((command, 'compile-'+name, entry['directory']))
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = {pool.submit(run, *item): item[1] for item in compilation}
            for future in as_completed(pending):
                try:
                    future.result()
                except Exception as error:
                    report['failures'].append(dict(stage=pending[future], error=str(error)))
        assert not report['failures'], report['failures']
        run([mgr.DTK+'/bin/hipcc', '--offload-arch=gfx936', '-mcumode', ART/'driver.o',
            *(replacement.get(path.resolve(), path) for path in objects),
            '-pthread', '-ldl', '-lstdc++fs', '-o', ART/'generate'], 'link', ART)
        kernels = ART/'representative-kernels'
        kernels.mkdir()
        unit = run([ART/'generate', MATRIX, kernels, REFERENCE, 'unit'], 'generate-unit', ART)
        scaled = run([ART/'generate', MATRIX, kernels, REFERENCE, 'scaled'], 'generate-scaled', ART)
        report['unit_sources_identical'] = len(unit.splitlines())
        report['scaled_cc_sources'] = sum(not line.startswith('BLUE_') for line in scaled.splitlines())
        report['bluestein_argument_cases'] = sum(line.startswith('BLUE_') for line in scaled.splitlines())
        assert report['unit_sources_identical'] == report['scaled_cc_sources'] == 2264
        assert report['bluestein_argument_cases'] == 192
        syntax = []
        for index, source in enumerate(sorted(kernels.glob('*.cpp'))):
            syntax.append(([mgr.DTK+'/bin/hipcc', '-std=c++17', '--offload-arch=gfx936',
                '-mcumode', '-x', 'hip', '-fsyntax-only', '-include', 'hip/hip_runtime.h', source],
                'syntax-%02d'%index, ART))
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending = {pool.submit(run, *item): item[1] for item in syntax}
            for future in as_completed(pending):
                try:
                    future.result()
                except Exception as error:
                    report['failures'].append(dict(stage=pending[future], error=str(error)))
        report['device_syntax_cases'] = len(syntax)
        report['representative_sources'] = [dict(path=str(p.relative_to(ROOT)),
            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(kernels.glob('*.cpp'))]
        assert syntax and not report['failures'], report['failures']
        report['complete'] = True
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic()-started
        (RECORD/'host-preflight.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
