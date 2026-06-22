#!/bin/bash
set -e
# ===================== 自动创建结果目录 =====================
mkdir -p $HOME/zr/results
# ===================== 配置参数 =====================
LENGTHS=(65536 131072 262144 524288)
# 分别对应: 64k, 128k, 256k, 512k
# 变换类型映射
# z2z (Complex to Complex) -> 0
# d2z (Real to Complex)    -> 2
# z2d (Complex to Real)    -> 3
TYPES=("z2z" "d2z" "z2d")
TYPE_VALS=(0 2 3)
# 获取当前时间戳
DATE_STR=$(date +%Y%m%d_%H%M%S)
# ===================== 开始循环测试 =====================
for LEN in "${LENGTHS[@]}"; do
    for i in "${!TYPES[@]}"; do
        TNAME="${TYPES[$i]}"
        TVAL="${TYPE_VALS[$i]}"
        
        # 将数字长度转换为可读前缀
        if [ "$LEN" -eq 65536 ]; then
            LNAME="64k"
        elif [ "$LEN" -eq 131072 ]; then
            LNAME="128k"
        elif [ "$LEN" -eq 262144 ]; then
            LNAME="256k"
        elif [ "$LEN" -eq 524288 ]; then
            LNAME="512k"
        fi
        
        # 定义输出的 CSV 文件名
        CSV_NAME="$HOME/zr/results/${TNAME}_${LNAME}_tuning_${DATE_STR}.csv"
        
        echo "================================================="
        echo "Running Benchmark: Length = ${LNAME} (${LEN}), Type = ${TNAME}"
        echo "Output: $CSV_NAME"
        
        # 运行 profiling
        LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH \
        hipprof --stats -o "$CSV_NAME" \
        $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench \
          --length $LEN \
          --batchSize 1000 \
          --precision double \
          --transformType $TVAL \
          -o \
          -N 10
          
        # 清理多余的生成文件，只保留 Kernel 的 CSV 文件
        # hipprof 通常会生成对应的 .db 文件和 .hiptrace.csv 文件，我们直接将其删除
        DB_FILE="${CSV_NAME}.db"
        HIPTRACE_FILE="${CSV_NAME}.hiptrace.csv"
        
        if [ -f "$DB_FILE" ]; then
            echo "Cleaning up $DB_FILE..."
            rm -f "$DB_FILE"
        fi
        
        if [ -f "$HIPTRACE_FILE" ]; then
            echo "Cleaning up $HIPTRACE_FILE..."
            rm -f "$HIPTRACE_FILE"
        fi
        
    done
done
echo "================================================="
echo "所有性能测试运行完毕！CSV 结果存放在 $HOME/zr/results 目录下。"
