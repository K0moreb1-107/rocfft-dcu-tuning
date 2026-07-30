#!/bin/bash
#SBATCH --job-name=opt_trials
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:1
#SBATCH --time=04:00:00
#SBATCH --output=optimizations/logs/trial_%j.out
#SBATCH --error=optimizations/logs/trial_%j.err

set -e

source ~/.bashrc
load_fft

cd /public/home/zhangkewei/zr/optimizations
mkdir -p logs results

BUILD_DIR="$HOME/zr/build/rocfft_build"
INSTALL_DIR="$HOME/zr/install"

# 初始化
echo "Trial,SBRR_512_AvgNs,SBRR_1024_AvgNs,Transpose_AvgNs,Total_FFT_ms" > results/trial_results.csv

TRIALS=("baseline" "trial1_wgs128_tpt64" "trial2_wgs256_tpt32" "trial3_halfLds_off" "trial4_dirReg_off" "trial5_wgs128_tpt32")

for TRIAL in "${TRIALS[@]}"; do
    echo ""
    echo "============================================="
    echo "  Trial: $TRIAL  ($(date))"
    echo "============================================="

    python3 apply_trial.py "$TRIAL"

    echo "编译..."
    cmake --build "$BUILD_DIR" -j$(nproc) --target install 2>&1 | tail -3
    BUILD_OK=$?
    if [ $BUILD_OK -ne 0 ]; then
        echo "========== 编译失败! =========="
        echo "$TRIAL,FAIL,FAIL,FAIL,FAIL" >> results/trial_results.csv
        continue
    fi

    echo "运行 benchmark..."
    T=$(date +%Y%m%d_%H%M%S)
    # NOTE: -o 参数不带 .csv 后缀，hipprof 会自动追加
    BASE="results/${TRIAL}_${T}"
    LD_LIBRARY_PATH="${INSTALL_DIR}/lib:${LD_LIBRARY_PATH}" \
    hipprof --stats --pmc --pmc-type 3 \
        -o "${BASE}" \
        "$INSTALL_DIR/../build/rocfft_build/clients/staging/rocfft-bench" \
        --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 5

    # hipprof 实际生成: ${BASE}.hipkernel.csv 等
    HK_CSV="${BASE}.hipkernel.csv"
    if [ -f "$HK_CSV" ]; then
        python3 analyze_kernel.py "$HK_CSV" "$TRIAL" results/trial_results.csv
    else
        echo "未找到: $HK_CSV"
        ls results/ | grep "$TRIAL"
        echo "$TRIAL,NOT_FOUND,NOT_FOUND,NOT_FOUND,NOT_FOUND" >> results/trial_results.csv
    fi
done

echo ""
echo "========== 完成 $(date) =========="
python3 -c "
import pandas as pd
df = pd.read_csv('results/trial_results.csv')
print()
print(df.to_string(index=False))
"