#!/usr/bin/env python3
import os
import re
import subprocess
import itertools
import time
import csv
import glob
from datetime import datetime
import argparse

# ================= 配置区 =================
ROCFFT_SRC_DIR = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft")
BUILD_DIR = os.path.expanduser("~/zr/build/rocfft_build")

# ================= 调优参数库 =================
TUNING_PLANS = {
    65536: [ # 64K
        {"name": "256_sbrc", "len": 256, "file": "config_sbrc.py", "tpl": "NS(length=256, factors={f}, scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=256, factors=[8,2,2,2,2,2], scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size=64, threads_per_transform=64, runtime_compile=True),"},
        {"name": "128_sbcc", "len": 128, "file": "config_sbcc.py", "tpl": "NS(length=128, factors={f}, use_3steps_large_twd={{'sp': 'true', 'dp': 'true'}}, workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=128, factors=[8,2,2,2,2], use_3steps_large_twd={'sp': 'true', 'dp': 'true'}, workgroup_size=64, threads_per_transform=64, runtime_compile=True),"}
    ],
    131072: [ # 128K
        {"name": "256_sbrc", "len": 256, "file": "config_sbrc.py", "tpl": "NS(length=256, factors={f}, scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=256, factors=[8,8,4], scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size=256, threads_per_transform=32, runtime_compile=True),"},
        {"name": "256_sbcc", "len": 256, "file": "config_sbcc.py", "tpl": "NS(length=256, factors={f}, use_3steps_large_twd={{'sp': 'true', 'dp': 'true'}}, workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=256, factors=[8,4,8], use_3steps_large_twd={'sp': 'true', 'dp': 'true'}, workgroup_size=256, threads_per_transform=32, runtime_compile=True),"}
    ],
    262144: [ # 256K
        {"name": "512_sbrc", "len": 512, "file": "config_sbrc.py", "tpl": "NS(length=512, factors={f}, scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=512, factors=[8,8,8], scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size=512, threads_per_transform=128, runtime_compile=True),"},
        {"name": "256_sbcc", "len": 256, "file": "config_sbcc.py", "tpl": "NS(length=256, factors={f}, use_3steps_large_twd={{'sp': 'true', 'dp': 'true'}}, workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=256, factors=[8,4,8], use_3steps_large_twd={'sp': 'true', 'dp': 'true'}, workgroup_size=256, threads_per_transform=32, runtime_compile=True),"}
    ],
    524288: [ # 512K
        {"name": "4096_sbrr", "len": 4096, "file": "config_sbrr.py", "tpl": "NS(length=4096, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),", "base": "NS(length=4096, workgroup_size=256, threads_per_transform=256, factors=[16,16,16], runtime_compile=True),"},
        {"name": "64_sbcc", "len": 64, "file": "config_sbcc.py", "tpl": "NS(length=64, factors={f}, use_3steps_large_twd={{'sp': 'true', 'dp': 'true'}}, workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),", "base": "NS(length=64, factors=[8,8], use_3steps_large_twd={'sp': 'true', 'dp': 'true'}, workgroup_size=256, threads_per_transform=8, runtime_compile=True),"}
    ]
}

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
    raw = get_factors_raw(n, allowed_radices)
    unique_factors = set(tuple(sorted(f, reverse=True)) for f in raw)
    return [list(f) for f in unique_factors]

def modify_config(filepath, length, new_str_template):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    import re
    # 核心修复：匹配整行，彻底替换，不留尾巴
    pattern = r"^[ \t]*NS\(\s*length=" + str(length) + r"\s*,.*$"
    new_content = re.sub(pattern, "    " + new_str_template, content, flags=re.MULTILINE)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

