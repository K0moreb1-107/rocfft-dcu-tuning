#!/bin/bash
#SBATCH --job-name=fft_managed
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
set -euo pipefail
ROOT=/public/home/zhangkewei/zr
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
if [[ "${1:-}" == measure ]]; then
    exec srun --exclusive --nodes=1 --ntasks=1 \
        --cpus-per-task="${SLURM_CPUS_PER_TASK:?CPU request missing}" --gres=dcu:1 \
        /public/software/apps/anaconda3/2023.09/bin/python "$ROOT/manage.py" \
        measure --config "${2:?frozen config required}" --worker
fi
exec /public/software/apps/anaconda3/2023.09/bin/python "$ROOT/manage.py" "${1:?task required}" --config "${2:?frozen config required}" --worker
