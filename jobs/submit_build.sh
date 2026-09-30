#!/bin/bash
ZR_ROOT=/public/home/zhangkewei/zr
cd "$ZR_ROOT"
mkdir -p "$ZR_ROOT/logs/jobs/build" "$ZR_ROOT/build/tools/bin"
CURRENT_TIME=$(date +%Y%m%d_%H%M%S)

echo "Submitting build.slurm with timestamp: ${CURRENT_TIME}"
sbatch -o $ZR_ROOT/logs/jobs/build/build_fft_%j_${CURRENT_TIME}.out \
       -e $ZR_ROOT/logs/jobs/build/build_fft_%j_${CURRENT_TIME}.err \
       "$ZR_ROOT/jobs/build.slurm"
