#!/bin/bash
#SBATCH -J isa_exp086_guard
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:20:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail
ROOT="$HOME/zr/exp-078-sbrc-two-tier"
cd "$ROOT"
source ~/.bashrc
load_fft
HELPER="$ROOT/build/rocfft_build/library/src/rocfft_rtc_helper"
READELF="/public/software/compiler/dtk-26.04/dcc/bin/llvm-readelf"
for label in stable candidate; do
  "$HELPER" gfx936 < "results/exp086_isa_guard/${label}.cpp" > "results/exp086_isa_guard/${label}.co"
  "$READELF" -S -n "results/exp086_isa_guard/${label}.co" > "results/exp086_isa_guard/${label}.readelf"
done
wc -c results/exp086_isa_guard/*.co
