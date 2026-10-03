ZR_ROOT=/public/home/zhangkewei/zr
RUN_ID="${SLURM_JOB_ID:-$(date +%Y%m%d_%H%M%S)}_$$"
RESULT_DIR="$ZR_ROOT/results/runbank/$RUN_ID"
mkdir -p "$RESULT_DIR"
cd "$ZR_ROOT"
LD_LIBRARY_PATH=$ZR_ROOT/install/lib:$LD_LIBRARY_PATH \
 hipprof --pmc \
   --pmc-type 3 \
   -o $RESULT_DIR/z2z_512k_tuning_$(date +%Y%m%d_%H%M%S).csv \
 $ZR_ROOT/build/rocfft_build/clients/staging/rocfft-bench \
   --length 524288 \
   --batchSize 1000 \
   --precision double \
   --transformType 0 \
   -o \
   -N 10