#!/bin/bash
#SBATCH --job-name=fft_formal
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=30G
#SBATCH --gres=dcu:1
#SBATCH --time=02:00:00
#SBATCH --nodelist=f09r1n01
#SBATCH --output=/public/home/zhangkewei/zr/logs/fft_measurement/fft_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/logs/fft_measurement/fft_%j.err
set -euo pipefail
ROOT=/public/home/zhangkewei/zr
PYTHON=/public/software/apps/anaconda3/2023.09/bin/python
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
"$PYTHON" "$ROOT/tools/fft_measurement/run.py" "${1:?supply preregistration JSON absolute path}" --execute
