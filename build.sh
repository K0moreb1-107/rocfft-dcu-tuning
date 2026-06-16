#!/bin/bash
set -e

# ===================== 自动创建目录 =====================



mkdir -p $HOME/zr/logs
mkdir -p $HOME/zr/build
mkdir -p $HOME/zr/build/rocfft_build
mkdir -p $HOME/zr/build/hipfft_build
mkdir -p $HOME/zr/install

exec 1>$HOME/zr/logs/fft_test_$$.out # 标准输出
exec 2>$HOME/zr/logs/fft_test_$$.err # 错误输出

# 加载环境
source $HOME/zr/dtk-26.04/env.sh

which hipcc

# ===================== 打印开始信息 =====================
echo "====================================================="
echo "        开始编译 rocfft + hipfft (ROCm 7.2.2)         "
echo "====================================================="
echo " 家目录:         $HOME"
echo " rocfft 构建:    $HOME/zr/build/rocfft_build"
echo " hipfft 构建:    $HOME/zr/build/hipfft_build"
echo " 安装路径:       $HOME/zr/install"
echo " 开始时间:       $(date)"
echo "====================================================="


# 清理旧 build
# rm -rf $HOME/zr/build/rocfft_build/*
# rm -rf $HOME/zr/build/hipfft_build/*

# ===================== rocfft: CMake 配置 =====================
echo -e "\n[1/6] rocfft: CMake 配置 ..."

# ===================== 设置路径，避免rocm-cmake和 sqlite-amalgamation在线下载=====================
export SQLITE_3_50_2_SRC_URL=file://$HOME/zr/extern/sqlite/sqlite-amalgamation-3500200.zip

cmake -S $HOME/zr/rocm-libraries-rocm-7.2.2/projects/rocfft \
      -B $HOME/zr/build/rocfft_build \
      -DCMAKE_C_COMPILER=hipcc \
      -DCMAKE_CXX_COMPILER=hipcc \
      -DGPU_TARGETS=gfx906 \
      -DHAVE_STD_FILESYSTEM=ON \
      -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++fs" \
      -DCMAKE_EXE_LINKER_FLAGS="-lstdc++fs" \
      -DBUILD_CLIENTS_BENCH=ON \
      -DFFTW_SRC_URL="file://$HOME/zr/extern/fftw-3.3.9.tar.gz" \
      -DCMAKE_PREFIX_PATH="$HOME/zr/extern/rocm-cmake;$HOME/zr/install" \
      -Dhiprtc_DIR=$HOME/zr/extern/hiprtc \
      -DCMAKE_INSTALL_PREFIX=$HOME/zr/install

# ===================== rocfft: 编译 =====================
echo -e "\n[2/6] rocfft: 编译  ..."
cd $HOME/zr/build/rocfft_build
cmake --build . 

# ===================== rocfft: 安装 =====================
echo -e "\n[3/6] rocfft: 安装到 $HOME/zr/install ..."
cmake --install .

echo -e "\n====================================================="
echo "                rocfft 编译 + 安装 完成！              "
echo "====================================================="

# ===================== hipfft: CMake 配置 =====================
echo -e "\n[4/6] hipfft: CMake 配置 ..."
cmake \
  -S $HOME/zr/rocm-libraries-rocm-7.2.2/projects/hipfft \
  -B $HOME/zr/build/hipfft_build \
  -DCMAKE_C_COMPILER=hipcc \
  -DCMAKE_CXX_COMPILER=hipcc \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++fs" \
  -DCMAKE_EXE_LINKER_FLAGS="-lstdc++fs" \
  -DCMAKE_PREFIX_PATH="$HOME/zr/install;$HOME/zr/extern/rocm-cmake" \
  -DCMAKE_INSTALL_PREFIX=$HOME/zr/install

# ===================== hipfft: 编译 =====================
echo -e "\n[5/6] hipfft: 编译  ..."
cd $HOME/zr/build/hipfft_build
cmake --build . 
# ===================== hipfft: 安装 =====================
echo -e "\n[6/6] hipfft: 安装到 $HOME/zr/install ..."
cmake --install .

# ===================== 完成信息 =====================
echo -e "\n====================================================="
echo "            rocfft + hipfft 编译安装全部完成！         "
echo " 安装路径: $HOME/zr/install"
echo "====================================================="