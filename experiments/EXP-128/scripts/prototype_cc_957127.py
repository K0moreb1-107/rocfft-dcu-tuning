"""Offline IO prototypes on copied RTC text; never modify the production generator."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from isa_cc_957127 import compile_one

RECORD = ROOT/'experiments/EXP-128/records/regression-955252-20261022/analysis-957127'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/regression-957127'


def scope_end(source,start):
    # These accepted generated bodies contain no braces in strings/comments.
    begin = source.rfind('extern "C" __global__',0,start)
    assert begin >= 0
    opening = source.index('{',begin)
    level = source[opening:start].count('{')-source[opening:start].count('}')
    assert level > 0
    depth = level
    for pos in range(start,len(source)):
        depth += (source[pos] == '{')-(source[pos] == '}')
        if depth < level:
            return pos
    raise ValueError('missing scope end')


def output_hoist(source,c,q,p,t):
    assert t*p > 0
    pieces = []
    for component in (0,1):
        value = 'x' if component == 0 else 'y'
        prefix = f'''{{
const unsigned int first = tile_index_in_plane * {t};
const unsigned int valid = min({t},{c} - first);
const unsigned int slot = threadIdx.x % {t};
const unsigned int p0 = threadIdx.x / {t};
const unsigned int head = (first + {c*component}) % 2;
const unsigned int base = first + slot + {c*component};
if(slot < valid) {{
if(slot >= head && (slot-head)%2 == 0 && slot+1 < valid) {{
'''
        vector,scalar = [],[]
        for i in range((q+p-1)//p):
            j = f'(p0 + {i*p})'
            guard = f'if({j} < {q})'
            vector.append(f'''{guard} {{
scalar_type value{{lds_complex[slot*{q}+{j}].{value},lds_complex[(slot+1)*{q}+{j}].{value}}};
store_cb(buf_out,(base+{2*c}*{j})/2,value,store_cb_data,nullptr);
}}
''')
            scalar.append(f'''{guard} {{
store_cb(cc_real_pointer(buf_out),base+{2*c}*{j},lds_complex[slot*{q}+{j}].{value},store_cb_data,nullptr);
}}
''')
        pieces.append(prefix+''.join(vector)+'''}
else if((slot==0 && head==1) || (slot+1==valid && base%2==0)) {
'''+''.join(scalar)+'}\n}\n}\n')
    starts = [m.start() for m in re.finditer(r'const unsigned int cc_output_first =',source)]
    assert len(starts) == 2
    for start in reversed(starts):
        source = source[:start]+''.join(pieces)+source[scope_end(source,start):]
    return source


def mirrored_pre(source,c,q,p,t):
    start = source.index('// load global into registers\n')
    end = source.index('// calc the thread_in_device',start)
    original = source[start:end]
    zero = original.index('R[0] = {0,0};')
    first_sync = original.index('__syncthreads();',zero)
    last_sync = original.rindex('__syncthreads();')
    body = original[first_sync+len('__syncthreads();'):last_sync]
    pattern = r'R\[(\d+)\] = lds_complex\[threadIdx.x / '+str(p)+r' \* '+str(q)+r' \+ \((.*?)\)\];'
    assert re.findall(pattern,body)
    def own(match):
        reg,j = match.groups()
        middle = f'else if(j=={q//2}) own=cc_inverse_middle(p);' if q%2 == 0 else ''
        return f'''{{
const unsigned int j=({j});
if(j<={q//2}) {{
const unsigned int slot=threadIdx.x/{p};
const unsigned int row=tile_index_in_plane*{t}+slot;
scalar_type p=load_cb(buf_in,row*{q}+j,load_cb_data,nullptr),own,other;
if(j==0) own=cc_inverse_endpoints(p);
{middle}
else {{
scalar_type peer=load_cb(buf_in,row*{q}+{q}-j,load_cb_data,nullptr);
cc_pre_pair<scalar_type>(p,peer,cc_real_twiddles[j],own,other);
lds_complex[slot*{q}+{q}-j]=other;
}}
R[{reg}]=own;
}}
}}'''
    first = re.sub(pattern,own,body)
    second = re.sub(pattern,lambda m:f'if(({m[2]})>{q//2}) '+m[0],body)
    replacement = original[zero:first_sync]+first+'\n__syncthreads();\n'+second+'\n__syncthreads();\n\n'
    return source[:start]+replacement+source[end:]


def mirrored_post(source,c,q,t):
    starts = [m.start() for m in re.finditer(r'const unsigned int cc_post_lane =',source)]
    assert len(starts) == 2
    for start in reversed(starts):
        end = scope_end(source,start)
        old = source[start:end]
        pattern = r'lds_(?:complex|real)\[\((.*?)\) \* '+str(t)+r' \+ cc_post_slot\] = R\[(\d+)\](?:\.[xy])?;'
        mapped = list(dict.fromkeys(re.findall(pattern,old)))
        assert mapped
        header = f'''const unsigned int cc_post_lane=threadIdx.x/{t};
const unsigned int cc_post_slot=threadIdx.x%{t};
const unsigned int b=tile_index*{t}+cc_post_slot;
__syncthreads();
if(b<{q}) {{
'''
        stores,consumes = [],[]
        for j,reg in mapped:
            stores.append(f'''{{ const unsigned int j=({j});
if(j>{c//2} && j<{c}) lds_complex[({c}-j-1)*{t}+cc_post_slot]=R[{reg}];
}}
''')
            middle = f'''else if(j=={c//2}) store_cb(buf_out,j*{q}+b,cc_conjugate(R[{reg}]),store_cb_data,nullptr);''' if c%2 == 0 else ''
            consumes.append(f'''{{ const unsigned int j=({j});
if(j<={c//2}) {{
if(j==0) store_cb(buf_out,b,R[{reg}],store_cb_data,nullptr);
{middle}
else {{
scalar_type own,other,peer=lds_complex[(j-1)*{t}+cc_post_slot];
cc_post_pair<scalar_type>(R[{reg}],peer,cc_real_twiddles[j],own,other);
store_cb(buf_out,j*{q}+b,own,store_cb_data,nullptr);
store_cb(buf_out,({c}-j)*{q}+b,other,store_cb_data,nullptr);
}}
}}
}}
''')
        new = header+''.join(stores)+'}\n__syncthreads();\n'+f'if(b<{q}) {{\n'+''.join(consumes)+'}\n'
        source = source[:start]+new+source[end:]
    return source


def verify_models():
    pairs = 0
    for length in range(2,2049):
        lower = list(range(1,(length-1)//2+1))
        upper = [length-j for j in lower]
        assert not set(lower)&set(upper)
        assert sorted(lower+upper+[0]+([length//2] if length%2==0 else [])) == list(range(length))
        for j in lower:
            assert length-(length-j)-1 == j-1
        for t in range(1,33):
            assert len(lower)*t <= length*t//2
        pairs += len(lower)
    matrices = json.loads((ROOT/'experiments/EXP-128/records/regression-955252-20261022/selection.json').read_text())['cases']
    outputs = 0
    for case in matrices:
        c,q = case['C'],case['Q']
        for t in (1,2,5,7,8,11,16):
            for first in sorted({0,t,(c-1)//t*t}):
                if first >= c: continue
                valid = min(t,c-first)
                for comp in (0,1):
                    head = (first+c*comp)%2
                    for slot in range(valid):
                        base = first+slot+c*comp
                        for j in (0,q//2,q-1):
                            oldindex = first+slot+c*(2*j+comp)
                            assert oldindex == base+2*c*j
                            assert oldindex%2 == base%2
                            old = slot>=head and (slot-head)%2==0 and slot+1<valid
                            scalar = (slot==0 and head==1) or (slot+1==valid and oldindex%2==0)
                            newscalar = (slot==0 and head==1) or (slot+1==valid and base%2==0)
                            assert scalar == newscalar
                            if old: assert oldindex%2 == 0
                            outputs += 1
    return dict(pair_lengths=2047,mirror_pairs=pairs,output_index_checks=outputs,
        proof='Retain the native register mapping. Only lower representatives own pairs; upper mirror indices are unique. '
              'DC/middle stay fixed. Pair stores and real-output alignment are independent of frequency j.')


def main():
    models = verify_models()
    originals = json.loads((RECORD/'isa-summary.json').read_text())['kernels']
    tasks = []
    for item in originals:
        if item['arm'] != 'candidate': continue
        name = item['name']
        role = int(re.search(r'_role(\d+)_',name)[1])
        c,q = map(int,re.search(r'_C(\d+)_Q(\d+)_',name).groups())
        wgs,p = map(int,re.search(r'_wgs_(\d+)_tpt_(\d+)_',name).groups())
        assert wgs%p == 0
        t = wgs//p
        source = Path(item['offline_source']).read_text()
        variants = {}
        if role == 5:
            variants['output_hoist'] = output_hoist(source,c,q,p,t)
            if name.endswith('_lds'):
                variants['mirrored_pre'] = mirrored_pre(source,c,q,p,t)
                variants['mirrored_pre_output_hoist'] = output_hoist(variants['mirrored_pre'],c,q,p,t)
        elif role == 6:
            variants['mirrored_post'] = mirrored_post(source,c,q,t)
        for variant,text in variants.items():
            path = ART/('%d-%s-%s-stage%d-%s.hip.cpp'%(item['N'],item['func'],item['arm'],item['position'],variant))
            path.write_text(text)
            tasks.append(dict(N=item['N'],func=item['func'],arm=item['arm'],position=item['position'],
                name=name,variant=variant,offline_source=str(path)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compile_one,tasks))
    result = dict(complete=True,device_execution=False,models=models,kernels=results,
                  limitation='Only address/ownership models and offline compilation passed. Device numerical checks '
                             'and controlled timings are still required before claiming optimization benefits.')
    (RECORD/'prototype-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PROTOTYPES',len(results),'MODELS',models,flush=True)


if __name__ == '__main__':
    main()
