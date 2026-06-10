#!/bin/bash

echo -e "\e[36m=============================================\e[0m"
echo -e "\e[36m Compiling Benchmark (C++ OpenMP on Linux) \e[0m"
echo -e "\e[36m=============================================\e[0m"

# 使用最高优化 -O3，启用 OpenMP，并针对当前 Linux 机器的 CPU 架构优化 (-march=native)
# 注意：在 Linux 上不需要像 Windows 那样加 -fexec-charset=GBK，因为 Linux 终端默认原生就是 UTF-8 编码
g++ benchmark.cpp -o benchmark -O3 -fopenmp -march=native

# 检查编译是否成功
if [ $? -eq 0 ]; then
    echo -e "\e[32mCompilation Successful! Running Benchmark...\e[0m"
    echo ""
    # 运行编译出的程序
    ./benchmark
else
    echo -e "\e[31mCompilation Failed. Please check if g++ supports OpenMP.\e[0m"
fi
