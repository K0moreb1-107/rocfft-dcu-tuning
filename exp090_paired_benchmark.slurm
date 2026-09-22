#!/bin/bash
#SBATCH -J exp090_paired
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=01:00:00
#SBATCH -o logs/exp090_paired_%j.out
#SBATCH -e logs/exp090_paired_%j.err

set -eo pipefail

ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
HARNESS=/public/home/zhangkewei/zr/exp-085-auto-communication-classification
CONTROL_INSTALL=/public/home/zhangkewei/zr/install-exp090-control
CANDIDATE_INSTALL=/public/home/zhangkewei/zr/install-exp090-candidate
OUT_ROOT=${ROOT}/results/exp090_paired_${SLURM_JOB_ID}

mkdir -p "${ROOT}/logs" "${ROOT}/results" "${OUT_ROOT}"
cd "${ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u

HIPPROF=$(command -v hipprof)
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "source_head=$(git rev-parse HEAD)"
echo "node=$(hostname)"
echo "start=$(date --iso-8601=seconds)"
echo "hipprof=${HIPPROF}"
sha256sum "${CONTROL_INSTALL}/lib/librocfft.so.0.1"
sha256sum "${CANDIDATE_INSTALL}/lib/librocfft.so.0.1"

run_one()
{
    local variant=$1
    local install_root=$2
    local length=$3
    local round=$4
    local bench=${install_root}/bin/rocfft-bench
    local output=${OUT_ROOT}/${variant}_${length}_${round}

    test -x "${bench}"
    echo "variant=${variant} length=${length} round=${round} start=$(date --iso-8601=seconds)"
    LD_LIBRARY_PATH="${install_root}/lib:${LD_LIBRARY_PATH:-}" \
        "${HIPPROF}" --stats -o "${output}" \
        "${bench}" \
        --length "${length}" \
        --batchSize 1000 \
        --precision double \
        --transformType 0 \
        --notInPlace \
        -N 10
    test -s "${output}.hipkernel.csv"
}

for length in 65536 131072 262144 524288; do
    run_one stable "${CONTROL_INSTALL}" "${length}" r1
    run_one candidate "${CANDIDATE_INSTALL}" "${length}" r1
    run_one candidate "${CANDIDATE_INSTALL}" "${length}" r2
    run_one stable "${CONTROL_INSTALL}" "${length}" r2
done

/public/software/apps/anaconda3/2023.09/bin/python "${HARNESS}/exp085_analyze_paired.py" \
    --input-dir "${OUT_ROOT}" \
    --json "${ROOT}/results/exp090_paired_${SLURM_JOB_ID}.json" \
    --text "${ROOT}/results/exp090_paired_${SLURM_JOB_ID}.txt"
