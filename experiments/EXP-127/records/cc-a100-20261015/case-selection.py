import csv
import hashlib
import json
import re
from pathlib import Path

WORK = Path(__file__).resolve().parent
ctx = json.loads((WORK / 'context.json').read_text(encoding='utf-8'))
checkpoint = json.loads((WORK / 'checkpoint-receipt.json').read_text(encoding='utf-8'))
source = WORK / 'before/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src'
factory = (source / 'node_factory.cpp').read_text(encoding='utf-8')
table = factory[factory.index('NodeFactory::Map1DLength const NodeFactory::map1DLengthDouble'):]
table = table[:table.index('\n};')]
table = '\n'.join(line.split('//', 1)[0] for line in table.splitlines())
cc = {int(n): int(c) for n, c in re.findall(r'\{(\d+),\s*(\d+)\}', table)}
reference_path = WORK / 'before/results/reference/a100/test_fft_261012/medians.csv'
reference = {(int(r['N']), r['func']): r for r in csv.DictReader(reference_path.open(encoding='utf-8'))}


def factors(n):
    result = {}
    p = 2
    while p * p <= n:
        while n % p == 0:
            result[p] = result.get(p, 0) + 1
            n //= p
        p += 1
    if n > 1:
        result[n] = result.get(n, 0) + 1
    return result


allowed = {2, 3, 7, 11, 13, 17}
eligible = sorted({n for n, f in reference if n > 65536 and n % 2 == 0
                   and set(factors(n)) <= allowed})
matched = [n for n in eligible if n // 2 in cc]
assert matched == [120224, 131072, 142688, 262144, 524288, 1048576]
additional = [101088, 123904, 129024, 166698, 596288, 702464]
sizes = sorted(matched + additional)
assert len(set(sizes)) == 12
geometries = {}
cases = []
for n in sizes:
    assert n > 65536 and n % 2 == 0 and set(factors(n)) <= allowed and n // 2 in cc
    c, q = cc[n // 2], n // 2 // cc[n // 2]
    assert c * q == n // 2
    geometries[str(n)] = dict(C=c, Q=q, factors=factors(n), matched_a100=n in matched,
                              implementation='EXP125 power-of-two' if n & (n - 1) == 0 else 'EXP126 generic CC',
                              parity=('even' if c % 2 == 0 else 'odd') + '/' + ('even' if q % 2 == 0 else 'odd'))
    for func in ('d2z_1d', 'z2d_1d'):
        row = reference.get((n, func))
        cases.append(dict(N=n, func=func, C=c, Q=q,
                          a100_median_ms=row['median_ms'] if row else None,
                          a100_source_file=row['source_file'] if row else None,
                          a100_source_row=int(row['source_row']) if row else None))
coverage = dict(schema='cc-a100-followup-v1', experiment='EXP-127',
                checkpoint_commit=checkpoint['commit'], source_tree=checkpoint['source_tree'],
                candidate_build_commit='2ef393567f2637f356bfc75db78bce53ad0f42fd',
                stable_unchanged=checkpoint['stable_refs_unchanged'],
                factor_interpretation='4 is included in powers of 2; use exactly {2,3,7,11,13,17}; exclude 5',
                matched_A100_sizes=matched, additional_CC_sizes=additional,
                eligible_A100_sizes=eligible,
                excluded_non_CC_A100_sizes=[n for n in eligible if n not in matched],
                geometries=geometries, cases=cases, size_count=12, case_count=24,
                arms=['official', 'candidate'], processes=48, event_iterations=50,
                event_samples=2400, warmups=3, batch=1, precision='double', placement='out-of-place',
                plan_selection='default; no forced registers/LDS/solution overrides',
                validation='same accepted candidate installation; strict frozen per-process correctness during measurement; CPU production-plan preflight',
                a100_dataset='results/reference/a100/test_fft_261012',
                a100_median_table_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                a100_conditions=dict(warmups=10, event_iterations=30),
                a100_comparison='cross-device reference only; conditions differ; missing sizes stay blank',
                baseline='original official ROCm 7.2.2 default plan; any decomposition difference is part of the measured change',
                automatic_promotion=False, stop_after_submission=True)
(WORK / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(WORK / 'matrix.txt').write_text('\n'.join(f'{row["N"]} {0 if row["func"] == "d2z_1d" else 1} {row["C"]} {row["Q"]}' for row in cases) + '\n', encoding='utf-8')
print(json.dumps({'sizes': sizes, 'matched_a100': matched, 'additional': additional,
                  'geometries': geometries, 'processes': 48, 'event_samples': 2400}, ensure_ascii=False))
