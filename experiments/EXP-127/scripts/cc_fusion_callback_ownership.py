"""Independent ownership and shared-cache model for the entire folded family."""
import json
from collections import Counter


def geometry(n):
    q = 256 if n <= 131072 else 512
    c = n // (2*q)
    p = {128:16,256:32,512:64,1024:64}[c]
    return c,q,256//p


def check(n,lds):
    c,q,slots=geometry(n)
    assert q % slots == 0 and q >= slots and c % 2 == 0
    available_complex=c*slots//(1 if lds or c==128 else 2)
    assert available_complex>=c
    reads=[0]*(n//2+1)
    old_reads=[0]*(n//2+1)
    transformed=0
    barriers=0
    def value(k,count=1):
        # A count-dependent result also detects duplicated callback execution
        # that a pure scale-and-offset callback would conceal numerically.
        return complex(0.75*k+(k%7)*0.03125+count*0.125,-0.25*k-count*0.0625)
    def load(k):
        reads[k]+=1
        return value(k,reads[k])
    for tile in range(q//slots+1):
        boundary=tile in (0,q//slots)
        cache=[None]*c
        writes=[0]*c
        if boundary:
            column=0 if tile==0 else q
            limit=c//2+(column==0)
            owners=[]
            for thread in range(256):
                for row in range(thread,limit,256):
                    owners.append(row)
                    raw=load(2*q*row+column)
                    mirror=(c-row)%c if column==0 else c-1-row
                    for at in {row,mirror}:
                        writes[at]+=1
                        cache[at]=raw
            assert sorted(owners)==list(range(limit))
            assert writes==[1]*c and all(x is not None for x in cache)
            barriers+=1
        consumed=set()
        # Deliberately consume the opposite half first. LDS stores may reuse
        # the cache only after the same logical row has read its raw value.
        for hor in range(slots):
            column=tile*slots+hor
            if column>q:continue
            for row in reversed(range(c)):
                logical=2*q*row+column
                physical=min(logical,n-logical)
                old_reads[physical]+=1
                cached=boundary and hor==0
                raw=cache[row] if cached else load(physical)
                actual=raw.conjugate() if logical>n//2 else raw
                expected=value(physical).conjugate() if logical>n//2 else value(physical)
                assert actual==expected,(n,lds,logical,physical)
                transformed+=1
                if cached:
                    assert row not in consumed
                    consumed.add(row)
                    if lds:
                        # The boundary column is transform zero in each tile;
                        # its LDS destination equals its unique cache index.
                        target=hor*c+row
                        assert target==row
                        cache[target]=actual
                elif lds:
                    assert not boundary or hor*c+row>=c
        if boundary:
            assert len(consumed)==c
            barriers+=1
    assert reads==[1]*len(reads)
    assert old_reads==[2 if 0<k<n//2 and k%q==0 else 1 for k in range(n//2+1)]
    assert transformed==c*(q+1) and barriers==4
    return dict(N=n,C=c,Q=q,slots=slots,load='LDS' if lds else 'registers',
        unique_callback_elements=len(reads),old_duplicate_elements=old_reads.count(2),
        new_duplicate_elements=reads.count(2),dc_reads=reads[0],nyquist_reads=reads[-1],
        cache_complex_elements=c,allocated_complex_elements=available_complex,
        extra_grid_barrier_instances=barriers,logical_values_checked=transformed,
        stateful_reference_passed=True,LDS_in_place_cache_reuse_proved=lds)


if __name__=='__main__':
    rows=[check(n,lds) for n in (65536,131072,262144,524288,1048576) for lds in (False,True)]
    print(json.dumps(dict(complete=True,device_execution=False,rows=rows),indent=2))
