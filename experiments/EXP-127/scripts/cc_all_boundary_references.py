"""Independent whole-transform identities for isolated CC real boundaries.

No production real-pair formulas, slot mapping or Stockham code is reused.
These are numerical fixtures, not default full-plan or performance evidence.
"""
import hashlib
import json
from pathlib import Path
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(case, callbacks=False, scale=1.0):
    pre = case['direction'] == 'pre'
    c, q = (case['L'], case['axis']) if pre else (case['axis'], case['L'])
    m = c * q
    rng = np.random.default_rng(2026101900 + 17 * c + 31 * q + int(pre))
    size = m + int(pre)
    data = rng.standard_normal(size) + 1j * rng.standard_normal(size)
    data = data.astype(np.complex128)
    data[0] += 3
    data[-1] += 2
    if pre:
        data[[0, -1]] = data[[0, -1]].real
        spectrum = data.copy()
        if callbacks:
            index = np.arange(size)
            imaginary = (index % 11) * .015625
            imaginary[[0, -1]] = 0
            spectrum = spectrum * .75 + (index % 7) * .03125 + 1j * imaginary
        # Unnormalized N-point inverse, packed into M complex time samples.
        real_time = np.fft.irfft(spectrum, n=2*m) * (2*m)
        packed_time = real_time[0::2] + 1j * real_time[1::2]
        packed_spectrum = np.fft.fft(packed_time) / m
        expected = np.fft.ifft(packed_spectrum.reshape(c, q), axis=0) * c
        expected *= np.exp(2j * np.pi * np.arange(c)[:, None] * np.arange(q)[None, :] / m)
        expected = expected.reshape(-1) * scale
    else:
        row_spectra = np.fft.fft(data.reshape(c, q), axis=1)
        packed_spectrum = row_spectra.T.copy().reshape(-1)
        packed_time = np.fft.ifft(packed_spectrum)
        real_time = np.empty(2*m, dtype=np.float64)
        real_time[0::2], real_time[1::2] = packed_time.real, packed_time.imag
        expected = np.fft.rfft(real_time) * scale
        if callbacks:
            expected = expected * 1.125 + (np.arange(m+1) % 5) * .015625
    return data, np.ascontiguousarray(expected, dtype=np.complex128)


def references(model, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    metadata, lines, covered = [], [], set()
    for index, case in enumerate(model['results']):
        key = case['direction'], case['L']
        variants = [(False, 1.0)]
        if key not in covered:
            variants.append((True, .375))
            covered.add(key)
        for callbacks, scale in variants:
            ident = '%s%d_N%d_%d%s' % (case['direction'],case['L'],case['N'],index,
                                        '_callback_scaled' if callbacks else '')
            original, expected = values(case, callbacks, scale)
            source, target = folder/(ident+'.input.bin'), folder/(ident+'.expected.bin')
            original.tofile(source)
            expected.tofile(target)
            pre = case['direction'] == 'pre'
            c, q = (case['L'], case['axis']) if pre else (case['axis'], case['L'])
            phase = case['twiddle']
            lines.append(' '.join(map(str,[ident,case['N'],int(pre),c,q,case['P'],case['T'],
                         phase['base'],phase['steps'],int(callbacks),scale,source,target])))
            metadata.append(dict(id=ident,case_index=index,N=case['N'],C=c,Q=q,pre=pre,
                callbacks=callbacks,scale=scale,inputs={str(source):sha(source),str(target):sha(target)}))
    assert len(covered)==model['configurations']==54
    manifest=folder/'manifest.txt'
    manifest.write_text('\n'.join(lines)+'\n')
    (folder/'references.json').write_text(json.dumps(dict(numpy=np.__version__,cases=metadata),indent=2))
    return manifest, metadata