def build_rocfft():
    cmd_build = "cmake --build . -j$(nproc) --target install"
    res = subprocess.run(cmd_build, shell=True, cwd=BUILD_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0

def run_benchmark(target_n):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.expanduser(f"~/zr/results/z2d_tuning_{timestamp}.csv")
    
    cmd = (
        "LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH "
        f"hipprof --stats -o {csv_file} "
        "$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench "
        f"--length {target_n} --batchSize 1000 --precision double --transformType 3 -o -N 10"
    )
    
    subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    csv_pattern = os.path.expanduser(f"~/zr/results/z2d_tuning_{timestamp}*.csv")
    csv_files = glob.glob(csv_pattern)
    
    total_ns = 0.0
    found_kernels = False
    
    for fpath in csv_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as cf:
                reader = csv.DictReader(cf)
                for row in reader:
                    name = row.get("Name", "")
                    if "fft_rtc_back_len_" in name or "c2r_even_pre_" in name:
                        avg_ns = float(row.get("AverageNs", 0))
                        total_ns += avg_ns
                        found_kernels = True
        except Exception:
            pass
            
        try:
            os.remove(fpath)
        except Exception:
            pass
            
    db_pattern = os.path.expanduser(f"~/zr/results/z2d_tuning_{timestamp}*.db")
    for db_fpath in glob.glob(db_pattern):
        try:
            os.remove(db_fpath)
        except Exception:
            pass
            
    if found_kernels:
        return total_ns / 1e6
    else:
        return -1.0

# ================= 调优引擎 =================
def tune_for_N(target_n):
    print(f"\n=======================================================")
    print(f"========== 启动 N={target_n} 的两步解耦调优 ==========")
    print(f"=======================================================")
    
    csv_output = f"tuning_results_{target_n}.csv"
    with open(csv_output, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Stage", "Length", "Factors", "WGS", "TPT", "GPU_Time_ms"])
    
    plan = TUNING_PLANS.get(target_n)
    if not plan:
        print(f"不支持的 N: {target_n}")
        return
        
    stage1 = plan[0]
    stage2 = plan[1]
    
    s1_path = os.path.join(ROCFFT_SRC_DIR, f"library/src/device/kernels/configs/{stage1['file']}")
    s2_path = os.path.join(ROCFFT_SRC_DIR, f"library/src/device/kernels/configs/{stage2['file']}")
    
    factors_s1 = get_factors(stage1['len'], [16, 8, 4, 2])
    factors_s2 = get_factors(stage2['len'], [16, 8, 4, 2])
    wgs_list = [64, 128, 256, 512, 1024]
    
    print(f"Stage 1: 调优 {stage1['name']} ({len(factors_s1)} 种排列)")
    print(f"Stage 2: 调优 {stage2['name']} ({len(factors_s2)} 种排列)")

    # ================= 第一阶段：固定 Stage 2，搜索 Stage 1 =================
    print(f"\n>>> 阶段 1：固定 {stage2['name']} 为保底值，爆破 {stage1['name']} <<<")
    modify_config(s2_path, stage2['len'], stage2['base'])

    best_s1_time = float('inf')
    best_s1_config = ""

    for f1 in factors_s1:
        for wgs in wgs_list:
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                # ====== LDS 核心拦截 ======
                # 对于 SBRC 和 SBRR，bwd = wgs / tpt，计算 LDS 是否溢出 64KB (65536 bytes)
                if 'sbrc' in stage1['name'] or 'sbrr' in stage1['name']:
                    lds_bytes = (wgs / tpt) * stage1['len'] * 16  
                    if lds_bytes > 65536:
                        continue
                # ==========================

                print(f"测 {stage1['name']}: f={f1}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                s1_str = stage1['tpl'].format(f=str(f1), wgs=wgs, tpt=tpt)
                modify_config(s1_path, stage1['len'], s1_str)
                
                # 开始记录建库时间
                t0_build = time.time()
                if not build_rocfft():
                    print(" [编译失败]")
                    continue
                t_build = time.time() - t0_build
                
                # 开始记录运行时间
                t0_run = time.time()
                gpu_time = run_benchmark(target_n)
                t_run = time.time() - t0_run
                
                if gpu_time > 0:
                    print(f" [建库: {t_build:.1f}s | 运行: {t_run:.1f}s] [成功] {gpu_time:.4f} ms")
                    with open(csv_output, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow([f"N={target_n}_Stage1_{stage1['name']}", stage1['len'], str(f1), wgs, tpt, gpu_time])
                    
                    if gpu_time < best_s1_time:
                        best_s1_time = gpu_time
                        best_s1_config = s1_str
                else:
                    print(" [崩溃]")

    # ================= 第二阶段：固定最优 Stage 1，搜索 Stage 2 =================
    if not best_s1_config:
        print(f"未找到合法的 {stage1['name']} 配置！")
        return

    print(f"\n>>> 阶段 2：固定 {stage1['name']} ({best_s1_time:.4f} ms)，爆破 {stage2['name']} <<<")
    modify_config(s1_path, stage1['len'], best_s1_config) # 锁定最强 S1

    best_s2_time = float('inf')
    best_s2_config = ""

    for f2 in factors_s2:
        for wgs in wgs_list:
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                # ====== LDS 核心拦截 ======
                if 'sbrc' in stage2['name'] or 'sbrr' in stage2['name']:
                    lds_bytes = (wgs / tpt) * stage2['len'] * 16  
                    if lds_bytes > 65536:
                        continue
                # ==========================

                print(f"测 {stage2['name']}: f={f2}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                s2_str = stage2['tpl'].format(f=str(f2), wgs=wgs, tpt=tpt)
                modify_config(s2_path, stage2['len'], s2_str)
                
                # 开始记录建库时间
                t0_build = time.time()
                if not build_rocfft():
                    print(" [编译失败]")
                    continue
                t_build = time.time() - t0_build
                
                # 开始记录运行时间
                t0_run = time.time()
                gpu_time = run_benchmark(target_n)
                t_run = time.time() - t0_run
                
                if gpu_time > 0:
                    print(f" [建库: {t_build:.1f}s | 运行: {t_run:.1f}s] [成功] {gpu_time:.4f} ms")
                    with open(csv_output, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow([f"N={target_n}_Stage2_{stage2['name']}", stage2['len'], str(f2), wgs, tpt, gpu_time])
                    
                    if gpu_time < best_s2_time:
                        best_s2_time = gpu_time
                        best_s2_config = s2_str
                else:
                    print(" [崩溃]")

    print(f"\n>>> N={target_n} 调优结束 <<<")
    print(f"最强 {stage1['name']}: {best_s1_config}")
    print(f"最强 {stage2['name']}: {best_s2_config}")
    print(f"最优耗时: {best_s2_time:.4f} ms\n")

def main():
    # 枚举运行 128k, 256k, 512k 的最优寻找
    for target in [524288]:
        tune_for_N(target)

if __name__ == "__main__":
    main()