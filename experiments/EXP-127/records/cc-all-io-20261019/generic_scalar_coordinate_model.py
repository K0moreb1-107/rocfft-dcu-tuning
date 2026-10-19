"""Pure coordinate model of existing generic real pair backends; no device run.

Reads the frozen generated function pool.  The model checks addresses and unique
owners, not floating point FFT arithmetic or arbitrary GPU interleavings.
"""
import hashlib
import json
import math
from pathlib import Path
import re

W = Path(__file__).resolve().parent
RX = re.compile(r'FFTKernel\((true|false),\s*\{([\d,]+)\},\s*(\d+),\s*(\d+),\s*\{(\d+),(\d+)\},\s*(true|false),\s*(true|false),\s*(true|false),')
KEY = re.compile(r'FMKey\((\d+), 0, rocfft_precision_double, (CS_KERNEL_STOCKHAM_BLOCK_CC|CS_KERNEL_STOCKHAM_BLOCK_RC), (NONE|TILE_ALIGNED|TILE_UNALIGNED),')


def mapped_row(axis, slots, slot, block):
    half = slots // 2
    p = block * half + slot % half
    if p >= (axis + 1) // 2:
        return axis
    if slot < half:
        return p
    return axis // 2 if p == 0 and axis % 2 == 0 else axis if p == 0 else axis - p


def peer(axis, slots, slot, row):
    if row == 0 or axis % 2 == 0 and row == axis // 2:
        return slot
    return slot + slots // 2 if slot < slots // 2 else slot - slots // 2


