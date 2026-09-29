#!/bin/bash
#SBATCH --job-name=exp123_csv
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=30G
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH --output=/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark/exp123_rocfft_csv/logs/exp123_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark/exp123_rocfft_csv/logs/exp123_%j.err

set -euo pipefail

ROOT=/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark
HARNESS="$ROOT/exp123_rocfft_csv"
INSTALL=/public/home/zhangkewei/zr/exp122-A-install
DTK=/public/software/compiler/dtk-26.04
PYTHON=/public/software/apps/anaconda3/2023.09/bin/python
JOB="${SLURM_JOB_ID:?missing SLURM_JOB_ID}"
RESULTS="$HARNESS/data/results_gfx936_${JOB}"
PROVENANCE="$HARNESS/logs/exp123_${JOB}.provenance"

mkdir -p "$HARNESS/bin" "$HARNESS/logs" "$RESULTS" "$HARNESS/tmp_${JOB}"
export TMPDIR="$HARNESS/tmp_${JOB}"
export PATH="$DTK/bin:${PATH}"
export HIP_PATH="$DTK"
export ROCM_PATH="$DTK"
export HIP_PLATFORM=amd
export LD_LIBRARY_PATH="$INSTALL/lib:$DTK/hip/lib:$DTK/dcc/comgr/lib64:$DTK/lib:${LD_LIBRARY_PATH:-}"
export LD_PRELOAD="$INSTALL/lib/librocfft.so.0.1"
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

{
    echo "experiment=EXP-123"
    echo "job_id=$JOB"
    echo "host=$(hostname)"
    echo "start=$(date -Is)"
    echo "source_commit=$(git -C "$ROOT" rev-parse HEAD)"
    echo "source_status_begin"
    git -C "$ROOT" status --short
    echo "source_status_end"
    echo "install=$INSTALL"
    echo "library=$(readlink -f "$INSTALL/lib/librocfft.so.0.1")"
    sha256sum "$INSTALL/lib/librocfft.so.0.1"
    "$DTK/bin/hipcc" --version
    rocminfo | grep -m1 -A8 'Name:.*gfx' || true
} | tee "$PROVENANCE"

"$DTK/bin/hipcc" -O3 -std=c++17 "$HARNESS/src/fft_test_1d.cpp" \
    -I"$INSTALL/include" -L"$INSTALL/lib" -Wl,-rpath,"$INSTALL/lib" \
    -lrocfft -o "$HARNESS/bin/fft_test_1d"

{
    echo "ldd_begin"
    ldd "$HARNESS/bin/fft_test_1d"
    echo "ldd_end"
} | tee -a "$PROVENANCE"

"$PYTHON" "$HARNESS/analysis/run_all_size_1d.py" \
    --bin "$HARNESS/bin/fft_test_1d" \
    --out-dir "$RESULTS" \
    --device-label gfx936

sha256sum "$RESULTS"/*.csv | tee -a "$PROVENANCE"
echo "end=$(date -Is)" | tee -a "$PROVENANCE"
