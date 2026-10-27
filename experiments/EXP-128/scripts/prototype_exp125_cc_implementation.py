"""Analysis-only prototypes on logged RTC copies; no production changes or GPU execution."""
from concurrent.futures import ThreadPoolExecutor
import cmath
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa
from audit_exp125_cc_implementation import capture

RECORD = ROOT / 'experiments/EXP-128/records/exp125-fusion-audit-20261027'
ART = ROOT / 'experiments/EXP-128/artifacts/preflight/exp125-fusion-audit-20261027/prototypes'
ORIGINAL_ART = ART.parent
V4 = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-grouped-validate-20261026/measurement-validation'
MATRIX = ROOT / 'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'


def shape(name):
    c, q = map(int, re.search(r'_C(\d+)_Q(\d+)_', name).groups())
    tpt = int(re.search(r'_tpt_(\d+)_', name).group(1))
    wgs = int(re.search(r'_wgs_(\d+)_', name).group(1))
    factors = list(map(int, re.search(r'_factors_([0-9_]+)_wgs_', name).group(1).split('_')))
    return c, q, tpt, wgs // tpt, factors[0]


def product(a, b):
    return '{' + f'{a}.x * {b}.x - {a}.y * {b}.y,{a}.y * {b}.x + {a}.x * {b}.y' + '}'


def lookup(index):
    return 'TW_NSteps<scalar_type,cc_boundary_phase_base,cc_boundary_phase_steps>(cc_boundary_large_twiddles,' + index + ')'


