hipcc bench_z2d_1d.cpp \
  -o bench_z2d_1d \
  -I$HOME/zr/install/include \
  -L$HOME/zr/install/lib \
  -lrocfft -lhipfft -lm -lstdc++fs -std=c++17