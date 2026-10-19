"""Coordinate model using each case's actual twiddle and LDS budget.

Preserves the earlier model and JSON. No compilation or device execution.
"""
import hashlib
import json
from pathlib import Path

W = Path(__file__).resolve().parent
old = W / 'generic_scalar_coordinate_model.py'
old_text = old.read_text(encoding='utf-8')
# Reuse only imports/constants/functions, before the original executable body.
prefix, separator, _ = old_text.partition('\ncatalog = {}\n')
assert separator
namespace = {'__file__': str(old)}
exec(compile(prefix, str(old), 'exec'), namespace)
RX, KEY = namespace['RX'], namespace['KEY']
io_map = namespace['io_map']
scalar_pre, scalar_post = namespace['scalar_pre'], namespace['scalar_post']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def twiddle(m, use3):
    assert m > 0
    bits = (m - 1).bit_length()
    base = min(6, max(4, (bits + 2) // 3)) if use3 and m <= (1 << 18) else 8
    steps = 0
    while (1 << (base * steps)) < m:
        steps += 1
    assert (base == 8 and steps <= 3) or (base < 8 and steps == 3)
    assert m <= (1 << (base * steps))
    extra = 3 * (1 << base) * 16 if base < 8 and steps > 0 else 0
    return dict(base=base, steps=steps, extra_lds_bytes=extra,
                representable_entries=1 << (base * steps))


catalog = {}
pool = W / 'generated-pool-kernels.json'
for source in json.loads(pool.read_text(encoding='utf-8')):
    for entry in source['entries']:
        a, b = RX.search(entry['definition']), KEY.search(entry['entry'])
        assert a and b
        use3, fs, t, w, p, p2, half, direct, aot = a.groups()
        length, scheme, tile = b.groups()
        if tile == 'TILE_UNALIGNED':
            continue
        key = scheme, int(length)
        assert key not in catalog
        catalog[key] = dict(length=int(length), P=int(p), factors=list(map(int, fs.split(','))),
                            ordinary_T=int(t), ordinary_W=int(w),
                            use3=use3 == 'true', ordinary_half_lds=half == 'true')

results = []
catalog_checks = []
for (scheme, length), cfg in sorted(catalog.items()):
    p = cfg['P']
    pre = scheme.endswith('_CC')
    first = io_map(length, p, cfg['factors'], True)
    last = io_map(length, p, cfg['factors'], False)
    lower = max(3, 65536 // (2 * length) + 1)
    axes = set(range(lower, lower + 5))
    # Include a tail at the real initial resource-derived slot count.
    initial_twd = twiddle(lower * length, cfg['use3']) if pre else dict(base=0, steps=0, extra_lds_bytes=0)
    initial_slots = min(max(2, cfg['ordinary_T']), 1024 // p,
                        (65536 - initial_twd['extra_lds_bytes']) // (16 * length)) & ~1
    assert initial_slots >= 2
    h = initial_slots // 2
    axes.add(((lower + h - 1) // h + 1) * h - 1)
    if pre:
        # Both sides of base-8 two/three-step and small/base-8 transitions.
        for boundary in (1 << 16, 1 << 18):
            below = boundary // length
            above = below + 1
            if 2 * below * length > 65536:
                axes.add(below)
            axes.add(above)
        # A larger member after every currently possible transition.
        axes.add((524288 + length - 1) // length)
    else:
        large_axis = max(lower + initial_slots + 1, (262144 + length - 1) // length)
        axes.update((large_axis, large_axis + 1))

    family_rows = []
    for axis in sorted(axes):
        m = length * axis
        n = 2 * m
        assert n > 65536
        phase = twiddle(m, cfg['use3']) if pre else dict(base=0, steps=0, extra_lds_bytes=0,
                                                         representable_entries=None)
        max_by_threads = 1024 // p
        max_by_full_lds = (65536 - phase['extra_lds_bytes']) // (16 * length)
        slots = min(max(2, cfg['ordinary_T']), max_by_threads, max_by_full_lds) & ~1
        assert slots >= 2 and slots * p <= 1024
        complex_bytes = slots * length * 16 + phase['extra_lds_bytes']
        scalar_bytes = slots * length * 8 + phase['extra_lds_bytes']
        assert complex_bytes <= 65536 and scalar_bytes <= 65536
        check = scalar_pre(length, p, slots, axis) if pre else scalar_post(length, p, slots, axis)
        half_slots = slots // 2
        blocks = ((axis + 1) // 2 + half_slots - 1) // half_slots
        mapped_row = namespace['mapped_row']
        invalid_slots = sum(mapped_row(axis, slots, s, b) >= axis
                            for b in range(blocks) for s in range(slots))
        item = dict(direction='pre' if pre else 'post', L=length, P=p, T=slots, W=slots * p,
                    axis=axis, N=n, M=m, factors=cfg['factors'], use3=cfg['use3'],
                    ordinary_T=cfg['ordinary_T'], twiddle=phase,
                    max_slots_by_threads=max_by_threads,
                    max_slots_by_full_lds=max_by_full_lds,
                    complex_LDS_bytes=complex_bytes, scalar_LDS_bytes=scalar_bytes,
                    blocks=blocks, invalid_slots=invalid_slots,
                    first_pass_registers=len(first), last_pass_registers=len(last),
                    **check)
        results.append(item)
        family_rows.append(item)
    phase_modes = sorted({(r['twiddle']['base'], r['twiddle']['steps'], r['twiddle']['extra_lds_bytes'])
                          for r in family_rows})
    if pre:
        assert len(phase_modes) >= 2, (length, cfg['use3'], phase_modes)
        assert any(r['M'] > 262144 and r['twiddle']['base'] == 8 and r['twiddle']['steps'] == 3
                   for r in family_rows)
    assert {r['axis'] % 2 for r in family_rows} == {0, 1}
    assert any(r['invalid_slots'] > 0 for r in family_rows)
    assert max(r['M'] for r in family_rows) >= 262144
    catalog_checks.append(dict(direction='pre' if pre else 'post', L=length, P=p,
                               factors=cfg['factors'], cases=len(family_rows),
                               phase_modes=phase_modes, slots=sorted({r['T'] for r in family_rows}),
                               parity_and_tail_covered=True,
                               first_last_R_in_bounds_and_coordinate_bijections=True,
                               field_coordinate_identity=True,
                               max_M=max(r['M'] for r in family_rows)))

special = [r for r in results if r['direction'] == 'pre' and r['L'] == 1024
           and r['twiddle']['base'] == 8]
assert special and all(r['T'] == 4 and r['complex_LDS_bytes'] == 65536 for r in special)
proof = dict(complete=True, model_only=True, device_execution=False,
             production_changes=False, configurations=len(catalog), cases=len(results),
             source_pool_sha256=digest(pool), reused_model_sha256=digest(old),
             model_sha256=digest(Path(__file__)),
             correction='The previous model reserved 3072 LDS bytes unconditionally; this model calculates twiddles and resources per case. The earlier script and evidence are preserved.',
             notes=['Exact resource rule matches current generic full-LDS geometry before backend selection.',
                    'Scalar exchange is checked at the same T; this does not model a future policy that enlarges scalar T.',
                    'Tags prove coordinates, R indices and unique ownership, not FFT arithmetic or arbitrary GPU interleavings.',
                    'Mandatory publication/read-before-reuse barriers remain required.',
                    'Synthetic axes stress parity, tails, large M and twiddle transitions; actual CC plan selection is not tested.'],
             configuration_checks=catalog_checks, results=results)
out = W / 'generic-exact-coordinate-proof.json'
assert not out.exists()
out.write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: proof[k] for k in ('complete', 'configurations', 'cases', 'model_only', 'device_execution')}))
