#!/bin/bash
#SBATCH -J build_exp086
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=2:00:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -e

# ===================== Create Directories =====================
mkdir -p $HOME/zr/exp-078-sbrc-two-tier/logs
mkdir -p $HOME/zr/exp-078-sbrc-two-tier/build
mkdir -p $HOME/zr/exp-078-sbrc-two-tier/build/rocfft_build
mkdir -p $HOME/zr/exp-078-sbrc-two-tier/build/hipfft_build
mkdir -p $HOME/zr/exp-078-sbrc-two-tier/install

# ===================== Load Environment =====================
# Call the custom function to load FFT env
source ~/.bashrc
load_fft
which hipcc

# [CRITICAL FIX 1] Define correct target GPU architecture for Sugon DCU
TARGET_GPU="gfx936"

# ===================== Print Info =====================
echo "====================================================="
echo "      Start building rocfft + hipfft (ROCm 7.2.2)    "
echo "====================================================="
echo " HOME Dir:       $HOME"
echo " rocfft Build:   $HOME/zr/exp-078-sbrc-two-tier/build/rocfft_build"
echo " hipfft Build:   $HOME/zr/exp-078-sbrc-two-tier/build/hipfft_build"
echo " Install Dir:    $HOME/zr/exp-078-sbrc-two-tier/install"
echo " GPU Target:     $TARGET_GPU"
echo " Slurm Job ID:   ${SLURM_JOB_ID:-none}"
echo " Start Time:     $(date)"
echo "====================================================="

# rm -rf $HOME/zr/exp-078-sbrc-two-tier/build/rocfft_build/*
# rm -rf $HOME/zr/exp-078-sbrc-two-tier/build/hipfft_build/*

# ===================== rocfft: CMake Config =====================
echo -e "\n[1/6] rocfft: CMake Config ..."

export SQLITE_3_50_2_SRC_URL=file://$HOME/zr/exp-078-sbrc-two-tier/extern/sqlite/sqlite-amalgamation-3500200.zip

cmake -S $HOME/zr/exp-078-sbrc-two-tier/rocm-libraries-rocm-7.2.2/projects/rocfft \
      -B $HOME/zr/exp-078-sbrc-two-tier/build/rocfft_build \
      -DCMAKE_C_COMPILER=hipcc \
      -DCMAKE_CXX_COMPILER=hipcc \
      -DGPU_TARGETS="$TARGET_GPU" \
      -DHAVE_STD_FILESYSTEM=ON \
      -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++fs" \
      -DCMAKE_EXE_LINKER_FLAGS="-lstdc++fs" \
      -DBUILD_CLIENTS_BENCH=ON \
      -DCMAKE_PREFIX_PATH="$HOME/zr/exp-078-sbrc-two-tier/extern/rocm-cmake;$HOME/zr/exp-078-sbrc-two-tier/install" \
      -Dhiprtc_DIR=$HOME/zr/exp-078-sbrc-two-tier/extern/hiprtc \
      -DROCFFT_BUILD_OFFLINE_TUNER=OFF \
      -DROCFFT_KERNEL_CACHE_ENABLE=OFF \
      -DCMAKE_INSTALL_PREFIX=$HOME/zr/exp-078-sbrc-two-tier/install

# ===================== rocfft: Build =====================
echo -e "\n[2/6] rocfft: Build (using all cores) ..."
cd $HOME/zr/exp-078-sbrc-two-tier/build/rocfft_build
# [CRITICAL FIX 2] Use all cores on the compute node
cmake --build . -- -j "$(nproc)"

# ===================== rocfft: Install =====================
echo -e "\n[3/6] rocfft: Install to $HOME/zr/exp-078-sbrc-two-tier/install ..."
cmake --install .

# [CRITICAL FIX 3] Disable shipped cache to avoid runtime errors
SHIPPED_CACHE="$HOME/zr/exp-078-sbrc-two-tier/install/lib/rocfft/rocfft_kernel_cache.db"
if [ -f "$SHIPPED_CACHE" ]; then
    echo "[INFO] Disabling shipped cache: $SHIPPED_CACHE"
    mv -f "$SHIPPED_CACHE" "$SHIPPED_CACHE.disabled_by_runtime_cache_workflow"
fi

echo -e "\n====================================================="
echo "           rocfft Build + Install Complete!            "
echo "====================================================="

# ===================== hipfft: CMake Config =====================
echo -e "\n[4/6] hipfft: CMake Config ..."
cmake \
  -S $HOME/zr/exp-078-sbrc-two-tier/rocm-libraries-rocm-7.2.2/projects/hipfft \
  -B $HOME/zr/exp-078-sbrc-two-tier/build/hipfft_build \
  -DCMAKE_C_COMPILER=hipcc \
  -DCMAKE_CXX_COMPILER=hipcc \
  -DGPU_TARGETS="$TARGET_GPU" \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++fs" \
  -DCMAKE_EXE_LINKER_FLAGS="-lstdc++fs" \
  -DCMAKE_PREFIX_PATH="$HOME/zr/exp-078-sbrc-two-tier/install;$HOME/zr/exp-078-sbrc-two-tier/extern/rocm-cmake" \
  -DCMAKE_INSTALL_PREFIX=$HOME/zr/exp-078-sbrc-two-tier/install

# ===================== hipfft: Build =====================
echo -e "\n[5/6] hipfft: Build (using all cores) ..."
cd $HOME/zr/exp-078-sbrc-two-tier/build/hipfft_build
cmake --build . -- -j "$(nproc)"

# ===================== hipfft: Install =====================
echo -e "\n[6/6] hipfft: Install to $HOME/zr/exp-078-sbrc-two-tier/install ..."
cmake --install .

# ===================== Final Info =====================
echo -e "\n====================================================="
echo "       rocfft + hipfft Build/Install Complete!         "
echo " Install Dir: $HOME/zr/exp-078-sbrc-two-tier/install"
echo " End Time: $(date)"
echo "====================================================="