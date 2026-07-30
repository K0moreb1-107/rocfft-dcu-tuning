#include <complex>
#include <iostream>
#include <vector>

#include <hipfft/hipfft.h>
#include <hip/hip_runtime_api.h>

#define CHECK_HIP(x) \
    do { \
        if((x) != hipSuccess){ \
            std::cerr << "HIP error: " << hipGetErrorString(x) << " at line " << __LINE__ << "\n"; \
            exit(1); \
        } \
    } while(0)

#define CHECK_FFT(x) \
    do { \
        if((x) != HIPFFT_SUCCESS){ \
            std::cerr << "HIPFFT error at line " << __LINE__ << "\n"; \
            exit(1); \
        } \
    } while(0)

int main()
{
    // 测试规模：逻辑实数序列长度为 2^20
    int N = 1048576; 
    int complex_N = N / 2 + 1; // 对应的复数输入长度
    int num_iters = 10000;

    // 1. Host 端初始化输入数据 (频域复数)
    std::vector<std::complex<double>> h_x(complex_N, {1.0, 0.0});

    // 2. 申请 Device 端内存
    hipfftDoubleComplex *x;
    double *y;  // 注意：输出是双精度实数
    CHECK_HIP(hipMalloc(&x, sizeof(hipfftDoubleComplex) * complex_N));
    CHECK_HIP(hipMalloc(&y, sizeof(double) * N));
    
    // 拷贝数据
    CHECK_HIP(hipMemcpy(x, h_x.data(), sizeof(hipfftDoubleComplex) * complex_N, hipMemcpyHostToDevice));

    // 3. 创建 Z2D Plan
    // 注意：这里的 N 传入的是逻辑实数序列的大小
    hipfftHandle plan;
    CHECK_FFT(hipfftCreate(&plan));
    CHECK_FFT(hipfftPlan1d(&plan, N, HIPFFT_Z2D, 1));

    // 4. 预热 (Warmup)
    CHECK_FFT(hipfftExecZ2D(plan, x, y));
    CHECK_HIP(hipDeviceSynchronize());

    hipEvent_t start, stop;
    CHECK_HIP(hipEventCreate(&start));
    CHECK_HIP(hipEventCreate(&stop));

    CHECK_HIP(hipEventRecord(start));
    for (int i = 0; i < num_iters; i++) {
        CHECK_FFT(hipfftExecZ2D(plan, x, y));
    }
    CHECK_HIP(hipEventRecord(stop));
    
    CHECK_HIP(hipEventSynchronize(stop));

    // 6. 计算时间
    float milliseconds = 0;
    CHECK_HIP(hipEventElapsedTime(&milliseconds, start, stop));
    float avg_ms = milliseconds / num_iters;

    std::cout << "Z2D FFT Size (Real N): " << N << std::endl;
    std::cout << "Iterations: " << num_iters << std::endl;
    std::cout << "Average Time per Z2D FFT: " << avg_ms << " ms" << std::endl;

    // 释放资源
    CHECK_HIP(hipEventDestroy(start));
    CHECK_HIP(hipEventDestroy(stop));
    CHECK_FFT(hipfftDestroy(plan));
    CHECK_HIP(hipFree(x));
    CHECK_HIP(hipFree(y));

    return 0;
}