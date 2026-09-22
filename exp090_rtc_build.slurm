#!/bin/bash
#SBATCH -J exp090_rtc
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:45:00
#SBATCH -o logs/exp090_rtc_build_%j.out
#SBATCH -e logs/exp090_rtc_build_%j.err

set -eo pipefail

ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
SOURCE=${ROOT}/rocm-libraries-rocm-7.2.2/projects/rocfft
BUILD=/public/home/zhangkewei/zr/build/exp090_candidate
INSTALL=/public/home/zhangkewei/zr/install-exp090-candidate

mkdir -p "${ROOT}/logs" "${BUILD}" "${INSTALL}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u
export SQLITE_3_50_2_SRC_URL=file:///public/home/zhangkewei/zr/extern/sqlite/sqlite-amalgamation-3500200.zip

cmake -S "${SOURCE}" -B "${BUILD}" \
    -DCMAKE_C_COMPILER=hipcc \
    -DCMAKE_CXX_COMPILER=hipcc \
    -DGPU_TARGETS=gfx936 \
    -DHAVE_STD_FILESYSTEM=ON \
    -DCMAKE_SHARED_LINKER_FLAGS=-lstdc++fs \
    -DCMAKE_EXE_LINKER_FLAGS=-lstdc++fs \
    -DBUILD_CLIENTS_BENCH=ON \
    -DCMAKE_PREFIX_PATH=/public/home/zhangkewei/zr/extern/rocm-cmake \
    -Dhiprtc_DIR=/public/home/zhangkewei/zr/extern/hiprtc \
    -DROCFFT_BUILD_OFFLINE_TUNER=OFF \
    -DROCFFT_KERNEL_CACHE_ENABLE=OFF \
    -DCMAKE_INSTALL_PREFIX="${INSTALL}"

cmake --build "${BUILD}" --target rocfft-rtc-gen -- -j "$(nproc)"
printf 'EXP-090 rtc generator build complete\n'
printf 'source_head=%s\n' "$(cd "${ROOT}" && git rev-parse HEAD)"
