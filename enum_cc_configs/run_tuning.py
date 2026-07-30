#!/usr/bin/env python3
"""
读取 enumerate_configs.py 生成的 CSV, 执行两阶段暴力调优:
  阶段1: 固定 Stage2 为基线, 枚举 Stage1 所有候选 → 找最优
  阶段2: 固定最优 Stage1, 枚举 Stage2 所有候选 → 找最优

每轮: 修改 config 文件 → cmake 编译 → rocfft-bench 运行 → 记录耗时
支持断点续传 (以 HashKey 为去重键)
"""

import os
import re
import subprocess
import time
import csv
import glob
import argparse
import hashlib
from datetime import datetime
from collections import defaultdict

# ============================================================================
# 路径配置 (独立 configs 副本 + 独立 build/install, 其余源码共享)
# ============================================================================
ROCFFT_SRC_DIR = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft")
SRC_CONFIG_DIR = os.path.join(ROCFFT_SRC_DIR, "library/src/device/kernels/configs")
BUILD_DIR = os.path.expanduser("~/zr/build/tuning_cc_build")
INSTALL_DIR = os.path.expanduser("~/zr/install_tuning_cc")
# 独立的 configs 副本 (运行时修改, 编译前 rsync 回源目录)
CONFIG_SANDBOX_DIR = os.path.expanduser("~/zr/configs_tuning_cc")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# 基线配置 (每个 stage 的默认值, 来自 config_sbcc/sbrc/sbrr.py)
# 用于: 在枚举 Stage1 时固定 Stage2, 反之亦然
# ============================================================================
BASELINES = {
    # SBCC: 单行格式, use_3steps_large_twd 内联
    ("sbcc", 256):  "NS(length=256, factors=[8,4,8], use_3steps_large_twd={'sp': 'true', 'dp': 'true'}, workgroup_size=256, threads_per_transform=64, runtime_compile=True),",
    ("sbcc", 512):  "NS(length=512, factors=[8,8,8], use_3steps_large_twd={'sp': 'true', 'dp': 'false'}, workgroup_size=256, threads_per_transform=64, runtime_compile=True),",
    # SBRC: 单行格式
    ("sbrc", 256):  "NS(length=256, factors=[4,4,4,4], scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size=256, threads_per_transform=32, runtime_compile=True),",
    ("sbrc", 512):  "NS(length=512, factors=[8,8,8], scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size=512, threads_per_transform=128, runtime_compile=True),",
    # SBRR: length= 后面有空格
    ("sbrr", 512):  "NS(length= 512, workgroup_size=64, threads_per_transform=64, factors=(8,8,8), runtime_compile=True),",
    ("sbrr", 1024): "NS(length= 1024, workgroup_size=256, threads_per_transform=256, factors=(16,16,4), runtime_compile=True),",
}

