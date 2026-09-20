#!/bin/bash
#SBATCH -J bench_exp086_final
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=01:00:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail
ROOT="$HOME/zr/exp-078-sbrc-two-tier"
STABLE_ROOT="$ROOT"
mkdir -p "$ROOT/logs" "$ROOT/results"
source ~/.bashrc
load_fft

run_one()
{
    label="$1"
    bench="$2"
    install="$3"
    out="$ROOT/results/${label}.csv"
    echo "RUN $label"
    LD_LIBRARY_PATH="$install/lib:${LD_LIBRARY_PATH:-}" \
      hipprof --stats -o "$out" \
      "$bench" \
        --length 524288 \
        --batchSize 1000 \
        --precision double \
        --transformType 0 \
        -o \
        -N 10
}

run_one exp086_final_r1_stable "$STABLE_ROOT/build-stable/rocfft_build/clients/staging/rocfft-bench" "$STABLE_ROOT/install-stable"
run_one exp086_final_r1_candidate "$ROOT/build/rocfft_build/clients/staging/rocfft-bench" "$ROOT/install"
run_one exp086_final_r2_candidate "$ROOT/build/rocfft_build/clients/staging/rocfft-bench" "$ROOT/install"
run_one exp086_final_r2_stable "$STABLE_ROOT/build-stable/rocfft_build/clients/staging/rocfft-bench" "$STABLE_ROOT/install-stable"
