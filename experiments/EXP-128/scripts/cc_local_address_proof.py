"""Exhaustive ownership and native register-map checks for the EXP128 catalogue."""
from collections import Counter
from pathlib import Path
import json


def register_pre(q, factors, p):
    f=factors[0];k=q//f;lanes=min(k,p)
    eligible=f%2==0 and lanes<=64 and not (lanes&(lanes-1)) and k%lanes==0 and p%lanes==0
    if not eligible:return False
    butterflies=k//lanes
    for lane in range(p):
        expected={h*f+w:lane+h*p+w*k for h in range((k+p-1)//p)
                  for w in range(f) if lane+h*p<k}
        actual={}
        def put(reg,index):
            assert reg not in actual,(q,p,lane,reg)
            actual[reg]=index
        if lane<lanes:
            for h in range(butterflies):
                for w in range(f//2):
                    j=lane+h*p+w*k;put(h*f+w,j)
                    if lane:
                        source=(lanes-lane)%lanes
                        put((butterflies-1-h)*f+f-1-w,q-(source+h*p+w*k))
                    elif h==0 and w>0:put(f-w,q-j)
                    elif h>0:put((butterflies-h)*f+f-1-w,q-j)
            if lane==0:put(f//2,q//2)
        assert actual==expected,(q,p,lane,actual,expected)
    return True


def verify(coverage):
    rows={x['aligned']['length']:x['aligned'] for x in coverage['rows']}
    cols={x['length']:x for x in coverage['columns']}
    registers=[];largest=0
    for x in coverage['geometries']:
        c,q,n=x['C'],x['Q'],x['N'];m=c*q
        assert n==2*m and n>65536
        ct,rt=cols[c]['ordinary_T'],rows[q]['ordinary_T']
        assert q>=ct and c*ct//(2 if cols[c]['half_lds'] else 1)>=c
        # Every original half-spectrum element reaches its callback once.
        loads=Counter()
        for b in range(q+1):
            for a in range(c):
                if b in (0,q):
                    peer=(c-a)%c if b==0 else c-a-1
                    if a>peer:continue
                k=2*q*a+b;loads[min(k,n-k)]+=1
        assert len(loads)==m+1 and all(v==1 for v in loads.values())
        # Both endpoint columns write disjoint scalar components.
        writes=Counter()
        for a in range(c):
            writes[2*a*q]+=1;writes[2*a*q+1]+=1
            for b in range(1,q):writes[2*(a*q+b)]+=1;writes[2*(a*q+b)+1]+=1
        assert len(writes)==n and max(writes.values())==1
        # Mixed row output only packs aligned adjacent elements from this block.
        output=Counter()
        for first in range(0,c,rt):
            valid=min(rt,c-first)
            for comp in (0,1):
                head=(first+c*comp)%2
                for p in range(q):
                    for slot in range(valid):
                        index=first+slot+c*(2*p+comp)
                        if slot>=head and (slot-head)%2==0 and slot+1<valid:
                            assert index%2==0
                            output[index]+=1;output[index+1]+=1
                        elif (slot==0 and head==1) or (slot+1==valid and index%2==0):
                            output[index]+=1
        assert len(output)==n and max(output.values())==1
        spectrum=Counter()
        for a in range(1,c):
            for h in range(q):
                k=2*c*h+a;spectrum[min(k,n-k)]+=1
        for t in range(q+1):spectrum[c*t]+=1
        assert len(spectrum)==m+1 and max(spectrum.values())==1
        if register_pre(q,rows[q]['factors'],rows[q]['P']):registers.append((c,q))
        largest=max(largest,n)
    return dict(complete=True,geometries=len(coverage['geometries']),
        register_pre_geometries=len(registers),largest_N=largest,
        checks=['unique physical load callbacks','disjoint endpoint scalar stores',
                'aligned bounded mixed output','complete folded spectrum','ordinary first-pass register ownership'])


if __name__=='__main__':
    here=Path(__file__).resolve().parent
    coverage=json.loads((here.parent/'records/implementation-20261021/coverage.json').read_text())
    print(json.dumps(verify(coverage),indent=2))
