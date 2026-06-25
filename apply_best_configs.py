import os
import re
import subprocess

ROCFFT_SRC_DIR = os.path.expanduser("~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft")
CONFIG_FILE = os.path.join(ROCFFT_SRC_DIR, "library/src/device/kernels/configs/config_sbrr.py")
BUILD_DIR = os.path.expanduser("~/zr/build/rocfft_build")

def apply_all_rtc_configs():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ 找不到文件: {CONFIG_FILE}")
        return False

    with open(CONFIG_FILE, "r") as f:
        content = f.read()

    # 包含 128, 256, 512, 1024，全部强制挂上极限因数 + runtime_compile=True
    replacements = [
        # 128
        (r"^[ \t]*NS\(length=\s*128\s*,.*", 
         r"    NS(length= 128, workgroup_size=64, threads_per_transform=64, factors=(2, 2, 2, 2, 2, 2, 2), runtime_compile=True),"),
        # 256
        (r"^[ \t]*NS\(length=\s*256\s*,.*", 
         r"    NS(length= 256, workgroup_size=256, threads_per_transform=64, factors=(4, 4, 4, 4), runtime_compile=True),"),
        # 512
        (r"^[ \t]*NS\(length=\s*512\s*,.*", 
         r"    NS(length= 512, workgroup_size=512, threads_per_transform=256, factors=(2, 2, 2, 2, 2, 2, 2, 2, 2), runtime_compile=True),"),
        # 1024
        (r"^[ \t]*NS\(length=\s*1024\s*,.*", 
         r"    NS(length=1024, workgroup_size=1024, threads_per_transform=512, factors=(2, 2, 2, 2, 2, 2, 2, 2, 2, 2), runtime_compile=True),")
    ]

    for pattern, repl in replacements:
        content = re.sub(pattern, repl, content, flags=re.MULTILINE)

    with open(CONFIG_FILE, "w") as f:
        f.write(content)

    print("✅ 已成功将 128/256/512/1024 全部替换为调优的最佳/极限参数，并开启了 RTC！")
    return True

if __name__ == "__main__":
    if apply_all_rtc_configs():
        print("🔨 正在重新编译 rocFFT ...")
        res = subprocess.run("cmake --build . -j$(nproc) --target install", shell=True, cwd=BUILD_DIR)
        if res.returncode == 0:
            print("🚀 编译完成！你可以运行 ./runall.sh 测试了！")
        else:
            print("❌ 编译失败，请检查 CMake 报错信息。")
