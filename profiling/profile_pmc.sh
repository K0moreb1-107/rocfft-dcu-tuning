#!/bin/bash
#SBATCH --job-name=pmc_profile
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=dcu:1
#SBATCH --time=01:00:00
#SBATCH --output=profiling/logs/pmc_%j.out
#SBATCH --error=profiling/logs/pmc_%j.err

source ~/.bashrc
load_fft

cd /public/home/zhangkewei/zr/profiling
mkdir -p logs results pmc_reports

T=$(date +%Y%m%d_%H%M%S)
LIB="$HOME/zr/install/lib"
BENCH="$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench"
N=524288

echo "=== PMC Profiling z2z 512K $(date) ==="

run_pmc() {
    local tag="$1"; shift
    echo ">>> $tag <<<"
    LD_LIBRARY_PATH="${LIB}:${LD_LIBRARY_PATH}" \
    hipprof --hip-trace --stats --pmc --pmc-type 3 "$@" \
        -o "results/pmc_${tag}_${T}.csv" \
        ${BENCH} --length ${N} --batchSize 1000 --precision double --transformType 0 -o -N 5
}

# 全量 PMC
run_pmc "full"

# 读焦点
run_pmc "read" --pmc-read

# 写焦点
run_pmc "write" --pmc-write

# 逐内核
for K in "sbrr" "transpose"; do
    run_pmc "kernel_${K}" --kernel-name "${K}"
done

echo "=== Done $(date) ==="

python3 -c "
import pandas as pd, os
for f in sorted(os.listdir('results')):
    if 'pmc_' in f and '${T}' in f and f.endswith('.csv'):
        path = os.path.join('results', f)
        try:
            df = pd.read_csv(path, nrows=5)
            print(f'\n===== {f} ({len(open(path).readlines())} lines) =====')
            print(df.head(3).to_string())
        except Exception as e:
            print(f'  [skip] {f}: {e}')
"