#!/usr/bin/env python3
"""
枚举 config_sbcc.py / config_sbrc.py / config_sbrr.py 中所有可调优的参数组合,
按 N(64k~512k) × FFT类型(z2d/d2z/z2z) × 分解方式, 输出到 CSV 文件。

架构: gfx936 (LDS 64KB 默认, 可选 160KB)
策略: 64K~256K 全部 CC, 512K z2z 用 TRTRT (sbrr), 512K d2z/z2d 用 CC

支持: 断点续传、LDS 约束、参数合法性检查。
"""

import os
import re
import csv
import math
import hashlib
import argparse
from collections import OrderedDict

# ============================================================================
# 1. N 分解方式 (来自 node_factory.cpp map1DLengthDouble + tune_all.py PLAN)
# ============================================================================

DECOMPOSITIONS = {
    # N -> { type_prefix -> [ (kernel_type, length, config_file) ] }
    65536: {
        "z2z": [
            ("sbcc", 256, "config_sbcc.py"),
            ("sbcc", 256, "config_sbcc.py"),
        ],
        "d2z_z2d": [
            ("sbcc", 256, "config_sbcc.py"),
            ("sbrc", 256, "config_sbrc.py"),
        ],
    },
    131072: {
        "z2z": [
            ("sbcc", 256, "config_sbcc.py"),
            ("sbcc", 512, "config_sbcc.py"),
        ],
        "d2z_z2d": [
            ("sbcc", 256, "config_sbcc.py"),
            ("sbrc", 512, "config_sbrc.py"),
        ],
    },
    262144: {
        "z2z": [
            ("sbcc", 512, "config_sbcc.py"),
            ("sbcc", 512, "config_sbcc.py"),
        ],
        "d2z_z2d": [
            ("sbcc", 512, "config_sbcc.py"),
            ("sbrc", 512, "config_sbrc.py"),
        ],
    },
    524288: {
        "z2z": [
            # 512K z2z: 默认 TRTRT 分解, 使用 sbrr
            ("sbrr", 1024, "config_sbrr.py"),
            ("sbrr", 512, "config_sbrr.py"),
        ],
        "d2z_z2d": [
            # 512K d2z/z2d: CC 分解
            ("sbcc", 512, "config_sbcc.py"),
            ("sbrc", 512, "config_sbrc.py"),
        ],
    },
}

# ============================================================================
# 2. 参数枚举范围
# ============================================================================

# 允许的 radix (用于分解 length)
ALLOWED_RADICES = [16, 8, 4, 2]

# workgroup_size 范围
WGS_LIST = [64, 128, 256, 512, 1024]

# threads_per_transform 范围 (2^4 到 2^10)
TPT_EXPONENTS = list(range(4, 11))  # 16, 32, 64, 128, 256, 512, 1024

# LDS 上限 (bytes)
LDS_LIMIT_DEFAULT = 65536   # 64 KiB (gfx936 默认)
LDS_LIMIT_160K = 160 * 1024 # 160 KiB (大 LDS 模式)

# ============================================================================
# 3. 辅助函数
# ============================================================================

