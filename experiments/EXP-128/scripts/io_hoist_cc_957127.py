"""Offline common boundary-classification prototypes; keep every floating formula."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re

from isa_cc_957127 import compile_one, RECORD, ART


def close_brace(text,start):
    assert text[start]=='{'
    depth=1
    for pos in range(start+1,len(text)):
        depth += (text[pos]=='{')-(text[pos]=='}')
        if depth==0: return pos
    raise ValueError('unbalanced accepted source')


def resolve(text,predicate,choose_else=False):
    while True:
        selected=next((m for m in re.finditer(r'^if\(([^\n]+)\) \{',text,re.M) if predicate(m[1])),None)
        if not selected: return text
        opening=selected.end()-1
        close=close_brace(text,opening)
        body=text[opening+1:close]
        after=close+1
        tail=re.match(r'\s*else \{',text[after:])
        if tail:
            other_open=after+tail.end()-1
            other_close=close_brace(text,other_open)
            if choose_else: body=text[other_open+1:other_close]
            after=other_close+1
        else: assert not choose_else
        text=text[:selected.start()]+'{'+body+'}'+text[after:]


def input_hoist(source,c,q,p,t):
    start=source.index('// load global into registers\n')
    end=source.index('// calc the thread_in_device',start)
    old=source[start:end]
    initial=re.match(r'// load global into registers\n((?:R\[\d+\] = \{0,0\};\n)+)',old)
    assert initial
    body=old[initial.end():]
    pred=lambda condition:'tile_index_in_plane' in condition and '== 0' in condition
    first=resolve(body,pred)
    second=resolve(body,pred,True)
    active=lambda condition:'tile_index_in_plane' in condition and ('< '+str(c)) in condition
    first,second=resolve(first,active),resolve(second,active)
    row=f'tile_index_in_plane * {t} + threadIdx.x / {p}'
    first,second=first.replace(row,'cc_input_row'),second.replace(row,'cc_input_row')
    replacement=initial[0]+f'''const unsigned int cc_input_row={row};
if(cc_input_row<{c}) {{
if(cc_input_row==0) {{
'''+first+'\n} else {\n'+second+'\n}\n}\n'
    return source[:start]+replacement+source[end:]


def spectrum_hoist(source,c,q,p,t):
    begins=[m.start() for m in re.finditer(r'const unsigned int cc_spectrum_task = threadIdx.x \+ 0;',source)]
    assert len(begins)==2
    for position in reversed(begins):
        start=source.rfind('if(threadIdx.x + 0 <',0,position)
        terminal=source.index('if(tile_index_in_plane == 0)',position)
        body=f'''const unsigned int cc_output_slot=threadIdx.x%{t};
const unsigned int cc_output_row=tile_index_in_plane*{t}+cc_output_slot;
const unsigned int cc_output_p0=threadIdx.x/{t};
if(cc_output_row!=0 && cc_output_row<{c}) {{
'''
        for i in range((q+p-1)//p):
            body+=f'''{{ const unsigned int j=cc_output_p0+{i*p};
if(j<{q}) {{
scalar_type value=lds_complex[cc_output_slot*{q}+j];
unsigned int physical={2*c}*j+cc_output_row;
if(j>={(q+1)//2}) {{ value=cc_conjugate(value); physical={2*c*q}-physical; }}
store_cb(buf_out,physical,value,store_cb_data,nullptr);
}}
}}
'''
        source=source[:start]+body+'}\n'+source[terminal:]
    return source


def merge_column_boundaries(source,q):
    begins=[m.start() for m in re.finditer(r'if\(cc_store_column == 0\) \{',source)]
    assert len(begins)==2
    for start in reversed(begins):
        opening=source.index('{',start)
        close=close_brace(source,opening)
        match=re.match(r'\s*else if\(cc_store_column == '+str(q)+r'\) \{',source[close+1:])
        assert match
        other_open=close+1+match.end()-1
        end=close_brace(source,other_open)+1
        body=source[opening+1:close].replace('cc_real_pointer(buf_out)','cc_boundary_output')
        replacement=f'''if(cc_store_column == 0 || cc_store_column == {q}) {{
auto* const cc_boundary_output=cc_real_pointer(buf_out)+(cc_store_column=={q});
'''+body+'\n}'
        source=source[:start]+replacement+source[end:]
    return source


def main():
    originals=json.loads((RECORD/'isa-summary.json').read_text())['kernels']
    tasks=[]
    for item in originals:
        if item['arm']!='candidate': continue
        name=item['name']
        role=int(re.search(r'_role(\d+)_',name)[1])
        c,q=map(int,re.search(r'_C(\d+)_Q(\d+)_',name).groups())
        wgs,p=map(int,re.search(r'_wgs_(\d+)_tpt_(\d+)_',name).groups())
        assert wgs%p==0
        t=wgs//p
        source=Path(item['offline_source']).read_text()
        variants={}
        if role==4:
            variants['column_boundary_merge']=merge_column_boundaries(source,q)
        elif role==7:
            variants['row_input_hoist']=input_hoist(source,c,q,p,t)
            variants['row_input_output_hoist']=spectrum_hoist(variants['row_input_hoist'],c,q,p,t)
        for variant,text in variants.items():
            path=ART/('%d-%s-stage%d-%s.hip.cpp'%(item['N'],item['func'],item['position'],variant))
            path.write_text(text)
            tasks.append(dict(N=item['N'],func=item['func'],arm=item['arm'],position=item['position'],
                              name=name,variant=variant,offline_source=str(path)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(compile_one,tasks))
    (RECORD/'io-hoist-summary.json').write_text(json.dumps(dict(complete=True,device_execution=False,
        semantics='Same phases, arithmetic, global addresses, ownership and synchronization; classify boundaries once.',
        limitation='Offline compilation only; no new device correctness or performance claim.',
        kernels=results),ensure_ascii=False,indent=2)+'\n')
    print('IO_PROTOTYPES',len(results),flush=True)


if __name__=='__main__': main()
