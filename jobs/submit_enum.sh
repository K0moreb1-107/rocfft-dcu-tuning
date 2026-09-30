#!/bin/bash
#SBATCH --chdir=/public/home/zhangkewei/zr
#SBATCH --job-name=enum_configs
#SBATCH --output=/public/home/zhangkewei/zr/logs/jobs/submit_enum/%x_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/logs/jobs/submit_enum/%x_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:30:00
#SBATCH --partition=normal

ZR_ROOT=/public/home/zhangkewei/zr
cd "$ZR_ROOT"
mkdir -p "$ZR_ROOT/logs/jobs/submit_enum" "$ZR_ROOT/build/tools/bin"
cd /public/home/zhangkewei/zr
mkdir -p "$ZR_ROOT/results/enumeration"
rm -f "$ZR_ROOT/results/enumeration/config_enumerations.csv"
python3 "$ZR_ROOT/tools/enumerate_configs.py" --no-resume -o "$ZR_ROOT/results/enumeration/config_enumerations.csv"