def get_factors_raw(n, allowed_radices=None):
    """递归生成 n 的所有因子序列 (有序)"""
    if allowed_radices is None:
        allowed_radices = ALLOWED_RADICES
    if n == 1:
        return [[]]
    res = []
    for r in allowed_radices:
        if n % r == 0:
            for sub in get_factors_raw(n // r, allowed_radices):
                res.append([r] + sub)
    return res


def get_factors(n, allowed_radices=None):
    """获取 n 的所有去重因子组合 (降序排列)"""
    if allowed_radices is None:
        allowed_radices = ALLOWED_RADICES
    raw = get_factors_raw(n, allowed_radices)
    # 去重: 排序后转为 tuple
    unique = set()
    for f in raw:
        unique.add(tuple(sorted(f, reverse=True)))
    return [list(f) for f in sorted(unique)]


def get_tpt_list(wgs):
    """对于给定 wgs, 返回所有合法的 tpt: 2^4..2^10, 且 tpt <= wgs 且 wgs % tpt == 0"""
    tpts = []
    for exp in TPT_EXPONENTS:
        tpt = 2 ** exp
        if tpt <= wgs and wgs % tpt == 0:
            tpts.append(tpt)
    return tpts


def calc_lds_bytes(wgs, tpt, length):
    """计算 LDS 需求 (bytes), 假设 double precision (16 bytes/element)"""
    return int((wgs / tpt) * length * 16)


def format_factors(factors, use_tuple=False):
    """将 factors 列表转为字符串表达形式"""
    if use_tuple:
        return "(" + ", ".join(str(f) for f in factors) + ")"
    else:
        return "[" + ", ".join(str(f) for f in factors) + "]"


def generate_kernel_config(kernel_type, length, factors, wgs, tpt, extra_opts=None):
    """
    生成一条 kernel 配置条目 (替换字符串).
    返回: (config_line_str, hash_key)
    
    Parameters
    ----------
    kernel_type : str - 'sbcc', 'sbrc', 'sbrr'
    length : int
    factors : list of int
    wgs : int - workgroup_size
    tpt : int - threads_per_transform
    extra_opts : dict - 额外的参数, 取决于 kernel_type
        sbcc: {'sp': 'true'/'false', 'dp': 'true'/'false', 'half_lds': bool, 'flavour': 'wide'/None}
        sbrc: {'direct_to_from_reg': bool}
        sbrr: {'half_lds': bool, 'direct_to_from_reg': bool, 'double_precision': bool}
    """
    if extra_opts is None:
        extra_opts = {}

    base = f"NS(length={length}"
    
    if kernel_type == "sbcc":
        f_str = format_factors(factors, use_tuple=False)
        sp = extra_opts.get("sp", "true")
        dp = extra_opts.get("dp", "true")
        twd = f"{{'sp': '{sp}', 'dp': '{dp}'}}"
        # SBCC 参数顺序: length, factors, use_3steps_large_twd={...}(单行), workgroup_size, threads_per_transform, half_lds, flavour, runtime_compile
        line = f"{base}, factors={f_str}, use_3steps_large_twd={twd}"
        if wgs:
            line += f", workgroup_size={wgs}"
        if tpt:
            line += f", threads_per_transform={tpt}"
        if extra_opts.get("half_lds"):
            line += ", half_lds=True"
        if extra_opts.get("flavour"):
            line += f", flavour='{extra_opts['flavour']}'"
        line += ", runtime_compile=True),"

    elif kernel_type == "sbrc":
        f_str = format_factors(factors, use_tuple=False)
        # SBRC 参数顺序: length, factors, scheme, workgroup_size, threads_per_transform, direct_to_from_reg, runtime_compile
        line = f"{base}, factors={f_str}, scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size={wgs}, threads_per_transform={tpt}"
        if not extra_opts.get("direct_to_from_reg", True):
            line += ", direct_to_from_reg=False"
        line += ", runtime_compile=True),"

    elif kernel_type == "sbrr":
        f_str = format_factors(factors, use_tuple=True)
        # SBRR 参数顺序: length, workgroup_size, threads_per_transform, factors(tuple), half_lds, direct_to_from_reg, double_precision, runtime_compile
        # 注意 length= 后面有空格 (如 length= 512)
        line = f"NS(length= {length}, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f_str}"
        if extra_opts.get("half_lds") == False:
            line += ", half_lds=False"
        if extra_opts.get("direct_to_from_reg") == False:
            line += ", direct_to_from_reg=False"
        if extra_opts.get("double_precision") == False:
            line += ", double_precision=False"
        line += ", runtime_compile=True),"

    else:
        raise ValueError(f"Unknown kernel_type: {kernel_type}")

    # 生成唯一 hash key (用于断点续传)
    key_str = f"{kernel_type}|{length}|{factors}|{wgs}|{tpt}|{extra_opts}"
    key_hash = hashlib.md5(key_str.encode()).hexdigest()[:12]

    return line, key_hash


def check_lds_constraint(kernel_type, wgs, tpt, length, extra_opts):
    """
    检查 LDS 约束.
    SBCC: 不需要 (因为 CC kernel 特点不同)
    SBRC: (wgs/tpt) * length * 16 <= 65536
    SBRR: 如果 half_lds=False (默认 True), 约束同 SBRC
    """
    if kernel_type == "sbcc":
        return True
    
    lds_bytes = calc_lds_bytes(wgs, tpt, length)
    
    if kernel_type == "sbrc":
        return lds_bytes <= LDS_LIMIT_DEFAULT
    
    if kernel_type == "sbrr":
        if extra_opts:
            half_lds = extra_opts.get("half_lds", True)
            if half_lds == False:
                lds_bytes *= 2
        return lds_bytes <= LDS_LIMIT_DEFAULT
    
    return True


# ============================================================================
# 4. 枚举所有配置
# ============================================================================

def enumerate_all_configs():
    for N, type_decomps in DECOMPOSITIONS.items():
        for type_name, stages in type_decomps.items():
            decomp_method = type_name
            
            for stage_idx, (kernel_type, length, config_file) in enumerate(stages):
                factors_list = get_factors(length, ALLOWED_RADICES)
                
                for factors in factors_list:
                    for wgs in WGS_LIST:
                        tpts = get_tpt_list(wgs)
                        if not tpts:
                            continue
                        
                        for tpt in tpts:
                            extra_opts_variants = _get_extra_opts_variants(
                                kernel_type, length
                            )
                            
                            for extra_opts in extra_opts_variants:
                                if not check_lds_constraint(
                                    kernel_type, wgs, tpt, length, extra_opts
                                ):
                                    continue
                                
                                if extra_opts and extra_opts.get("flavour") == "wide":
                                    if length not in (160, 256):
                                        continue
                                
                                config_line, hash_key = generate_kernel_config(
                                    kernel_type, length, factors, wgs, tpt, extra_opts
                                )
                                
                                yield {
                                    "N": N,
                                    "Type": type_name,
                                    "DecompMethod": decomp_method,
                                    "StageIndex": stage_idx + 1,
                                    "TotalStages": len(stages),
                                    "KernelType": kernel_type,
                                    "ConfigFile": config_file,
                                    "Length": length,
                                    "Factors": str(factors),
                                    "WGS": wgs,
                                    "TPT": tpt,
                                    "ExtraOpts": str(extra_opts) if extra_opts else "",
                                    "ConfigLine": config_line,
                                    "HashKey": hash_key,
                                }


def _get_extra_opts_variants(kernel_type, length):
    variants = []
    
    if kernel_type == "sbcc":
        # sp 固定 'true' (不测单精度), dp 枚举 (影响 DP 性能), half_lds 枚举, 去掉 flavour
        for dp in ["true", "false"]:
            base_opts = {"sp": "true", "dp": dp}
            variants.append(dict(base_opts))
            opts_hl = dict(base_opts)
            opts_hl["half_lds"] = True
            variants.append(opts_hl)
    
    elif kernel_type == "sbrc":
        variants.append({"direct_to_from_reg": True})
        variants.append({"direct_to_from_reg": False})
    
    elif kernel_type == "sbrr":
        for half_lds in [True, False]:
            for dir_reg in [True, False]:
                if not half_lds and not dir_reg:
                    continue
                opts = {}
                if half_lds == False:
                    opts["half_lds"] = False
                if dir_reg == False:
                    opts["direct_to_from_reg"] = False
                variants.append(opts)
        
        if length > 4096:
            for v in list(variants):
                v_dp = dict(v)
                v_dp["double_precision"] = False
                variants.append(v_dp)
        
        seen = set()
        unique_variants = []
        for v in variants:
            key = str(sorted(v.items()))
            if key not in seen:
                seen.add(key)
                unique_variants.append(v)
        variants = unique_variants
    
    if not variants:
        variants = [{}]
    
    return variants


# ============================================================================
# 5. 断点续传 + CSV 输出
# ============================================================================

def load_completed_keys(csv_path):
    completed = set()
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                hk = row.get("HashKey", "")
                if hk:
                    completed.add(hk)
    return completed


def write_csv_header(csv_path):
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "N", "Type", "DecompMethod", "StageIndex", "TotalStages",
                "KernelType", "ConfigFile", "Length", "Factors",
                "WGS", "TPT", "ExtraOpts", "ConfigLine", "HashKey"
            ])


