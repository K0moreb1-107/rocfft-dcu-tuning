"""Check short-lived pair indices against globally hoisted pair coordinates."""
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
from evaluate_cc_row_cost_reduction import output_tight

RECORD = ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/row-cost-reduction-20261027'


def input_round_local(text, g):
    start = text.index('// load global into registers\n')
    end = text.index('// calc the thread_in_device', start)
    old = text[start:end]
    reload = old[old.index('R[0] = {0,0};'):]
    c, q, t, r = (g[k] for k in ('C', 'Q', 'T', 'R'))
    half = q//2+1
    lines = ['// load global into registers']
    for i in range((half+t-1)//t):
        offset = i*t
        lines += ['{', f'const unsigned int ev_slot = threadIdx.x%{r};',
                  f'const unsigned int ev_j = threadIdx.x/{r}+{offset};',
                  f'const unsigned int ev_row = tile_index_in_plane*{r}+ev_slot;']
        tests = []
        if offset+t > half:
            tests.append(f'ev_j < {half}')
        if c % r:
            tests.append(f'ev_row < {c}')
        if tests:
            lines.append('if('+' && '.join(tests)+') {')
        lines += [f'scalar_type ev_p = load_cb(buf_in,ev_row*{q}+ev_j,load_cb_data,nullptr);',
                  'scalar_type ev_own, ev_other;']
        if i == 0:
            lines += [f'if(ev_j == 0) {{ lds_complex[ev_slot*{q}] = cc_inverse_endpoints(ev_p); }} else {{']
        middle = q % 2 == 0 and offset <= q//2 < offset+t
        if middle:
            lines += [f'if(ev_j == {q//2}) {{ lds_complex[ev_slot*{q}+ev_j] = cc_inverse_middle(ev_p); }} else {{']
        lines += [f'scalar_type ev_q = load_cb(buf_in,ev_row*{q}+{q}-ev_j,load_cb_data,nullptr);',
                  'cc_pre_pair<scalar_type>(ev_p,ev_q,cc_real_twiddles[ev_j],ev_own,ev_other);',
                  f'lds_complex[ev_slot*{q}+ev_j] = ev_own;',
                  f'lds_complex[ev_slot*{q}+{q}-ev_j] = ev_other;']
        if middle:
            lines.append('}')
        if i == 0:
            lines.append('}')
        if tests:
            lines.append('}')
        lines.append('}')
    return text[:start]+'\n'.join(lines)+'\n'+reload+text[end:]


def main():
    original = json.loads((RECORD/'prototype-compilation.json').read_text())['compiled']
    original += json.loads((RECORD/'remaining-row-compilation.json').read_text())['compiled']
    selected = {}
    for e in original:
        if e['variant'] == 'current' and e['geometry']['load'] == 'LDS':
            selected.setdefault(e['geometry']['Q'], e)
    tasks = []
    for q, e in sorted(selected.items()):
        text = input_round_local(Path(e['source']).read_text(), e['geometry'])
        tasks.append(dict(N=e['N'], geometry=e['geometry'], variant='input_local', text=text))
        if not e['geometry']['packed']:
            tasks.append(dict(N=e['N'], geometry=e['geometry'], variant='input_local_tight',
                              text=output_tight(text, e['geometry'])))

    def compile_one(item):
        item = dict(item)
        source = item.pop('text')
        path = ART/f"{item['N']}-{item['variant']}.cpp"
        unit, assembly = path.with_suffix('.hip.cpp'), path.with_suffix('.s')
        path.write_text(source)
        unit.write_text('#include <hip/hip_runtime.h>\n'+source)
        argv = [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++14', '--offload-arch=gfx936',
                '--cuda-device-only', '-mcumode', '-S', str(unit), '-o', str(assembly)]
        p = subprocess.run(argv, env=mgr.environment(ART), text=True, capture_output=True, timeout=180)
        path.with_suffix('.err').write_text(p.stderr)
        item.update(complete=p.returncode == 0, source=str(path), command=argv,
                    sha256=hashlib.sha256(source.encode()).hexdigest())
        if p.returncode:
            item['error'] = p.stderr[-3000:]
        else:
            item.update(analyze_isa(assembly.read_text()))
        return item

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compile_one, tasks))
    failures = [x for x in results if not x['complete']]
    result = dict(complete=not failures, device_execution=False, compiled=results, failures=failures,
                  limitation='Offline scheduling variants only; use model from mapping-model.json, no device timing.')
    (RECORD/'input-schedule-compilation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(complete=not failures, row_types=len(selected), compiled=len(results), failures=failures)))
    assert not failures


if __name__ == '__main__':
    main()
