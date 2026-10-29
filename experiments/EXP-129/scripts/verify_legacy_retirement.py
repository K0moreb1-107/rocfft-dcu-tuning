"""Compile every changed C++ unit and compare the retained CC generated sources."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr

ART = ROOT/'experiments/EXP-129/artifacts/legacy-retirement-preflight-20261029'
RECORD = ROOT/'experiments/EXP-129/records/legacy-retirement-20261029'
BUILD = ROOT/'experiments/EXP-129/artifacts/build/EXP-129-gate-simplification-20261029'
BASE = ROOT/'experiments/EXP-129/artifacts/host-equivalence-20261029'
MATRIX = ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'
SCRIPTS = ROOT/'experiments/EXP-129/scripts'
UNITS = ('repo.cpp', 'rtc_stockham_gen.cpp', 'rtc_stockham_kernel.cpp', 'rtc_twiddle_gen.cpp',
         'tree_node.cpp', 'tree_node_1D.cpp', 'tree_node_real.cpp', 'twiddles.cpp')


def run(args, label, cwd):
    command = list(map(str, args))
    result = subprocess.run(command, cwd=cwd, env=mgr.environment(ART), capture_output=True, timeout=240)
    (ART/(label+'.out')).write_bytes(result.stdout)
    (ART/(label+'.err')).write_bytes(result.stderr)
    (ART/(label+'-command.json')).write_text(json.dumps(dict(command=command, cwd=str(cwd),
        returncode=result.returncode), indent=2)+'\n')
    if result.returncode:
        raise RuntimeError(label+': '+result.stderr.decode(errors='replace')[-2000:])
    return result.stdout.decode()


def command_output(entry):
    args = shlex.split(entry['command'])
    output = Path(args[args.index('-o')+1])
    return output if output.is_absolute() else Path(entry['directory'])/output


def main():
    started = time.monotonic()
    ART.mkdir(parents=True, exist_ok=False)
    RECORD.mkdir(parents=True, exist_ok=True)
    report = dict(complete=False, device_execution=False, failures=[])
    try:
        commands = json.loads((BUILD/'compile_commands.json').read_text())
        by_object = {command_output(entry).resolve(): entry for entry in commands}
        objects = list((BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o'))
        objects += list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
        objects += list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
        mgr.require(objects, 'generator link objects missing')
        entries = {path.resolve(): by_object[path.resolve()] for path in objects}
        for unit in UNITS:
            entry = next(item for item in commands if item['file'].endswith('/'+unit))
            entries[command_output(entry).resolve()] = entry
        compilation, replaced = [], {}
        for index, (old, entry) in enumerate(entries.items()):
            output = ART/('unit-%02d.o' % index)
            args = [arg for arg in shlex.split(entry['command'])
                    if not arg.startswith(('-DROCFFT_CC_REAL_FUSION=', '-DROCFFT_CC_LOCAL_REAL_FUSION='))]
            args += ['-DROCFFT_CC_REAL_FUSION=1', '--offload-arch=gfx936', '-mcumode']
            args[args.index('-o')+1] = str(output)
            replaced[old] = output
            label = 'compile-%02d-%s' % (index, Path(entry['file']).name)
            compilation.append((args, label, entry['directory']))
            if entry['file'].endswith('/tree_node_real.cpp'):
                off = [arg for arg in args if arg != '-DROCFFT_CC_REAL_FUSION=1']
                off += ['-DROCFFT_CC_REAL_FUSION=0']
                off[off.index('-o')+1] = str(ART/'tree-off.o')
                compilation.append((off, 'compile-tree-off', entry['directory']))
            if old == next(path.resolve() for path in objects if path.name == 'rtc_stockham_gen.cpp.o'):
                driver = list(args)
                driver[driver.index('-c')+1] = str(SCRIPTS/'generate_cc_retirement.cpp')
                driver[driver.index('-o')+1] = str(ART/'driver.o')
                compilation.append((driver, 'compile-driver', entry['directory']))
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending = {pool.submit(run, *item): item[1] for item in compilation}
            for future in as_completed(pending):
                try:
                    future.result()
                except Exception as error:
                    report['failures'].append(dict(stage=pending[future], error=str(error)))
        mgr.require(not report['failures'], 'compile failures: '+str(report['failures']))
        report['host_compiles'] = len(compilation)
        report['changed_cpp_units'] = list(UNITS)
        print('HOST_COMPILES_PASS', len(compilation), flush=True)
        run([mgr.DTK+'/bin/hipcc', '--offload-arch=gfx936', '-mcumode', ART/'driver.o',
             *(replaced[path.resolve()] for path in objects), '-pthread', '-ldl', '-lstdc++fs',
             '-o', ART/'generate'], 'link-generator', ART)
        checks = []
        for mode, extra, expected in (('default', [], 2264), ('retained-lds', ['lds'], 566)):
            reference = BASE/('candidate-'+mode)
            names = {path.name for path in reference.glob('*.cpp')}
            mgr.require(len(names) == expected, 'reference generation coverage differs')
            candidate = ART/('candidate-'+mode)
            candidate.mkdir()
            required = sum((reference/name).stat().st_size for name in names) + (512 << 20)
            mgr.require(shutil.disk_usage(ART).free > required, 'insufficient generation workspace')
            output = run([ART/'generate', MATRIX, candidate, *extra], 'generate-'+mode, ART)
            mgr.require(len(output.splitlines()) == expected, 'generation output count differs')
            mgr.require(names == {path.name for path in candidate.glob('*.cpp')}, 'generation files differ')
            for name in sorted(names):
                old, new = (reference/name).read_bytes(), (candidate/name).read_bytes()
                mgr.require(old == new, mode+': GPU source differs: '+name)
                checks.append(dict(mode=mode, file=name, sha256=hashlib.sha256(new).hexdigest(),
                                   source=str(reference/name)))
            # Identical sources share the retained, immutable reference; keep one
            # source copy and the complete hash index instead of duplicate trees.
            for name in names:
                (candidate/name).unlink()
            candidate.rmdir()
            print('EXACT_GENERATION_PASS', mode, expected, flush=True)
        report.update(complete=True, geometries=283, generated_sources_identical=len(checks),
                      comparison='byte-for-byte against retained EXP129 generator sources',
                      fresh_generator_link_objects=len(objects),
                      matrix_sha256=hashlib.sha256(MATRIX.read_bytes()).hexdigest(), sources=checks)
    except Exception as error:
        report['failure'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic()-started
        (RECORD/'host-preflight.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({key:value for key,value in report.items() if key != 'sources'}), flush=True)


if __name__ == '__main__':
    main()
