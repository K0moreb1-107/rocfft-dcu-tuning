#!/bin/bash
#SBATCH -J run_bench
#SBATCH -p hx1hdnormal01
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --gres=dcu:1
#SBATCH --time=2:00:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -eo pipefail

# 接收传入的参数，如果不传则使用默认值
LENGTH=${1:-524288}         # 默认长度 524288
BATCH=${2:-1000}            # 默认 Batch 1000
TRANSFORM_TYPE=${3:-0}      # 默认变换类型 0 (z2z)
TAG=${4:-cc512k}            # 用于区分本次机制原型

mkdir -p "$HOME/zr/logs" "$HOME/zr/results"

source ~/.bashrc
load_fft
set -u

BENCH="$HOME/zr/install/bin/rocfft-bench"
HIPPROF=$(command -v hipprof)

if [ ! -x "$BENCH" ]; then
    echo "rocfft-bench not found or not executable: $BENCH" >&2
    exit 1
fi

# 1. 自动转换变换类型名称
if [ "$TRANSFORM_TYPE" -eq 0 ]; then
    TYPE_STR="z2z"
elif [ "$TRANSFORM_TYPE" -eq 2 ]; then
    TYPE_STR="d2z"
elif [ "$TRANSFORM_TYPE" -eq 3 ]; then
    TYPE_STR="z2d"
else
    TYPE_STR="type${TRANSFORM_TYPE}"
fi

# 2. 自动转换长度为 K 级别名称（让文件名更好看）
if [ "$LENGTH" -eq 524288 ]; then
    LEN_STR="512k"
elif [ "$LENGTH" -eq 262144 ]; then
    LEN_STR="256k"
elif [ "$LENGTH" -eq 131072 ]; then
    LEN_STR="128k"
elif [ "$LENGTH" -eq 65536 ]; then
    LEN_STR="64k"
else
    LEN_STR="${LENGTH}"
fi

# 3. 动态拼接文件名
CSV_NAME="${TYPE_STR}_${LEN_STR}_b${BATCH}_${TAG}_$(date +%Y%m%d_%H%M%S).csv"
OUT_PATH="$HOME/zr/results/$CSV_NAME"

echo "=========================================================="
echo " Running rocfft-bench"
echo " Length: $LENGTH ($LEN_STR) | Batch: $BATCH | Type: $TYPE_STR"
echo " Output: $OUT_PATH"
echo "=========================================================="

# 4. 执行原有的 hipprof 测试命令
LD_LIBRARY_PATH="$HOME/zr/install/lib:${LD_LIBRARY_PATH:-}" \
 "$HIPPROF" --stats -o "$OUT_PATH" \
 "$BENCH" \
   --length "$LENGTH" \
   --batchSize "$BATCH" \
   --precision double \
   --transformType "$TRANSFORM_TYPE" \
   -o \
   -N 10

# 5. 清理多余的原始 Trace 和 DB 文件，只保留 .hipkernel.csv 统计文件
echo "Cleaning up raw trace files..."
rm -f "${OUT_PATH}.db"
rm -f "${OUT_PATH}.hiptrace.csv"

echo "Done! Cleaned up trace files, kept only ${OUT_PATH}.hipkernel.csv"
