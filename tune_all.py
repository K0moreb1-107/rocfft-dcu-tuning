#!/usr/bin/env python3
import os
import re
import subprocess
import time
import csv
import glob
from datetime import datetime
import argparse

# ================= 配置区 =================
ROCFFT_SRC_DIR = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft")
BUILD_DIR = os.path.expanduser("~/zr/build/rocfft_build")

# ================= 模板区 =================
TPL_SBRC = "NS(length={l}, factors={f}, scheme='CS_KERNEL_STOCKHAM_BLOCK_RC', workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),"
TPL_SBCC = "NS(length={l}, factors={f}, use_3steps_large_twd={{'sp': 'true', 'dp': 'true'}}, workgroup_size={wgs}, threads_per_transform={tpt}, runtime_compile=True),"
TPL_SBRR = "NS(length={l}, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"

# ================= 调优参数库 (包含 d2z/z2d/z2z 各自解耦结构) =================
# 对于 d2z 和 z2d，它们的分解是一样的，所以共享一份词典
PLAN_D2Z_Z2D = {
    65536: [ # 64K
        {"name": "256_sbrc", "len": 256, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=256, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=256, f="[8,8,4]", wgs="256", tpt="32")},
        {"name": "128_sbcc", "len": 128, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=128, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=128, f="[8,4,4]", wgs="256", tpt="32")}
    ],
    131072: [ # 128K
        {"name": "256_sbrc", "len": 256, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=256, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=256, f="[8,8,4]", wgs="256", tpt="32")},
        {"name": "256_sbcc", "len": 256, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=256, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=256, f="[8,4,8]", wgs="256", tpt="32")}
    ],
    262144: [ # 256K
        {"name": "512_sbrc", "len": 512, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=512, f="[8,8,8]", wgs="512", tpt="128")},
        {"name": "512_sbcc", "len": 512, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=512, f="[8,8,8]", wgs="256", tpt="64")}
    ],
    524288: [ # 512K
        {"name": "512_sbrc", "len": 512, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=512, f="[8,8,8]", wgs="512", tpt="128")},
        {"name": "512_sbcc", "len": 512, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=512, f="[8,8,8]", wgs="256", tpt="64")}
    ]
}

PLAN_Z2Z = {
    65536: [ # 64K
        {"name": "256_sbrc", "len": 256, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=256, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=256, f="[8,8,4]", wgs="256", tpt="32")},
        {"name": "256_sbcc", "len": 256, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=256, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=256, f="[8,4,8]", wgs="256", tpt="32")}
    ],
    131072: [ # 128K
        {"name": "512_sbrc", "len": 512, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=512, f="[8,8,8]", wgs="512", tpt="128")},
        {"name": "256_sbcc", "len": 256, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=256, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=256, f="[8,4,8]", wgs="256", tpt="32")}
    ],
    262144: [ # 256K
        {"name": "512_sbrc", "len": 512, "file": "config_sbrc.py", "tpl": TPL_SBRC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRC.format(l=512, f="[8,8,8]", wgs="512", tpt="128")},
        {"name": "512_sbcc", "len": 512, "file": "config_sbcc.py", "tpl": TPL_SBCC.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBCC.format(l=512, f="[8,8,8]", wgs="256", tpt="64")}
    ],
    524288: [ # 512K (z2z切换长序列)
        {"name": "1024_sbrr", "len": 1024, "file": "config_sbrr.py", "tpl": TPL_SBRR.format(l=1024, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRR.format(l=1024, f="[8,8,4,4]", wgs="128", tpt="128")},
        {"name": "512_sbrr", "len": 512, "file": "config_sbrr.py", "tpl": TPL_SBRR.format(l=512, f="{f}", wgs="{wgs}", tpt="{tpt}"), "base": TPL_SBRR.format(l=512, f="[8,8,8]", wgs="64", tpt="64")}
    ]
}

