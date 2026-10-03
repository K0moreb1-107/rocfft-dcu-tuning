#!/bin/bash
#SBATCH -J exp091_b1_pmc
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH -o logs/exp091_batch1_pmc_%j.out
#SBATCH -e logs/exp091_batch1_pmc_%j.err

set -eo pipefail

EXP_ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
INSTALL_ROOT=/public/home/zhangkewei/zr/install-exp090-candidate
BENCH=${INSTALL_ROOT}/bin/rocfft-bench
OUT_ROOT=${EXP_ROOT}/results/exp091_batch1_pmc_${SLURM_JOB_ID}
SBCC_FILTER=len_1024_factors_8_8_4_4
SBRC_FILTER=len_512_factors_8_8_8

mkdir -p "${EXP_ROOT}/logs" "${EXP_ROOT}/results" "${OUT_ROOT}"
cd "${EXP_ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u

HIPPROF=$(command -v hipprof)
PYTHON=$(command -v python3)
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "experiment=EXP-091 phase=batch1-512k-pmc"
echo "branch=$(git branch --show-current)"
echo "record_head=$(git rev-parse HEAD)"
echo "validated_source=0473680e99b181e4660643425f53382f3a6afad7"
echo "stable_tag=stable-exp090-inverse-recurrence-fix-20260922"
echo "node=$(hostname)"
echo "start=$(date --iso-8601=seconds)"
echo "hipprof=${HIPPROF}"
sha256sum "${INSTALL_ROOT}/lib/librocfft.so.0.1" "${BENCH}"
test -x "${BENCH}"

run_pmc()
{
    local mode=$1
    local batch=$2
    local family=$3
    local kernel_filter=$4
    local round=$5
    local output=${OUT_ROOT}/${mode}_b${batch}_${family}_${round}
    local pmc_flag

    case "${mode}" in
        full) pmc_flag=--pmc ;;
        read) pmc_flag=--pmc-read ;;
        write) pmc_flag=--pmc-write ;;
        *) echo "unknown PMC mode: ${mode}" >&2; return 2 ;;
    esac

    echo "mode=${mode} batch=${batch} family=${family} filter=${kernel_filter} round=${round} start=$(date --iso-8601=seconds)"
    LD_LIBRARY_PATH="${INSTALL_ROOT}/lib:${LD_LIBRARY_PATH:-}" \
        "${HIPPROF}" --hip-trace --stats "${pmc_flag}" --pmc-type 3 \
        --kernel-name "${kernel_filter}" \
        -o "${output}" \
        "${BENCH}" \
        --length 524288 \
        --batchSize "${batch}" \
        --precision double \
        --transformType 0 \
        --notInPlace \
        -N 1
    test -s "${output}.csv"
}

# Full counter set: three independent batch=1 processes per kernel.  N=1
# produces the rocfft-bench warm-up plus one trial, so the CSV retains two
# dispatch rows and exposes first-versus-second-dispatch cache warming.
run_pmc full 1 sbcc "${SBCC_FILTER}" r1
run_pmc full 1 sbrc "${SBRC_FILTER}" r1
run_pmc full 1 sbcc "${SBCC_FILTER}" r2
run_pmc full 1 sbrc "${SBRC_FILTER}" r2
run_pmc full 1 sbcc "${SBCC_FILTER}" r3
run_pmc full 1 sbrc "${SBRC_FILTER}" r3

# Same stable binary and allocation, but legacy throughput workload.  This is
# a mechanism contrast only; it is never a batch=1 performance baseline.
run_pmc full 1000 sbcc "${SBCC_FILTER}" r1
run_pmc full 1000 sbrc "${SBRC_FILTER}" r1

# Focused request-size groups.  These runs are separate PMC replays and must
# not be treated as counters from the same physical execution as the full set.
run_pmc read 1 sbrc "${SBRC_FILTER}" r1
run_pmc read 1 sbrc "${SBRC_FILTER}" r2
run_pmc write 1 sbcc "${SBCC_FILTER}" r1
run_pmc write 1 sbcc "${SBCC_FILTER}" r2
run_pmc write 1 sbrc "${SBRC_FILTER}" r1
run_pmc write 1 sbrc "${SBRC_FILTER}" r2

"${PYTHON}" "${EXP_ROOT}/exp091_analyze_pmc.py" \
    --input-dir "${OUT_ROOT}" \
    --json "${EXP_ROOT}/results/exp091_batch1_pmc_${SLURM_JOB_ID}.json" \
    --text "${EXP_ROOT}/results/exp091_batch1_pmc_${SLURM_JOB_ID}.txt"

echo "end=$(date --iso-8601=seconds)"