# ============================================================================
# 辅助: 修改 config 文件 (支持跨行)
# ============================================================================
def modify_config(filepath, length, new_line):
    """
    用 new_line 替换文件中 NS(length=xxx,...) 的条目.
    支持 SBCC 的多行 use_3steps_large_twd={...} 格式,
    以及 SBRC 行尾的 # 注释.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 构建正则: 匹配 NS(length=XXX 开头, 到第一个 ), 为止 (含行尾注释)
    # 使用 re.DOTALL 让 . 匹配换行符
    content = ''.join(lines)
    
    # 模式: NS(length=XXX ... ),  (允许中间跨行, 允许行尾有注释)
    # 注意 SBRR 的 length= 后面有空格: length= 512
    pattern = r"^[ \t]*NS\(\s*length\s*=\s*" + str(length) + r"\s*,.*?\),[^\n]*"
    replacement = "    " + new_line
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)


# ============================================================================
# 编译 rocFFT
# ============================================================================
def sync_sandbox_to_src():
    """将 sandbox 中的 config 文件同步到源码目录"""
    if not os.path.isdir(CONFIG_SANDBOX_DIR):
        return False
    cmd = f"rsync -a {CONFIG_SANDBOX_DIR}/ {SRC_CONFIG_DIR}/"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0

def build_rocfft():
    # 编译前同步 sandbox → 源码
    sync_sandbox_to_src()
    cmd = "cmake --build . -j$(nproc) --target install"
    res = subprocess.run(cmd, shell=True, cwd=BUILD_DIR,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0


# ============================================================================
# 运行 benchmark
# ============================================================================
def run_benchmark(target_n, mode):
    """运行 rocfft-bench, 返回 FFT kernel 总耗时 (ms), 失败返回 -1"""
    # mode: "z2z" -> type 0, "d2z" -> type 2, "z2d" -> type 3
    type_map = {"z2z": 0, "d2z": 2, "z2d": 3}
    ttype = type_map.get(mode, 0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_prefix = os.path.expanduser(f"~/zr/enum_cc_configs/tmp/tune_{mode}_{target_n}_{timestamp}")
    os.makedirs(os.path.dirname(csv_prefix), exist_ok=True)
    
    csv_file = f"{csv_prefix}.csv"
    
    cmd = (
        f"LD_LIBRARY_PATH={INSTALL_DIR}/lib:$LD_LIBRARY_PATH "
        f"hipprof --stats -o {csv_file} "
        f"{BUILD_DIR}/clients/staging/rocfft-bench "
        f"--length {target_n} --batchSize 1000 --precision double --transformType {ttype} -o -N 10"
    )
    
    subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # 读取生成的 CSV
    csv_files = glob.glob(f"{csv_prefix}*.csv")
    total_ns = 0.0
    found_kernels = False
    
    exclude_kws = ['generate_random', 'impose_hermitian', 'Total', 'twiddle_gen']
    
    for fpath in csv_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as cf:
                reader = csv.DictReader(cf)
                for row in reader:
                    name = row.get("Name", "")
                    if not name:
                        continue
                    if any(kw in name for kw in exclude_kws):
                        continue
                    total_ns += float(row.get("AverageNs", 0))
                    found_kernels = True
        except Exception:
            pass
    
    # 清理临时文件
    for fpath in glob.glob(f"{csv_prefix}*"):
        try:
            os.remove(fpath)
        except Exception:
            pass
    
    if found_kernels:
        return total_ns / 1e6  # ns -> ms
    else:
        return -1.0


# ============================================================================
# 读取枚举 CSV 并分组
# ============================================================================
def load_config_csv(csv_path):
    """返回: list of dict, 每个 dict 有 N, Type, StageIndex, TotalStages, KernelType, ConfigFile, Length, Factors, WGS, TPT, ExtraOpts, ConfigLine, HashKey"""
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def group_by_n_type(rows):
    """按 (N, Type) 分组, 每组内再按 StageIndex 分组"""
    groups = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key = (int(r["N"]), r["Type"])
        stage_idx = int(r["StageIndex"])
        groups[key][stage_idx].append(r)
    return groups


# ============================================================================
# 断点续传: 加载已完成的结果
# ============================================================================
def load_completed_results(result_csv_path):
    """返回 set of HashKey"""
    completed = set()
    if os.path.exists(result_csv_path):
        with open(result_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                hk = row.get("HashKey", "")
                if hk:
                    completed.add(hk)
    return completed


def load_best_per_stage(result_csv_path):
    """
    从已有结果中找每个 (N, Type, Stage) 的最优记录.
    返回: dict (N, type_name, stage_idx) -> {"ConfigLine": str, "TimeMs": float, "HashKey": str}
    """
    best = {}
    if not os.path.exists(result_csv_path):
        return best
    
    with open(result_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (int(row["N"]), row["Type"], int(row["StageIndex"]))
            time_ms = float(row.get("GPU_Time_ms", row.get("TimeMs", "inf")))
            if time_ms <= 0:
                continue
            if key not in best or time_ms < best[key]["TimeMs"]:
                best[key] = {
                    "ConfigLine": row["ConfigLine"],
                    "TimeMs": time_ms,
                    "HashKey": row["HashKey"],
                }
    return best


# ============================================================================
# 结果写入
# ============================================================================
def write_result_header(result_csv_path):
    if not os.path.exists(result_csv_path):
        with open(result_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "N", "Type", "StageIndex", "TotalStages",
                "KernelType", "ConfigFile", "Length", "Factors",
                "WGS", "TPT", "ExtraOpts", "ConfigLine",
                "GPU_Time_ms", "HashKey", "Timestamp"
            ])


def append_result(result_csv_path, config_dict, gpu_time_ms):
    with open(result_csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            config_dict["N"],
            config_dict["Type"],
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
            f"{gpu_time_ms:.4f}",
            config_dict["HashKey"],
            datetime.now().strftime("%Y%m%d_%H%M%S"),
        ])


# ============================================================================
# 调优主流程
# ============================================================================

def tune_one_group(N, type_name, stages_dict, completed_keys, result_csv_path, best_per_stage):
    """
    对一组 (N, Type) 进行两阶段调优.
    
    stages_dict: {1: [rows], 2: [rows]}  (StageIndex -> list of CSV rows)
    """
    print(f"\n{'='*70}")
    print(f"========== 调优 N={N}, Type={type_name} ==========")
    print(f"{'='*70}")
    
    total_stages = max(stages_dict.keys())
    
    # 映射 type_name 中的 "d2z_z2d" -> 需要测试的实际 mode
    # 对于 d2z_z2d, 需要测试两个 mode: d2z 和 z2d, 取总时间
    mode_list = _get_mode_list(type_name)
    
    # ============ 阶段 1: 枚举 Stage1, 固定 Stage2 为基线 ============
    stage1_rows = stages_dict.get(1, [])
    stage2_rows = stages_dict.get(2, [])
    
    print(f"\n>>> 阶段 1: 枚举 Stage1 ({len(stage1_rows)} 候选), 固定 Stage2 为基线 <<<")
    
    # 先固定 Stage2 为基线
    if stage2_rows:
        # 取第一条 Stage2 记录的 kernel_type 和 length, 设置基线
        s2_ktype = stage2_rows[0]["KernelType"]
        s2_length = int(stage2_rows[0]["Length"])
        s2_file = os.path.join(CONFIG_SANDBOX_DIR, stage2_rows[0]["ConfigFile"])
        baseline_key = (s2_ktype, s2_length)
        if baseline_key in BASELINES:
            modify_config(s2_file, s2_length, BASELINES[baseline_key])
            print(f"  [固定 Stage2] {s2_ktype} length={s2_length} → 基线")
        else:
            # 如果没在 BASELINES 里, 就用 stage2_rows 的第一条作为基线
            modify_config(s2_file, s2_length, stage2_rows[0]["ConfigLine"])
            print(f"  [固定 Stage2] {s2_ktype} length={s2_length} → 首条候选")
        
        # 编译一次 (基线)
        if not build_rocfft():
            print("  [基线编译失败, 跳过本组]")
            return
    
    best_s1_time = float('inf')
    best_s1_config = None
    
    for row in stage1_rows:
        hk = row["HashKey"]
        if hk in completed_keys:
            print(f"  [跳过] S1 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']} [已存在]")
            # 从已有结果中检查是否更优
            exist_key = (N, type_name, 1)
            if exist_key in best_per_stage and best_per_stage[exist_key]["TimeMs"] < best_s1_time:
                best_s1_time = best_per_stage[exist_key]["TimeMs"]
                best_s1_config = best_per_stage[exist_key]["ConfigLine"]
            continue
        
        s1_length = int(row["Length"])
        s1_file = os.path.join(CONFIG_SANDBOX_DIR, row["ConfigFile"])
        
        # 修改 Stage1 配置
        modify_config(s1_file, s1_length, row["ConfigLine"])
        
        # 编译
        t0 = time.time()
        if not build_rocfft():
            print(f"  [编译失败] S1 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']}")
            continue
        t_build = time.time() - t0
        
        # 运行 benchmark (对 d2z_z2d 需跑两个 mode 取总时间)
        t0 = time.time()
        total_time = 0.0
        all_ok = True
        for m in mode_list:
            t = run_benchmark(N, m)
            if t < 0:
                all_ok = False
                break
            total_time += t
        t_run = time.time() - t0
        
        if all_ok and total_time > 0:
            print(f"  [OK] S1 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']} "
                  f"[build:{t_build:.1f}s run:{t_run:.1f}s] → {total_time:.4f} ms")
            append_result(result_csv_path, row, total_time)
            
            if total_time < best_s1_time:
                best_s1_time = total_time
                best_s1_config = row["ConfigLine"]
        else:
            print(f"  [FAIL] S1 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']}")
    
    if best_s1_config is None:
        print(f"  阶段 1 未找到合法配置, 结束本组")
        return
    
    print(f"\n  >>> 阶段 1 最优: {best_s1_config.strip()[:-1]} ... ({best_s1_time:.4f} ms)")
    
    # 固定最优 Stage1
    s1_row = stage1_rows[0]
    modify_config(os.path.join(CONFIG_SANDBOX_DIR, s1_row["ConfigFile"]), int(s1_row["Length"]), best_s1_config)
    
    # ============ 阶段 2: 枚举 Stage2, 固定最优 Stage1 ============
    if not stage2_rows:
        print("  无 Stage2, 结束")
        return
    
    print(f"\n>>> 阶段 2: 枚举 Stage2 ({len(stage2_rows)} 候选), 固定最优 Stage1 <<<")
    
    best_s2_time = float('inf')
    best_s2_config = None
    
    for row in stage2_rows:
        hk = row["HashKey"]
        if hk in completed_keys:
            print(f"  [跳过] S2 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']} [已存在]")
            exist_key = (N, type_name, 2)
            if exist_key in best_per_stage and best_per_stage[exist_key]["TimeMs"] < best_s2_time:
                best_s2_time = best_per_stage[exist_key]["TimeMs"]
                best_s2_config = best_per_stage[exist_key]["ConfigLine"]
            continue
        
        s2_length = int(row["Length"])
        s2_file = os.path.join(CONFIG_SANDBOX_DIR, row["ConfigFile"])
        
        modify_config(s2_file, s2_length, row["ConfigLine"])
        
        t0 = time.time()
        if not build_rocfft():
            print(f"  [编译失败] S2 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']}")
            continue
        t_build = time.time() - t0
        
        t0 = time.time()
        total_time = 0.0
        all_ok = True
        for m in mode_list:
            t = run_benchmark(N, m)
            if t < 0:
                all_ok = False
                break
            total_time += t
        t_run = time.time() - t0
        
        if all_ok and total_time > 0:
            print(f"  [OK] S2 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']} "
                  f"[build:{t_build:.1f}s run:{t_run:.1f}s] → {total_time:.4f} ms")
            append_result(result_csv_path, row, total_time)
            
            if total_time < best_s2_time:
                best_s2_time = total_time
                best_s2_config = row["ConfigLine"]
        else:
            print(f"  [FAIL] S2 {row['KernelType']} f={row['Factors']} wgs={row['WGS']} tpt={row['TPT']}")
    
    if best_s2_config:
        print(f"\n  >>> 阶段 2 最优: {best_s2_config.strip()[:-1]} ... ({best_s2_time:.4f} ms)")
    
    print(f"\n  ====== N={N}, Type={type_name} 调优完成 ======")
    print(f"  最优 Stage1: {best_s1_config.strip()[:-1]} ({best_s1_time:.4f} ms)")
    if best_s2_config:
        print(f"  最优 Stage2: {best_s2_config.strip()[:-1]} ({best_s2_time:.4f} ms)")


def _get_mode_list(type_name):
    """将 type_name 映射为需要测试的 mode 列表"""
    if type_name == "z2z":
        return ["z2z"]
    elif type_name == "d2z_z2d":
        return ["d2z", "z2d"]
    else:
        return [type_name]


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="rocFFT 自动调优 (从 CSV 读取候选配置)")
    parser.add_argument("-i", "--input-csv",
                        default=os.path.join(SCRIPT_DIR, "config_enumerations.csv"),
                        help="枚举 CSV 文件路径")
    parser.add_argument("-o", "--output-csv",
                        default=os.path.join(SCRIPT_DIR, "tuning_results.csv"),
                        help="调优结果 CSV 输出路径")
    parser.add_argument("--N", type=int, default=0,
                        help="仅调优指定 N (0 = 全部)")
    parser.add_argument("--type", dest="filter_type", default="all",
                        help="仅调优指定 type (z2z/d2z_z2d/all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印将要执行的候选数, 不实际调优")
    parser.add_argument("--no-resume", action="store_true",
                        help="忽略已有结果, 全部重新测试")
    args = parser.parse_args()
    
    if not os.path.exists(args.input_csv):
        print(f"错误: 枚举 CSV 不存在: {args.input_csv}")
        print("请先运行 enumerate_configs.py 生成候选配置")
        return
    
    # 读取 CSV
    rows = load_config_csv(args.input_csv)
    print(f"已加载 {len(rows)} 条候选配置")
    
    # 分组
    groups = group_by_n_type(rows)
    
    # 过滤
    filtered_groups = {}
    for (N, type_name), stages in groups.items():
        if args.N > 0 and N != args.N:
            continue
        if args.filter_type != "all" and type_name != args.filter_type:
            continue
        filtered_groups[(N, type_name)] = stages
    
    if not filtered_groups:
        print("没有匹配的调优组")
        return
    
    # 统计候选数
    total_candidates = 0
    for (N, type_name), stages in sorted(filtered_groups.items()):
        s1_cnt = len(stages.get(1, []))
        s2_cnt = len(stages.get(2, []))
        print(f"  N={N}, Type={type_name}: Stage1={s1_cnt}, Stage2={s2_cnt}")
        total_candidates += s1_cnt + s2_cnt
    
    print(f"\n总候选数: {total_candidates}")
    
    if args.dry_run:
        print("(dry-run 模式, 不实际调优)")
        return
    
    # 加载已完成结果
    completed_keys = set()
    if not args.no_resume:
        completed_keys = load_completed_results(args.output_csv)
        if completed_keys:
            print(f"断点续传: 已加载 {len(completed_keys)} 条已完成记录")
    
    best_per_stage = load_best_per_stage(args.output_csv)
    
    # 写入结果 CSV 表头
    write_result_header(args.output_csv)
    
    # 逐组调优
    for (N, type_name), stages in sorted(filtered_groups.items()):
        tune_one_group(N, type_name, stages, completed_keys, args.output_csv, best_per_stage)
        # 每完成一组, 重新加载 best_per_stage (因为可能有新结果)
        best_per_stage = load_best_per_stage(args.output_csv)
    
    print(f"\n全部调优完成! 结果保存在 {args.output_csv}")


if __name__ == "__main__":
    main()