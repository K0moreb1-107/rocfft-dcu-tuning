"""Host generation, native-map proofs and offline resource comparisons; no GPU execution."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import json
import math
import re
import shlex
import subprocess
import time

ROOT = Path('/public/home/zhangkewei/zr')
SOURCE = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
HERE = ROOT/'experiments/EXP-128/scripts'
OUT = ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021'
OLD = ROOT/'experiments/EXP-128/artifacts/preflight/regression-953997'
BUILD = ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-callbackfix-20261021'
DTK = Path('/public/software/compiler/dtk-26.04')


def run(argv, label, cwd=OUT, timeout=180):
    argv = list(map(str, argv))
    proc = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)
    (OUT/(label+'.out')).write_bytes(proc.stdout)
    (OUT/(label+'.err')).write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError(label+': '+proc.stderr.decode(errors='replace')[-3000:])
    return proc.stdout.decode(errors='replace')


def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    coverage = json.loads((ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json').read_text())
    import sys
    sys.path.insert(0, str(HERE))
    from audit_cc_unified_coverage import validate_coverage, parse_mapping
    audit = validate_coverage(coverage, parse_mapping((SOURCE/'library/src/node_factory.cpp').read_text()))
    cols = {x['length']: x for x in coverage['columns']}
    rows = {x['aligned']['length']: x['aligned'] for x in coverage['rows']}
    maps = []
    for q, spec in rows.items():
        width, threads = spec['factors'][0], spec['P']
        count = q//width
        indices = [lane+h*threads+w*count for h in range(math.ceil(count/threads))
                   for lane in range(threads) if lane+h*threads < count for w in range(width)]
        assert sorted(indices) == list(range(q)), (q, spec)
        maps.append(dict(Q=q, P=threads, coverage=q, unique=True))
    choices = { (128,256) }
    public = [x for x in coverage['public'] if x['N'] > 65536]
    for c in cols:
        choices.add(next((x['C'],x['Q']) for x in public if x['C'] == c))
    for q in {x['Q'] for x in coverage['geometries']}:
        choices.add(next((x['C'],x['Q']) for x in coverage['geometries'] if x['Q'] == q))
    choices |= {(x['C'],x['Q']) for x in coverage['public'] if x['C'] == 289}
    lines = []
    for case in coverage['geometries']:
        n,c,q = (case[x] for x in ('N','C','Q'))
        col,row = cols[c],rows[q]
        lines.append(' '.join(map(str,[n,c,q,col['P'],col['ordinary_T'],int(col['half_lds']),
            ','.join(map(str,col['factors'])),row['P'],row['ordinary_T'],0,
            ','.join(map(str,row['factors'])),int((c,q) in choices)])))
    matrix = OUT/'native-matrix.txt'
    matrix.write_text('\n'.join(lines)+'\n')
    driver = (OLD/'generate-default.cpp').read_text()
    driver = driver.replace('(role == 7 && !(q & (q - 1)) && transpose == TILE_ALIGNED)',
        '(role == 7 && RealBlockIO::CanRegisterInput(q, specs.factors, rp, rp * rt))')
    driver = driver.replace('steps = role == 4 ? 3 : 0;',
        'steps = role == 4 ? (base == 8 && n <= 65536 ? 2 : 3) : 0;')
    (OUT/'generate-unified.cpp').write_text(driver)
    commands = json.loads((BUILD/'compile_commands.json').read_text())
    entry = next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    argv = shlex.split(entry['command'])
    argv += ['--offload-arch=gfx936', '-mcumode']
    argv[argv.index('-o')+1] = str(OUT/'rtc-stockham.o')
    run(argv, 'compile-generator', Path(entry['directory']))
    driver_argv = argv.copy()
    driver_argv[driver_argv.index('-o')+1] = str(OUT/'generate-unified.o')
    driver_argv[driver_argv.index('-c')+1] = str(OUT/'generate-unified.cpp')
    run(driver_argv, 'compile-driver', Path(entry['directory']))
    objects = [x for x in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o')
               if x.name != 'rtc_stockham_gen.cpp.o']
    objects += list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects += list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    run([DTK/'bin/hipcc', '--offload-arch=gfx936', '-mcumode',
         OUT/'generate-unified.o', OUT/'rtc-stockham.o', *objects,
         '-pthread', '-ldl', '-lstdc++fs', '-o', OUT/'generate-unified'], 'link-driver')
    for variant,binary in [('previous-generated',OLD/'generate-default'),('unified',OUT/'generate-unified')]:
        folder = OUT/variant
        folder.mkdir(exist_ok=True)
        run([binary,matrix,folder], 'generate-'+variant)
    syntax = []
    for name in ('tree_node_real.cpp','rtc_stockham_kernel.cpp'):
        entry = next(x for x in commands if x['file'].endswith('/'+name))
        args = shlex.split(entry['command'])
        at = args.index('-o')
        del args[at:at+2]
        args.remove('-c')
        args += ['-fsyntax-only']
        run(args, 'syntax-'+name, Path(entry['directory']))
        syntax.append(name)
    # Compare the same native geometry at source level. This is not an execution
    # of either version's public default plan (notably the former 64K legacy path).
    selected = set()
    for c in cols:
        case = next(x for x in public if x['C'] == c)
        selected.add((case['C'],case['Q'],4))
    for q in {x['Q'] for x in coverage['geometries']}:
        case = next(x for x in coverage['geometries'] if x['Q'] == q)
        selected.add((case['C'],case['Q'],7))
    selected |= {(x['C'],x['Q'],4) for x in coverage['public'] if x['C'] == 289}
    selected.add((128,256,4))
    tasks = [(variant,c,q,role) for c,q,role in sorted(selected)
             for variant in ('previous-generated','unified')]

    def compile_one(task):
        variant,c,q,role = task
        stem = OUT/variant/(str(c)+'-'+str(q)+'-'+str(role)+'-0')
        source = stem.with_suffix('.cpp')
        hip = stem.with_suffix('.hip.cpp')
        hip.write_text('#include <hip/hip_runtime.h>\n'+source.read_text())
        bundle = stem.with_suffix('.bundle')
        device = stem.with_suffix('.device.hsaco')
        label = variant+'-'+stem.name
        command = [DTK/'bin/hipcc','-O3','-std=c++14','--genco',
                   '--offload-arch=gfx936','-mcumode',hip,'-o',bundle]
        item = dict(variant=variant,C=c,Q=q,N=2*c*q,role=role,command=list(map(str,command)))
        try:
            run(command,label+'-compile')
            run([DTK/'llvm/bin/clang-offload-bundler','--unbundle','--type=o',
                 '--targets=hipv4-amdgcn-amd-amdhsa--gfx936','--input='+str(bundle),
                 '--output='+str(device)],label+'-unbundle')
            notes = run([DTK/'llvm/bin/llvm-readelf','--notes',device],label+'-notes')
            fields = ('vgpr_count','vgpr_spill_count','private_segment_fixed_size','sgpr_count')
            item['resources'] = {key:int(re.search(r'\.'+key+r':\s*(\d+)',notes).group(1)) for key in fields}
            item['returncode'] = 0
            # Retain source, device object and metadata; discard duplicate compiler inputs/bundles.
            hip.unlink()
            bundle.unlink()
        except Exception as error:
            item.update(returncode=1,error=str(error))
        return item

    with ThreadPoolExecutor(max_workers=2) as pool:
        resources = list(pool.map(compile_one,tasks))
    failures = [x for x in resources if x['returncode']]
    for item in resources:
        if item['variant'] == 'unified' and item['C'] == 289 and item['role'] == 4 and not item['returncode']:
            if item['resources']['vgpr_spill_count'] or item['resources']['private_segment_fixed_size']:
                failures.append(dict(N=item['N'],role=4,error='wide-column spill remains',resources=item['resources']))
    record = dict(complete=not failures,host_only=True,device_execution=False,coverage=audit,
        native_input_maps=maps,generated_sources_per_variant=4*len(coverage['geometries']),
        selected_geometries=len(choices),resources=resources,failures=failures,
        translation_units=syntax,elapsed_seconds=time.monotonic()-started,
        limitation='Offline compiler comparison of matched native source fixtures, not public-plan timing or loaded-runtime resource records.')
    (OUT/'preflight-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(complete=record['complete'],generated_sources_per_variant=record['generated_sources_per_variant'],
        native_input_maps=len(maps),compiled=len(resources),failures=failures,
        elapsed_seconds=record['elapsed_seconds'])))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
