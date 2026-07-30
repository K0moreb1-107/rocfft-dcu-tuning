#!/bin/bash
#SBATCH --job-name=enum_configs
#SBATCH --output=logs/enum_configs_%j.out
#SBATCH --error=logs/enum_configs_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:30:00
#SBATCH --partition=normal

cd /public/home/zhangkewei/zr
rm -f config_enumerations.csv
python3 enumerate_configs.py --no-resume -o config_enumerations.csv