def append_config_to_csv(csv_path, config_dict):
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            config_dict["N"],
            config_dict["Type"],
            config_dict["DecompMethod"],
            config_dict["StageIndex"],
            config_dict["TotalStages"],
            config_dict["KernelType"],
            config_dict["ConfigFile"],
            config_dict["Length"],
            config_dict["Factors"],
            config_dict["WGS"],
            config_dict["TPT"],
            config_dict["ExtraOpts"],
            config_dict["ConfigLine"],
            config_dict["HashKey"],
        ])


# ============================================================================
# 6. 替换映射
# ============================================================================

def generate_replacement_map():
    rep_map = {}
    for N, type_decomps in DECOMPOSITIONS.items():
        for type_name, stages in type_decomps.items():
            for stage_idx, (kernel_type, length, config_file) in enumerate(stages):
                key = (N, type_name, stage_idx)
                rep_map[key] = {
                    "kernel_type": kernel_type,
                    "length": length,
                    "config_file": config_file,
                    "config_file_path": os.path.join(
                        os.path.dirname(__file__),
                        "..",
                        "rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device/kernels/configs",
                        config_file
                    )
                }
    return rep_map


# ============================================================================
# 7. 统计信息
# ============================================================================

def print_statistics(csv_path):
    if not os.path.exists(csv_path):
        print("CSV 文件不存在")
        return
    
    df_data = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            df_data.append(row)
    
    if not df_data:
        print("CSV 为空")
        return
    
    print(f"\n{'='*60}")
    print(f"总配置数: {len(df_data)}")
    print(f"{'='*60}")
    
    from collections import Counter
    n_counts = Counter(row["N"] for row in df_data)
    print("\n按 N 统计:")
    for N in sorted(n_counts.keys(), key=int):
        print(f"  N={N}: {n_counts[N]} 条")
    
    type_counts = Counter(row["Type"] for row in df_data)
    print("\n按 Type 统计:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c} 条")
    
    kt_counts = Counter(row["KernelType"] for row in df_data)
    print("\n按 KernelType 统计:")
    for kt, c in sorted(kt_counts.items()):
        print(f"  {kt}: {c} 条")
    
    nt_counts = Counter((row["N"], row["Type"]) for row in df_data)
    print("\n按 N+Type 详细统计:")
    for (N, t), c in sorted(nt_counts.items()):
        print(f"  N={N}, Type={t}: {c} 条")
    
    print()


