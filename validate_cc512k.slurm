#!/bin/bash
#SBATCH -J validate_cc512k
#SBATCH -p hx1hdexclu12
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:20:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail
cd "$HOME/zr"
source ~/.bashrc
load_fft
module load anaconda3/2023.09

hipcc validate_rocfft_512k.cpp \
    -I"$HOME/zr/install/include" \
    -L"$HOME/zr/install/lib" \
    -Wl,-rpath,"$HOME/zr/install/lib" \
    -lrocfft \
    -o validate_rocfft_512k

/public/software/apps/anaconda3/2023.09/bin/python validate_cc512k.py
