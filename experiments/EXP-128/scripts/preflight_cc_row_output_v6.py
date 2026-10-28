"""Generate final v6 output adapters; prove unchanged inputs and compile changed layouts."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa
from evaluate_cc_row_cost_reduction import geometry, check_model

BUILD = ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-boundary-v5-20261027'
PREVIOUS = ROOT/'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027'
MATRIX = ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/row-output-v6-20261028'
RECORD = ROOT/'experiments/EXP-128/records/row-output-v6-20261028'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def run(args, label, cwd=None):
    p = subprocess.run(list(map(str, args)), cwd=cwd or ART, env=mgr.environment(ART),
                       capture_output=True, timeout=240)
    (ART/(label+'.out')).write_bytes(p.stdout)
    (ART/(label+'.err')).write_bytes(p.stderr)
    mgr.require(p.returncode == 0, label+': '+p.stderr.decode(errors='replace')[-3000:])
    return p.stdout.decode()


def input_region(text):
    start = text.index('// load global into registers\n')
    end = text.index('// calc the thread_in_device', start)
    return text[start:end]


def main():
    started = time.monotonic()
    ART.mkdir(exist_ok=True)
    RECORD.mkdir(exist_ok=True)
    matrix = [line.split() for line in MATRIX.read_text().splitlines()]
    assert len(matrix) == 283
    commands = json.loads((BUILD/'compile_commands.json').read_text())
    entry = next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    args = shlex.split(entry['command'])+['--offload-arch=gfx936', '-mcumode']
    args[args.index('-o')+1] = str(ART/'generator.o')
    run(args, 'compile-generator', Path(entry['directory']))
    driver = ART/'generate.cpp'
    driver.write_text((PREVIOUS/'generate.cpp').read_text())
    args[args.index('-o')+1] = str(ART/'driver.o')
    args[args.index('-c')+1] = str(driver)
    run(args, 'compile-driver', Path(entry['directory']))
    objects = [p for p in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o')
               if p.name != 'rtc_stockham_gen.cpp.o']
    objects += list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects += list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    run([mgr.DTK+'/bin/hipcc', '--offload-arch=gfx936', '-mcumode', ART/'driver.o',
         ART/'generator.o', *objects, '-pthread', '-ldl', '-lstdc++fs', '-o', ART/'generate'], 'link')
    changed, unchanged, models, syntax = [], [], [], {}
    generated = 0
    for mode, extra, expected in [('default', [], 2264), ('retained-lds', ['lds'], 566)]:
        folder = ART/mode
        folder.mkdir(exist_ok=True)
        lines = run([ART/'generate', MATRIX, folder, *extra], 'generate-'+mode).splitlines()
        assert len(lines) == expected
        generated += len(lines)
        for line in lines:
            n, c, q, role, cb, size, name = line.split()
            n, c, q, role, cb = map(int, (n, c, q, role, cb))
            path = folder/f'{c}-{q}-{role}-{cb}.cpp'
            text = path.read_text()
            previous = (PREVIOUS/mode/path.name).read_text()
            normalized = text.replace('_cc_local_v6_', '_cc_local_v5_')
            assert '_cc_local_v6_role'+str(role) in name
            assert normalized.split('extern "C" __global__')[0] == previous.split('extern "C" __global__')[0]
            assert input_region(normalized) == input_region(previous), ('input changed', path)
            if role in (4, 6):
                assert normalized == previous, ('column changed', path)
                unchanged.append(str(path))
                continue
            g, _ = geometry(path, n, c, q)
            direct = g['R'] == 1 and g['T'] == q//g['factors'][-1]
            flag = 'const bool direct_store_from_reg = '+('true;' if direct else 'false;')
            assert flag in text
            modifies = direct or (role == 5 and not g['packed'])
            if not modifies:
                assert normalized == previous, ('unselected output changed', path)
                unchanged.append(str(path))
                continue
            if direct:
                assert 'const unsigned int cc_direct_row = tile_index_in_plane;' in text
                assert 'cc_output_first' not in text and 'cc_spectrum_p0' not in text
                if role == 7:
                    assert 'if(cc_direct_row != 0)' in text and 'cc_terminal_j' in text
            else:
                assert role == 5 and 'cc_output_p0' in text
                if c % g['R'] == 0:
                    assert 'const unsigned int cc_output_valid = '+str(g['R'])+';' in text
                for offset in re.findall(r'if\(cc_output_p0 \+ (\d+) < '+str(q)+r'\)', text):
                    assert int(offset)+g['T'] > q, ('unnecessary full frequency guard', path)
            if mode == 'default' and cb == 0:
                models.append(dict(N=n, C=c, Q=q, role=role, model=check_model(g)))
            changed.append(dict(N=n, C=c, Q=q, role=role, callback=cb, mode=mode,
                                direct=direct, source=str(path)))
            syntax.setdefault((role, q, g['T'], g['R'], cb, c % 2, c % g['R'] == 0), path)

    def compile_one(item):
        key, path = item
        unit, asm = path.with_suffix('.hip.cpp'), path.with_suffix('.s')
        unit.write_text('#include <hip/hip_runtime.h>\n'+path.read_text())
        command = [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++14', '--offload-arch=gfx936',
                   '--cuda-device-only', '-mcumode', '-S', str(unit), '-o', str(asm)]
        p = subprocess.run(command, env=mgr.environment(ART), capture_output=True, text=True, timeout=180)
        path.with_suffix('.err').write_text(p.stderr)
        result = dict(shape=key, source=str(path), complete=p.returncode == 0, command=command)
        if p.returncode:
            result['error'] = p.stderr[-3000:]
        else:
            result['isa'] = analyze_isa(asm.read_text())
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        compiled = list(pool.map(compile_one, syntax.items()))
    failures = [x for x in compiled if not x['complete']]
    result = dict(complete=not failures, device_execution=False, geometries=283,
                  generated_sources=generated, unchanged_sources=len(unchanged), changed_sources=changed,
                  models=models, compiles=compiled, failures=failures, input_changed=False,
                  column_changed=False, elapsed_seconds=time.monotonic()-started)
    save(RECORD/'host-preflight.json', result)
    print(json.dumps(dict(complete=not failures, generated=generated, changed=len(changed),
                          unchanged=len(unchanged), compiles=len(compiled), failures=failures,
                          elapsed_seconds=result['elapsed_seconds'])), flush=True)
    mgr.require(not failures, 'v6 final generator compiler errors')


if __name__ == '__main__':
    main()
