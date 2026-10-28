"""Compare measured EXP125 with V6 z2d. CPU-only, no FFT source changes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT / 'experiments/EXP-128/scripts'))
import audit_exp125_cc_implementation as prior

RECORD = ROOT / 'experiments/EXP-128/records/exp125-power2-recheck-20261028'
ART = ROOT / 'experiments/EXP-128/artifacts/preflight/exp125-power2-recheck-20261028'
V5 = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-boundary-v5-validate-20261027'
V6 = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-validate-20261028'
G5 = ROOT / 'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027/default'
G6 = ROOT / 'experiments/EXP-128/artifacts/preflight/row-output-v6-20261028/default'
CASES = [(65536, 128, 256), (131072, 256, 256), (262144, 256, 512),
         (524288, 512, 512), (1048576, 1024, 512)]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized(text):
    return re.sub(r'_cc_local_v[0-9]+_', '_cc_local_vX_', text).strip()


def main():
    ART.mkdir(parents=True, exist_ok=True)
    RECORD.mkdir(parents=True, exist_ok=True)
    prior.ART = ART
    old = json.loads((ROOT / 'experiments/EXP-128/records/exp125-fusion-audit-20261027/exact-rtc-static-comparison.json').read_text())
    tasks = []
    for x in old['kernels']:
        if x['version'] == 'exp125' and x['func'] == 'z2d_1d':
            dest = ART / Path(x['source']).name
            dest.write_bytes(Path(x['source']).read_bytes())
            tasks.append(dict(version='exp125', N=x['N'], func=x['func'], position=x['position'],
                              name=x['name'], source=str(dest), evidence=x['evidence'],
                              evidence_sha256=x['evidence_sha256'], source_sha256=x['source_sha256'],
                              source_normalized_sha256=x['source_normalized_sha256']))
    assert len(tasks) == 10
    comparisons = []
    for n, c, q in CASES:
        for role in [4, 5]:
            a = G5 / f'{c}-{q}-{role}-0.cpp'
            b = G6 / a.name
            same = normalized(a.read_text()) == normalized(b.read_text())
            comparisons.append(dict(kind='complete_generator_output_v5_v6', N=n, C=c, Q=q, role=role,
                                    same_except_version=same, v5=str(a), v6=str(b),
                                    v5_sha256=digest(a.read_bytes()), v6_sha256=digest(b.read_bytes())))
            assert same, comparisons[-1]
        log6 = V6 / 'measurement-validation' / f'{n}-z2d_1d/metadata/rtc.txt'
        log5 = V5 / 'measurement-validation' / f'{n}-z2d_1d/metadata/rtc.txt'
        if log6.exists():
            chosen, label = log6, 'v6'
            if log5.exists():
                a = prior.sources(log5)
                b = prior.sources(log6)
                for role in [4, 5]:
                    va = [(k, v) for k, v in a.items() if f'_role{role}_' in k and '_CB' not in k]
                    vb = [(k, v) for k, v in b.items() if f'_role{role}_' in k and '_CB' not in k]
                    assert len(va) == len(vb) == 1, (n, role, list(a), list(b))
                    same = normalized(va[0][1]) == normalized(vb[0][1])
                    comparisons.append(dict(kind='actual_logged_v5_v6', N=n, role=role,
                                            same_except_version=same, v5_log=str(log5), v6_log=str(log6)))
                    assert same, comparisons[-1]
        else:
            assert log5.exists(), n
            chosen, label = log5, 'v6_equivalent_v5_log'
        tasks += prior.capture(label, n, 'z2d_1d', chosen)
    assert len(tasks) == 20
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(prior.compile_one, tasks))
    failures = [x for x in rows if not x['complete']]
    source_root = 'rocm-libraries-rocm-7.2.2/projects/rocfft/'
    cmd = ['git', 'diff', 'e9d515047c9c39c15f8b562f0f35df59a12ce616',
           'babe7b5379aa37892f56cd190de21190d1838f68', '--', source_root + 'library']
    diff = subprocess.check_output(cmd, cwd=ROOT)
    (RECORD / 'v5-to-v6-production.diff').write_bytes(diff)
    result = dict(complete=not failures, GPU_execution=False, production_source_modified=False,
                  exact_exp125_source='1d745ec17f516fa3bf1100c2fbd63baffa7e6d1d',
                  exact_v6_source='babe7b5379aa37892f56cd190de21190d1838f68',
                  evidence_policy='V6 logs for 65536/1048576; accepted V5 logs for other three, with full default-generated source equality except version for all ten kernels. Static ISA is not dynamic instruction counts or a measured timing attribution.',
                  kernels=rows, comparisons=comparisons, failures=failures)
    out = RECORD / 'current-vs-exp125-static.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for x in rows:
        print(json.dumps(dict(version=x['version'], N=x['N'], position=x['position'],
                              resources=x.get('resources'), counts=x.get('static_instruction_groups'))))
    print(json.dumps(dict(complete=not failures, kernels=len(rows), comparisons=len(comparisons), output=str(out))))
    assert not failures


if __name__ == '__main__':
    main()
