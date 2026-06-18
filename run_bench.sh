LD_LIBRARY_PATH=$HOME/zr/install/lib:$LD_LIBRARY_PATH \
 hipprof --stats -o $HOME/zr/results/z2d_64k_tuning_$(date +%Y%m%d_%H%M%S).csv \
 $HOME/zr/build/rocfft_build/clients/staging/rocfft-bench \
   --length 131072 \
   --batchSize 1000 \
   --precision double \
   --transformType 2 \
    -o \
    -N 10