def packed_output(source, c, q, tpt, rows):
    assert c % 2 == rows % 2 == c % rows == 0
    body = [f'const unsigned int audit_slot=threadIdx.x%{rows};',
            f'const unsigned int audit_component=audit_slot/{rows//2};',
            f'const unsigned int audit_pair=audit_slot%{rows//2};',
            'scalar_type audit_output;']
    for i in range((q + tpt - 1) // tpt):
        j = f'(threadIdx.x/{rows}+{i*tpt})'
        entry = [f'audit_output={{lds_real[2*(2*audit_pair*{q}+{j})+audit_component],lds_real[2*((2*audit_pair+1)*{q}+{j})+audit_component]}};',
                 f'store_cb(buf_out,tile_index_in_plane*{rows//2}+audit_pair+{c}*{j}+audit_component*{c//2},audit_output,store_cb_data,nullptr);']
        if (i + 1) * tpt > q:
            body.append(f'if({j}<{q})' + '{' + '\n'.join(entry) + '}')
        else:
            body += entry
    body = '\n'.join(body) + '\n'
    marker = 'const unsigned int cc_output_first ='
    replacements = 0
    while marker in source:
        a = source.index(marker)
        outer = source.index('if(cc_output_slot < cc_output_valid)', a)
        start = source.index('{', outer)
        depth = 1
        end = start + 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        source = source[:a] + body + source[end:]
        replacements += 1
    assert replacements == 2, replacements
    return source


def phase_recurrence(source, c, q, tpt, width, pair_step):
    count = q // width
    a = source.index('// load global into registers\n')
    b = source.index('// calc the thread_in_device', a)
    region = source[a:b]
    pattern = r'const scalar_type cc_row_phase_(\d+) = (TW_NSteps<scalar_type,cc_boundary_phase_base,cc_boundary_phase_steps>\(cc_boundary_large_twiddles,([^;]+)\));'
    originals = list(re.finditer(pattern, region))
    expected = math.ceil(count / tpt) * width
    assert len(originals) == expected, (q, tpt, width, len(originals), expected)
    declarations = ['scalar_type audit_delta;']
    if pair_step:
        declarations.append('scalar_type audit_delta2;')
    declarations += [f'scalar_type audit_phase_{h};' for h in range(math.ceil(count/tpt))]
    init = f'audit_delta={lookup(f"cc_input_row*{count}")};'
    if pair_step:
        init += 'audit_delta2=' + product('audit_delta', 'audit_delta') + ';'
    declarations.append(f'if(cc_input_row!=0 && cc_input_row<{c} && threadIdx.x%{tpt}<{count})' + '{' + init + '}')
    row_decl = re.search(r'const unsigned int cc_input_row = [^;]+;', region)
    assert row_decl
    region = region[:row_decl.end()] + '\n' + '\n'.join(declarations) + region[row_decl.end():]

    def replace(match):
        reg = int(match[1])
        h, w = divmod(reg, width)
        running = f'audit_phase_{h}'
        lines = []
        if w == 0:
            lines.append(f'{running}={match[2]};')
        phase = product(running, 'audit_delta') if pair_step and w % 2 else running
        lines.append(f'const scalar_type cc_row_phase_{reg}={phase};')
        if pair_step:
            if w % 2 and w + 1 < width:
                lines.append(f'{running}=' + product(running, 'audit_delta2') + ';')
        elif w + 1 < width:
            lines.append(f'{running}=' + product(running, 'audit_delta') + ';')
        return '\n'.join(lines)

    region = re.sub(pattern, replace, region)
    return source[:a] + region + source[b:]


def model():
    maximum_error = 0.0
    chain_error = 0.0
    pair_error = 0.0
    phase_values = 0
    eligible_output = []
    cases = []
    for line in MATRIX.read_text().splitlines():
        f = line.split()
        n, c, q = map(int, f[:3])
        tpt, rows = map(int, f[7:9])
        width = int(f[10].split(',')[0])
        count = q // width
        if c % 2 == rows % 2 == c % rows == 0:
            checked = 0
            for block in {0, c//rows - 1}:
                got = {}
                for tid in range(tpt*rows):
                    slot = tid % rows
                    comp, pair = divmod(slot, rows//2)
                    for i in range((q+tpt-1)//tpt):
                        j = tid//rows+i*tpt
                        if j >= q:
                            continue
                        dst = 2*(block*(rows//2)+pair+c*j+comp*(c//2))
                        srcs = [(2*pair, j, comp), (2*pair+1, j, comp)]
                        for k, src in enumerate(srcs):
                            assert dst+k not in got
                            got[dst+k] = src
                expected = {block*rows+s+c*(2*j+component):(s,j,component)
                            for s in range(rows) for j in range(q) for component in range(2)}
                assert got == expected, (n, c, q, rows, block)
                checked += len(got)
            eligible_output.append(dict(N=n,C=c,Q=q,rows=rows,checked_scalars=checked))
        # Mathematical phase identity with a CPU model of segmented lookup and short recurrence.
        steps = math.ceil((n-1).bit_length()/8)
        def lut(k):
            z = 1+0j
            for segment in range(steps):
                digit = (k >> (8*segment)) & 255
                z *= cmath.exp(-2j*math.pi*digit*(256**segment)/n)
            return z
        for r in {1, max(1,c//2), c-1}:
            delta = lut(r*count)
            delta2 = delta*delta
            for h in {0, (count+tpt-1)//tpt-1}:
                active = min(tpt,count-h*tpt)
                for lane in {0, max(0,active//2), max(0,active-1)}:
                    if not active:
                        continue
                    base = lane+h*tpt
                    running = lut(r*base)
                    chained = running
                    for w in range(width):
                        got = running*delta if w % 2 else running
                        expected = lut(r*(base+w*count))
                        pair_error = max(pair_error,abs(got-expected))
                        chain_error = max(chain_error,abs(chained-expected))
                        maximum_error = max(pair_error,chain_error)
                        phase_values += 1
                        chained *= delta
                        if w % 2 and w+1<width:
                            running *= delta2
        cases.append(dict(N=n,C=c,Q=q,first_factor=width,tpt=tpt))
    return dict(complete=True,geometries=len(cases),output_fast_eligible=eligible_output,
                phase_values=phase_values,maximum_phase_absolute_difference=maximum_error,
                maximum_chain_phase_difference=chain_error,maximum_pair_phase_difference=pair_error,
                limitation='Address bijection and CPU segmented-phase model; not FFT device accuracy or performance.')


def compile_one(task):
    path = Path(task['source'])
    assembly = path.with_suffix('.s')
    cmd = [mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936',
           '--cuda-device-only','-S','-mcumode',str(path),'-o',str(assembly)]
    p = subprocess.run(cmd,env=mgr.environment(ART),capture_output=True,text=True,timeout=150)
    path.with_suffix('.err').write_text(p.stderr)
    if p.returncode:
        return dict(task,complete=False,error=p.stderr[-2500:])
    text = assembly.read_text()
    first = text.find('\ts_barrier')
    return dict(task,complete=True,command=cmd,assembly=str(assembly),
                static_wait_all_before_first_barrier=text[:first].count('s_waitcnt vmcnt(0)'),
                **analyze_isa(text))


def main():
    ART.mkdir(parents=True,exist_ok=True)
    original = json.loads((RECORD/'exact-rtc-static-comparison.json').read_text())['kernels']
    selected = [x for x in original if x['version']=='v4' and x['position']==1]
    for n, func in [(120224,'z2d_1d'),(70000,'z2d_1d'),(73008,'d2z_1d'),
                    (167042,'d2z_1d'),(142688,'d2z_1d'),(204800,'d2z_1d'),(361250,'d2z_1d')]:
        selected += [x for x in capture('v4',n,func,V4/f'{n}-{func}'/'metadata/rtc.txt') if x['position']==1]
    tasks=[]
    for x in selected:
        c,q,tpt,rows,width = shape(x['name'])
        source=Path(x['source']).read_text()
        variants=[]
        if x['func']=='z2d_1d':
            if c%2==rows%2==c%rows==0:
                variants.append(('packed-output',packed_output(source,c,q,tpt,rows)))
        else:
            variants += [('phase-chain',phase_recurrence(source,c,q,tpt,width,False)),
                         ('phase-pairs',phase_recurrence(source,c,q,tpt,width,True))]
        for variant,text in variants:
            p=ART/f'{x["N"]}-{x["func"]}-{variant}.hip.cpp';p.write_text(text)
            tasks.append(dict(N=x['N'],func=x['func'],variant=variant,C=c,Q=q,tpt=tpt,rows=rows,
                              source=str(p),original_source=x['source'],original_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                              source_sha256=hashlib.sha256(text.encode()).hexdigest()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        compiles=list(pool.map(compile_one,tasks))
    failures=[x for x in compiles if not x['complete']]
    models=model()
    result=dict(complete=not failures,device_execution=False,production_modified=False,
                model=models,compiles=compiles,failures=failures)
    (RECORD/'offline-prototypes.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=not failures,compiles=len(compiles),failures=failures,
                         eligible_geometry_count=len(models['output_fast_eligible']),phase_model_error=models['maximum_phase_absolute_difference'])))
    assert not failures


if __name__=='__main__':main()
