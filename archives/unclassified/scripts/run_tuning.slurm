#!/bin/bash
#SBATCH --job-name=rocfft_tune
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:1
#SBATCH --time=333-08:00:00
#SBATCH --output=tune_all.log
#SBATCH --error=tune_all.err

# 加载必要环境（如果需要的话，例如 module load rocm）
# module load rocm/xxx

source ~/.bashrc
load_fft 

echo "Starting ROCFFT Tuning Job at $(date)"
echo "Running on node: $SLURMD_NODENAME"

# 将 python 缓冲关闭，保证实时能在 tune_all.log 看到打印结果
export PYTHONUNBUFFERED=1

# 执行自动调优脚本，覆盖全部规模和模式
python3 /public/home/scnethpc2688/zr/tune_all.py --mode all --size 0

echo "Finished ROCFFT Tuning Job at $(date)"
