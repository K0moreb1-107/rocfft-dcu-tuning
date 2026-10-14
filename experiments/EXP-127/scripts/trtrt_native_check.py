"""Build and run CPU checks using real helper text and actual core I/O AST.

This script compiles host executables only and calls no GPU API. A separately
configured, isolated candidate build must already contain generator/common
objects; it never creates a CMake checkout, submits work, or measures devices.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def base_command(entry):
    tokens = shlex.split(entry['command']) if 'command' in entry else list(entry['arguments'])
    result, skip = [], False
    for token in tokens:
        if skip:
            skip = False
            continue
        if token in ('-o', '-MF', '-MT', '-MQ'):
            skip = True
        elif token in ('-c', '-MD', '-MMD', '-MP') or token == entry['file']:
            continue
        else:
            result.append(token)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Candidate rocFFT source root')
    parser.add_argument('--build', type=Path, required=True, help='Candidate rocFFT CMake build root')
    parser.add_argument('--coverage', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='Unused independent native evidence directory')
    parser.add_argument('--compiler', type=Path, required=True)
    args = parser.parse_args()
    source, build, out = args.source.resolve(), args.build.resolve(), args.out.resolve()
    if out.exists():
        raise ValueError('native evidence directory already exists')
    out.mkdir(parents=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    generator = source/'library/src/device/generator'
    configs_dir = source/'library/src/device/kernels/configs'
    sys.path.insert(0, str(source/'library/src/device'))
    spec = importlib.util.spec_from_file_location('native_sbrr_configs', configs_dir/'config_sbrr.py')
    configs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(configs)
    pool = {}
    for kernel in configs.sbrr_kernels:
        if getattr(kernel, 'double_precision', True) is False or getattr(kernel, 'lds_size_bytes', 65536) > 65536:
            continue
        if kernel.length in pool:
            continue
        tpt = kernel.threads_per_transform
        # Match kernel-generator.py: a single radix uses no shared FFT
        # exchange, so its half_lds flag is disabled before launcher derivation.
        # The precision-specific override is applied to the pool flag after
        # the generator has returned the launch geometry.
        generated_half = getattr(kernel, 'half_lds', True) and len(kernel.factors) > 1
        half = 'dp' in kernel.half_lds_precision if hasattr(kernel, 'half_lds_precision') else generated_half
        slots = min(32768 // (kernel.length*16//(2 if generated_half else 1)), kernel.workgroup_size//tpt)
        pool[kernel.length] = dict(N=kernel.length, TPT=tpt, TPB=slots,
                                  half_lds=half, factors=list(kernel.factors))
    # Add the prior known unsafe thread-count shape: testing address<length
    # instead of add_work's thread predicate must fail this map.
    exact = {(row['N'], row['TPT'], row['TPB'], row['half_lds'], tuple(row['factors']))
             for row in pool.values()}
    exact.add((512, 128, 4, True, (8, 8, 8)))
    exact.add((1024, 128, 4, True, (8, 8, 4, 4)))
    cases = sorted(exact)
    (out/'core-configs.txt').write_text(''.join('%d %d %d %d %d %s\n' %
        (n, tpt, tpb, half, len(factors), ' '.join(map(str, factors)))
        for n, tpt, tpb, half, factors in cases))
    coverage = json.loads(args.coverage.read_text())
    matrix_rows = []
    for row in coverage['sizes'].values():
        pre = row.get('B_T', 0) if row['TR_scheme_predicate'] else 0
        post = row.get('A_T', 0) if row['RT_scheme_predicate'] else 0
        matrix_rows.append((row['A'], row['B'], pre-pre%2, post-post%2))
    (out/'matrices.txt').write_text(''.join('%d %d %d %d\n' % row for row in matrix_rows))
    commands = json.loads((build/'compile_commands.json').read_text())
    entry = next(row for row in commands if row['file'].endswith('/rtc_stockham_gen.cpp'))
    cpp = Path(__file__).with_name('trtrt_boundary_index_export.cpp').resolve()
    object_path, executable = out/'index-exporter.o', out/'index-exporter'
    common = build/'library/src/CMakeFiles/rocfft-rtc-common.dir'
    generated = build/'library/src/CMakeFiles/rocfft-rtc-gen.dir'
    objects = [generated/'rtc_stockham_gen.cpp.o', generated/'load_store_ops_gen.cpp.o',
               build/'library/src/device/generator/CMakeFiles/generator.dir/generator.cpp.o',
               build/'library/src/device/generator/CMakeFiles/generator.dir/fftgenerator.cpp.o']
    objects += list(common.rglob('kernel-generator-embed.cpp.o'))
    if len(objects) != 5 or not all(p.is_file() for p in objects):
        raise ValueError('isolated generator/rocfft-rtc-common objects missing; build those targets first')
    steps = []

    def run(command, name, cwd=None):
        command = list(map(str, command))
        with (out/(name+'.log')).open('xb') as log:
            result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        steps.append(dict(name=name, command=command, returncode=result.returncode,
                          log_sha256=sha(out/(name+'.log'))))
        (out/'progress.json').write_text(json.dumps(steps, indent=2))
        if result.returncode:
            raise RuntimeError('native step failed: '+name)

    run(base_command(entry)+['--offload-arch=gfx936', '-I'+str(source/'library/src'), '-c', cpp, '-o', object_path],
        'exporter-compile', entry['directory'])
    run([args.compiler, '-x', 'none', object_path, *objects, '-pthread', '-o', executable], 'exporter-link')
    generated = out/'host-index-model.cpp'
    run([executable, out/'core-configs.txt', out/'matrices.txt', generated], 'exporter-execute')
    host = out/'host-index-model'
    host_compiler = args.compiler.parent.parent/'llvm/bin/clang++'
    if not host_compiler.is_file():
        raise ValueError('registered DTK host compiler missing')
    run([host_compiler, '-O2', '-std=c++17', '-UNDEBUG', '-x', 'c++', generated, '-o', host], 'host-model-compile')
    run([host], 'host-model-execute')
    text = (out/'host-model-execute.log').read_text()
    if 'TRTRT_NATIVE_INDEX_PASS' not in text or 'actual_add_work_predicates=1' not in text:
        raise ValueError('native ownership proof missing')
    source_inputs = [cpp, Path(__file__).resolve(), args.coverage,
                     generator/'stockham_gen_base.h', generator/'stockham_gen_rr.h',
                     generator/'real_pair_layout.h', configs_dir/'config_sbrr.py', configs_dir/'config_lds.py',
                     source/'library/src/device/kernel-generator.py']
    proof = dict(complete=True, formal=False, gpu_execution=False, started_utc=started,
        ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), steps=steps,
        source_inputs={str(p): sha(p) for p in source_inputs},
        actual_core_configs=len(cases), registered_matrices=len(matrix_rows),
        tests='Actual add_work first/last I/O predicates and maps; all 64KiB DP SBRR default configs; '
              'two known excess-thread shapes; paired helper row/peer and pre/post formulas; '
              'two 32x33 shared tiles, all 25 matrices in both orientations and padding 0/1/7; '
              '169 toy rectangles with even slots and invalid slots; DC/Nyquist/self mirror arithmetic',
        evidence_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()})
    with (out/'native-check.json').open('x') as stream:
        json.dump(proof, stream, indent=2)
    print(out/'native-check.json')


if __name__ == '__main__':
    main()
