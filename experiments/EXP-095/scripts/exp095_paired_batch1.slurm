#!/bin/bash
#SBATCH -J exp095_b1_pair
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=03:00:00
#SBATCH -o logs/exp095_paired_batch1_%j.out
#SBATCH -e logs/exp095_paired_batch1_%j.err

set -eo pipefail
ROOT=/public/home/zhangkewei/zr/exp-095-sbrc128k-only
STABLE=/public/home/zhangkewei/zr/install-exp090-candidate
CANDIDATE=/public/home/zhangkewei/zr/install-exp095-candidate
OUT=${ROOT}/results/exp095_paired_batch1_${SLURM_JOB_ID}
BUILD_JOB_ID=${EXP095_BUILD_JOB_ID:?paired test requires EXP095_BUILD_JOB_ID}
CORRECTNESS=${ROOT}/results/exp095_build_validate_${BUILD_JOB_ID}/correctness.json
REPETITIONS=10000

mkdir -p "${ROOT}/logs" "${OUT}/timing"
cd "${ROOT}"
source /public/home/zhangkewei/.bashrc
load_fft
set -u
HIPPROF=$(command -v hipprof)
export ROCFFT_RTC_CACHE_READ_DISABLE=1
export ROCFFT_RTC_CACHE_WRITE_DISABLE=1

echo "experiment=EXP-095 phase=paired_batch1"
echo "node=$(hostname) start=$(date --iso-8601=seconds)"
echo "branch=$(git branch --show-current) source_head=$(git rev-parse HEAD)"
echo "batch=1 N=${REPETITIONS} divisor=$((REPETITIONS + 1)) rounds=8 hipprof=${HIPPROF}"
git diff --quiet
git diff --cached --quiet
test -x "${STABLE}/bin/rocfft-bench"
test -x "${CANDIDATE}/bin/rocfft-bench"
python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["status"] == "PASS" and x["case_count"] == 32' "${CORRECTNESS}"
STABLE_HASH=$(sha256sum "${STABLE}/lib/librocfft.so.0.1" | awk '{print $1}')
test "${STABLE_HASH}" = ad152877ba276dd70d6dbdac2e6fec454e348eb989431229f412a69f2da531a5
sha256sum "${STABLE}/lib/librocfft.so.0.1" "${CANDIDATE}/lib/librocfft.so.0.1" \
    "${STABLE}/bin/rocfft-bench" "${CANDIDATE}/bin/rocfft-bench"

run_one()
{
    local variant=$1 length=$2 round=$3 install_root output
    if [[ "${variant}" == stable ]]; then install_root=${STABLE}; else install_root=${CANDIDATE}; fi
    output=${OUT}/timing/${variant}_${length}_r${round}
    echo "timing variant=${variant} length=${length} round=${round} start=$(date --iso-8601=seconds)"
    LD_LIBRARY_PATH="${install_root}/lib:${LD_LIBRARY_PATH:-}" \
        "${HIPPROF}" --stats -o "${output}" \
        "${install_root}/bin/rocfft-bench" \
        --length "${length}" --batchSize 1 --precision double \
        --transformType 0 --notInPlace -N "${REPETITIONS}"
    test -s "${output}.hipkernel.csv"
}

for round in 1 2 3 4 5 6 7 8; do
    echo "timing_round=${round} start=$(date --iso-8601=seconds)"
    if command -v rocm-smi >/dev/null 2>&1; then
        rocm-smi --showclocks --showtemp --showpower || true
    fi
    if (( round % 2 == 0 )); then
        lengths=(524288 262144 131072 65536)
    else
        lengths=(65536 131072 262144 524288)
    fi
    for length in "${lengths[@]}"; do
        if (( round % 4 == 1 || round % 4 == 0 )); then
            run_one stable "${length}" "${round}"
            run_one candidate "${length}" "${round}"
        else
            run_one candidate "${length}" "${round}"
            run_one stable "${length}" "${round}"
        fi
    done
done

python3 "${ROOT}/exp095_analyze_paired.py" \
    --input-dir "${OUT}/timing" --json "${OUT}/paired.json" --text "${OUT}/paired.txt"
sha256sum "${OUT}"/timing/*.hipkernel.csv > "${OUT}/raw_sha256.txt"
echo "completed=$(date --iso-8601=seconds) output=${OUT}"
