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
CMAKE_CONCURRENCY = 16  # 核心修改：限制并发编译数量，防止内存爆满和硬盘瞬时爆满

# ================= TRTRT 物理感知调优参数库 =================
PROFILES = [
    # ============== 64K 系列 ==============
    {
        "name": "64K_z2z", "N": 65536, "types": [0],
        "stages": [
            {"name": "256_sbrr", "len": 256, "base": "NS(length= 256, workgroup_size=256, threads_per_transform=256, factors=[16,16], runtime_compile=True),", "tpl": "NS(length= 256, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    {
        "name": "64K_d2z_z2d", "N": 65536, "types": [2, 3],
        "stages": [
            {"name": "128_sbrr", "len": 128, "base": "NS(length= 128, workgroup_size=256, threads_per_transform= 16, factors=[16, 8], runtime_compile=True),", "tpl": "NS(length= 128, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"},
            {"name": "256_sbrr", "len": 256, "base": "NS(length= 256, workgroup_size=256, threads_per_transform=256, factors=[16,16], runtime_compile=True),", "tpl": "NS(length= 256, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    # ============== 128K 系列 ==============
    {
        "name": "128K_z2z", "N": 131072, "types": [0],
        "stages": [
            {"name": "256_sbrr", "len": 256, "base": "NS(length= 256, workgroup_size=256, threads_per_transform=256, factors=[16,16], runtime_compile=True),", "tpl": "NS(length= 256, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"},
            {"name": "512_sbrr", "len": 512, "base": "NS(length= 512, workgroup_size=64, threads_per_transform=64, factors=[8,8,8], runtime_compile=True),", "tpl": "NS(length= 512, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    {
        "name": "128K_d2z_z2d", "N": 131072, "types": [2, 3],
        "stages": [
            {"name": "256_sbrr", "len": 256, "base": "NS(length= 256, workgroup_size=256, threads_per_transform=256, factors=[16,16], runtime_compile=True),", "tpl": "NS(length= 256, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    # ============== 256K 系列 ==============
    {
        "name": "256K_z2z", "N": 262144, "types": [0],
        "stages": [
            {"name": "512_sbrr", "len": 512, "base": "NS(length= 512, workgroup_size=64, threads_per_transform=64, factors=[8,8,8], runtime_compile=True),", "tpl": "NS(length= 512, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    {
        "name": "256K_d2z_z2d", "N": 262144, "types": [2, 3],
        "stages": [
            {"name": "256_sbrr", "len": 256, "base": "NS(length= 256, workgroup_size=256, threads_per_transform=256, factors=[16,16], runtime_compile=True),", "tpl": "NS(length= 256, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"},
            {"name": "512_sbrr", "len": 512, "base": "NS(length= 512, workgroup_size=64, threads_per_transform=64, factors=[8,8,8], runtime_compile=True),", "tpl": "NS(length= 512, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    # ============== 512K 系列 ==============
    {
        "name": "512K_z2z", "N": 524288, "types": [0],
        "stages": [
            {"name": "512_sbrr", "len": 512, "base": "NS(length= 512, workgroup_size=64, threads_per_transform=64, factors=[8,8,8], runtime_compile=True),", "tpl": "NS(length= 512, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"},
            {"name": "1024_sbrr", "len": 1024, "base": "NS(length= 1024, workgroup_size=256, threads_per_transform=256, factors=[16,16,4], runtime_compile=True),", "tpl": "NS(length= 1024, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    },
    {
        "name": "512K_d2z_z2d", "N": 524288, "types": [2, 3],
        "stages": [
            {"name": "512_sbrr", "len": 512, "base": "NS(length= 512, workgroup_size=64, threads_per_transform=64, factors=[8,8,8], runtime_compile=True),", "tpl": "NS(length= 512, workgroup_size={wgs}, threads_per_transform={tpt}, factors={f}, runtime_compile=True),"}
        ]
    }
]

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
    
    pattern = r"^[ \t]*NS\(\s*length=\s*" + str(length) + r"\s*,.*$"
    new_content = re.sub(pattern, "    " + new_str_template, content, flags=re.MULTILINE)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

def build_rocfft():
    # 使用修改后的并发数量
    cmd_build = f"cmake --build . -j{CMAKE_CONCURRENCY} --target install"
    res = subprocess.run(cmd_build, shell=True, cwd=BUILD_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0

def run_benchmark(target_n, types):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_time_all_types = 0.0
    types_ran = 0
    
    exclude_kws = ['generate_random_interleaved', 'generate_random_real', 'impose_hermitian_symmetry', 'Total']
    
    for tval in types:
        csv_prefix = os.path.expanduser(f"~/zr/results/tune_tmp_{timestamp}_{tval}")
        csv_file = f"{csv_prefix}.csv"
        
        cmd = (
            "LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH "
            f"hipprof --stats -o {csv_file} "
            "$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench "
            f"--length {target_n} --batchSize 1000 --precision double --transformType {tval} -o -N 10"
        )
        subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        csv_files = glob.glob(f"{csv_prefix}*.csv")
        type_time = 0.0
        found_kernels = False
        
        for fpath in csv_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as cf:
                    reader = csv.DictReader(cf)
                    for row in reader:
                        name = row.get("Name", "")
                        if not name: continue
                        if any(kw in name for kw in exclude_kws): continue
                        type_time += float(row.get("TotalDurationNs", 0))
                        found_kernels = True
            except Exception: pass
                
        # 彻底清理所有中间文件
        for cleanup_fpath in glob.glob(f"{csv_prefix}*"):
            try: os.remove(cleanup_fpath)
            except Exception: pass
                    
        if found_kernels:
            total_time_all_types += (type_time / 11.0 / 1e6)
            types_ran += 1
            
    if types_ran == len(types):
        return total_time_all_types
    else:
        return -1.0

def load_completed_tasks(csv_output):
    completed = set()
    if os.path.exists(csv_output):
        with open(csv_output, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if len(row) >= 5:
                    # 记录 Stage, Length, Factors, WGS, TPT
                    task_key = (row[0], str(row[1]), row[2], str(row[3]), str(row[4]))
                    completed.add(task_key)
    return completed

# ================= 调优引擎 =================
def run_stage(profile_name, target_n, types, stage_info, s_path, csv_output, completed_tasks):
    best_time = float('inf')
    best_config = ""
    
    factors_list = get_factors(stage_info['len'], [16, 8, 4, 2])
    wgs_list = [64, 128, 256, 512, 1024]
    
    print(f"\n>>> 开始爆破 {stage_info['name']} ({len(factors_list)} 种因子排列) <<<")
    
    for f_arr in factors_list:
        for wgs in wgs_list:
            tpts = [2**i for i in range(4, 11) if 2**i <= wgs and wgs % (2**i) == 0]
            for tpt in tpts:
                lds_bytes = (wgs / tpt) * stage_info['len'] * 16  
                if lds_bytes > 65536:
                    continue
                    
                # 【断点续传核心逻辑】判断当前组合是否已经跑过了
                task_key = (f"{profile_name}_{stage_info['name']}", str(stage_info['len']), str(f_arr), str(wgs), str(tpt))
                if task_key in completed_tasks:
                    print(f"测 {stage_info['name']}: f={f_arr}, wgs={wgs}, tpt={tpt} ... [已完成，跳过]")
                    continue

                print(f"测 {stage_info['name']}: f={f_arr}, wgs={wgs}, tpt={tpt} ...", end="", flush=True)
                
                s_str = stage_info['tpl'].format(f=str(f_arr), wgs=wgs, tpt=tpt)
                modify_config(s_path, stage_info['len'], s_str)
                
                t0_build = time.time()
                if not build_rocfft():
                    print(" [编译失败]")
                    continue
                t_build = time.time() - t0_build
                
                t0_run = time.time()
                gpu_time = run_benchmark(target_n, types)
                t_run = time.time() - t0_run
                
                if gpu_time > 0:
                    print(f" [建库: {t_build:.1f}s | 运行: {t_run:.1f}s] [成功] 综合耗时: {gpu_time:.4f} ms")
                    # 使用追加模式 'a'，保护已有的数据
                    with open(csv_output, 'a', newline='') as csvfile:
                        csv.writer(csvfile).writerow([f"{profile_name}_{stage_info['name']}", stage_info['len'], str(f_arr), wgs, tpt, gpu_time])
                    
                    if gpu_time < best_time:
                        best_time = gpu_time
                        best_config = s_str
                else:
                    print(" [崩溃]")
                    
    return best_time, best_config

def tune_profile(profile):
    print(f"\n=======================================================")
    print(f"========== 启动 {profile['name']} 任务组调优 ==========")
    print(f"========== N={profile['N']}, 涉及类型={profile['types']} ==========")
    print(f"=======================================================")
    
    csv_output = f"trtrt_tuning_results_{profile['name']}.csv"
    
    # 如果文件不存在，先写个表头
    if not os.path.exists(csv_output):
        with open(csv_output, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Stage", "Length", "Factors", "WGS", "TPT", "Total_Time_ms"])
            
    completed_tasks = load_completed_tasks(csv_output)
    
    s_path = os.path.join(ROCFFT_SRC_DIR, "library/src/device/kernels/configs/config_sbrr.py")
    stages = profile['stages']
    
    if len(stages) > 1:
        stage1 = stages[0]
        stage2 = stages[1]
        
        modify_config(s_path, stage2['len'], stage2['base'])
        best_s1_time, best_s1_config = run_stage(profile['name'], profile['N'], profile['types'], stage1, s_path, csv_output, completed_tasks)
        
        if not best_s1_config:
            # 说明可能之前就跑完了，去找目前最优的
            print(f"当前阶段无需新跑或失败。如果有历史最优值，将通过历史数据选择。")
        
        # 实际情况为了简单，如果阶段断点了，可能需要手动调整。
        # 但我们加入了自动跳过，他会跳过已存在的，并接着找。
        print(f"\n--- 锁定 {stage1['name']} 最强配置并进入下一阶段 ---")
        if best_s1_config:
            modify_config(s_path, stage1['len'], best_s1_config)
            
        best_s2_time, best_s2_config = run_stage(profile['name'], profile['N'], profile['types'], stage2, s_path, csv_output, completed_tasks)
        
        print(f"\n>>> {profile['name']} 调优结束 <<<")
        
    else:
        stage1 = stages[0]
        best_s1_time, best_s1_config = run_stage(profile['name'], profile['N'], profile['types'], stage1, s_path, csv_output, completed_tasks)
        print(f"\n>>> {profile['name']} 调优结束 <<<")

def main():
    for p in PROFILES:
        tune_profile(p)

if __name__ == "__main__":
    main()
