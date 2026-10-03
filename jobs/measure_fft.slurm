#!/bin/bash
# Submission compatibility entry: use bash, not sbatch; manage.py submits one job.
set -euo pipefail
ROOT=/public/home/zhangkewei/zr
export PYTHONDONTWRITEBYTECODE=1
exec /public/software/apps/anaconda3/2023.09/bin/python "$ROOT/manage.py" measure --config "${1:?preregistration JSON required}" --execute
