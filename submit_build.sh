#!/bin/bash
CURRENT_TIME=$(date +%Y%m%d_%H%M%S)

echo "Submitting build.slurm with timestamp: ${CURRENT_TIME}"
sbatch -o logs/build_fft_%j_${CURRENT_TIME}.out \
       -e logs/build_fft_%j_${CURRENT_TIME}.err \
       build.slurm
