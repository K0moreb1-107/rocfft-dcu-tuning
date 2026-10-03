#!/bin/bash
#SBATCH -J pmc_exp086_final
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
mkdir -p "$ROOT/logs" "$ROOT/results/exp086_pmc_final"
source ~/.bashrc
load_fft

run_pmc()
{
    label="$1"
    bench="$2"
    install="$3"
    out="$ROOT/results/exp086_pmc_final/${label}.csv"
    echo "PMC $label"
    LD_LIBRARY_PATH="$install/lib:${LD_LIBRARY_PATH:-}" \
      hipprof --hip-trace --stats --pmc --pmc-type 3 \
        --kernel-name "len_512_factors_8_8_8" \
        -o "$out" \
        "$bench" \
          --length 524288 \
          --batchSize 1000 \
          --precision double \
          --transformType 0 \
          -o \
          -N 1
}

run_pmc stable "$STABLE_ROOT/build-stable/rocfft_build/clients/staging/rocfft-bench" "$STABLE_ROOT/install-stable"
run_pmc candidate "$ROOT/build/rocfft_build/clients/staging/rocfft-bench" "$ROOT/install"
