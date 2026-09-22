#!/bin/bash
#SBATCH -J exp092_caps
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:10:00
#SBATCH -o logs/exp092_device_caps_%j.out
#SBATCH -e logs/exp092_device_caps_%j.err

set -eo pipefail

EXP_ROOT=/public/home/zhangkewei/zr/exp-078-sbrc-two-tier
SOURCE=${EXP_ROOT}/exp092_query_device_capabilities.cpp
OUT_DIR=${EXP_ROOT}/results/exp092_device_caps_${SLURM_JOB_ID}
BINARY=${OUT_DIR}/exp092_query_device_capabilities
RESULT=${EXP_ROOT}/results/exp092_device_caps_${SLURM_JOB_ID}.txt

mkdir -p "${EXP_ROOT}/logs" "${EXP_ROOT}/results" "${OUT_DIR}"
cd "${EXP_ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u

echo "experiment=EXP-092 phase=gfx936-device-capability-query"
echo "branch=$(git branch --show-current)"
echo "record_head=$(git rev-parse HEAD)"
echo "node=$(hostname)"
echo "start=$(date --iso-8601=seconds)"
echo "hipcc=$(command -v hipcc)"

hipcc -std=c++17 -O2 "${SOURCE}" -o "${BINARY}"
"${BINARY}" > "${RESULT}"
cat "${RESULT}"

echo "result=${RESULT}"
echo "end=$(date --iso-8601=seconds)"
