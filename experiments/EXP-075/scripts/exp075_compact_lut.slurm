#!/bin/bash
#SBATCH -J exp075_compact_lut
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail
cd /public/home/zhangkewei/zr
source ~/.bashrc
load_fft
module load anaconda3/2023.09
set -u

root=/public/home/zhangkewei/zr
out="$root/results/exp075_${SLURM_JOB_ID}"
mkdir "$out"
exec > >(tee "$out/driver.log") 2>&1
trap 'rc=$?; echo "EXIT_CODE=$rc"; exit "$rc"' EXIT
python_bin=/public/software/apps/anaconda3/2023.09/bin/python
bench="$root/install/bin/rocfft-bench"
export LD_LIBRARY_PATH="$root/install/lib:${LD_LIBRARY_PATH:-}"
export ROCFFT_RTC_CACHE_READ_DISABLE=1
unset ROCFFT_LAYER ROCFFT_LOG_RTC_PATH ROCFFT_LOG_PLAN_PATH

git diff --exit-code -- rocm-libraries-rocm-7.2.2/projects/rocfft build.slurm
git rev-parse HEAD | tee "$out/commit.txt"
git show --format=fuller --stat HEAD > "$out/commit_details.txt"
git diff f9755e4f36706cf372f7b22c44470431263293d1 HEAD -- \
    rocm-libraries-rocm-7.2.2/projects/rocfft > "$out/source.patch"
hostname
echo "HIP_VISIBLE_DEVICES=${HIP_VISIBLE_DEVICES:-unset}"
echo "ROCR_VISIBLE_DEVICES=${ROCR_VISIBLE_DEVICES:-unset}"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
test "$(git rev-parse --abbrev-ref HEAD)" = exp-075-compact-late-lut
sha256sum -c exp075_previous_install.sha256
"$python_bin" exp075_checks.py prove | tee "$out/reachability.jsonl"

hipcc validate_rocfft_batch.cpp -I"$root/install/include" -L"$root/install/lib" \
    -Wl,-rpath,"$root/install/lib" -lrocfft -o "$out/validate_batch"

benchmark_phase() {
    local phase=$1 length run csv
    for run in 1 2; do
        for length in 65536 131072 262144 524288; do
            csv="$out/${phase}_${length}_r${run}.csv"
            hipprof --stats -o "$csv" "$bench" --length "$length" \
                --batchSize 1000 --precision double --transformType 0 -o -N 10 \
                > "$out/${phase}_${length}_r${run}.log" 2>&1
            test -s "$csv.hipkernel.csv"
            echo "PROFILE=$csv.hipkernel.csv"
        done
    done
}

"$python_bin" exp075_checks.py validate "$root" "$out" previous
benchmark_phase previous
sha256sum -c exp075_previous_install.sha256

bash build.slurm > "$out/build.log" 2>&1
sha256sum install/lib/librocfft.so.0.1 install/bin/rocfft-bench > "$out/candidate_install.sha256"
test "$(sha256sum install/lib/librocfft.so.0.1 | cut -d ' ' -f 1)" != \
    9873e5d9cdb8544cd0eb4f18c37b5b6d4ecd4d65bffc7843ed9c99945e620814
git diff --exit-code -- rocm-libraries-rocm-7.2.2/projects/rocfft build.slurm
"$python_bin" exp075_checks.py validate "$root" "$out" candidate
benchmark_phase candidate
"$python_bin" exp075_checks.py compare "$root" "$out" | tee "$out/comparison.jsonl"
echo "EXP075_COMPLETED=$out/comparison.json"
