LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH \
 hipprof --stats -o $HOME/zr/results/z2d_tuning_$(date +%Y%m%d_%H%M%S).csv \
 $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench \
   --length 65536 \
   --batchSize 1000 \
   --precision double \
   --transformType 3 \
    -o \
    -N 10