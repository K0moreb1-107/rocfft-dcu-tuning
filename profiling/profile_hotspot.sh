#!/bin/bash
#SBATCH --job-name=profile_fft
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=dcu:1
#SBATCH --time=01:00:00
#SBATCH --output=profiling/logs/profile_%j.out
#SBATCH --error=profiling/logs/profile_%j.err

# ============================================================
# 对 z2z_512k 热点内核进行指令级 profiling
# 采集硬件计数器: VALU/memory 占用率、L1/L2 命中率等
# ============================================================

source ~/.bashrc
load_fft

cd /public/home/zhangkewei/zr/profiling
mkdir -p logs results

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "============================================="
echo " Profiling: z2z 512K (热点内核 sbrr_512/1024)"
echo " Time: $(date)"
echo "============================================="

# ===================== 方法1: hipprof --hip-trace (详细时间线) =====================
echo ""
echo ">>> 方法1: hipprof --hip-trace <<<"
LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH \
hipprof --hip-trace --stats \
    -o results/z2z_512k_trace_${TIMESTAMP}.csv \
    $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench \
    --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 5

# rename trace db
if ls /tmp/*.db 2>/dev/null | head -1 >/dev/null; then
    for db in /tmp/*.db; do
        cp "$db" "results/z2z_512k_${TIMESTAMP}_$(basename $db)"
    done
fi

# ===================== 方法2: rocprof 硬件计数器 =====================
echo ""
echo ">>> 方法2: rocprof 硬件计数器 <<<"
if which rocprof &>/dev/null; then
    # 生成 PM4 计数器配置文件
    cat > /tmp/rocprof_counters.txt << 'EOF'
# 基础性能计数器
pmc : GRBM_COUNT
pmc : GRBM_GUI_ACTIVE
pmc : SQ_WAVES
pmc : SQ_INSTS_VALU
pmc : SQ_INSTS_SALU
pmc : SQ_INSTS_VMEM_RD
pmc : SQ_INSTS_VMEM_WR
pmc : SQ_INSTS_LDS
pmc : SQ_INSTS_FLAT
# 缓存与内存
pmc : TCP_TOTAL_CACHE_ACCESSES_sum
pmc : TCP_TCP_NA_RDREQ_CM_IS_ISSUED_sum
pmc : TCP_TCP_NA_WRREQ_CM_IS_ISSUED_sum
EOF
    
    rocprof --hip-trace --stats \
        -i /tmp/rocprof_counters.txt \
        -o results/z2z_512k_counters_${TIMESTAMP}.csv \
        $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench \
        --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 3
else
    echo "rocprof not available, skipping hardware counter collection"
fi

# ===================== 方法3: 单独 trace 生成 (离线分析) =====================
echo ""
echo ">>> 方法3: 生成 JSON trace 文件 <<<"
LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH \
hipprof --hip-trace --stats --output-type 0 \
    -o results/z2z_512k_json_${TIMESTAMP}.json \
    $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench \
    --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 3

echo ""
echo "============================================="
echo " Profiling complete at $(date)"
echo "============================================="

# 快速分析结果
echo ""
echo ">>> 快速分析: 按 AverageNs 排序 <<<"
python3 -c "
import pandas as pd, os
for f in sorted(os.listdir('results')):
    if f.endswith('.csv') and '${TIMESTAMP}' in f:
        df = pd.read_csv(os.path.join('results', f))
        print(f'\n===== {f} =====')
        kernels = df[df['Name'].str.contains('fft_rtc|sbrr|sbcc|sbrc', na=False)]
        if not kernels.empty:
            print(kernels[['Name','AverageNs','Percentage']].head(20).to_string())
        else:
            print(df.head(10).to_string())
"