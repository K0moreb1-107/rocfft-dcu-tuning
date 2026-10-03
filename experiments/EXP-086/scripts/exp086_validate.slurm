#!/bin/bash
#SBATCH -J valid_exp086
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:20:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail
cd "$HOME/zr/exp-078-sbrc-two-tier"
source ~/.bashrc
load_fft
module load anaconda3/2023.09

LENGTH=${1:-524288}

hipcc validate_rocfft_length.cpp \
    -I"$HOME/zr/exp-078-sbrc-two-tier/install/include" \
    -L"$HOME/zr/exp-078-sbrc-two-tier/install/lib" \
    -Wl,-rpath,"$HOME/zr/exp-078-sbrc-two-tier/install/lib" \
    -lrocfft \
    -o validate_rocfft_length

LD_LIBRARY_PATH="$HOME/zr/exp-078-sbrc-two-tier/install/lib:${LD_LIBRARY_PATH:-}" \
  /public/software/apps/anaconda3/2023.09/bin/python validate_cc_length.py "$LENGTH"
