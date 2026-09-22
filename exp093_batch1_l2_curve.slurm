#!/bin/bash
#SBATCH -J exp093_l2curve
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH -o logs/exp093_batch1_l2_curve_%j.out
#SBATCH -e logs/exp093_batch1_l2_curve_%j.err

set -eo pipefail

EXP_ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
INSTALL_ROOT=/public/home/zhangkewei/zr/install-exp090-candidate
BENCH=${INSTALL_ROOT}/bin/rocfft-bench
OUT_ROOT=${EXP_ROOT}/results/exp093_batch1_l2_curve_${SLURM_JOB_ID}

mkdir -p "${EXP_ROOT}/logs" "${EXP_ROOT}/results" "${OUT_ROOT}"
cd "${EXP_ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u

HIPPROF=$(command -v hipprof)
PYTHON=$(command -v python3)
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "experiment=EXP-093 phase=batch1-sbrc-l2-capacity-curve"
echo "branch=$(git branch --show-current)"
echo "record_head=$(git rev-parse HEAD)"
echo "validated_source=0473680e99b181e4660643425f53382f3a6afad7"
echo "stable_tag=stable-exp092-gfx936-capability-gate-20260923"
echo "node=$(hostname)"
echo "start=$(date --iso-8601=seconds)"
echo "hipprof=${HIPPROF}"
sha256sum "${INSTALL_ROOT}/lib/librocfft.so.0.1" "${BENCH}"
test -x "${BENCH}"

kernel_filter()
{
    case "$1" in
        65536) echo len_256_factors_4_4_4_4 ;;
        131072|262144|524288) echo len_512_factors_8_8_8 ;;
        *) echo "unsupported length: $1" >&2; return 2 ;;
    esac
}

run_pmc()
{
    local mode=$1
    local length=$2
    local round=$3
    local filter
    local pmc_flag
    local output=${OUT_ROOT}/${mode}_n${length}_r${round}

    filter=$(kernel_filter "${length}")
    case "${mode}" in
        full) pmc_flag=--pmc ;;
        read) pmc_flag=--pmc-read ;;
        *) echo "unknown PMC mode: ${mode}" >&2; return 2 ;;
    esac

    echo "mode=${mode} length=${length} intermediate_bytes=$((length * 16)) filter=${filter} round=${round} start=$(date --iso-8601=seconds)"
    LD_LIBRARY_PATH="${INSTALL_ROOT}/lib:${LD_LIBRARY_PATH:-}" \
        "${HIPPROF}" --hip-trace --stats "${pmc_flag}" --pmc-type 3 \
        --kernel-name "${filter}" \
        -o "${output}" \
        "${BENCH}" \
        --length "${length}" \
        --batchSize 1 \
        --precision double \
        --transformType 0 \
        --notInPlace \
        -N 1
    test -s "${output}.csv"
}

# Three full-counter rounds in balanced length order.  N=1 retains warm-up and
# trial as two dispatch rows.  PMC time is never used as a latency metric.
for length in 65536 131072 262144 524288; do run_pmc full "${length}" 1; done
for length in 524288 262144 131072 65536; do run_pmc full "${length}" 2; done
for length in 131072 524288 65536 262144; do run_pmc full "${length}" 3; done

# Focused EA read-request counters use separate profiler replays.
for length in 65536 131072 262144 524288; do run_pmc read "${length}" 1; done
for length in 524288 262144 131072 65536; do run_pmc read "${length}" 2; done

"${PYTHON}" "${EXP_ROOT}/exp093_analyze_l2_curve.py" \
    --input-dir "${OUT_ROOT}" \
    --json "${EXP_ROOT}/results/exp093_batch1_l2_curve_${SLURM_JOB_ID}.json" \
    --text "${EXP_ROOT}/results/exp093_batch1_l2_curve_${SLURM_JOB_ID}.txt"

echo "end=$(date --iso-8601=seconds)"
