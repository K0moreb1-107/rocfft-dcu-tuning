#!/bin/bash
#SBATCH --job-name=exp125_default_retest_i
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
set -euo pipefail
ROOT=/public/home/zhangkewei/zr
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
exec /public/software/apps/anaconda3/2023.09/bin/python "$ROOT/experiments/EXP-125/scripts/measure_default_retest_i.py" "${1:?formal config required}"
