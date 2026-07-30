#!/bin/bash
#SBATCH --job-name=tune_cc
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:1
#SBATCH --time=30-00:00:00
#SBATCH --output=enum_cc_configs/logs/tune_%j.out
#SBATCH --error=enum_cc_configs/logs/tune_%j.err

# ============================================================
# rocFFT 自动调优 (CC 策略, 暴力枚举)
# 使用独立的 build/install 目录, 不干扰日常开发
# ============================================================

set -e

source ~/.bashrc
load_fft

TARGET_GPU="gfx936"
ENUM_DIR="/public/home/zhangkewei/zr/enum_cc_configs"
BUILD_DIR="$HOME/zr/build/tuning_cc_build"
INSTALL_DIR="$HOME/zr/install_tuning_cc"
SRC_DIR="$HOME/zr/rocm-libraries-rocm-7.2.2/projects/rocfft"
SQLITE_URL="file://$HOME/zr/extern/sqlite/sqlite-amalgamation-3500200.zip"
HIPRTC_DIR="$HOME/zr/extern/hiprtc"
ROCM_CMAKE_DIR="$HOME/zr/extern/rocm-cmake"

cd "$ENUM_DIR"
mkdir -p logs tmp

# ===================== 初始化独立 build 目录 (首次运行) =====================
if [ ! -f "$BUILD_DIR/CMakeCache.txt" ]; then
    echo "====================================================="
    echo "  首次运行: 初始化独立 build 目录"
    echo "  BUILD_DIR:  $BUILD_DIR"
    echo "  INSTALL_DIR: $INSTALL_DIR"
    echo "====================================================="
    
    rm -rf "$BUILD_DIR" "$INSTALL_DIR"
    mkdir -p "$BUILD_DIR" "$INSTALL_DIR"
    
    export SQLITE_3_50_2_SRC_URL="$SQLITE_URL"
    
    cmake -S "$SRC_DIR" \
          -B "$BUILD_DIR" \
          -DCMAKE_C_COMPILER=hipcc \
          -DCMAKE_CXX_COMPILER=hipcc \
          -DGPU_TARGETS="$TARGET_GPU" \
          -DHAVE_STD_FILESYSTEM=ON \
          -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++fs" \
          -DCMAKE_EXE_LINKER_FLAGS="-lstdc++fs" \
          -DBUILD_CLIENTS_BENCH=ON \
          -DCMAKE_PREFIX_PATH="$ROCM_CMAKE_DIR;$INSTALL_DIR" \
          -Dhiprtc_DIR="$HIPRTC_DIR" \
          -DROCFFT_BUILD_OFFLINE_TUNER=OFF \
          -DROCFFT_KERNEL_CACHE_ENABLE=OFF \
          -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
    
    echo "  cmake configure 完成"
fi

# ===================== 运行调优 =====================
export PYTHONUNBUFFERED=1

echo "开始调优: $(date)"
python3 run_tuning.py -i config_enumerations.csv -o tuning_results.csv
echo "调优完成: $(date)"