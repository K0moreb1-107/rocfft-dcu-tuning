"""Produce traceable local analysis tables from saved results and exact source snapshots."""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / 'work/EXP128-implementation-20261021/remote'
REC = REMOTE / 'experiments/EXP-128/records/exp125-fusion-audit-20261027'
OUT = ROOT / 'outputs/EXP128-与EXP125融合实现对比-20261027'
FUSED = {65536, 131072, 262144, 524288, 1048576}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def table(name, rows):
    assert rows
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def divisor_table(path):
    s = path.read_text(encoding='utf-8')
    match = re.search(r'NodeFactory::Map1DLength const NodeFactory::map1DLengthDouble\s*=\s*\{(.*?)\n\};', s, re.S)
    assert match
    s = re.sub(r'/\*.*?\*/|//[^\n]*', '', match[1], flags=re.S)
    items = [tuple(map(int, p)) for p in re.findall(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}', s)]
    assert len(items) == len(dict(items))
    return dict(items)


def group(n, old):
    return '旧已融合' if n in FUSED else '原CC未融合' if n // 2 in old else '原非CC'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = read(REC / 'source-manifest.json')
    for x in manifest:
        p = REMOTE / x['path']
        assert p.stat().st_size == x['bytes'] and sha(p) == x['sha256'], str(p)
    old = divisor_table(REC / 'source/exp125/library/src/node_factory.cpp')
    new = divisor_table(REC / 'source/v4/library/src/node_factory.cpp')
    v3 = divisor_table(REC / 'source/v3/library/src/node_factory.cpp')
    assert all(new[k] == v for k, v in old.items()) and new == v3
    old_cc = {int(r['N']) for r in csv.DictReader((ROOT / 'outputs/EXP128-原CC尺寸加速比-20261023/原CC全部64个方向组合.csv').open(encoding='utf-8-sig'))}
    sources = {}
    groups = []
    power_rows = []
    classified = []
    cases = {}
    for version, job, directory in [('v3', 960099, 'EXP128-通用行端简化性能960099'), ('v4', 979273, 'EXP128-双寄存器分组性能979273')]:
        path = ROOT / 'outputs' / directory / 'all-samples-and-statistics.json'
        rows = read(path)
        assert len(rows) == 388 and len({r['N'] for r in rows}) == 194
        cc = {r['N'] for r in rows if r['N'] // 2 in old}
        assert cc == old_cc and len(cc) == 32
        sources[version] = dict(job=job, path=str(path), sha256=sha(path), arms=read(path.with_name('audit-and-statistics.json'))['arms'])
        cases[version] = rows
        for r in rows:
            n = r['N']
            for arm, samples in r['samples_us'].items():
                assert len(samples) == 30 and all(math.isfinite(t) and t > 0 for t in samples)
                assert abs(statistics.median(samples) - r[arm + '_us']) < 1e-8
            assert abs(r['baseline_us'] / r['candidate_us'] - r['speedup_baseline']) < 1e-12
            assert new[n // 2] == r['C'] and n == 2 * r['C'] * r['Q']
            kind = group(n, old)
            item = dict(version=version, source_job=job, N=n, type=r['type'], C=r['C'], Q=r['Q'],
                        comparison_group=kind, EXP125_us=r['baseline_us'], current_us=r['candidate_us'],
                        speedup=r['speedup_baseline'], assessment=r['assessment_baseline'],
                        EXP125_p25_us=r['baseline_p25_us'], EXP125_p75_us=r['baseline_p75_us'],
                        current_p25_us=r['candidate_p25_us'], current_p75_us=r['candidate_p75_us'])
            classified.append(item)
            if n >= 65536 and n & (n-1) == 0:
                power_rows.append(item)
        for kind in ['旧已融合', '原CC未融合', '原非CC']:
            for func in ['z2d', 'd2z']:
                subset = [r for r in rows if group(r['N'], old) == kind and r['type'] == func]
                values = [r['speedup_baseline'] for r in subset]
                groups.append(dict(version=version, job=job, comparison_group=kind, type=func,
                                   cases=len(subset), median_of_case_speedups=statistics.median(values),
                                   faster=sum(x > 1 for x in values), same=sum(x == 1 for x in values), slower=sum(x < 1 for x in values),
                                   clear_faster=sum(r['assessment_baseline']=='更快' for r in subset),
                                   clear_slower=sum(r['assessment_baseline']=='更慢' for r in subset)))
    table('默认性能按原路径分组.csv', groups)
    table('默认二次幂逐项对照.csv', power_rows)
    table('全部默认尺寸与原路径.csv', classified)

    grid = list(csv.DictReader((ROOT / 'outputs/EXP128-v3行列热力图补全-20261027/补测84格双向结果.csv').open(encoding='utf-8-sig')))
    grid_pow2 = [dict(r) for r in grid if int(r['N']) in FUSED]
    table('指定分解二次幂补测.csv', grid_pow2)
    grid_counts = {}
    for func in ['z2d','d2z']:
        ratios = [r['speedup_baseline'] for r in cases['v3'] if r['N'] in FUSED and r['type']==func]
        ratios += [float(r['speedup_baseline']) for r in grid_pow2 if r['type']==func]
        grid_counts[func] = dict(geometries=len(ratios), faster=sum(x>1 for x in ratios), same=sum(x==1 for x in ratios), slower=sum(x<1 for x in ratios))

    isa = read(REC / 'exact-rtc-static-comparison.json')
    assert isa['complete'] and isa['exact_logged_sources'] and len(isa['kernels']) == 58
    assert all(x['resources']['vgpr_spill_count']==0 for x in isa['kernels'])
    assert all(x['resources']['private_segment_fixed_size']==0 for x in isa['kernels'])
    assert all(not any('swappc' in k or 'call' in k for k in x['mnemonics']) for x in isa['kernels'])
    table('实际源码离线编译58项.csv', [dict(version=x['version'], N=x['N'], type=x['func'][:3], stage=x['position'],
                                        **x['resources'], **x['static_instruction_groups'],
                                        first_barrier_wait_all=x['static_wait_all_before_first_barrier'],
                                        source_sha256=x['source_sha256'], evidence=x['evidence']) for x in isa['kernels']])
    prototypes = read(REC / 'offline-prototypes.json')
    assert prototypes['complete'] and len(prototypes['compiles']) == 26
    table('源码副本原型26项.csv', [dict(N=x['N'], type=x['func'][:3], C=x['C'], Q=x['Q'], variant=x['variant'],
                                   **x['resources'], **x['static_instruction_groups'],
                                   first_barrier_wait_all=x['static_wait_all_before_first_barrier']) for x in prototypes['compiles']])

    # Count source-level large-phase lookup evaluations, not hardware transactions.
    lookup_rows = []
    for n in sorted(FUSED):
        col = next(x for x in isa['kernels'] if (x['version'], x['N'], x['func'], x['position']) == ('exp125',n,'d2z_1d',0))
        row = next(x for x in isa['kernels'] if (x['version'], x['N'], x['func'], x['position']) == ('v4',n,'d2z_1d',1))
        c, q = map(int,re.search(r'_C(\d+)_Q(\d+)_',row['name']).groups())
        ct = int(re.search(r'_tpt_(\d+)_', col['name'])[1])
        last = int(re.search(r'_factors_([0-9_]+)_wgs_',col['name'])[1].split('_')[-1])
        recurrent = c in (256,512,1024) and last in (4,8)
        before = q * ct * (1 + c//last//ct) if recurrent else c*q
        after = (c-1)*q
        base, steps = map(int,re.search(r'_twdbase(\d+)_(\d+)step',col['name']).groups())
        lookup_rows.append(dict(N=n,C=c,Q=q,EXP125_recurrence=recurrent,EXP125_phase_period=n//2,
                                current_phase_period=n,EXP125_lookup_calls=before,current_lookup_calls=after,
                                call_ratio=after/before,EXP125_table_base=base,EXP125_table_steps=steps,
                                current_table_base=8,current_table_steps=math.ceil((n-1).bit_length()/8),
                                EXP125_padded_z2d_pitch=q+8,current_z2d_pitch=q,
                                saved_z2d_main_signal_bytes=32*c,
                                saved_z2d_temporary_capacity_bytes=128*c))
    table('大相位查询及中间布局成本模型.csv',lookup_rows)

    oldrec = REMOTE / 'experiments/EXP-128/records/regression-955252-20261022/analysis-957127'
    counter = read(oldrec/'counter-summary.json')
    pmc = []
    wanted = ['number of L2 cache read requests','shared memory operation','shared memory bank conflict',
              'L1 cache unit is stalled','vgpr count','scratch size','shared memory size']
    for x in counter['pmc']:
        if x['N'] not in FUSED or x['arm'] not in ('baseline','candidate'):
            continue
        for k in x['kernels']:
            pmc.append(dict(N=x['N'],type=x['func'][:3],version='EXP125' if x['arm']=='baseline' else '旧通用第二版',
                            stage=k['position'],mode=x['mode'],**{key:k['fields'][key]['median'] for key in wanted if key in k['fields']},
                            evidence=x['evidence'],evidence_sha256=x['sha256']))
    table('已有二次幂计数器证据.csv', pmc)
    applicability = read(REC/'previous-diagnostic-column-applicability.json')
    assert applicability['complete'] and len(applicability['comparisons'])==10
    for name in ['exact-rtc-static-comparison.json','offline-prototypes.json','source-manifest.json','previous-diagnostic-column-applicability.json']:
        (OUT/name).write_bytes((REC/name).read_bytes())
    summary = dict(complete=True,production_fft_modified=False,new_GPU_jobs_submitted=False,
                   versions=sources,default_groups=groups,grid_power2_counts=grid_counts,
                   source_snapshots=len(manifest),source_snapshot_bytes=sum(x['bytes'] for x in manifest),
                   old_CC_table_entries=len(old),new_CC_table_entries=len(new),old_entries_preserved=True,
                   ISA_sources=58,ISA_spills=0,offline_prototypes=26,prototype_model=prototypes['model'],
                   large_phase_lookup_model=lookup_rows,
                   old_PMC_scope='957127: EXP125 vs v2; 10 column sources identical to v4 except names. Historical row counters are not current-v4 counters.',
                   interpretation='Separate batch-matched speedups, static compilation, source-level work model, and device counters. No new device speedup is asserted for prototypes.')
    save('核对与证据口径.json',summary)
    print(json.dumps(dict(complete=True,source_files=len(manifest),groups=len(groups),ISA=58,prototypes=26,
                          grid_counts=grid_counts,lookup=lookup_rows,output=str(OUT)),ensure_ascii=False))


if __name__=='__main__':main()
