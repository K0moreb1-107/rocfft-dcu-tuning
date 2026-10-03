#!/bin/bash
#SBATCH -J exp091_b1_cal
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=01:00:00
#SBATCH -o logs/exp091_batch1_calibration_%j.out
#SBATCH -e logs/exp091_batch1_calibration_%j.err

set -eo pipefail

EXP_ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
INSTALL_ROOT=/public/home/zhangkewei/zr/install-exp090-candidate
BENCH=${INSTALL_ROOT}/bin/rocfft-bench
OUT_ROOT=${EXP_ROOT}/results/exp091_batch1_calibration_${SLURM_JOB_ID}

mkdir -p "${EXP_ROOT}/logs" "${EXP_ROOT}/results" "${OUT_ROOT}"
cd "${EXP_ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u

HIPPROF=$(command -v hipprof)
PYTHON=$(command -v python3)
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "experiment=EXP-091 phase=batch1-N-calibration"
echo "branch=$(git branch --show-current)"
echo "record_head=$(git rev-parse HEAD)"
echo "validated_source=0473680e99b181e4660643425f53382f3a6afad7"
echo "stable_tag=stable-exp090-inverse-recurrence-fix-20260922"
echo "node=$(hostname)"
echo "start=$(date --iso-8601=seconds)"
echo "hipprof=${HIPPROF}"
echo "python=${PYTHON}"
sha256sum "${INSTALL_ROOT}/lib/librocfft.so.0.1" "${BENCH}"

test -x "${BENCH}"

# One unprofiled warm-up stabilizes clocks before the N sweep.  It is not part
# of any reported timing sample.
LD_LIBRARY_PATH="${INSTALL_ROOT}/lib:${LD_LIBRARY_PATH:-}" \
    "${BENCH}" \
    --length 524288 \
    --batchSize 1 \
    --precision double \
    --transformType 0 \
    --notInPlace \
    -N 200

run_one()
{
    local repetitions=$1
    local round=$2
    local output=${OUT_ROOT}/n${repetitions}_${round}

    echo "length=524288 batch=1 N=${repetitions} round=${round} start=$(date --iso-8601=seconds)"
    LD_LIBRARY_PATH="${INSTALL_ROOT}/lib:${LD_LIBRARY_PATH:-}" \
        "${HIPPROF}" --stats -o "${output}" \
        "${BENCH}" \
        --length 524288 \
        --batchSize 1 \
        --precision double \
        --transformType 0 \
        --notInPlace \
        -N "${repetitions}"
    test -s "${output}.hipkernel.csv"
}

# Balanced order limits monotonic clock/temperature drift from being confused
# with the effect of N.
run_one 100 r1
run_one 1000 r1
run_one 10000 r1
run_one 10000 r2
run_one 1000 r2
run_one 100 r2
run_one 1000 r3
run_one 100 r3
run_one 10000 r3

"${PYTHON}" "${EXP_ROOT}/exp091_analyze_batch1.py" calibration \
    --input-dir "${OUT_ROOT}" \
    --json "${EXP_ROOT}/results/exp091_batch1_calibration_${SLURM_JOB_ID}.json" \
    --text "${EXP_ROOT}/results/exp091_batch1_calibration_${SLURM_JOB_ID}.txt"

echo "end=$(date --iso-8601=seconds)"
