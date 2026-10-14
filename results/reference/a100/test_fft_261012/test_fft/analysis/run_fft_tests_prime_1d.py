import subprocess
import os
import sys

# ===================== PATH 配置 =====================
# 可执行文件所在目录（bin 目录绝对路径）
BIN_PATH = os.path.join("../bin/")
CSV_PATH = os.path.join("../data/results/")
# =====================================================

# ===================== 必须传入 sizes =====================
if len(sys.argv) < 2:
    print("Usage:")
    print("python run_fft_tests_prime_1d.py 65539 131111 262151 524341")
    sys.exit(1)

sizes = [int(x) for x in sys.argv[1:]]
# =====================================================

# 可执行程序路径
exe = BIN_PATH + "fft_test_1d"

# 参数集合
warmups = [1]  # False, True # always warmup


funcs = [
    #"z2z_2d",
    #"d2z_2d",
    #"z2d_2d",
    "z2z_1d",
    "d2z_1d",
    "z2d_1d",
]

# 三重循环
for is_warmup in warmups:
    print(f"\n=== Warmup = {is_warmup} ===") 

    for size in sizes:
        print(f"\n--- Size = {size} ---")

        for func in funcs:
            #cmd = [exe, str(size), str(is_warmup), func]
             # 正确构建文件名
            csv_log = f"prof_{size}_{func}_w{is_warmup}.csv"
            nvvp_trace = f"trace_{size}_{func}_w{is_warmup}.nvvp"
            analysis_prof = f"analysis_{size}_{func}_w{is_warmup}.prof"
            
            cmd = [exe, str(size), str(is_warmup), func]

            """
            cmd = [
                "nsys",
                "profile",
                "--trace=cuda",
                "--sample=none",
                "--stats=true",
                "-o", f"trace_{size}_{func}_w{is_warmup}",
                "--force-overwrite", "true",
                exe,
                str(size),
                str(is_warmup),
                func
            ]
            """

            print(f"Running: {cmd}")
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Failed: {cmd}", flush=True)
                raise

# ===================== 测试结束后重命名 CSV =====================
# 拼接 SIZE_TAG

size_tag = f"{sizes[0]}_to_{sizes[-1]}_{len(sizes)}sizes"

# size_tag = "_".join(str(s) for s in sizes)

# 原始 CSV 文件
src_csv = os.path.join(CSV_PATH, "fft_test_1d.csv")

# 新文件名
dst_csv = os.path.join(
    CSV_PATH,
    f"A100_1d_{size_tag}.csv"
)

# 重命名
if os.path.exists(src_csv):
    os.replace(src_csv, dst_csv)
    print(f"\n[INFO] CSV renamed:")
    print(f"{src_csv}")
    print("->")
    print(f"{dst_csv}")
else:
    print(f"\n[WARNING] CSV not found: {src_csv}")