# ============================================================================
# 8. 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="枚举 rocFFT config 的所有可调优参数组合 (CC 策略)"
    )
    parser.add_argument(
        "-o", "--output",
        default="config_enumerations.csv",
        help="输出 CSV 文件路径"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="启用断点续传 (默认开启)"
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="禁用断点续传, 从头生成"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="仅显示已有 CSV 的统计信息"
    )
    parser.add_argument(
        "--print-rep-map",
        action="store_true",
        help="打印替换映射"
    )
    args = parser.parse_args()
    
    if args.print_rep_map:
        rep_map = generate_replacement_map()
        print("\n替换映射 (N, Type, StageIndex) -> (KernelType, Length, ConfigFile):")
        for key, val in sorted(rep_map.items()):
            N, type_name, stage_idx = key
            print(f"  N={N}, Type={type_name}, Stage={stage_idx+1}: "
                  f"{val['kernel_type']} length={val['length']} -> {val['config_file']}")
        return
    
    if args.stats_only:
        print_statistics(args.output)
        return
    
    completed_keys = set()
    if args.resume:
        completed_keys = load_completed_keys(args.output)
        if completed_keys:
            print(f"断点续传: 已加载 {len(completed_keys)} 条已完成记录")
    
    write_csv_header(args.output)
    
    total_generated = 0
    total_skipped = 0
    
    print("开始枚举所有配置...")
    for config in enumerate_all_configs():
        hk = config["HashKey"]
        if hk in completed_keys:
            total_skipped += 1
            continue
        
        append_config_to_csv(args.output, config)
        completed_keys.add(hk)
        total_generated += 1
        
        if total_generated % 5000 == 0:
            print(f"  已生成 {total_generated} 条 (跳过 {total_skipped} 条)...")
    
    print(f"\n枚举完成!")
    print(f"  新生成: {total_generated} 条")
    print(f"  跳过: {total_skipped} 条")
    print(f"  总计: {total_generated + total_skipped} 条")
    print(f"  输出文件: {args.output}")
    
    print_statistics(args.output)


if __name__ == "__main__":
    main()