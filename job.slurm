#!/bin/bash
#SBATCH -J test_fft
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#SBATCH --time=1:30:00

cd ~/zr
source ~/.bashrc
load_fft 
./runall.sh
