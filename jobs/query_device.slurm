#!/bin/bash
#SBATCH --chdir=/public/home/zhangkewei/zr
#SBATCH -J query_device
#SBATCH -p hx1hdexclu12
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:05:00
#SBATCH --output=/public/home/zhangkewei/zr/logs/jobs/query_device/%x_%j.out
#SBATCH --error=/public/home/zhangkewei/zr/logs/jobs/query_device/%x_%j.err

ZR_ROOT=/public/home/zhangkewei/zr
cd "$ZR_ROOT"
mkdir -p "$ZR_ROOT/logs/jobs/query_device" "$ZR_ROOT/build/tools/bin"
set -eo pipefail
cd "$ZR_ROOT"
source ~/.bashrc
load_fft
hipcc "$ZR_ROOT/tools/query_device.cpp" -o "$ZR_ROOT/build/tools/bin/query_device"
"$ZR_ROOT/build/tools/bin/query_device"
