hipcc benchmark_z2z.hip \
  -o bench_z2z \
  -I$HOME/zr/install/include \
  -L$HOME/zr/install/lib \
  -lrocfft -lhipfft -lm -lstdc++fs -std=c++17

./bench_z2z