#!/bin/bash
#SBATCH --job-name=exp123_retest
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=30G
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH --nodelist=f09r1n01
#SBATCH --output=/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark/exp123_rocfft_csv/logs/exp123_retest_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark/exp123_rocfft_csv/logs/exp123_retest_%j.err

set -euo pipefail

ROOT=/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark
HARNESS="$ROOT/exp123_rocfft_csv"
OFFICIAL=/public/home/zhangkewei/zr/install-exp096-official
LATEST=/public/home/zhangkewei/zr/exp122-A-install
DTK=/public/software/compiler/dtk-26.04
PYTHON=/public/software/apps/anaconda3/2023.09/bin/python
JOB="${SLURM_JOB_ID:?missing SLURM_JOB_ID}"
RAW="$HARNESS/data/outlier_retest_${JOB}"
PROVENANCE="$HARNESS/logs/exp123_retest_${JOB}.provenance"

mkdir -p "$HARNESS/bin" "$HARNESS/logs" "$RAW/csv" "$RAW/stdout" \
    "$HARNESS/tmp_retest_${JOB}"
export TMPDIR="$HARNESS/tmp_retest_${JOB}"
export PATH="$DTK/bin:${PATH}"
export HIP_PATH="$DTK"
export ROCM_PATH="$DTK"
export HIP_PLATFORM=amd
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1
export FFT_TEST_ITERS=50

{
    echo "experiment=EXP-123 paired outlier retest"
    echo "job_id=$JOB"
    echo "host=$(hostname)"
    echo "start=$(date -Is)"
    echo "source_commit=$(git -C "$ROOT" rev-parse HEAD)"
    echo "source_status_begin"
    git -C "$ROOT" status --short
    echo "source_status_end"
    echo "official=$OFFICIAL"
    sha256sum "$OFFICIAL/lib/librocfft.so.0.1"
    echo "latest=$LATEST"
    sha256sum "$LATEST/lib/librocfft.so.0.1"
    "$DTK/bin/hipcc" --version
    rocminfo | grep -m1 -A8 'Name:.*gfx' || true
} | tee "$PROVENANCE"

"$DTK/bin/hipcc" -O3 -std=c++17 "$HARNESS/src/fft_test_1d.cpp" \
    -I"$OFFICIAL/include" -L"$OFFICIAL/lib" -Wl,-rpath,"$OFFICIAL/lib" \
    -lrocfft -o "$HARNESS/bin/fft_test_1d_retest"

for arm in official latest; do
    install="$OFFICIAL"
    if [[ "$arm" == latest ]]; then
        install="$LATEST"
    fi
    {
        echo "ldd_${arm}_begin"
        env LD_LIBRARY_PATH="$install/lib:$DTK/hip/lib:$DTK/dcc/comgr/lib64:$DTK/lib" \
            LD_PRELOAD="$install/lib/librocfft.so.0.1" \
            ldd "$HARNESS/bin/fft_test_1d_retest"
        echo "ldd_${arm}_end"
    } | tee -a "$PROVENANCE"
done

run_case() {
    local arm="$1" n="$2" func="$3" round="$4" slot="$5"
    local install="$OFFICIAL"
    if [[ "$arm" == latest ]]; then
        install="$LATEST"
    fi
    local case_key="${n}_${func}"
    local out_dir="$RAW/csv/$arm/$case_key"
    local stdout_file="$RAW/stdout/${case_key}_r${round}_s${slot}_${arm}.txt"
    mkdir -p "$out_dir"
    env LD_LIBRARY_PATH="$install/lib:$DTK/hip/lib:$DTK/dcc/comgr/lib64:$DTK/lib" \
        LD_PRELOAD="$install/lib/librocfft.so.0.1" \
        FFT_TEST_OUT="$out_dir" \
        "$HARNESS/bin/fft_test_1d_retest" "$n" 1 "$func" 1 | tee "$stdout_file"
}

for case_spec in "131072 d2z_1d" "262144 z2d_1d" "524288 d2z_1d"; do
    read -r n func <<< "$case_spec"
    for round in 1 2 3 4 5 6 7 8; do
        if (( round % 2 == 1 )); then
            arms=(official latest latest official)
        else
            arms=(latest official official latest)
        fi
        slot=0
        for arm in "${arms[@]}"; do
            slot=$((slot + 1))
            run_case "$arm" "$n" "$func" "$round" "$slot"
        done
    done
done

"$PYTHON" "$HARNESS/analysis/analyze_outlier_retest.py" "$RAW"
find "$RAW" -type f ! -name raw_sha256.txt -print0 \
    | sort -z | xargs -0 sha256sum > "$RAW/raw_sha256.txt"
cat "$RAW/summary.txt" | tee -a "$PROVENANCE"
echo "end=$(date -Is)" | tee -a "$PROVENANCE"
