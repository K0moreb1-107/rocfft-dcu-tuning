#!/bin/bash
#SBATCH --chdir=/public/home/zhangkewei/zr
#SBATCH -J test_fft
#SBATCH -p hx1hdexclu12
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --output=/public/home/zhangkewei/zr/logs/jobs/job_bank/%x_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/logs/jobs/job_bank/%x_%j.err
#SBATCH --time=1:30:00

ZR_ROOT=/public/home/zhangkewei/zr
cd "$ZR_ROOT"
mkdir -p "$ZR_ROOT/logs/jobs/job_bank" "$ZR_ROOT/build/tools/bin"
cd ~/zr
source ~/.bashrc
load_fft
"$ZR_ROOT/tools/runbank.sh"
