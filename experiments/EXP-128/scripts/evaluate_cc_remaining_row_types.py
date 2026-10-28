"""Complete offline coverage of row geometries absent from the actual-source subset."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa
from evaluate_cc_row_cost_reduction import input_hoist, output_tight, output_direct

RECORD = ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/row-cost-reduction-20261027'


def main():
    cases = json.loads((RECORD/'mapping-model.json').read_text())['cases']
    previous = json.loads((RECORD/'prototype-compilation.json').read_text())['compiled']
    seen = {x['geometry']['Q'] for x in previous}
    selected = {}
    for g in cases:
        if g['Q'] not in seen:
            selected.setdefault(g['Q'], g)
    tasks = []
    for q, g in sorted(selected.items()):
        original = Path(g['path']).read_text()
        variants = dict(current=original)
        if g['load'] == 'LDS':
            variants['input_hoist'] = input_hoist(original, g)
        if not g['packed']:
            variants['output_tight'] = output_tight(original, g)
            if g['load'] == 'LDS':
                variants['input_tight'] = output_tight(variants['input_hoist'], g)
        for variant, source in variants.items():
            tasks.append(dict(N=g['N'], geometry=g, variant=variant, text=source))

    def compile_one(item):
        item = dict(item)
        source = item.pop('text')
        path = ART/f"remaining-{item['N']}-{item['variant']}.cpp"
        path.write_text(source)
        unit, assembly = path.with_suffix('.hip.cpp'), path.with_suffix('.s')
        unit.write_text('#include <hip/hip_runtime.h>\n'+source)
        argv = [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++14', '--offload-arch=gfx936',
                '--cuda-device-only', '-mcumode', '-S', str(unit), '-o', str(assembly)]
        p = subprocess.run(argv, env=mgr.environment(ART), text=True, capture_output=True, timeout=180)
        path.with_suffix('.err').write_text(p.stderr)
        item.update(complete=p.returncode == 0, command=argv, source=str(path),
                    sha256=hashlib.sha256(source.encode()).hexdigest(), source_kind='generated default map')
        if p.returncode:
            item['error'] = p.stderr[-3000:]
        else:
            item.update(analyze_isa(assembly.read_text()))
        return item

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compile_one, tasks))
    failures = [x for x in results if not x['complete']]
    result = dict(complete=not failures, device_execution=False, compiled=results, failures=failures,
                  limitation='Generated default sources for geometry coverage, not captured dispatches or device acceptance.')
    (RECORD/'remaining-row-compilation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(complete=not failures, row_types=len(selected), compiled=len(results), failures=failures)))
    assert not failures


if __name__ == '__main__':
    main()
