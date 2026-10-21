"""Check every covered forward row against the allocated phase-table segment count."""
import json
import re
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
SOURCE = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
OLD = ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021'
BUILD = ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-unified-20261021'
OUT = ROOT/'experiments/EXP-128/artifacts/preflight/phasefix-20261022'
RECORD = ROOT/'experiments/EXP-128/records/phasefix-20261022'
DTK = Path('/public/software/compiler/dtk-26.04')


def run(argv, label, cwd=OUT):
    proc = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True, timeout=180)
    (OUT/(label+'.out')).write_bytes(proc.stdout)
    (OUT/(label+'.err')).write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError(label+': '+proc.stderr.decode(errors='replace')[-3000:])
    return proc.stdout.decode()


def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    RECORD.mkdir(parents=True, exist_ok=True)
    driver = (OLD/'generate-unified.cpp').read_text()
    driver = driver.replace('#include <sstream>', '#include <sstream>\n#include "../../shared/arithmetic.h"')
    driver = driver.replace('for (int role = 4; role <= 7; ++role)', 'for (int role = 7; role <= 7; ++role)')
    driver = driver.replace('if (keep)', '''const auto segments = DivRoundingUp<size_t>(CeilPo2(n), 8);
                if (code.find("cc_boundary_phase_steps=" + std::to_string(segments) + ";") == std::string::npos)
                    throw std::runtime_error("phase table allocation and generated lookup disagree");
                if (n == 65536 || n == 69938)''')
    (OUT/'generate.cpp').write_text(driver)
    commands = json.loads((BUILD/'compile_commands.json').read_text())
    entry = next(x for x in commands if x['file'].endswith('/rtc_stockham_gen.cpp'))
    argv = shlex.split(entry['command']) + ['--offload-arch=gfx936', '-mcumode']
    argv[argv.index('-o')+1] = str(OUT/'generator.o')
    run(argv, 'compile-generator', Path(entry['directory']))
    argv[argv.index('-o')+1] = str(OUT/'driver.o')
    argv[argv.index('-c')+1] = str(OUT/'generate.cpp')
    run(argv, 'compile-driver', Path(entry['directory']))
    objects = [x for x in (BUILD/'library/src/CMakeFiles/rocfft-rtc-gen.dir').glob('*.o')
               if x.name != 'rtc_stockham_gen.cpp.o']
    objects += list((BUILD/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    objects += list((BUILD/'library/src/device/generator/CMakeFiles/generator.dir').glob('*.o'))
    run([DTK/'bin/hipcc', '--offload-arch=gfx936', '-mcumode', OUT/'driver.o', OUT/'generator.o',
         *objects, '-pthread', '-ldl', '-lstdc++fs', '-o', OUT/'generate'], 'link')
    generated = run([OUT/'generate', OLD/'native-matrix.txt', OUT], 'generate')
    rows = [line.split() for line in generated.splitlines()]
    assert len(rows) == 283 and all(row[3:5] == ['7', '0'] for row in rows)
    coverage = json.loads((ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json').read_text())
    allocated = {x['N']: ((x['N']-1).bit_length()+7)//8 for x in coverage['geometries']}
    invalid_old = [n for n, segments in allocated.items() if segments != 3]
    assert invalid_old == [65536], invalid_old
    proof = dict(complete=True, host_only=True, device_execution=False,
        generated_rows=len(rows), public_N=len(coverage['public']),
        allocation_rule='256 * ceil(ceil(log2(N)) / 8) complex entries; TwiddleTableLarge',
        old_fixed_three_segments_invalid_N=invalid_old,
        N65536=dict(allocated_entries=512, old_third_segment_first_index=512, corrected_segments=2),
        steps_by_N=allocated, elapsed_seconds=time.monotonic()-started)
    (RECORD/'phase-table-preflight.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps({key:value for key,value in proof.items() if key != 'steps_by_N'}))


if __name__ == '__main__':
    main()
