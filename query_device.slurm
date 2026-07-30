#!/bin/bash
#SBATCH -J query_device
#SBATCH -p hx1hdexclu12
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=00:05:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail
cd "$HOME/zr"
source ~/.bashrc
load_fft
hipcc query_device.cpp -o query_device
./query_device
