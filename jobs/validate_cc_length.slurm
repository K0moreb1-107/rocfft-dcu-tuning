#!/bin/bash
#SBATCH --chdir=/public/home/zhangkewei/zr
#SBATCH -J validate_cc
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:20:00
#SBATCH --output=/public/home/zhangkewei/zr/logs/jobs/validate_cc_length/%x_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/logs/jobs/validate_cc_length/%x_%j.err

ZR_ROOT=/public/home/zhangkewei/zr
cd "$ZR_ROOT"
mkdir -p "$ZR_ROOT/logs/jobs/validate_cc_length" "$ZR_ROOT/build/tools/bin"
set -eo pipefail
cd "$ZR_ROOT"
source ~/.bashrc
load_fft
module load anaconda3/2023.09

LENGTH=${1:-524288}

hipcc "$ZR_ROOT/tools/validate_rocfft_length.cpp" \
    -I"$ZR_ROOT/install/include" \
    -L"$ZR_ROOT/install/lib" \
    -Wl,-rpath,"$ZR_ROOT/install/lib" \
    -lrocfft \
    -o "$ZR_ROOT/build/tools/bin/validate_rocfft_length"

LD_LIBRARY_PATH="$ZR_ROOT/install/lib:${LD_LIBRARY_PATH:-}" \
  /public/software/apps/anaconda3/2023.09/bin/python "$ZR_ROOT/tools/validate_cc_length.py" "$LENGTH"
