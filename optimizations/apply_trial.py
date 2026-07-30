#!/usr/bin/env python3
"""
针对 z2z 512K 进行多方向优化试验。
支持修改: config_sbrr.py + transpose tile + twiddle 步数
"""

import os, re, sys

BASE = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device")

CONFIG_SBRR = os.path.join(BASE, "kernels/configs/config_sbrr.py")
LIB_SRC = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src")
TRANSPOSE_CPP = os.path.join(LIB_SRC, "rtc_transpose_kernel.cpp")
CC_H = os.path.join(LIB_SRC, "device/generator/stockham_gen_cc.h")

TRIALS = [
    # (label, sbrr_512, sbrr_1024, tileX, tileY, tw_base, tw_steps)
    ("baseline",
     "NS(length= 512, workgroup_size= 64, threads_per_transform= 64, factors=(8, 8, 8)),",
     "NS(length=1024, workgroup_size=128, threads_per_transform=128, factors=(8, 8, 4, 4)),",
     32, 32, 8, 3),

    ("sbrr_wgs128_tpt64",
     "NS(length= 512, workgroup_size=128, threads_per_transform= 64, factors=(16, 16, 2), runtime_compile=True),",
     "NS(length=1024, workgroup_size=256, threads_per_transform= 64, factors=(16, 16, 4), runtime_compile=True),",
     32, 32, 8, 3),

    ("tile_16x16",
     "NS(length= 512, workgroup_size= 64, threads_per_transform= 64, factors=(8, 8, 8)),",
     "NS(length=1024, workgroup_size=128, threads_per_transform=128, factors=(8, 8, 4, 4)),",
     16, 16, 8, 3),

    ("tile_64x64",
     "NS(length= 512, workgroup_size= 64, threads_per_transform= 64, factors=(8, 8, 8)),",
     "NS(length=1024, workgroup_size=128, threads_per_transform=128, factors=(8, 8, 4, 4)),",
     64, 64, 8, 3),

    ("twiddle_base4_step2",
     "NS(length= 512, workgroup_size= 64, threads_per_transform= 64, factors=(8, 8, 8)),",
     "NS(length=1024, workgroup_size=128, threads_per_transform=128, factors=(8, 8, 4, 4)),",
     32, 32, 4, 2),

    ("sbrr_best_combo",
     "NS(length= 512, workgroup_size=128, threads_per_transform= 64, factors=(16, 16, 2), runtime_compile=True),",
     "NS(length=1024, workgroup_size=256, threads_per_transform= 64, factors=(16, 16, 4), runtime_compile=True),",
     64, 64, 4, 2),
]

def modify_line(filepath, pattern, replacement):
    with open(filepath, 'r') as f:
        content = f.read()
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    with open(filepath, 'w') as f:
        f.write(content)

def apply_trial(trial_label):
    for label, sbrr_512, sbrr_1024, tileX, tileY, tw_base, tw_steps in TRIALS:
        if label == trial_label:
            # 1) config_sbrr.py
            modify_line(CONFIG_SBRR,
                        r"^[ \t]*NS\(\s*length\s*=\s*512\s*,.*$",
                        "    " + sbrr_512)
            modify_line(CONFIG_SBRR,
                        r"^[ \t]*NS\(\s*length\s*=\s*1024\s*,.*$",
                        "    " + sbrr_1024)
            print(f"[config] {label}: 512/1024 已更新")

            # 2) transpose tile (rtc_transpose_kernel.cpp line 41-42)
            #    原: unsigned int tileX = node.precision == rocfft_precision_single ? 64 : 32;
            modify_line(TRANSPOSE_CPP,
                        r"unsigned int tileX = node\.precision == rocfft_precision_single \? 64 : \d+;",
                        f"unsigned int tileX = node.precision == rocfft_precision_single ? 64 : {tileX};")
            modify_line(TRANSPOSE_CPP,
                        r"unsigned int tileY = node\.precision == rocfft_precision_single \? 16 : \d+;",
                        f"unsigned int tileY = node.precision == rocfft_precision_single ? 16 : {tileY};")
            print(f"[transpose] tileX={tileX} tileY={tileY}")

            # 3) twiddle base/steps (stockham_gen_cc.h line 33-34)
            modify_line(CC_H,
                        r"large_twiddle_steps\.decl_default = \d+;",
                        f"large_twiddle_steps.decl_default = {tw_steps};")
            modify_line(CC_H,
                        r"large_twiddle_base\.decl_default  = \d+;",
                        f"large_twiddle_base.decl_default  = {tw_base};")
            print(f"[twiddle] base={tw_base} steps={tw_steps}")
            break

    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 apply_trial.py <trial_name>")
        for t in TRIALS:
            print(f"  {t[0]}")
        sys.exit(1)
    apply_trial(sys.argv[1])