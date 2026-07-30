#!/bin/bash
#SBATCH --job-name=enum_configs_cc
#SBATCH --output=enum_cc_configs/logs/enum_%j.out
#SBATCH --error=enum_cc_configs/logs/enum_%j.err
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
# 注意: 此任务为纯 CPU 枚举, 不修改 config 文件、不编译、不运行 GPU
# 不需要 --gres=dcu, 且与你的编译/调优任务完全相互独立
cd /public/home/zhangkewei/zr/enum_cc_configs
rm -f config_enumerations.csv
mkdir -p logs
python3 enumerate_configs.py --no-resume -o config_enumerations.csv
