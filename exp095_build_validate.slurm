#!/bin/bash
#SBATCH -J exp095_build_check
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=03:00:00
#SBATCH -o logs/exp095_build_validate_%j.out
#SBATCH -e logs/exp095_build_validate_%j.err

set -eo pipefail
ROOT=/public/home/zhangkewei/zr/exp-095-sbrc128k-only
SOURCE=${ROOT}/rocm-libraries-rocm-7.2.2/projects/rocfft
HARNESS=/public/home/zhangkewei/zr/exp-085-auto-communication-classification
BUILD=/public/home/zhangkewei/zr/build/exp095_candidate
CANDIDATE=/public/home/zhangkewei/zr/install-exp095-candidate
OUT=${ROOT}/results/exp095_build_validate_${SLURM_JOB_ID}
RUNNER=${OUT}/exp095_correctness_runner
NUMPY_PYTHON=/public/software/apps/anaconda3/2023.09/bin/python

mkdir -p "${ROOT}/logs" "${ROOT}/results" "${BUILD}" "${CANDIDATE}" "${OUT}"
cd "${ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
module load anaconda3/2023.09
set -u

export SQLITE_3_50_2_SRC_URL=file:///public/home/zhangkewei/zr/extern/sqlite/sqlite-amalgamation-3500200.zip
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "experiment=EXP-095 phase=build_validate"
echo "node=$(hostname) start=$(date --iso-8601=seconds)"
echo "branch=$(git branch --show-current) source_head=$(git rev-parse HEAD)"
git diff --quiet
git diff --cached --quiet
sha256sum "${SOURCE}/library/src/device/generator/stockham_gen.h" \
    "${SOURCE}/library/src/device/generator/stockham_gen_base.h" \
    "${SOURCE}/library/src/rtc_stockham_kernel.cpp" \
    "${SOURCE}/library/src/rtc_stockham_gen.cpp"

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
    -DCMAKE_INSTALL_PREFIX="${CANDIDATE}"

# Catch generator C++/AST errors before committing to the full build.
cmake --build "${BUILD}" --target rocfft-rtc-gen -j16
cmake --build "${BUILD}" -- -j "$(nproc)"
cmake --install "${BUILD}"
test -x "${CANDIDATE}/bin/rocfft-bench"
sha256sum "${CANDIDATE}/lib/librocfft.so.0.1" "${CANDIDATE}/bin/rocfft-bench"

hipcc -std=c++17 "${HARNESS}/exp085_correctness_runner.cpp" \
    -I"${CANDIDATE}/include" -L"${CANDIDATE}/lib" \
    -Wl,-rpath,"${CANDIDATE}/lib" -lrocfft -o "${RUNNER}"

LD_LIBRARY_PATH="${CANDIDATE}/lib:${LD_LIBRARY_PATH:-}" \
    "${NUMPY_PYTHON}" "${HARNESS}/exp085_correctness.py" \
    --runner "${RUNNER}" \
    --workdir "${OUT}/correctness_work" \
    --json "${OUT}/correctness.json"
"${NUMPY_PYTHON}" -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["status"] == "PASS" and x["case_count"] == 32' "${OUT}/correctness.json"
echo "completed=$(date --iso-8601=seconds) correctness=${OUT}/correctness.json"
