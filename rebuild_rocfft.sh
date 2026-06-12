#!/bin/bash
set -e
source ~/zr/dtk-26.04/env.sh
cd ~/zr/build/rocfft_build

# 1. 强制 cmake 重新配置（识别 config python 改动）
cmake ~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft \
  -DCMAKE_C_COMPILER=hipcc -DCMAKE_CXX_COMPILER=hipcc \
  -DGPU_TARGETS=gfx906 -DHAVE_STD_FILESYSTEM=ON \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++fs" \
  -DCMAKE_EXE_LINKER_FLAGS="-lstdc++fs" \
  -DCMAKE_PREFIX_PATH="$HOME/zr/extern/rocm-cmake;$HOME/zr/install" \
  -Dhiprtc_DIR=$HOME/zr/extern/hiprtc \
  -DCMAKE_INSTALL_PREFIX=$HOME/zr/install

# 2. 编译 + 安装
cmake --build . -j$(nproc)
cmake --install .

echo "Done."
