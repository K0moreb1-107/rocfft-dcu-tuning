#!/bin/bash
#SBATCH -J exp091_b1_base
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH -o logs/exp091_batch1_baseline_%j.out
#SBATCH -e logs/exp091_batch1_baseline_%j.err

set -eo pipefail

EXP_ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
INSTALL_ROOT=/public/home/zhangkewei/zr/install-exp090-candidate
BENCH=${INSTALL_ROOT}/bin/rocfft-bench
REPETITIONS=10000
ROUNDS=5
OUT_ROOT=${EXP_ROOT}/results/exp091_batch1_baseline_${SLURM_JOB_ID}

mkdir -p "${EXP_ROOT}/logs" "${EXP_ROOT}/results" "${OUT_ROOT}"
cd "${EXP_ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u

HIPPROF=$(command -v hipprof)
PYTHON=$(command -v python3)
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "experiment=EXP-091 phase=batch1-four-length-baseline"
echo "branch=$(git branch --show-current)"
echo "record_head=$(git rev-parse HEAD)"
echo "validated_source=0473680e99b181e4660643425f53382f3a6afad7"
echo "stable_tag=stable-exp090-inverse-recurrence-fix-20260922"
echo "node=$(hostname)"
echo "start=$(date --iso-8601=seconds)"
echo "hipprof=${HIPPROF}"
echo "N=${REPETITIONS} divisor=$((REPETITIONS + 1)) rounds=${ROUNDS}"
sha256sum "${INSTALL_ROOT}/lib/librocfft.so.0.1" "${BENCH}"
test -x "${BENCH}"

record_telemetry()
{
    local label=$1
    if command -v rocm-smi >/dev/null 2>&1; then
        echo "telemetry=${label}"
        rocm-smi --showclocks --showpower --showtemp || true
    fi
}

run_one()
{
    local length=$1
    local round=$2
    local output=${OUT_ROOT}/${length}_${round}

    echo "length=${length} batch=1 N=${REPETITIONS} round=${round} start=$(date --iso-8601=seconds)"
    record_telemetry "before_${length}_${round}"
    LD_LIBRARY_PATH="${INSTALL_ROOT}/lib:${LD_LIBRARY_PATH:-}" \
        "${HIPPROF}" --stats -o "${output}" \
        "${BENCH}" \
        --length "${length}" \
        --batchSize 1 \
        --precision double \
        --transformType 0 \
        --notInPlace \
        -N "${REPETITIONS}"
    test -s "${output}.hipkernel.csv"
    record_telemetry "after_${length}_${round}"
}

# Five balanced rounds reduce correlation between length and monotonic
# temperature/clock drift.  Each profile is an independent process.
run_one 65536 r1
run_one 131072 r1
run_one 262144 r1
run_one 524288 r1

run_one 524288 r2
run_one 262144 r2
run_one 131072 r2
run_one 65536 r2

run_one 131072 r3
run_one 524288 r3
run_one 65536 r3
run_one 262144 r3

run_one 262144 r4
run_one 65536 r4
run_one 524288 r4
run_one 131072 r4

run_one 65536 r5
run_one 262144 r5
run_one 131072 r5
run_one 524288 r5

"${PYTHON}" "${EXP_ROOT}/exp091_analyze_batch1.py" baseline \
    --input-dir "${OUT_ROOT}" \
    --repetitions "${REPETITIONS}" \
    --rounds "${ROUNDS}" \
    --json "${EXP_ROOT}/results/exp091_batch1_baseline_${SLURM_JOB_ID}.json" \
    --text "${EXP_ROOT}/results/exp091_batch1_baseline_${SLURM_JOB_ID}.txt"

echo "end=$(date --iso-8601=seconds)"
