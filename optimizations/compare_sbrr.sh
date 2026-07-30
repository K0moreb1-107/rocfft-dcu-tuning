#!/bin/bash
#SBATCH --job-name=compare_sbrr
#SBATCH --partition=hx1hdexclu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:1
#SBATCH --time=00:30:00
#SBATCH --output=optimizations/logs/sbrr_pad_%j.out
#SBATCH --error=optimizations/logs/sbrr_pad_%j.err

source ~/.bashrc
load_fft

cd /public/home/zhangkewei/zr/optimizations
mkdir -p logs results

SRC=~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device/generator/stockham_gen_rr.h
LIB=$HOME/zr/install/lib
BENCH=$HOME/zr/build/rocfft_build/clients/staging/rocfft-bench

echo "=== SBRR Stride Padding 对比 Profiling ==="

test_with_label() {
    local LABEL="$1"
    echo ""
    echo ">>> $LABEL <<<"
    T=$(date +%Y%m%d_%H%M%S)
    LD_LIBRARY_PATH="${LIB}:${LD_LIBRARY_PATH}" \
    hipprof --stats --pmc --pmc-type 3 \
        -o "results/sbrr_${LABEL}_${T}.csv" \
        "$BENCH" --length 524288 --batchSize 1000 --precision double --transformType 0 -o -N 3
    echo "results/sbrr_${LABEL}_${T}.csv.csv"
}

# ==== 测试 1: padding=ON (当前) ====
test_with_label "padon"

# ==== 测试 2: padding=OFF ====
echo ""
echo ">>> 关闭 SBRR padding <<<"
python3 -c "
import re
with open('$SRC') as f: c = f.read()
# 移除 get_lds_padding override
c = re.sub(r'virtual Expression get_lds_padding\(\) override\s*\{\s*return Literal\{1\};\s*\}', '', c, flags=re.MULTILINE)
with open('$SRC','w') as f: f.write(c)
print('SBRR padding OFF')
"

cmake --build "$HOME/zr/build/rocfft_build" -j$(nproc) --target install 2>&1 | tail -3

test_with_label "padoff"

# ==== 恢复 ====
echo ""
python3 -c "
import re
with open('$SRC') as f: c = f.read()
# 在 tiling_name() 后插入 padding override
c = re.sub(r'(std::string tiling_name\(\) override\s*\{\s*return "SBRR";\s*\})', r'\1\n\n    virtual Expression get_lds_padding() override { return Literal{1}; }', c, flags=re.MULTILINE)
with open('$SRC','w') as f: f.write(c)
print('SBRR padding restored')
"

echo ""
echo "=== 分析结果 ==="
python3 -c "
import csv, os
for label, pattern in [('padon', 'sbrr_padon'), ('padoff', 'sbrr_padoff')]:
    files = [f for f in os.listdir('results') if pattern in f and f.endswith('.csv.csv')]
    if not files: 
        print(f'{label}: no file found'); continue
    f = sorted(files)[-1]
    with open(f) as fp:
        reader = csv.DictReader(fp)
        fft_bc = fft_lds = fft_vmem_rd = fft_vmem_wr = fft_grbm = 0
        fft_count = 0
        for row in reader:
            name = row.get('KernelName','')
            if 'fft_rtc' in name:
                fft_bc += int(row.get('SQ_LDS_BANK_CONFLICT','0'))
                fft_lds += int(row.get('SQ_INSTS_LDS','0'))
                fft_vmem_rd += int(row.get('SQ_INSTS_VMEM_RD','0'))
                fft_vmem_wr += int(row.get('SQ_INSTS_VMEM_WR','0'))
                fft_grbm += int(row.get('GRBM_COUNT','0'))
                fft_count += 1
        print(f'{label}: FFT={fft_count}kernels, BC={fft_bc:,}, LDS={fft_lds:,}')
        if fft_lds > 0:
            print(f'  BC/LDS={fft_bc/fft_lds*100:.1f}%')
"