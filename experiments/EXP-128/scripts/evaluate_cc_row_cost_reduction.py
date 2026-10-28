"""Host models and offline prototypes only; do not change the production generator."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa
from cc_v5_regression_common import rtc_sources

RECORD=ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/row-cost-reduction-20261027'
SOURCE=ROOT/'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027/default'
DATA=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/results-983952-984725/all-samples-and-statistics.json'


def write(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def geometry(path,n,c,q):
    text=path.read_text();body=text[text.index('extern "C" __global__'):]
    name=re.search(r'extern "C" __global__.*? void ([^(]+)\(',body,re.S)[1]
    t=int(re.search(r'uses (\d+) threads per transform',body)[1])
    r=int(re.search(r'does (\d+) transforms per thread block',body)[1])
    f=list(map(int,re.search(r'_factors_([0-9_]+)_wgs_',name)[1].split('_')))
    regs=int(re.search(r'scalar_type R\[(\d+)\]',body)[1])
    assert r*t==int(re.search(r'_wgs_(\d+)_',name)[1])
    return dict(N=n,C=c,Q=q,T=t,R=r,factors=f,registers=regs,name=name,path=str(path),
        load='registers' if name.endswith('_reg') else 'LDS',
        packed=c%2==0 and r%2==0 and c%r==0),text


def pass_map(g,first):
    f=g['factors'][0 if first else -1];k=g['Q']//f;t=g['T'];mapping={}
    for lane in range(t):
        for h in range((k+t-1)//t):
            if lane+h*t>=k:continue
            for w in range(f):
                j=lane+h*t+w*k;reg=h*f+w
                assert 0<=j<g['Q'] and reg<g['registers'] and j not in mapping
                mapping[j]=(lane,reg)
    assert len(mapping)==g['Q']
    return mapping


def check_model(g):
    q,t,r,c=(g[k] for k in ('Q','T','R','C'));wgs=t*r;half=q//2+1
    first_map,last_map=pass_map(g,True),pass_map(g,False)
    tiles=sorted({0,max(0,c//r-1),c//r})
    checked=0
    for tile in tiles:
        if tile*r>=c:continue
        a=[];b=[]
        for tid in range(wgs):
            for i in range((half*r+wgs-1)//wgs):
                task=tid+i*wgs
                if task<half*r and tile*r+task%r<c:a.append((task%r,task//r))
            slot,lane=tid%r,tid//r
            if tile*r+slot<c:
                for i in range((half+t-1)//t):
                    j=lane+i*t
                    if j<half:b.append((slot,j))
        assert Counter(a)==Counter(b) and all(n==1 for n in Counter(a).values())
        # Compare the original vector/scalar stores against direct register output.
        expected={};old={};new={}
        for slot in range(min(r,c-tile*r)):
            for j in range(q):
                for comp in (0,1):expected[(tile*r+slot)+c*comp+2*c*j]=(slot,j,comp)
        def store(target,address,value):
            assert address not in target;target[address]=value
        valid=min(r,c-tile*r)
        for tid in range(wgs):
            slot,p0=tid%r,tid//r
            if g['packed']:
                comp,pair=divmod(slot,r//2)
                for i in range((q+t-1)//t):
                    j=p0+i*t
                    if j>=q:continue
                    address=tile*r+2*pair+2*c*j+c*comp
                    store(old,address,(2*pair,j,comp));store(old,address+1,(2*pair+1,j,comp))
            elif slot<valid:
                for comp in (0,1):
                    head=(tile*r+c*comp)%2;base=tile*r+slot+c*comp
                    vector=slot>=head and (slot-head)%2==0 and slot+1<valid
                    scalar=(slot==0 and head==1) or (slot+1==valid and base%2==0)
                    for i in range((q+t-1)//t):
                        j=p0+i*t
                        if j>=q:continue
                        address=base+2*c*j
                        if vector:
                            assert address%2==0
                            store(old,address,(slot,j,comp));store(old,address+1,(slot+1,j,comp))
                        elif scalar:store(old,address,(slot,j,comp))
        for j,(lane,reg) in last_map.items():
            for slot in range(valid):
                for comp in (0,1):store(new,tile*r+slot+c*comp+2*c*j,(slot,j,comp))
        assert old==new==expected
        checked+=len(expected)
    locality=Counter()
    for slot in range(r):
        for j in range(1,(q+1)//2):
            a,b=(slot*t+first_map[x][0] for x in (j,q-j))
            locality['same_thread' if a==b else 'same_wave' if a//64==b//64 else 'cross_wave']+=1
    return dict(complete=True,checked_output_points=checked,register_pair_locality=dict(locality),
        scope='Exact first/last native pass maps, full and partial row tiles; counts are element ownership, not device time.')


def input_hoist(text,g):
    assert g['load']=='LDS'
    start=text.index('// load global into registers\n');end=text.index('// calc the thread_in_device',start)
    old=text[start:end];reload_at=old.index('R[0] = {0,0};');reload=old[reload_at:]
    c,q,t,r=(g[k] for k in ('C','Q','T','R'));half=q//2+1
    lines=['// load global into registers',
        f'const unsigned int ev_slot = threadIdx.x % {r};',
        f'const unsigned int ev_lane = threadIdx.x / {r};',
        f'const unsigned int ev_row = tile_index_in_plane * {r} + ev_slot;']
    guarded=c%r!=0
    if guarded:lines.append(f'if(ev_row < {c}) {{')
    lines.append(f'const unsigned int ev_base = ev_row * {q};')
    for i in range((half+t-1)//t):
        offset=i*t;partial=offset+t>half
        lines+=['{',f'const unsigned int ev_j = ev_lane + {offset};']
        if partial:lines.append(f'if(ev_j < {half}) {{')
        lines+=['scalar_type ev_p = load_cb(buf_in,ev_base+ev_j,load_cb_data,nullptr);',
            'scalar_type ev_own, ev_other;']
        if i==0:
            lines += [f'if(ev_lane == 0) {{ lds_complex[ev_slot*{q}] = cc_inverse_endpoints(ev_p); }}', 'else {']
        middle=q%2==0 and offset<=q//2<offset+t
        if middle:
            lines += [f'if(ev_j == {q//2}) {{ lds_complex[ev_slot*{q}+ev_j] = cc_inverse_middle(ev_p); }}','else {']
        lines += [f'scalar_type ev_q = load_cb(buf_in,ev_base+{q}-ev_j,load_cb_data,nullptr);',
            'cc_pre_pair<scalar_type>(ev_p,ev_q,cc_real_twiddles[ev_j],ev_own,ev_other);',
            f'lds_complex[ev_slot*{q}+ev_j] = ev_own;',
            f'lds_complex[ev_slot*{q}+{q}-ev_j] = ev_other;']
        if middle:lines.append('}')
        if i==0:lines.append('}')
        if partial:lines.append('}')
        lines.append('}')
    if guarded:lines.append('}')
    # Both barriers in reload_input are deliberately retained.
    return text[:start]+'\n'.join(lines)+'\n'+reload+text[end:]


def output_direct(text,g):
    assert g['R']==1
    start=text.index('// call a post-store from registers to lds (if necessary)')
    c,q,t=(g[k] for k in ('C','Q','T'));f=g['factors'][-1];k=q//f
    lines=['// Direct real output, native last-pass register map.',
        f'const unsigned int ev_lane_out = threadIdx.x % {t};',
        'const unsigned int ev_row_out = tile_index_in_plane;']
    for h in range((k+t-1)//t):
        guard=(h+1)*t>k
        if guard:lines.append(f'if(ev_lane_out+{h*t} < {k}) {{')
        for w in range(f):
            j=f'(ev_lane_out+{h*t+w*k})';reg=h*f+w
            lines += [f'store_cb(cc_real_pointer(buf_out),ev_row_out+{2*c}*{j},R[{reg}].x,store_cb_data,nullptr);',
                f'store_cb(cc_real_pointer(buf_out),ev_row_out+{c}+{2*c}*{j},R[{reg}].y,store_cb_data,nullptr);']
        if guard:lines.append('}')
    return text[:start]+'\n'.join(lines)+'\n}\n'


def remove_if(text,start,head_end):
    depth=1;at=head_end
    while depth:
        if text[at]=='{':depth+=1
        elif text[at]=='}':depth-=1
        at+=1
    return text[:start]+text[head_end:at-1]+text[at:]


def output_tight(text,g):
    assert not g['packed']
    start=text.index('// call a post-store from registers to lds (if necessary)');prefix=text[:start];tail=text[start:]
    c,q,t,r=(g[k] for k in ('C','Q','T','R'))
    if r==1:
        # Keep the original post-store and its following barrier; replace output only.
        split=tail.index('if(direct_store_from_reg) {');post=tail[:split]
        lines=['// Scalar output for one-transform blocks.','__syncthreads();']
        for comp,part in enumerate(('x','y')):
            for i in range((q+t-1)//t):
                j=f'(threadIdx.x+{i*t})';guard=(i+1)*t>q
                if guard:lines.append(f'if({j} < {q}) {{')
                lines.append(f'store_cb(cc_real_pointer(buf_out),tile_index_in_plane+{comp*c}+{2*c}*{j},lds_complex[{j}].{part},store_cb_data,nullptr);')
                if guard:lines.append('}')
        return prefix+post+'\n'.join(lines)+'\n}\n'
    if c%r==0:
        tail=tail.replace(f'const unsigned int cc_output_valid = min({r},{c} - cc_output_first);',
                          f'const unsigned int cc_output_valid = {r};')
    while True:
        match=next((m for m in re.finditer(r'if\(cc_output_p0 \+ (\d+) < '+str(q)+r'\) \{',tail)
                    if int(m[1])+t<=q),None)
        if match is None:break
        tail=remove_if(tail,match.start(),match.end())
    return prefix+tail


def gauss(text):
    old='const auto a = vx * w.y - uy * w.x, b = uy * w.y + vx * w.x;'
    assert text.count(old)==1
    return text.replace(old,'const auto m1 = vx*w.y, m2 = uy*w.x, m3 = (vx+uy)*(w.x+w.y);\n    const auto a = m1-m2, b = m3-m1-m2;')


def main():
    RECORD.mkdir(parents=True,exist_ok=True);ART.mkdir(parents=True,exist_ok=True)
    rows=json.loads(DATA.read_text());unique={x['N']:(x['C'],x['Q']) for x in rows};assert len(unique)==194
    cases=[];sources={}
    for n,(c,q) in sorted(unique.items()):
        g,text=geometry(SOURCE/f'{c}-{q}-5-0.cpp',n,c,q);g['model']=check_model(g)
        cases.append(g);sources[n]=text
    write(RECORD/'mapping-model.json',dict(complete=True,device_execution=False,cases=cases,
        direct_scope='R=1; full native output map proved for all cases but multitransform output coalescing remains separate.',
        synchronization='Keep both reload barriers: native pass zero skips the overwrite barrier when direct_load_to_reg=true.'))
    representatives=(69938,97104,129472,142688,640000,425920,646866,2725888,346112,497664,1048576,303750)
    lookup={x['N']:x for x in cases};tasks=[]
    runtime=json.loads((ROOT/'experiments/EXP-128/runs/EXP-128-cc-v5-regression-diagnostic-20261027/diagnostic-result.json').read_text())
    traced={x['N']:x for x in runtime['traces'] if x['func']=='z2d_1d' and x['arm']=='candidate'}
    for n in representatives:
        generated=lookup[n];trace=traced[n];metadata=Path(trace['folder'])/'metadata/rtc.txt'
        name=trace['trace']['kernel_names'][1];original=rtc_sources(metadata.read_text())[name]
        actual=ART/(str(n)+'-actual.cpp');actual.write_text(original)
        g,_=geometry(actual,n,generated['C'],generated['Q'])
        assert all(g[k]==generated[k] for k in ('T','R','factors','registers','load','packed'))
        variants={'current':original}
        if g['load']=='LDS':variants['input_hoist']=input_hoist(original,g)
        if not g['packed']:
            variants['output_tight']=output_tight(original,g)
            if g['load']=='LDS':variants['input_tight']=output_tight(variants['input_hoist'],g)
        if g['R']==1:
            variants['direct_output']=output_direct(original,g)
            if g['load']=='LDS':variants['input_direct']=output_direct(variants['input_hoist'],g)
        if n in (97104,425920):variants['gauss_pair']=gauss(original)
        for variant,text in variants.items():
            path=ART/(str(n)+'-'+variant+'.cpp');path.write_text(text)
            tasks.append(dict(N=n,variant=variant,geometry={k:g[k] for k in ('C','Q','T','R','factors','load','packed')},
                metadata=str(metadata),actual_kernel=name,source=str(path),sha256=hashlib.sha256(text.encode()).hexdigest()))
    def compile_one(item):
        path=Path(item['source']);unit=path.with_suffix('.hip.cpp');asm=path.with_suffix('.s')
        unit.write_text('#include <hip/hip_runtime.h>\n'+path.read_text())
        argv=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936','--cuda-device-only','-mcumode','-S',str(unit),'-o',str(asm)]
        proc=subprocess.run(argv,env=mgr.environment(ART),text=True,capture_output=True,timeout=180)
        path.with_suffix('.err').write_text(proc.stderr);entry=dict(item,complete=proc.returncode==0,command=argv)
        if proc.returncode:entry['error']=proc.stderr[-3000:]
        else:
            text=asm.read_text();entry.update(analyze_isa(text))
            match=re.search(r'\.wavefront_size:\s*(\d+)',text);entry['wavefront_size']=int(match[1]) if match else None
        return entry
    with ThreadPoolExecutor(max_workers=2) as pool:compiled=list(pool.map(compile_one,tasks))
    failures=[x for x in compiled if not x['complete']]
    value=dict(complete=not failures,device_execution=False,compiled=compiled,failures=failures,
        limitations='Index models and offline compiler evidence only. No numeric device acceptance, timing, or speedup claim. Both reload barriers retained.')
    write(RECORD/'prototype-compilation.json',value)
    print(json.dumps(dict(complete=not failures,cases=len(cases),compiled=len(compiled),failures=failures,
        row_types=sorted({(x['Q'],x['T'],x['R']) for x in cases})),ensure_ascii=False,indent=2))
    assert not failures


if __name__=='__main__':main()
