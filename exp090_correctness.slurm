#!/bin/bash
#SBATCH -J exp090_correct
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:45:00
#SBATCH -o logs/exp090_correctness_%j.out
#SBATCH -e logs/exp090_correctness_%j.err

set -eo pipefail

VARIANT=${1:?usage: exp090_correctness.slurm control_or_candidate}
case "${VARIANT}" in
    control|candidate) ;;
    *) echo "invalid variant: ${VARIANT}" >&2; exit 2 ;;
esac

ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
HARNESS=/public/home/zhangkewei/zr/exp-085-auto-communication-classification
INSTALL=/public/home/zhangkewei/zr/install-exp090-${VARIANT}
BUILD=/public/home/zhangkewei/zr/build/exp090_correctness_${VARIANT}
RUNNER=${BUILD}/exp090_correctness_runner
WORKDIR=${ROOT}/results/exp090_correctness_${VARIANT}_tmp_${SLURM_JOB_ID}
RESULT=${ROOT}/results/exp090_correctness_${VARIANT}_${SLURM_JOB_ID}.json

mkdir -p "${ROOT}/logs" "${ROOT}/results" "${BUILD}" "${WORKDIR}"
cd "${ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
module load anaconda3/2023.09
set -u

hipcc -std=c++17 "${HARNESS}/exp085_correctness_runner.cpp" \
    -I"${INSTALL}/include" \
    -L"${INSTALL}/lib" \
    -Wl,-rpath,"${INSTALL}/lib" \
    -lrocfft \
    -o "${RUNNER}"

export LD_LIBRARY_PATH="${INSTALL}/lib:${LD_LIBRARY_PATH:-}"
/public/software/apps/anaconda3/2023.09/bin/python "${HARNESS}/exp085_correctness.py" \
    --runner "${RUNNER}" \
    --workdir "${WORKDIR}" \
    --json "${RESULT}"

rmdir "${WORKDIR}"
printf 'variant=%s\n' "${VARIANT}"
printf 'result=%s\n' "${RESULT}"