def io_map(length, p, factors, first):
    width = factors[0] if first else factors[-1]
    butterflies = length // width
    registers = max(math.ceil(length / r / p) * r for r in factors)
    out = []
    for lane in range(p):
        for h in range((butterflies + p - 1) // p):
            tid = lane + h * p
            if tid >= butterflies:
                continue
            for j in range(width):
                index = tid + j * butterflies
                if not first:
                    index = (tid // butterflies) * (width * butterflies) + tid % butterflies + j * butterflies
                reg = h * width + j
                assert reg < registers
                out.append((lane, reg, index))
    assert sorted(x[2] for x in out) == list(range(length))
    return out


def scalar_pre(length, p, slots, axis):
    """Existing pre field staging, with tags instead of numerical values."""
    m = length * axis
    blocks = ((axis + 1) // 2 + slots // 2 - 1) // (slots // 2)
    input_counts = bytearray(m + 1)
    for block in range(blocks):
        rows = [mapped_row(axis, slots, s, block) for s in range(slots)]
        real = {}
        imag_saved = {}
        imaginary = {}
        for slot, column in enumerate(rows):
            for a in range((length + 1) // 2):
                cell = a * slots + slot
                if column >= axis:
                    real[cell] = real[(length - 1 - a) * slots + slot] = None
                    imag_saved[slot, a, False] = imag_saved[slot, a, True] = None
                    continue
                k = a * axis + column
                cells = []
                if k == 0:
                    input_counts[0] += 1
                    input_counts[m] += 1
                    cells = [(slot, a, 0, False)]
                elif m % 2 == 0 and k == m // 2:
                    input_counts[k] += 1
                    cells = [(slot, a, k, False)]
                elif 0 < 2 * k < m:
                    input_counts[k] += 1
                    input_counts[m - k] += 1
                    other_a = (length - a - int(column != 0)) % length
                    cells = [(slot, a, k, False), (peer(axis, slots, slot, column), other_a, m - k, True)]
                for out_slot, out_a, tag, mirrored in cells:
                    at = out_a * slots + out_slot
                    assert at not in real
                    real[at] = tag
                    imag_saved[slot, a, mirrored] = tag
        if length % 2 == 0 and block == 0:
            assert m % 2 == 0
            input_counts[m // 2] += 1
            assert (length // 2) * slots not in real
            real[(length // 2) * slots] = m // 2
        assert len(real) == length * slots
        for slot, column in enumerate(rows):
            for a in range((length + 1) // 2):
                cell = a * slots + slot
                if column >= axis:
                    imaginary[cell] = imaginary[(length - 1 - a) * slots + slot] = None
                    continue
                k = a * axis + column
                canonical = 0 < 2 * k < m
                own_valid = k == 0 or canonical or length % 2 != 0 and m % 2 == 0 and k == m // 2
                if own_valid:
                    imaginary[cell] = imag_saved[slot, a, False]
                if canonical:
                    other_a = (length - a - int(column != 0)) % length
                    imaginary[other_a * slots + peer(axis, slots, slot, column)] = imag_saved[slot, a, True]
        if length % 2 == 0 and block == 0:
            imaginary[(length // 2) * slots] = m // 2
        assert imaginary == real
        for slot, column in enumerate(rows):
            for a in range(length):
                assert real[a * slots + slot] == (a * axis + column if column < axis else None)
    assert all(x == 1 for x in input_counts)
    return dict(input_elements=m + 1, output_complex_elements=m, field_coordinate_identity=True)


def scalar_post(length, p, slots, axis):
    """Existing real-save/imag-overwrite output staging with coordinate tags."""
    m = length * axis
    blocks = ((axis + 1) // 2 + slots // 2 - 1) // (slots // 2)
    output_counts = bytearray(m + 1)
    for block in range(blocks):
        rows = [mapped_row(axis, slots, s, block) for s in range(slots)]
        fields = {s * length + a: (r + axis * a if r < axis else None)
                  for s, r in enumerate(rows) for a in range(length)}
        saved = {}
        for slot, row in enumerate(rows):
            if row >= axis:
                continue
            for a in range((length + 1) // 2):
                k = row + axis * a
                if k == 0 or 0 < 2 * k < m:
                    saved[slot, a, False] = fields[slot * length + a]
                if 0 < 2 * k < m:
                    peer_cell = peer(axis, slots, slot, row) * length + (length - a - int(row != 0)) % length
                    saved[slot, a, True] = fields[peer_cell]
        midpoint_slot = 0 if length % 2 == 0 else slots // 2
        if block == 0 and m % 2 == 0:
            midpoint = fields[midpoint_slot * length + length // 2]
            assert midpoint == m // 2
            output_counts[m // 2] += 1
        # At the mandatory barriers all readers have saved the real field;
        # replacing real by imaginary preserves every coordinate's tag.
        imaginary = dict(fields)
        for slot, row in enumerate(rows):
            if row >= axis:
                continue
            for a in range((length + 1) // 2):
                k = row + axis * a
                if k == 0:
                    assert saved[slot, a, False] == imaginary[slot * length + a] == 0
                    output_counts[0] += 1
                    output_counts[m] += 1
                elif 0 < 2 * k < m:
                    peer_cell = peer(axis, slots, slot, row) * length + (length - a - int(row != 0)) % length
                    assert saved[slot, a, False] == imaginary[slot * length + a] == k
                    assert saved[slot, a, True] == imaginary[peer_cell] == m - k
                    output_counts[k] += 1
                    output_counts[m - k] += 1
    assert all(x == 1 for x in output_counts)
    return dict(input_complex_elements=m, output_elements=m + 1, field_coordinate_identity=True)


catalog = {}
raw = W / 'generated-pool-kernels.json'
for source in json.loads(raw.read_text()):
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
                            ordinary_T=int(t), use3=use3 == 'true', ordinary_half_lds=half == 'true')

results = []
for (scheme, length), cfg in sorted(catalog.items()):
    p = cfg['P']
    assert math.prod(cfg['factors']) == length
    first = io_map(length, p, cfg['factors'], True)
    last = io_map(length, p, cfg['factors'], False)
    slots = min(max(2, cfg['ordinary_T']), 1024 // p, (65536 - 3072) // (16 * length)) & ~1
    assert slots >= 2
    lower = max(3, 65536 // (2 * length) + 1)
    half = slots // 2
    axes = sorted({lower + i for i in range(5)} | {((lower + half - 1) // half + 1) * half - 1})
    pre = scheme.endswith('_CC')
    for axis in axes:
        n = 2 * length * axis
        assert n > 65536
        check = scalar_pre(length, p, slots, axis) if pre else scalar_post(length, p, slots, axis)
        results.append(dict(direction='pre' if pre else 'post', L=length, P=p, T=slots,
                            axis=axis, N=n, factors=cfg['factors'], **check))
proof = dict(complete=True, model_only=True, device_execution=False,
             production_changes=False, configurations=len(catalog), cases=len(results),
             source_pool_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
             model_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             notes=['Tags prove coordinate equality and unique user ownership, not FFT arithmetic.',
                    'Mandatory publication/read-before-reuse barriers remain required.',
                    'Fixed synthetic axes stress parity and tails; actual plan selection is not tested.',
                    'All configured first/last maps fit the existing register-array formula.'],
             results=results)
out = W / 'generic-scalar-coordinate-proof.json'
assert not out.exists()
out.write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: proof[k] for k in ('complete', 'configurations', 'cases', 'model_only', 'device_execution')}))
