#!/bin/bash
#SBATCH --job-name=compare_pad
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:1
#SBATCH --time=00:30:00
#SBATCH --output=optimizations/logs/compare_pad_%j.out
#SBATCH --error=optimizations/logs/compare_pad_%j.err

# ============================================================
# LDS padding 效果对比: baseline vs padding 1列
# 测试 z2z 512K 的 transpose kernel bank conflict 改善
# ============================================================

source ~/.bashrc
load_fft

cd /public/home/zhangkewei/zr/optimizations
mkdir -p logs results

INSTALL_LIB="$HOME/zr/install/lib"
BENCH="$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench"

echo "============================================="
echo " LDS Padding 对比 Profiling: z2z 512K"
echo " 当前状态: LDS 已应用 padding=1"
echo " Time: $(date)"
echo "============================================="

# ===================== 测试 1: 有 padding =====================
echo ""
echo ">>> 测试 1: LDS padding=1 (已应用) <<<"
T1=$(date +%Y%m%d_%H%M%S)
LD_LIBRARY_PATH="${INSTALL_LIB}:${LD_LIBRARY_PATH}" \
hipprof --stats --pmc --pmc-type 3 \
    -o "results/pad_on_${T1}.csv" \
    "$BENCH" \
    --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 3

# 提取数据
HK1="results/pad_on_${T1}.csv.hipkernel.csv"
PMC1="results/pad_on_${T1}.csv.csv"
echo "  结果: $HK1"

# ===================== 测试 2: 去掉 padding =====================
echo ""
echo ">>> 测试 2: 去掉 LDS padding <<<"
python3 patch_transpose_pad.py remove

echo "  重新编译..."
cmake --build "$HOME/zr/build/rocfft_build" -j$(nproc) --target install 2>&1 | tail -3

T2=$(date +%Y%m%d_%H%M%S)
LD_LIBRARY_PATH="${INSTALL_LIB}:${LD_LIBRARY_PATH}" \
hipprof --stats --pmc --pmc-type 3 \
    -o "results/pad_off_${T2}.csv" \
    "$BENCH" \
    --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 3

HK2="results/pad_off_${T2}.csv.hipkernel.csv"
PMC2="results/pad_off_${T2}.csv.csv"
echo "  结果: $HK2"

# ===================== 恢复 padding =====================
echo ""
echo ">>> 恢复 LDS padding <<<"
python3 patch_transpose_pad.py

echo ""
echo "============================================="
echo " 分析对比结果"
echo "============================================="

python3 -c "
import pandas as pd

def analyze(f1, f2, label):
    print(f'\n===== {label} =====')
    for tag, path in [('padding=1', f1), ('padding=0', f2)]:
        try:
            df = pd.read_csv(path)
            trans = df[df['Name'].str.contains('transpose', na=False)]
            if not trans.empty:
                t_total = trans['AverageNs'].sum() / 1e6
                bc_total = trans.get('SQ_LDS_BANK_CONFLICT', pd.Series([0])).sum() if 'SQ_LDS_BANK_CONFLICT' in df.columns else 0
                lds_total = trans.get('SQ_INSTS_LDS', pd.Series([0])).sum() if 'SQ_INSTS_LDS' in df.columns else 0
                print(f'  {tag}: transpose={t_total:.3f}ms, bank_conflicts={bc_total}, lds_insts={lds_total}')
        except Exception as e:
            print(f'  {tag}: ERROR {e}')

analyze('$HK1', '$HK2', 'z2z_512K_transpose')
"

# 如果 hipkernel 文件存在，也做个汇总
if [ -f "$HK1" ] && [ -f "$HK2" ]; then
    python3 -c "
import pandas as pd

d1 = pd.read_csv('$HK1')
d2 = pd.read_csv('$HK2')

for label, df in [('padding=1', d1), ('padding=0', d2)]:
    trans = df[df['Name'].str.contains('transpose', na=False)]
    fft = df[df['Name'].str.contains('fft_rtc', na=False)]
    t_total = trans['AverageNs'].sum()/1e6
    f_total = fft['AverageNs'].sum()/1e6
    print(f'{label}: transpose={t_total:.3f}ms, fft={f_total:.3f}ms, sum={t_total+f_total:.3f}ms')
"
fi