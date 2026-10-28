"""Address-footprint model only; address bins are not measured cache transactions."""
from collections import Counter
import json
from pathlib import Path
import sys


def footprint(g, grouped, tile):
    c, q, t, r = (g[k] for k in ('C', 'Q', 'T', 'R'))
    wgs = t*r
    data_blocks, phase_blocks, owners = 0, 0, []
    for i in range((q//2+1+t-1)//t):
        for wave in range((wgs+63)//64):
            p, peer, phase = set(), set(), set()
            for tid in range(wave*64, min(wgs, (wave+1)*64)):
                slot, lane = (tid//t, tid % t) if grouped else (tid % r, tid//r)
                j, row = lane+i*t, tile*r+slot
                if j > q//2 or row >= c:
                    continue
                owners.append((row, j))
                p.add(((row*q+j)*16)//64)
                if j != 0 and 2*j != q:
                    peer.add(((row*q+q-j)*16)//64)
                    phase.add((j*16)//64)
            data_blocks += len(p)+len(peer)
            phase_blocks += len(phase)
    return dict(data_address_bins=data_blocks, phase_address_bins=phase_blocks), Counter(owners)


def main():
    record = Path(sys.argv[1])
    cases = json.loads((record/'mapping-model.json').read_text(encoding='utf-8'))['cases']
    out = []
    for g in cases:
        for tile in sorted({0, max(0, g['C']//g['R']-1), g['C']//g['R']}):
            if tile*g['R'] >= g['C']:
                continue
            old, a = footprint(g, False, tile)
            new, b = footprint(g, True, tile)
            assert a == b and all(v == 1 for v in a.values())
        old, _ = footprint(g, False, 0)
        new, _ = footprint(g, True, 0)
        out.append(dict(N=g['N'], C=g['C'], Q=g['Q'], T=g['T'], R=g['R'],
                        load=g['load'], complete=True, current=old, row_grouped=new))
    result = dict(complete=True, device_execution=False, cases=out,
                  assumptions='64-thread waves; 64-byte address bins; aligned data and phase base zero. Count distinct bins separately for p, peer and phase per wave per source unroll. Full first tile footprints; full/partial tile pair coverage checked.',
                  limitations='This is not the generated instruction issue order, a cache simulation, measured memory requests, bytes transferred, or timing. Logical data/phase load count and shared-memory operation count do not decrease.')
    (record/'pair-distribution-model.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(complete=True, models=len(out))))


if __name__ == '__main__':
    main()
