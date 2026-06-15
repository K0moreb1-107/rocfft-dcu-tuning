#!/usr/bin/env python3
import os
import re
import subprocess
import itertools
import time
import csv
import glob
from datetime import datetime

# ================= 配置区 =================
ROCFFT_SRC_DIR = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft")
BUILD_DIR = os.path.expanduser("~/zr/build/rocfft_build")
CSV_OUTPUT = "tuning_results.csv"

# ================= 辅助函数 =================
def get_factors_raw(n, allowed_radices=[2, 4, 8, 16]):
    if n == 1:
        return [[]]
    res = []
    for r in allowed_radices:
        if n % r == 0:
            for sub in get_factors_raw(n // r, allowed_radices):
                res.append([r] + sub)
    return res

def get_factors(n, allowed_radices=[16, 8, 4, 2]):
    """递归生成所有合法的 factor 组合，强制降序排列并去重"""
    raw = get_factors_raw(n, allowed_radices)
    # 核心：排序后转为 tuple 进行去重，剔除本质相同的组合（如 [16,4,4] 和 [4,16,4]）
    unique_factors = set(tuple(sorted(f, reverse=True)) for f in raw)
    return [list(f) for f in unique_factors]

def modify_config(filepath, length, new_str_template):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则表达式精准替换对应的 length 行
    pattern = r"NS\(\s*length=" + str(length) + r"\s*,.*?\),"
    new_content = re.sub(pattern, new_str_template, content, flags=re.DOTALL)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

def build_rocfft():
    """增量编译并安装"""
    # cmake --build . 将自动调用 generator.py 并编译有改动的核心
    cmd_build = "cmake --build . -j$(nproc) --target install"
    res = subprocess.run(cmd_build, shell=True, cwd=BUILD_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0

def run_benchmark():
    """运行用户指定的测试命令并提取成绩"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.expanduser(f"~/zr/results/z2d_64k_tuning_{timestamp}.csv")
    
    cmd = (
        "LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH "
        f"hipprof --stats -o {csv_file} "
        "$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench "
        "--length 65536 --batchSize 1000 --precision double --transformType 3 -o -N 10"
    )
    
    subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    csv_pattern = os.path.expanduser(f"~/zr/results/z2d_64k_tuning_{timestamp}*.csv")
    csv_files = glob.glob(csv_pattern)
    
    total_ns = 0.0
    found_kernels = False
    
    for fpath in csv_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as cf:
                # 处理带有引号的 CSV
                reader = csv.DictReader(cf)
                for row in reader:
                    name = row.get("Name", "")
                    # 只统计我们关心的 FFT 内核，排除数据生成或验证的 Kernel
                    if "fft_rtc_back_len_" in name or "c2r_even_pre_" in name:
                        avg_ns = float(row.get("AverageNs", 0))
                        total_ns += avg_ns
                        found_kernels = True
        except Exception:
            pass
            
        # 解析完毕后立刻删除 csv 文件
        try:
            os.remove(fpath)
        except Exception:
            pass
            
    # ====== 新增：无情斩杀遗留的 .db 数据库文件 ======
    db_pattern = os.path.expanduser(f"~/zr/results/z2d_64k_tuning_{timestamp}*.db")
    for db_fpath in glob.glob(db_pattern):
        try:
            os.remove(db_fpath)
        except Exception:
            pass
    # =================================================
            
    if found_kernels:
        return total_ns / 1e6  # 返回转换为 ms 的时间
    else:
        # 如果所有 CSV 都找不到内核，说明运行崩溃
        return -1.0

# ================= 主逻辑 =================
def main():
    sbcc_path = os.path.join(ROCFFT_SRC_DIR, "library/src/device/kernels/configs/config_sbcc.py")
    sbrc_path = os.path.join(ROCFFT_SRC_DIR, "library/src/device/kernels/configs/config_sbrc.py")

    # 定义候选搜索空间 (使用去重算法)
    factors_128 = get_factors(128, [16, 8, 4, 2])
    factors_256 = get_factors(256, [16, 8, 4, 2])
    wgs_list = [64, 128, 256, 512, 1024]
    
    # 写 CSV 表头
    with open(CSV_OUTPUT, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Stage", "Length", "Factors", "WGS", "TPT", "GPU_Time_ms"])

    print(f"总计找到 {len(factors_128)} 种本质不同的 128 分解，{len(factors_256)} 种本质不同的 256 分解。")
    print("开始两步解耦调优...\n")

    # ================= 第一阶段：固定 128，搜索 256 =================
    print("=== 阶段 1：固定 128 为最优保底，开始爆破 256 ===")
    fixed_128_str = "NS(length=128, factors=[8,2,2,2,2], use_3steps_large_twd={'sp': 'true', 'dp': 'true'}, workgroup_size=64, threads_per_transform=64, runtime_compile=True),"
    modify_config(sbcc_path, 128, fixed_128_str)

    best_256_time = float('inf')
    best_256_config = ""

    for f256 in factors_256:
        for wgs in wgs_list:
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                # ====== 核心拦截：计算是否超过 64KB 的 LDS 上限 ======
                lds_bytes = (wgs / tpt) * 256 * 16  
                if lds_bytes > 65536:
                    continue  # 硬件不支持，直接跳过
                # ====================================================

                print(f"正在测试 256: factors={f256}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                # 开启 runtime_compile=True 进一步加快单核编译速度
                sbrc_str = f"NS(length=256, factors={f256}, scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),"
                modify_config(sbrc_path, 256, sbrc_str)
                
                if not build_rocfft():
                    print(" [编译失败/不支持]")
                    continue
                
                gpu_time = run_benchmark()
                if gpu_time > 0:
                    print(f" [成功] 耗时: {gpu_time:.4f} ms")
                    with open(CSV_OUTPUT, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow(["Stage1_256", 256, str(f256), wgs, tpt, gpu_time])
                    
                    if gpu_time < best_256_time:
                        best_256_time = gpu_time
                        best_256_config = sbrc_str
                else:
                    print(" [运行崩溃/计划创建失败]")

    # ================= 第二阶段：固定最优 256，搜索 128 =================
    if not best_256_config:
        print("未找到任何合法的 256 配置！调优中止。")
        return

    print(f"\n=== 阶段 2：固定 256 为最优 ({best_256_time:.4f} ms)，开始爆破 128 ===")
    modify_config(sbrc_path, 256, best_256_config) # 锁定最强 256

    best_128_time = float('inf')
    best_128_config = ""

    for f128 in factors_128:
        for wgs in wgs_list:
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                # ====== 核心拦截：计算是否超过 64KB 的 LDS 上限 ======
                lds_bytes = (wgs / tpt) * 128 * 16  
                if lds_bytes > 65536:
                    continue  # 硬件不支持，直接跳过
                # ====================================================

                print(f"正在测试 128: factors={f128}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                sbcc_str = f"NS(length=128, factors={f128}, use_3steps_large_twd={{'sp': 'true', 'dp': 'true'}}, workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),"
                modify_config(sbcc_path, 128, sbcc_str)
                
                if not build_rocfft():
                    print(" [编译失败/不支持]")
                    continue
                
                gpu_time = run_benchmark()
                if gpu_time > 0:
                    print(f" [成功] 耗时: {gpu_time:.4f} ms")
                    with open(CSV_OUTPUT, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow(["Stage2_128", 128, str(f128), wgs, tpt, gpu_time])
                    
                    if gpu_time < best_128_time:
                        best_128_time = gpu_time
                        best_128_config = sbcc_str
                else:
                    print(" [运行崩溃]")

    print(f"\n=== 调优结束 ===")
    print(f"最强 256 配置: {best_256_config}")
    print(f"最强 128 配置: {best_128_config}")
    print(f"全局最优耗时: {best_128_time:.4f} ms")
    print(f"所有结果已保存至 {CSV_OUTPUT}")

if __name__ == "__main__":
    main()