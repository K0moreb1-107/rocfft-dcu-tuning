"""Offline d2z boundary prototypes. No production edit or device execution."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa
from evaluate_cc_row_cost_reduction import pass_map

RECORD = ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/row-cost-reduction-20261027'
SOURCE = ROOT/'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027/default'


def shape(text):
    body = text[text.index('extern "C" __global__'):]
    t = int(re.search(r'uses (\d+) threads per transform', body)[1])
    r = int(re.search(r'does (\d+) transforms per thread block', body)[1])
    f = list(map(int, re.search(r'_factors_([0-9_]+)_wgs_', body)[1].split('_')))
    c, q, n = map(int, re.search(r'_C(\d+)_Q(\d+).*?_N(\d+)', body).groups())
    return dict(C=c, Q=q, N=n, T=t, R=r, factors=f,
                half='const bool lds_is_real = true;' in body)


def post_input(text, g):
    start = text.index('// load global into registers\n')
    end = text.index('// calc the thread_in_device', start)
    t, r, c, q = (g[k] for k in ('T', 'R', 'C', 'Q'))
    f = g['factors'][0]
    k = c//f
    lines = ['// load global into registers', '{',
             f'const unsigned int ev_lane = threadIdx.x/{r};',
             f'const unsigned int ev_col = tile_index*{r}+threadIdx.x%{r};']
    regs = int(re.search(r'scalar_type R\[(\d+)\]', text[text.index('extern "C" __global__'):])[1])
    lines += [f'R[{i}] = {{0,0}};' for i in range(regs)]
    guard_col = q % r != 0
    if guard_col:
        lines.append(f'if(ev_col < {q}) {{')
    for h in range((k+t-1)//t):
        guard = (h+1)*t > k
        if guard:
            lines.append(f'if(ev_lane+{h*t} < {k}) {{')
        for w in range(f):
            j = f'(ev_lane+{h*t+w*k})'
            address = f'({j}*{2*q}+ev_col)'
            lines.append(f'R[{h*f+w}] = {{load_cb(cc_real_pointer(buf_in),{address},load_cb_data,nullptr),load_cb(cc_real_pointer(buf_in),{address}+{q},load_cb_data,nullptr)}};')
        if guard:
            lines.append('}')
    if guard_col:
        lines.append('}')
    lines.append('}')
    return text[:start]+'\n'.join(lines)+'\n'+text[end:]


def post_consume(text, g):
    start = text.index('// call a post-store from registers to lds (if necessary)')
    c, q, t, r = (g[k] for k in ('C', 'Q', 'T', 'R'))
    f = g['factors'][-1]
    k = c//f
    half, rounds = c//2+1, (c//2+1+t-1)//t
    lines = [f'const unsigned int ev_lane = threadIdx.x/{r};',
             f'const unsigned int ev_slot = threadIdx.x%{r};',
             f'const unsigned int ev_col = tile_index*{r}+ev_slot;']
    if g['half']:
        lines.append(f'real_type_t<scalar_type> ev_saved[{2*rounds}];')

    def scatter(imaginary):
        v = ['__syncthreads();']
        for h in range((k+t-1)//t):
            guard = (h+1)*t > k
            if guard:
                v.append(f'if(ev_lane+{h*t} < {k}) {{')
            for w in range(f):
                index = f'((ev_lane+{h*t+w*k})*{r}+ev_slot)'
                reg = h*f+w
                if g['half']:
                    v.append(f'lds_real[{index}] = R[{reg}].'+('y;' if imaginary else 'x;'))
                else:
                    v.append(f'lds_complex[{index}] = R[{reg}];')
            if guard:
                v.append('}')
        v.append('__syncthreads();')
        return v

    def consume(save):
        v = []
        if q % r:
            v.append(f'if(ev_col < {q}) {{')
        for i in range(rounds):
            offset = i*t
            partial = offset+t > half
            v += ['{', f'const unsigned int ev_j = ev_lane+{offset};',
                  f'const unsigned int ev_peer = '+(f'(ev_j == 0 ? 0 : {c}-ev_j);' if i == 0 else f'{c}-ev_j;')]
            if partial:
                v.append(f'if(ev_j < {half}) {{')
            left, right = f'(ev_j*{r}+ev_slot)', f'(ev_peer*{r}+ev_slot)'
            if save:
                v += [f'ev_saved[{2*i}] = lds_real[{left}];',
                      f'ev_saved[{2*i+1}] = lds_real[{right}];']
            else:
                p = f'scalar_type{{ev_saved[{2*i}],lds_real[{left}]}}' if g['half'] else f'lds_complex[{left}]'
                peer = f'scalar_type{{ev_saved[{2*i+1}],lds_real[{right}]}}' if g['half'] else f'lds_complex[{right}]'
                v += [f'scalar_type ev_p = {p};', 'scalar_type ev_own, ev_other;']
                if i == 0:
                    v += ['if(ev_lane == 0) {', 'store_cb(buf_out,ev_col,ev_p,store_cb_data,nullptr);', '} else {']
                middle = c % 2 == 0 and offset <= c//2 < offset+t
                if middle:
                    v += [f'if(ev_j == {c//2}) {{',
                          f'store_cb(buf_out,ev_j*{q}+ev_col,cc_conjugate(ev_p),store_cb_data,nullptr);', '} else {']
                v += [f'scalar_type ev_q = {peer};',
                      'cc_post_pair<scalar_type>(ev_p,ev_q,cc_real_twiddles[ev_j],ev_own,ev_other);',
                      f'store_cb(buf_out,ev_j*{q}+ev_col,ev_own,store_cb_data,nullptr);',
                      f'store_cb(buf_out,ev_peer*{q}+ev_col,ev_other,store_cb_data,nullptr);']
                if middle:
                    v.append('}')
                if i == 0:
                    v.append('}')
            if partial:
                v.append('}')
            v.append('}')
        if q % r:
            v.append('}')
        return v

    lines += scatter(False)
    if g['half']:
        lines += consume(True)+scatter(True)
    lines += consume(False)
    return text[:start]+'\n'.join(lines)+'\n}\n'


def row_direct_ordinary(text, g):
    assert g['R'] == 1
    start = text.index('// call a post-store from registers to lds (if necessary)')
    q, c, t, n = (g[k] for k in ('Q', 'C', 'T', 'N'))
    f, k = g['factors'][-1], q//g['factors'][-1]
    lines = ['const unsigned int ev_row = tile_index_in_plane;',
             f'const unsigned int ev_lane = threadIdx.x%{t};', 'if(ev_row != 0) {']
    for h in range((k+t-1)//t):
        guard = (h+1)*t > k
        if guard:
            lines.append(f'if(ev_lane+{h*t} < {k}) {{')
        for w in range(f):
            offset = h*t+w*k
            lines += ['{', f'const unsigned int ev_j = ev_lane+{offset};',
                      f'unsigned int ev_index = {2*c}*ev_j+ev_row;', f'scalar_type ev_value = R[{h*f+w}];',
                      f'if(ev_j >= {(q+1)//2}) {{ ev_value = cc_conjugate(ev_value); ev_index = {n}-ev_index; }}',
                      'store_cb(buf_out,ev_index,ev_value,store_cb_data,nullptr);', '}']
        if guard:
            lines.append('}')
    lines += ['} else {', '__syncthreads();']
    for h in range((k+t-1)//t):
        guard = (h+1)*t > k
        if guard:
            lines.append(f'if(ev_lane+{h*t} < {k}) {{')
        for w in range(f):
            lines.append(f'lds_complex[ev_lane+{h*t+w*k}] = R[{h*f+w}];')
        if guard:
            lines.append('}')
    lines.append('__syncthreads();')
    for i in range((q//2+1+t-1)//t):
        offset = i*t
        guard = offset+t > q//2+1
        lines += ['{', f'const unsigned int ev_j = threadIdx.x+{offset};']
        if guard:
            lines.append(f'if(ev_j < {q//2+1}) {{')
        lines += ['scalar_type ev_p = lds_complex[ev_j], ev_own, ev_other;']
        if i == 0:
            lines += ['if(ev_j == 0) {',
                      'ev_own = {ev_p.x+ev_p.y,0}; ev_other = {ev_p.x-ev_p.y,0};',
                      'store_cb(buf_out,0,ev_own,store_cb_data,nullptr);',
                      f'store_cb(buf_out,{n//2},ev_other,store_cb_data,nullptr);', '} else {']
        middle = q % 2 == 0 and offset <= q//2 < offset+t
        if middle:
            lines += [f'if(ev_j == {q//2}) {{', f'store_cb(buf_out,{c}*ev_j,cc_conjugate(ev_p),store_cb_data,nullptr);', '} else {']
        lines += [f'scalar_type ev_q = lds_complex[{q}-ev_j];',
                  'cc_post_pair<scalar_type>(ev_p,ev_q,cc_real_twiddles[ev_j],ev_own,ev_other);',
                  f'store_cb(buf_out,{c}*ev_j,ev_own,store_cb_data,nullptr);',
                  f'store_cb(buf_out,{c}*({q}-ev_j),ev_other,store_cb_data,nullptr);']
        if middle:
            lines.append('}')
        if i == 0:
            lines.append('}')
        if guard:
            lines.append('}')
        lines.append('}')
    lines.append('}')
    return text[:start]+'\n'.join(lines)+'\n}\n'


def check_models():
    rows = json.loads((RECORD/'mapping-model.json').read_text())['cases']
    out = []
    for item in rows:
        n, c, q = (item[k] for k in ('N', 'C', 'Q'))
        text = (SOURCE/f'{c}-{q}-6-0.cpp').read_text()
        g = shape(text)
        t, r = g['T'], g['R']
        half, wgs = c//2+1, t*r
        for tile in sorted({0, max(0, q//r-1), q//r}):
            if tile*r >= q:
                continue
            a, b = [], []
            for tid in range(wgs):
                for i in range((half*r+wgs-1)//wgs):
                    task = tid+i*wgs
                    if task < half*r and tile*r+task%r < q:
                        a.append((task%r, task//r))
                for i in range((half+t-1)//t):
                    j = tid//r+i*t
                    if j < half and tile*r+tid%r < q:
                        b.append((tid%r, j))
            assert Counter(a) == Counter(b) and all(v == 1 for v in Counter(a).values())
        # Output pair ownership is determined by the *last* pass, interleaved CC map.
        m = pass_map(dict(Q=c, T=t, factors=g['factors'],
                          registers=int(re.search(r'scalar_type R\[(\d+)\]', text[text.index('extern "C" __global__'):])[1])), False)
        locality = Counter()
        for slot in range(r):
            for j in range(1, (c+1)//2):
                aa, bb = (m[z][0]*r+slot for z in (j, c-j))
                locality['same_thread' if aa == bb else 'same_wave' if aa//64 == bb//64 else 'cross_wave'] += 1
        # Row folding identity. Each sampled row's direct native map produces the old addresses.
        for rr in sorted({1, c//2, c-1}):
            if not 0 < rr < c:
                continue
            old = {2*c*j+rr if j < (q+1)//2 else n-(2*c*j+rr) for j in range(q)}
            assert len(old) == q and all(0 < k < n//2 for k in old)
            direct = set()
            for j in pass_map(item, False):
                direct.add(2*c*j+rr if j < (q+1)//2 else n-(2*c*j+rr))
            assert old == direct
        terminal = [0, n//2]
        for j in range(1, q//2+1):
            terminal.append(c*j)
            if 2*j != q:
                terminal.append(c*(q-j))
        assert len(terminal) == q+1 and len(set(terminal)) == q+1
        out.append(dict(N=n, C=c, Q=q, column_T=t, column_R=r, half=g['half'],
                        column_pair_locality=dict(locality), model_complete=True))
    return out


def main():
    cases = check_models()
    result_path = RECORD/'d2z-prototype-compilation.json'
    prior = json.loads(result_path.read_text()) if result_path.exists() else {}
    cache = {(x['N'], x['stage'], x['variant'], x['sha256']): x
             for x in prior.get('compiled', []) if x['complete']}
    if prior and not prior['complete']:
        archive = RECORD/'d2z-prototype-failed-scope-r2.json'
        if not archive.exists():
            archive.write_text(json.dumps(prior, ensure_ascii=False, indent=2)+'\n')
    tasks = []
    for n in (67200, 115600, 223608, 425920, 447216, 574992, 2725888):
        path = ART/f'{n}-d2z-actual-column.cpp'
        text = path.read_text()
        g = shape(text)
        variants = dict(current=text, input_hoist=post_input(text, g), pair_map=post_consume(text, g),
                        input_pair_map=post_consume(post_input(text, g), g))
        for variant, source in variants.items():
            tasks.append(dict(N=n, stage='column', variant=variant, geometry=g, text=source))
        row = (ART/f'{n}-d2z-actual-row.cpp').read_text()
        gr = shape(row)
        if gr['R'] == 1:
            for variant, source in dict(current=row, direct_ordinary=row_direct_ordinary(row, gr)).items():
                tasks.append(dict(N=n, stage='row', variant=variant, geometry=gr, text=source))
    # The captured subset has Q=1331 single-row kernels. Cover Q=625 too,
    # using generated defaults with both column parities, without a device run.
    for parity in (0, 1):
        item = next(x for x in cases if x['Q'] == 625 and x['C'] % 2 == parity)
        row = (SOURCE/f"{item['C']}-625-7-0.cpp").read_text()
        gr = shape(row)
        assert gr['R'] == 1
        for variant, source in dict(current=row, direct_ordinary=row_direct_ordinary(row, gr)).items():
            tasks.append(dict(N=item['N'], stage='row', variant=variant, geometry=gr, text=source,
                              source_kind='generated default map'))

    def compile_one(item):
        item = dict(item)
        text = item.pop('text')
        digest = hashlib.sha256(text.encode()).hexdigest()
        cached = cache.get((item['N'], item['stage'], item['variant'], digest))
        if cached is not None:
            return cached
        path = ART/f"{item['N']}-d2z-{item['stage']}-{item['variant']}.cpp"
        unit, assembly = path.with_suffix('.hip.cpp'), path.with_suffix('.s')
        path.write_text(text)
        unit.write_text('#include <hip/hip_runtime.h>\n'+text)
        command = [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++14', '--offload-arch=gfx936',
                   '--cuda-device-only', '-mcumode', '-S', str(unit), '-o', str(assembly)]
        p = subprocess.run(command, env=mgr.environment(ART), capture_output=True, text=True, timeout=180)
        path.with_suffix('.err').write_text(p.stderr)
        item.update(complete=p.returncode == 0, command=command, source=str(path),
                    sha256=digest)
        if p.returncode:
            item['error'] = p.stderr[-3000:]
        else:
            item.update(analyze_isa(assembly.read_text()))
        return item

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(compile_one, tasks))
    failures = [x for x in result if not x['complete']]
    data = dict(complete=not failures, device_execution=False, models=cases, compiled=result, failures=failures,
                limitations='Offline compiler and index models only. For row R=1, output barriers remain on the uniform terminal block; nonterminal blocks skip them. Static barrier totals do not count executed barriers per block.')
    (RECORD/'d2z-prototype-compilation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(complete=not failures, models=len(cases), compiled=len(result), failures=failures)))
    assert not failures


if __name__ == '__main__':
    main()