TUNING_PLANS = {
    "d2z": PLAN_D2Z_Z2D,
    "z2d": PLAN_D2Z_Z2D,
    "z2z": PLAN_Z2Z
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
    
    # 核心修复：匹配整行或多行配置，彻底替换，不留尾巴
    pattern = r"^[ \t]*NS\(\s*length=" + str(length) + r"\s*,.*?\),"
    new_content = re.sub(pattern, "    " + new_str_template, content, flags=re.MULTILINE | re.DOTALL)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

def build_rocfft():
    cmd_build = "cmake --build . -j$(nproc) --target install"
    res = subprocess.run(cmd_build, shell=True, cwd=BUILD_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0

def run_benchmark(target_n, mode):
    # 根据当前模式转换为 rocfft-bench 的类型枚举
    # 0 = complex_forward, 1 = complex_inverse, 2 = real_forward, 3 = real_inverse
    type_map = {"z2z": 0, "d2z": 2, "z2d": 3}
    ttype = type_map.get(mode, 0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.expanduser(f"~/zr/results/{mode}_{target_n}_tuning_{timestamp}.csv")
    
    cmd = (
        "LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH "
        f"hipprof --stats -o {csv_file} "
        "$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench "
        f"--length {target_n} --batchSize 1000 --precision double --transformType {ttype} -o -N 10"
    )
    
    subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    csv_pattern = os.path.expanduser(f"~/zr/results/{mode}_{target_n}_tuning_{timestamp}*.csv")
    csv_files = glob.glob(csv_pattern)
    
    total_ns = 0.0
    found_kernels = False
    
    for fpath in csv_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as cf:
                reader = csv.DictReader(cf)
                for row in reader:
                    name = row.get("Name", "")
                    if "fft_rtc_fwd_len_" in name or "fft_rtc_back_len_" in name or "c2r_" in name or "r2c_" in name:
                        avg_ns = float(row.get("AverageNs", 0))
                        total_ns += avg_ns
                        found_kernels = True
        except Exception:
            pass
            
        try:
            os.remove(fpath)
        except Exception:
            pass
            
    db_pattern = os.path.expanduser(f"~/zr/results/{mode}_{target_n}_tuning_{timestamp}*.db")
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
def load_completed_configs(csv_output):
    completed = {}
    if os.path.exists(csv_output):
        with open(csv_output, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    mode = row.get("Mode", "")
                    stage = row.get("Stage", "")
                    factors = row.get("Factors", "")
                    wgs = int(row.get("WGS", 0))
                    tpt = int(row.get("TPT", 0))
                    time_ms = float(row.get("GPU_Time_ms", float('inf')))
                    key = (mode, stage, factors, wgs, tpt)
                    # Keep the best time if there are duplicates
                    if key not in completed or time_ms < completed[key]:
                        completed[key] = time_ms
                except ValueError:
                    continue
    return completed

def tune_for_N(target_n, mode):
    print(f"\n=======================================================")
    print(f"========== 启动 [{mode}] N={target_n} 的两步解耦调优 ==========")
    print(f"=======================================================")
    
    csv_output = f"tuning_results_{mode}_{target_n}.csv"
    if not os.path.exists(csv_output):
        with open(csv_output, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Mode", "Stage", "Length", "Factors", "WGS", "TPT", "GPU_Time_ms"])

    completed_configs = load_completed_configs(csv_output)
    if completed_configs:
        print(f"已加载历史进度：针对 [{mode}] N={target_n} 发现 {len(completed_configs)} 条记录。")
        
    plan = TUNING_PLANS.get(mode, {}).get(target_n)
    if not plan:
        print(f"不支持的模式或规模: [{mode}] N={target_n}")
        return
        
    stage1 = plan[0]
    stage2 = plan[1]
    
    s1_path = os.path.join(ROCFFT_SRC_DIR, f"library/src/device/kernels/configs/{stage1['file']}")
    s2_path = os.path.join(ROCFFT_SRC_DIR, f"library/src/device/kernels/configs/{stage2['file']}")
    
    factors_s1 = get_factors(stage1['len'], [16, 8, 4, 2])
    factors_s2 = get_factors(stage2['len'], [16, 8, 4, 2])
    # wgs从64到1024，tpt从16开始（即2**4到2**10）
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
            # tpt 从 16 开始，直到 wgs
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                # ====== LDS 核心拦截 ======
                if 'sbrc' in stage1['name'] or 'sbrr' in stage1['name']:
                    lds_bytes = (wgs / tpt) * stage1['len'] * 16  
                    if lds_bytes > 65536:
                        continue
                # ==========================
                
                s1_str = stage1['tpl'].replace("{f}", str(f1)).replace("{wgs}", str(wgs)).replace("{tpt}", str(tpt))
                
                # ====== Resume Check ======
                stage_key = f"N={target_n}_Stage1_{stage1['name']}"
                lookup_key = (mode, stage_key, str(f1), wgs, tpt)
                if lookup_key in completed_configs:
                    cached_time = completed_configs[lookup_key]
                    print(f"跳过 {stage1['name']}: f={f1}, wgs={wgs}, tpt={tpt} [已存在, 耗时 {cached_time:.4f} ms]")
                    if cached_time < best_s1_time:
                        best_s1_time = cached_time
                        best_s1_config = s1_str
                    continue
                # ==========================

                print(f"测 {stage1['name']}: f={f1}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                modify_config(s1_path, stage1['len'], s1_str)
                
                t0_build = time.time()
                if not build_rocfft():
                    print(" [编译失败]")
                    continue
                t_build = time.time() - t0_build
                
                t0_run = time.time()
                gpu_time = run_benchmark(target_n, mode)
                t_run = time.time() - t0_run
                
                if gpu_time > 0:
                    print(f" [建库: {t_build:.1f}s | 运行: {t_run:.1f}s] [成功] {gpu_time:.4f} ms")
                    with open(csv_output, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow([mode, f"N={target_n}_Stage1_{stage1['name']}", stage1['len'], str(f1), wgs, tpt, gpu_time])
                    
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
            # tpt 从 16 开始，直到 wgs
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                # ====== LDS 核心拦截 ======
                if 'sbrc' in stage2['name'] or 'sbrr' in stage2['name']:
                    lds_bytes = (wgs / tpt) * stage2['len'] * 16  
                    if lds_bytes > 65536:
                        continue
                # ==========================

                s2_str = stage2['tpl'].replace("{f}", str(f2)).replace("{wgs}", str(wgs)).replace("{tpt}", str(tpt))
                
                # ====== Resume Check ======
                stage_key = f"N={target_n}_Stage2_{stage2['name']}"
                lookup_key = (mode, stage_key, str(f2), wgs, tpt)
                if lookup_key in completed_configs:
                    cached_time = completed_configs[lookup_key]
                    print(f"跳过 {stage2['name']}: f={f2}, wgs={wgs}, tpt={tpt} [已存在, 耗时 {cached_time:.4f} ms]")
                    if cached_time < best_s2_time:
                        best_s2_time = cached_time
                        best_s2_config = s2_str
                    continue
                # ==========================

                print(f"测 {stage2['name']}: f={f2}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                modify_config(s2_path, stage2['len'], s2_str)
                
                t0_build = time.time()
                if not build_rocfft():
                    print(" [编译失败]")
                    continue
                t_build = time.time() - t0_build
                
                t0_run = time.time()
                gpu_time = run_benchmark(target_n, mode)
                t_run = time.time() - t0_run
                
                if gpu_time > 0:
                    print(f" [建库: {t_build:.1f}s | 运行: {t_run:.1f}s] [成功] {gpu_time:.4f} ms")
                    with open(csv_output, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow([mode, f"N={target_n}_Stage2_{stage2['name']}", stage2['len'], str(f2), wgs, tpt, gpu_time])
                    
                    if gpu_time < best_s2_time:
                        best_s2_time = gpu_time
                        best_s2_config = s2_str
                else:
                    print(" [崩溃]")

    print(f"\n>>> [{mode}] N={target_n} 调优结束 <<<")
    print(f"最强 {stage1['name']}: {best_s1_config}")
    print(f"最强 {stage2['name']}: {best_s2_config}")
    print(f"最优耗时: {best_s2_time:.4f} ms\n")

def main():
    # 增加命令行控制支持，默认执行所有
    parser = argparse.ArgumentParser(description="ROCFFT 全自动调优脚本")
    parser.add_argument("--mode", choices=["z2z", "d2z", "z2d", "all"], default="all", help="指定调优模式")
    parser.add_argument("--size", type=int, choices=[65536, 131072, 262144, 524288, 0], default=0, help="指定规模")
    args = parser.parse_args()

    modes = ["z2z", "d2z", "z2d"] if args.mode == "all" else [args.mode]
    sizes = [65536, 131072, 262144, 524288] if args.size == 0 else [args.size]

    for mode in modes:
        for target in sizes:
            tune_for_N(target, mode)

if __name__ == "__main__":
    main()
