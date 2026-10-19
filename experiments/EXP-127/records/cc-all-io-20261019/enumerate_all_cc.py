"""Read frozen facts and enumerate all DP CC configs; no remote actions."""
import collections
import datetime
import fractions
import hashlib
import json
import math
import pathlib
import re

W = pathlib.Path(__file__).resolve().parent
ROOT = W / 'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src'
FROZEN = W.parent / 'CC-fusion-optimization-20261015/evidence/sources/library/src'
LEGACY = {65536: (128, 256), 131072: (256, 256),
          262144: (256, 512), 524288: (512, 512), 1048576: (1024, 512)}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def twiddle(m, use3):
    if m <= 0:
        raise ValueError('positive complex length required')
    base = min(6, max(4, ((m - 1).bit_length() + 2) // 3)) if use3 and m <= 262144 else 8
    steps = 0
    while (1 << (base * steps)) < m:
        steps += 1
    legal = (base == 8 and steps <= 3) or (base < 8 and steps == 3)
    return dict(base=base, steps=steps, legal=legal,
                extra_lds_bytes=3 * (1 << base) * 16 if base < 8 and steps else 0)


def backend(pre, cfg, t, base, steps):
    f, p = cfg['factors'], cfg['P']
    key = (tuple(f), p, t)
    if pre:
        if base == 8 and steps in (2, 3) and key in {
            ((4, 10, 4), 16, 12), ((13, 16), 16, 8),
            ((6, 7, 8), 56, 6), ((8, 8, 8), 64, 4),
            ((8, 8, 4, 4), 64, 4)}:
            return 'direct_complex'
        if base in (6, 8) and steps == 3 and key == ((17, 17), 17, 6):
            return 'direct_complex_phase_at_store'
    elif key in {((8, 8, 8), 128, 4), ((11, 11, 11), 121, 2)}:
        return 'direct_complex'
    return 'staged_complex'


def paired(cfg, pre, m):
    tw = twiddle(m, cfg['use_3steps_large_twd']) if pre else dict(base=0, steps=0, legal=True, extra_lds_bytes=0)
    limit = min(1024 // cfg['P'], (65536 - tw['extra_lds_bytes']) // 16 // cfg['length'])
    t = min(max(2, cfg['ordinary_T']), limit) & ~1
    return dict(T=t, W=t * cfg['P'],
                LDS_bytes=t * cfg['length'] * 16 + tw['extra_lds_bytes'],
                resource_max_slots=limit, minimum_two_applied=cfg['ordinary_T'] < 2,
                odd_slot_rounded_down=(min(max(2, cfg['ordinary_T']), limit) % 2 == 1),
                resource_reduction=limit < max(2, cfg['ordinary_T']),
                fusion_resource_legal=t >= 2 and tw['legal'],
                twiddle=tw, current_backend=backend(pre, cfg, t, tw['base'], tw['steps']))


def pass_map(length, p, width, first):
    b = length // width
    out = []
    for lane in range(p):
        for h in range((b + p - 1) // p):
            tid = lane + h * p
            if tid >= b:
                continue
            for j in range(width):
                index = tid + j * b if first else (tid // b) * (width * b) + tid % b + j * b
                out.append(index)
    assert sorted(out) == list(range(length))
    return dict(butterflies=b, height=str(fractions.Fraction(b, p)),
                p_divides_butterflies=b % p == 0,
                initial_lanes_masked=p > b,
                final_partial_work=b > p and b % p != 0,
                coordinate_bijection=True)


raw = json.loads((W / 'generated-pool-kernels.json').read_text())
catalog = {'columns': {}, 'rows': {}}
records = []
rx = re.compile(r'FFTKernel\((true|false),\s*\{([\d,]+)\},\s*(\d+),\s*(\d+),\s*\{(\d+),(\d+)\},\s*(true|false),\s*(true|false),\s*(true|false),')
krx = re.compile(r'FMKey\((\d+), 0, rocfft_precision_double, (CS_KERNEL_STOCKHAM_BLOCK_CC|CS_KERNEL_STOCKHAM_BLOCK_RC), (NONE|TILE_ALIGNED|TILE_UNALIGNED),')
for source in raw:
    for r in source['entries']:
        z = rx.search(r['definition'])
        k = krx.search(r['entry'])
        assert z and k, r
        use3, fs, t, w, p, p2, half, direct, aot = z.groups()
        length, scheme, tile = k.groups()
        c = dict(length=int(length), factors=list(map(int, fs.split(','))), P=int(p),
                 ordinary_T=int(t), ordinary_W=int(w), half_lds=half == 'true',
                 ordinary_direct_to_from_reg=direct == 'true',
                 use_3steps_large_twd=use3 == 'true', aot_rtc=aot == 'true',
                 scheme=scheme, tile_type=tile,
                 registered_pool_lds_tier=65536,
                 generated_definition=r['definition'], generated_entry=r['entry'],
                 source=source['path'], source_line=r['line'], source_sha256=source['sha256'])
        assert math.prod(c['factors']) == c['length'] and int(p2) == 0
        assert c['ordinary_W'] == c['ordinary_T'] * c['P']
        c['ordinary_data_LDS_bytes'] = c['ordinary_T'] * c['length'] * 16 // (2 if c['half_lds'] else 1)
        c['first_pass'] = pass_map(c['length'], c['P'], c['factors'][0], True)
        c['last_pass'] = pass_map(c['length'], c['P'], c['factors'][-1], False)
        if scheme.endswith('_CC'):
            assert tile == 'NONE' and c['length'] not in catalog['columns']
            catalog['columns'][c['length']] = c
        else:
            catalog['rows'].setdefault(c['length'], {})[tile] = c
        records.append(c)

for n, variants in catalog['rows'].items():
    assert set(variants) == {'TILE_ALIGNED', 'TILE_UNALIGNED'}
    a, b = variants['TILE_ALIGNED'], variants['TILE_UNALIGNED']
    for key in ('factors', 'P', 'ordinary_T', 'ordinary_W', 'half_lds', 'use_3steps_large_twd'):
        assert a[key] == b[key], (n, key)

for kind, cfg_name in [('columns', 'config_sbcc.py'), ('rows', 'config_sbrc.py')]:
    config_source = (ROOT / 'device/kernels/configs' / cfg_name).read_text()
    configured_lengths = set(map(int, re.findall(r'NS\(length=(\d+)', config_source)))
    assert configured_lengths == set(catalog[kind]), (kind, configured_lengths, set(catalog[kind]))

text = (ROOT / 'node_factory.cpp').read_text()
begin = text.index('NodeFactory::Map1DLength const NodeFactory::map1DLengthDouble')
end = text.index('\n};', begin)
stripped = re.sub(r'//[^\n]*', '', text[begin:end])
entries = re.findall(r'\{(\d+),\s*(\d+)\}', stripped)
mapping = {int(n): int(c) for n, c in entries}
assert len(mapping) == len(entries)
all_mapped = []
for m, c in sorted(mapping.items()):
    assert m % c == 0 and c in catalog['columns'] and m // c in catalog['rows'], (m, c)
    q = m // c
    n = 2 * m
    cc, rc = catalog['columns'][c], catalog['rows'][q]['TILE_ALIGNED']
    pre, post = paired(cc, True, m), paired(rc, False, m)
    old = n in LEGACY
    if old:
        assert LEGACY[n] == (c, q)
    row = dict(M=m, N=n, C=c, Q=q,
               in_user_N_scope=n > 65536,
               old_five_special_case=old,
               default_CC_decomposition_static=True,
               plan_evidence='frozen default map + generated function pool; no new production plan execution',
               pre_generic=pre, post_generic=post,
               real_z2d_route='legacy_folded_columns_plus_local_real_rows' if old else 'generic_CC' if n > 65536 else 'below_requested_N_scope',
               real_d2z_route='legacy_paired_post_rows' if old else 'generic_CC' if n > 65536 else 'below_requested_N_scope')
    all_mapped.append(row)

potential = []
for c, cc in sorted(catalog['columns'].items()):
    for q, rcs in sorted(catalog['rows'].items()):
        m, n = c * q, 2 * c * q
        if n <= 65536:
            continue
        if m in mapping and mapping[m] != c:
            status = 'conflicts_existing_default_map'
        elif m in mapping:
            status = 'existing_default_map'
        else:
            status = 'missing_map_legal_kernel_pair'
        potential.append(dict(N=n, M=m, C=c, Q=q, map_status=status,
                              existing_map_C=mapping.get(m), old_five_special_case=n in LEGACY,
                              pre=paired(cc, True, m),
                              post=paired(rcs['TILE_ALIGNED'], False, m)))

missing_by_m = collections.defaultdict(list)
for r in potential:
    if r['map_status'] == 'missing_map_legal_kernel_pair':
        missing_by_m[r['M']].append(r['C'])
for r in potential:
    r['other_missing_map_C_for_same_M'] = [c for c in missing_by_m.get(r['M'], []) if c != r['C']]

for kind, items in catalog.items():
    for length, value in items.items():
        cfg = value if kind == 'columns' else value['TILE_ALIGNED']
        pre = kind == 'columns'
        matches = [r for r in all_mapped if r['in_user_N_scope'] and r['C' if pre else 'Q'] == length]
        generic = [r for r in matches if not r['old_five_special_case']]
        potentials = [r for r in potential if r['C' if pre else 'Q'] == length]
        candidate_new = [r for r in potentials if r['map_status'] == 'missing_map_legal_kernel_pair'
                         and r['pre' if pre else 'post']['fusion_resource_legal']]
        cfg['mapped_default_real_N'] = [r['N'] for r in matches]
        cfg['mapped_default_generic_real_N'] = [r['N'] for r in generic]
        cfg['mapped_default_generic_N_count'] = len(generic)
        cfg['mapped_default_generic_fewer_than_five'] = len(generic) < 5
        cfg['legacy_N'] = [r['N'] for r in matches if r['old_five_special_case']]
        cfg['admissible_new_map_N_without_conflicts'] = sorted(r['N'] for r in candidate_new)
        cfg['total_generic_default_plus_missing_count_without_replacing_maps'] = len(generic) + len(candidate_new)
        cfg['five_sizes_possible_without_replacing_map'] = len(generic) + len(candidate_new) >= 5
        cfg['paired_geometry_over_existing_default_generic_N'] = [dict(N=r['N'], **r['pre_generic' if pre else 'post_generic']) for r in generic]
        examples = [r['pre' if pre else 'post'] for r in potentials]
        unique = {json.dumps(x, sort_keys=True): x for x in examples}
        cfg['paired_geometry_for_all_catalog_pairs_in_scope'] = list(unique.values())
        cfg['nominal_pair_geometry_without_an_actual_map'] = (
            None if pre else paired(cfg, False, 32769))
        cfg['large_twiddle_policy_in_requested_scope'] = (
            ('N<=524288: base6/3step with 3072 extra LDS; N>524288: base8/3step, up to encoding limit'
             if cfg['use_3steps_large_twd'] else
             'N<=131072: base8/2step; N>131072: base8/3step, up to encoding limit')
            if pre else 'No large-twiddle multiplication; strategy selection sees base0/step0; RTC normal template base8/step0')
        cfg['direct_IO_capacity_model'] = dict(
            first_pass_coordinate_bijection=cfg['first_pass']['coordinate_bijection'],
            last_pass_coordinate_bijection=cfg['last_pass']['coordinate_bijection'],
            requires_effective_work_masks=True,
            requires_zero_unused_initial_registers=True,
            resource_failures_for_catalog_pairs_in_scope=sum(not x['fusion_resource_legal'] for x in examples),
            evidence='coordinate/resource model only; does not prove generated code or device correctness/performance')

summary = dict(
    column_configs=len(catalog['columns']), row_lengths=len(catalog['rows']),
    row_tile_configs=sum(len(x) for x in catalog['rows'].values()),
    total_registered_DP_CC_RC_configs=len(records),
    mapped_decompositions=len(all_mapped),
    mapped_decompositions_real_N_gt65536=sum(r['in_user_N_scope'] for r in all_mapped),
    generic_mapped_decompositions_real_N_gt65536=sum(r['in_user_N_scope'] and not r['old_five_special_case'] for r in all_mapped),
    legacy_five_sizes=len(LEGACY), legacy_in_strict_requested_scope=sum(n > 65536 for n in LEGACY),
    potential_catalog_pairs_real_N_gt65536=len(potential),
    map_status_counts=dict(collections.Counter(r['map_status'] for r in potential)),
    distinct_missing_M=len(missing_by_m),
    missing_M_with_alternative_decomposition_choices=sum(len(v) > 1 for v in missing_by_m.values()),
    currently_mapped_generic_column_lengths=sorted({r['C'] for r in all_mapped if r['in_user_N_scope'] and not r['old_five_special_case']}),
    currently_mapped_generic_row_lengths=sorted({r['Q'] for r in all_mapped if r['in_user_N_scope'] and not r['old_five_special_case']}),
    column_configurations_fewer_than_five_default_generic_N=[l for l, c in catalog['columns'].items() if c['mapped_default_generic_N_count'] < 5],
    row_configurations_fewer_than_five_default_generic_N=[l for l, c in catalog['rows'].items() if c['TILE_ALIGNED']['mapped_default_generic_N_count'] < 5],
    columns_unable_to_supply_five_N_even_with_nonconflicting_missing_maps=[l for l, c in catalog['columns'].items() if not c['five_sizes_possible_without_replacing_map']],
    rows_unable_to_supply_five_N_even_with_nonconflicting_missing_maps=[l for l, c in catalog['rows'].items() if not c['TILE_ALIGNED']['five_sizes_possible_without_replacing_map']],
    no_resource_rejection_for_any_catalog_pair_in_scope=all(r[k]['fusion_resource_legal'] for r in potential for k in ('pre', 'post')),
    ordinary_one_slot_row_lengths=[l for l, c in catalog['rows'].items() if c['TILE_ALIGNED']['ordinary_T'] == 1],
    odd_ordinary_T_column_lengths=sorted(l for l, c in catalog['columns'].items() if c['ordinary_T'] % 2),
    odd_ordinary_T_row_lengths=sorted(l for l, c in catalog['rows'].items() if c['TILE_ALIGNED']['ordinary_T'] % 2),
)

data = dict(
    complete=True, read_only_remote=True, compilation=False, device_execution=False,
    date='2026-10-19', frozen_source_commit='3a668d26fd4f76dea08422274256d4830d83a0d0',
    device_model=dict(arch='gfx936', sharedMemPerBlock=65536, maxThreadsPerBlock=1024, warpSize=64),
    scope=dict(precision='double', dimensions=1, batch=1, placement='out_of_place', unit_stride=True,
               no_user_offsets=True, N_min_exclusive=65536, source_CC_fusion=True,
               scalar_capacity=False, external_solution_map=False),
    evidence_limits=[
        'Generated function pool metadata is taken from the already validated on-callback-fix build; all 8 generated file hashes retained.',
        'Default decomposition is static source derivation on gfx936 under the scope above; no newly executed production plan or GPU dispatch.',
        'Existing map includes sizes below scope for completeness; strict N>65536 generic coverage excludes all five legacy cases.',
        'Missing-map pairs are catalog support candidates only; no map has been added and no candidate is counted as an actual default plan.',
        'Missing-map candidates can share the same M with different C; only one direction can be the default. Per-config candidate counts are individually feasible, not a proof that every count can be achieved jointly.',
        'Index bijections and capacity do not establish arbitrary GPU synchronization or numeric FFT correctness.',
        'This does not enumerate runtime tuned solution-map kernels with user-supplied factors/P/T; those are separately gated by noSolution.'],
    summary=summary, columns=[catalog['columns'][n] for n in sorted(catalog['columns'])],
    rows=[dict(aligned=catalog['rows'][n]['TILE_ALIGNED'], unaligned=catalog['rows'][n]['TILE_UNALIGNED']) for n in sorted(catalog['rows'])],
    all_double_map_decompositions=all_mapped, catalog_pairs_N_gt65536=potential,
    routes=dict(
        legacy={str(n): dict(C=c, Q=q, z2d='HermitianColumns + LocalRealRows', d2z='PairedPostRows',
                            note='existing default register path remains separate; N=65536 retained as regression despite strict new scope') for n, (c, q) in LEGACY.items()},
        generic='RealTransEvenNode immediate N/2 CFFT must be CS_L1D_CC with exactly one CC and one RC leaf; noSolution required.',
        recursive='CC1DNode creates two leaf nodes directly, so there is no recursive CC child within a CC. CC nested inside TRTRT/Bluestein is not the immediate real CFFT and is not selected by TryFuseGenericRealPair.',
        other_rejections='Higher dimensions, batch other than 1, inplace, nonunit strides, user offsets, non-gfx936, embedded real or Bluestein leaves use other paths.'),
    source_hashes={str(p.relative_to(W)): sha(p) for p in [ROOT/'node_factory.cpp', ROOT/'tree_node_1D.cpp',
        ROOT/'device/kernels/configs/config_sbcc.py', ROOT/'device/kernels/configs/config_sbrc.py',
        W/'generated-pool-kernels.json', W/'library/src/include/function_pool.h']},
    generator_evidence_hashes={str(p): sha(p) for p in [FROZEN/'tree_node_real.cpp', FROZEN/'include/real_block_io.h',
        FROZEN/'device/generator/stockham_gen_base.h']},
    script_sha256=sha(pathlib.Path(__file__)))
(W/'all-cc-configurations.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
lines = [
    '# 全量双精度CC配置核查', '',
    '对象为已验收构建及冻结源码3a668d26；只读枚举，没有新编译、设备执行、映射修改或任务提交。', '',
    '完整机器记录见同目录all-cc-configurations.json；它保留75条函数池原始定义及对应文件校验值、114条双精度映射、279个目录内可组合的大尺寸几何。', '',
    '现有N＞65536映射85项；其中4项走旧五尺寸特化，其余81项走通用CC。旧65536点仍完整列为回归，但不计入新的严格尺寸范围。默认映射是源码静态推导，尚未为本轮逐项执行生产规划或设备。', '',
    '表中配对槽数和共享存储按现有规划公式及65536字节／1024线程预算计算；容量可用不是数值正确性或性能验收。空白默认覆盖数应保留为零，不能靠强制另一条分解凑覆盖。', '',
    '| 列长 | 因子 | 每变换线程 | 普通槽 | 配对槽 | 普通半共享区 | 配对共享区字节 | 现有通用默认N数量 |',
    '| ---: | --- | ---: | ---: | ---: | --- | --- | ---: |']
for c in data['columns']:
    v=c['paired_geometry_for_all_catalog_pairs_in_scope']
    lines.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
        c['length'], '×'.join(map(str,c['factors'])), c['P'], c['ordinary_T'],
        '/'.join(map(str,sorted({z['T'] for z in v}))), '是' if c['half_lds'] else '否',
        '/'.join(map(str,sorted({z['LDS_bytes'] for z in v}))),c['mapped_default_generic_N_count']))
lines += ['', '| 行长 | 因子 | 每变换线程 | 普通槽 | 配对槽 | 配对共享区字节 | 现有通用默认N数量 |',
          '| ---: | --- | ---: | ---: | ---: | ---: | ---: |']
for d in data['rows']:
    c=d['aligned'];z=c['nominal_pair_geometry_without_an_actual_map']
    lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (
        c['length'],'×'.join(map(str,c['factors'])),c['P'],c['ordinary_T'],z['T'],z['LDS_bytes'],c['mapped_default_generic_N_count']))
lines += ['', '所有行长均有对齐及非对齐两份注册配置，因子、线程和槽数相同；通用配对输出固定采用对齐模板并显式处理尾块。17行的配对数值只是资源公式：现有列长最大1024，无法组成N＞65536的完整CC，不能算实际覆盖。', '',
          '大旋转因子：启用三步策略的列长50、52、81、84、121、128、192、289、343，在本尺寸范围N≤524288采用六位基数三步，另加3072字节共享存储；更大采用八位基数三步。其他列长N≤131072采用八位基数两步，更大采用三步。编码上限仍须检查。行边界不执行大旋转相位。', '',
          '普通槽数为奇数的列长：'+ '、'.join(map(str,summary['odd_ordinary_T_column_lengths']))+'。行长：'+'、'.join(map(str,summary['odd_ordinary_T_row_lengths']))+'。625／1331行从一槽提高到合法两槽；不能把普通T=1直接当成不支持配对，也不能按普通共享容量验收配对。', '',
          '首末轮不是所有线程都有效。全部目录配置的首末轮坐标模型均为双射；必须保留首轮清零和有效工作掩码、尾轮部分工作掩码。240列实际P48而末轮只有40组；512行P128而首末轮都只有64组。完整边界标志与分数工作高度已写入JSON。', '',
          '279种目录内大尺寸几何中，85种已有正确方向的默认映射、132种为可补映射方向、62种与既有映射方向冲突；不修改任何旧映射。132种方向对应108个缺失M，其中23个M可选多个方向；同一个N不能同时默认使用两种方向。每类的可选数量是逐类上限，不能视为所有类型能同时取得这些覆盖。按现有规划公式，它们的配对资源均能放入当前设备预算，但缺表项尚未成为真实默认计划。', '',
          '即使允许补所有不冲突的缺项，以下列长仍不足五种通用N：'+'、'.join(map(str,sorted(summary['columns_unable_to_supply_five_N_even_with_nonconflicting_missing_maps'])))+'。行长：'+'、'.join(map(str,sorted(summary['rows_unable_to_supply_five_N_even_with_nonconflicting_missing_maps'])))+'。JSON逐项列出现有数量、可合法补充的数量和所有候选，不能把不可能的覆盖写成已完成。', '',
          '旧五尺寸保持独立：z2d为折叠列＋逐行实数组合，d2z为既有配对后处理；不能把通用T、共享布局或直接后端策略直接套到旧路径。CC1D本身固定创建CC／RC两片叶子，内部没有递归CC；转置或卷积内部的CC并不是实数变换的直接边界，现有通用融合入口不会进入它。', '']
(W/'all-cc-configurations-summary.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
