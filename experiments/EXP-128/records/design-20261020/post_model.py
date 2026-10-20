"""EXP128 design model only: no production source edits or device execution."""
from pathlib import Path
from collections import Counter
import argparse
import csv
import hashlib
import json
import math
import re
import numpy as np

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, default=HERE/'source')
parser.add_argument('--catalog', type=Path, default=HERE/'model-inputs.json')
parser.add_argument('--out-dir', type=Path, default=HERE)
args = parser.parse_args()
OUT = args.out_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
POOL_PATH = args.catalog
POOL = json.loads(POOL_PATH.read_text(encoding='utf-8'))
COLS = {v['length']: v for v in POOL['columns']}
ROWS = {v['aligned']['length']: v['aligned'] for v in POOL['rows']}
CATALOG = POOL['catalog_pairs_N_gt65536']


def local_post(raw):
    """C-point complex FFT to local real half-spectrum; keep raw DC packed."""
    length = raw.shape[0]
    out = np.empty_like(raw)
    out[0] = raw[0]
    j = np.arange(1, (length+1)//2)
    p, q = raw[j], raw[length-j]
    phase = np.exp(-1j*np.pi*j/length).reshape((len(j),)+(1,)*(raw.ndim-1))
    ux,uy = .5*(p.real+q.real), .5*(p.imag+q.imag)
    vx,vy = .5*(p.real-q.real), .5*(p.imag-q.imag)
    a = vx*phase.imag+uy*phase.real
    b = uy*phase.imag-vx*phase.real
    out[j] = ux+a+1j*(vy+b)
    out[length-j] = ux-a+1j*(b-vy)
    if length % 2 == 0:
        out[length//2] = np.conj(raw[length//2])
    return out


def terminal_half_spectrum(raw_fft):
    packed = local_post(raw_fft)
    result = np.empty(len(packed)+1, dtype=np.complex128)
    result[0] = packed[0].real+packed[0].imag
    result[-1] = packed[0].real-packed[0].imag
    result[1:-1] = packed[1:]
    return result


def callback_store(v, k):
    # Does not commute with conjugation; includes the physical output index.
    return v*(.93+.17j)+(k % 13)*(.007-.011j)


def mathematical_case(c,q,pattern,seed,callbacks=False):
    n,m=2*c*q,c*q
    rng=np.random.default_rng(seed)
    if pattern=='random':
        x=rng.normal(size=n)
    elif pattern=='impulses':
        x=np.zeros(n)
        for k in {0,n-1,min(q,n-1),min(2*q,n-1),n//2}:
            x[k]=1+.031*k
    else:
        k=np.arange(n)
        x=.2+np.cos(2*np.pi*k/n)+.17*(-1.)**k
    if callbacks:
        x=.83*x+np.sin(x)*.05+(np.arange(n) % 17)*.003
    # Ordinary C-point first stage, packing samples Q real elements apart.
    t=x.reshape(2*c,q)
    f=np.fft.fft(t[0::2]+1j*t[1::2],axis=0)
    packed=local_post(f)
    a=np.arange(1,c)[:,None]
    b=np.arange(q)[None,:]
    g=np.fft.fft(packed[1:]*np.exp(-2j*np.pi*a*b/n),axis=1)
    k=2*c*b+a
    physical=np.minimum(k,n-k)
    mirrored=k>m
    out=np.empty(m+1,dtype=np.complex128)
    out[physical]=np.where(mirrored,np.conj(g),g)
    # The two local endpoint rows are one 2Q-point REAL transform, not two
    # independent Q-point complex transforms. It still uses one Q-point FFT.
    u=np.concatenate((packed[0].real,packed[0].imag))
    terminal_input=u[0::2]+1j*u[1::2]
    terminal_fft=np.fft.fft(terminal_input)
    terminal=terminal_half_spectrum(terminal_fft)
    out[c*np.arange(q+1)]=terminal
    expected=np.fft.rfft(x)
    negative_error=0.
    if callbacks:
        wrong=np.empty_like(out)
        wrong[physical]=np.where(mirrored,np.conj(callback_store(g,physical)),callback_store(g,physical))
        wrong[c*np.arange(q+1)]=callback_store(terminal,c*np.arange(q+1))
        out=callback_store(out,np.arange(m+1))
        expected=callback_store(expected,np.arange(m+1))
        negative_error=float(np.max(np.abs(wrong-expected))/max(1.,np.max(np.abs(expected))))
    error=float(np.max(np.abs(out-expected))/max(1.,np.max(np.abs(expected))))
    assert error < 1e-11,(c,q,pattern,error)
    return {'N':n,'C':c,'Q':q,'pattern':pattern,'callbacks':callbacks,'error':error,'wrong_conjugation_callback_error':negative_error}


def address_case(c,q):
    n,m=2*c*q,c*q
    a=np.arange(1,c)[:,None]
    h=np.arange(q)[None,:]
    k=2*c*h+a
    idx=np.minimum(k,n-k).reshape(-1)
    idx=np.concatenate((idx,c*np.arange(q+1)))
    count=np.bincount(idx,minlength=m+1)
    assert len(idx)==m+1 and np.all(count==1)
    # Each raw packed endpoint component is read exactly once by the terminal.
    j=np.arange(q)
    t=np.stack((2*j,2*j+1),axis=1).reshape(-1)
    b=t % q
    component=t//q
    words=2*b+component
    assert np.array_equal(np.sort(words),np.arange(2*q))
    # Input pairs partition the original real array with no repeated callbacks.
    first=np.arange(c)[:,None]*2*q+np.arange(q)[None,:]
    assert np.array_equal(np.sort(np.concatenate((first.ravel(),(first+q).ravel()))),np.arange(n))


def register_map(length,factors,p,last=False):
    width=factors[-1] if last else factors[0]
    k=length//width
    result={}
    for t in range(k):
        for j in range(width):
            result[t+j*k]=(t%p,(t//p)*width+j)
    assert len(result)==length and len(set(result.values()))==length
    return result


def column_exchange_within_wave(col,wave=64):
    c,p,slots=col['length'],col['P'],col['ordinary_T']
    mp=register_map(c,col['factors'],p,last=True)
    for slot in range(slots):
        for j in range(1,(c+1)//2):
            producer=mp[j][0]*slots+slot
            consumer=mp[c-j][0]*slots+slot
            if producer//wave != consumer//wave:
                return False
    return True


def main():
    matched=[]
    for name in ['config_sbcc.py','config_sbrc.py']:
        rel='library/src/device/kernels/configs/'+name
        raw=(args.source_root/rel).read_bytes()
        key='rocm-libraries-rocm-7.2.2/projects/rocfft/'+rel
        old=POOL['source_hashes'][key.replace('/','\\')]
        assert old in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')).hexdigest()]
        matched.append(rel)
    text=(args.source_root/'library/src/node_factory.cpp').read_text(encoding='utf-8')
    block=text.split('NodeFactory::map1DLengthDouble = {',1)[1].split('};',1)[0]
    body='\n'.join(line.split('//')[0] for line in block.splitlines())
    old_map={int(m):int(c) for m,c in re.findall(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}',body)}
    old_five={65536,131072,262144,524288,1048576}
    actual={(c,m//c) for m,c in old_map.items() if 2*m>65536 and 2*m not in old_five and c in COLS and m//c in ROWS}
    costs=[]
    numerical=[]
    for i,case in enumerate(CATALOG):
        n,c,q=case['N'],case['C'],case['Q']
        col,row=COLS[c],ROWS[q]
        address_case(c,q)
        numerical.append(mathematical_case(c,q,'random',17200+i,callbacks=i%3==0))
        data=col['ordinary_data_LDS_bytes']
        full=16*c*col['ordinary_T']
        scalar=max(data,8*c*col['ordinary_T'])
        assert max(full,scalar)<=65536
        slots=row['ordinary_T']
        costs.append({'N':n,'C':c,'Q':q,'EXP125_existing_map_geometry':(c,q) in actual,
                      'first_C_FFTs':q,'last_Q_FFTs':c,'extra_FFTs':0,
                      'cc_T':col['ordinary_T'],'cc_blocks':math.ceil(q/col['ordinary_T']),
                      'rc_T':slots,'rc_blocks':math.ceil(c/slots),
                      'middle_bytes':16*c*q,'extra_middle_bytes':0,
                      'middle_read_bytes':16*c*q,'middle_write_bytes':16*c*q,
                      'logical_extra_global_bytes':0,
                      'column_post_small_phase_entries':(c+1)//2,
                      'terminal_small_phase_entries':(q+1)//2,
                      'full_post_shared_bytes':max(data,full),'scalar_post_shared_bytes':scalar,
                      'ordinary_core_shared_bytes':data,
                      'full_post_vs_core_shared_ratio':max(data,full)/data,
                      'column_wave_coordinate_condition':column_exchange_within_wave(col),
                      'terminal_extra_local_work_scale':1/c,
                      'discarded_extra_complex_FFT_route_work_scale':1/c,
                      'last_tail_rows':c % slots})
    for c in range(1,10):
        for q in range(1,18):
            address_case(c,q)
            for pattern in ['random','impulses','structured']:
                numerical.append(mathematical_case(c,q,pattern,1000+c*50+q,callbacks=(c+q)%2==1))
    for c,q in sorted(actual):
        for pattern in ['impulses','structured']:
            numerical.append(mathematical_case(c,q,pattern,1,callbacks=True))
    for n,c,q in [(65536,128,256),(131072,256,256),(262144,256,512),(524288,512,512),(1048576,1024,512)]:
        numerical.append(mathematical_case(c,q,'random',n,True))
    for col in COLS.values():
        register_map(col['length'],col['factors'],col['P'],last=True)
    for row in ROWS.values():
        register_map(row['length'],row['factors'],row['P'])
    summary={'complete':True,'branch':'exp-128-cc-local-real','base_commit':'77fd0040ab01aaeacd2cc6c30914185d9304adbd',
             'base_fft_tree':'5266f0f008c5c5b74bf2d1415bec37b842582e85','configuration_files_match':matched,
             'catalog_geometries':len(CATALOG),'EXP125_existing_generic_map_geometries':len(actual),
             'EXP125_existing_generic_C':sorted({c for c,q in actual}),'EXP125_existing_generic_Q':sorted({q for c,q in actual}),
             'numerical_cases':len(numerical),'max_relative_linf_error':max(v['error'] for v in numerical),
             'callback_wrong_order_negative_controls':sum(v['wrong_conjugation_callback_error']>1e-3 for v in numerical),
             'parities':dict(Counter(f"C{v['C']%2}_Q{v['Q']%2}" for v in costs)),
             'logical_global_bytes_added':0,'extra_complex_FFTs':0,'middle_size_increase_bytes':0,
             'ordinary_C_and_Q_workgroup_geometry_preserved':True,
             'column_post_same_wave_necessary_condition_lengths':[c for c,col in COLS.items() if column_exchange_within_wave(col)],
             'half_LDS_classes_with_twofold_full_post_exchange':[c for c,col in COLS.items() if col['half_lds']],
             'catalog_max_full_shared_bytes':max(v['full_post_shared_bytes'] for v in costs),
             'catalog_max_scalar_shared_bytes':max(v['scalar_post_shared_bytes'] for v in costs),
             'terminal_repack_all_Q_parities':True,'input_and_output_callbacks_unique':True,
             'device_execution':False,'production_source_modified':False,'performance_evidence':False,
             'limits':'Independent NumPy FFT reference and address/resource model; not generated-device-code acceptance.'}
    payload={'summary':summary,'numerical':numerical,'costs':costs}
    (OUT/'post-model-results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'后处理模型摘要.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,rows in [('279种后处理组合静态代价.csv',costs),('EXP125已有27项分解静态代价.csv',[v for v in costs if v['EXP125_existing_map_geometry']])]:
        with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
