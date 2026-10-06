#!/bin/bash
#SBATCH --job-name=exp125_paired_post_g
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
set -euo pipefail
ROOT=/public/home/zhangkewei/zr
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
exec /public/software/apps/anaconda3/2023.09/bin/python "$ROOT/experiments/EXP-125/scripts/validate_paired_post_g.py" "${1:?build config required}" "${2:?validation config required}"
