#!/bin/bash
#SBATCH -J rocfft_prof
#SBATCH -p hx1hdexclu12
#SBATCH -N 1
#SBATCH --gres=dcu:1
#SBATCH -n 1
#SBATCH --cpus-per-task=4
#SBATCH -o prof.log
#SBATCH -e prof.err

module load compiler/rocm/dtk-23.04
source ~/miniconda3/etc/profile.d/conda.sh
conda activate fft

hipprof --stats -o test_prof.csv $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench --length 262144 --batchSize 1000 --precision double --transformType complex_forward -N 1
