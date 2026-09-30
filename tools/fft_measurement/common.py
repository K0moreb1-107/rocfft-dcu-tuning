"""Frozen EXP-123 measurement contract; no GPU work in this module."""
import csv
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
SIZES = (65536, 131072, 262144, 524288, 1048576)
FUNCS = ('z2z_1d', 'd2z_1d', 'z2d_1d')
ARMS = ('official', 'previous', 'candidate')
HEADER = 'func,N,batch,is_warmup,iters,plan_ms,first_ms,min_ms,mean_ms,max_ms,per_tf_ms,check,err_a,err_b'.split(',')
SOURCE_SHA = '849d011336601e6cffb1959e89590847e26160f7b3e256482a5eb37289e333da'
A100_SHA = '3b376eb69a77318ace8fbe537acfc7b3e82cdff1ea847f6177ed7ea82b27603b'
OFFICIAL_COMMIT = 'dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef'
OFFICIAL_SHA = '3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5'
REFERENCE = ROOT / 'results/reference/a100/A100_1d_32768_65536_131072_262144_524288_1048576.csv'
POLICY = 'EXP123-event-50-three-arm-8-v1'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def inside(path, root=ROOT):
    p = Path(path).resolve()
    require(p == root.resolve() or root.resolve() in p.parents, 'path outside approved workspace: ' + str(p))
    return p

def schedule():
    out = []
    for n in SIZES:
        for func in FUNCS:
            for round_no in range(1, 9):
                arms = ('official', 'previous', 'candidate', 'candidate', 'previous', 'official')
                if round_no % 2 == 0:
                    arms = arms[::-1]
                for slot, arm in enumerate(arms, 1):
                    out.append(dict(index=len(out), N=n, func=func, round=round_no, slot=slot, arm=arm))
    return out

def manifest(path):
    m = json.loads(Path(path).read_text(encoding='utf-8'))
    require(m.get('policy') == POLICY, 'wrong policy')
    require(re.fullmatch(r'EXP-\d{3,}', m.get('experiment', '')) is not None, 'explicit EXP identifier required')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', m.get('run_id', '')) is not None, 'invalid run_id')
    require(isinstance(m.get('acceptance'), str) and len(m['acceptance'].strip()) >= 10 and 'REPLACE' not in m['acceptance'], 'preregister experiment-specific acceptance criteria')
    require(m.get('gpu_arch') == 'gfx936', 'this validated profile requires gfx936; register a new profile for other hardware')
    require(set(m.get('arms', {})) == set(ARMS), 'exactly official, previous and candidate required')
    for arm in ARMS:
        a = m['arms'][arm]
        for field, length in (('source_commit', 40), ('library_sha256', 64)):
            require(re.fullmatch('[0-9a-f]{%d}' % length, a.get(field, '')) is not None, arm + ': invalid ' + field)
        for field in ('install', 'source_repo'):
            inside(a[field])
        require(isinstance(a.get('source_state'), str) and bool(a['source_state'].strip()) and 'REPLACE' not in a['source_state'], arm + ': explicit source-state description required')
        require(isinstance(a.get('build_provenance'), str) and len(a['build_provenance'].strip()) >= 10 and 'REPLACE' not in a['build_provenance'], arm + ': build/source provenance required')
    require(m['arms']['official']['source_commit'] == OFFICIAL_COMMIT, 'official source is fixed')
    require(m['arms']['official']['library_sha256'] == OFFICIAL_SHA, 'official library is fixed')
    return m

def read_rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        require(r.fieldnames == HEADER, 'invalid 14-column CSV: ' + str(path))
        rows = list(r)
    for row in rows:
        require(set(row) == set(HEADER) and all(v is not None for v in row.values()), 'malformed CSV row')
    return rows

def validate_row(row, n, func):
    require(row['func'] == func and int(row['N']) == n, 'case mismatch')
    require(int(row['batch']) == 1 and int(row['iters']) == 50 and int(row['is_warmup']) == 1, 'batch/iters/warmup mismatch')
    require(row['check'] == 'PASS', 'correctness did not PASS')
    v = {k: float(row[k]) for k in HEADER[5:11] + ['err_a', 'err_b']}
    require(all(math.isfinite(x) for x in v.values()), 'nonfinite measurement')
    require(v['plan_ms'] >= 0 and v['first_ms'] >= 0, 'negative diagnostic time')
    require(0 < v['min_ms'] <= v['mean_ms'] <= v['max_ms'], 'invalid timing order')
    require(math.isclose(v['per_tf_ms'], v['min_ms'], rel_tol=1e-6, abs_tol=1e-9), 'invalid per_tf_ms (original min/batch diagnostic)')
    require(0 <= v['err_a'] < 1e-9, 'err_a failed original strict threshold')
    if func == 'z2z_1d':
        require(0 <= v['err_b'] < 1e-9, 'err_b failed original strict threshold')
    else:
        require(v['err_b'] == -1, 'unexpected original real-transform err_b sentinel')
    return v

def reference(path=REFERENCE):
    require(sha(path) == A100_SHA, 'fixed A100 raw CSV hash mismatch')
    rows = read_rows(path)
    expected = [(n, f) for n in (32768,) + SIZES for f in FUNCS]
    require([(int(r['N']), r['func']) for r in rows] == expected, 'A100 reference cases/order mismatch')
    return {(n, f): validate_row(r, n, f)['mean_ms'] for r, (n, f) in zip(rows, expected) if n in SIZES}

def write_json(path, obj):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')
