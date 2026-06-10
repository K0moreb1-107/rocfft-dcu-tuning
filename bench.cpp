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
    // 测试规模：2^20 (约一百万个点)
    int N = 1048576; 
    int num_iters = 100; // 测试循环次数

    std::vector<std::complex<double>> h(N, {1.0, 0.0});

    hipfftDoubleComplex *x, *y;
    CHECK_HIP(hipMalloc(&x, sizeof(hipfftDoubleComplex) * N));
    CHECK_HIP(hipMalloc(&y, sizeof(hipfftDoubleComplex) * N));
    CHECK_HIP(hipMemcpy(x, h.data(), sizeof(hipfftDoubleComplex) * N, hipMemcpyHostToDevice));

    hipfftHandle plan;
    CHECK_FFT(hipfftCreate(&plan));
    CHECK_FFT(hipfftPlan1d(&plan, N, HIPFFT_Z2Z, 1));

    // 1. 预热 (Warmup)
    // 预热非常重要，它可以排除第一次执行时的上下文初始化时间
    CHECK_FFT(hipfftExecZ2Z(plan, x, y, HIPFFT_FORWARD));
    CHECK_HIP(hipDeviceSynchronize());

    // 2. 创建计时事件
    hipEvent_t start, stop;
    CHECK_HIP(hipEventCreate(&start));
    CHECK_HIP(hipEventCreate(&stop));

    // 3. 开始计时
    CHECK_HIP(hipEventRecord(start));
    for (int i = 0; i < num_iters; i++) {
        CHECK_FFT(hipfftExecZ2Z(plan, x, y, HIPFFT_FORWARD));
    }
    CHECK_HIP(hipEventRecord(stop));
    
    // 4. 等待执行完成
    CHECK_HIP(hipEventSynchronize(stop));

    // 5. 计算时间
    float milliseconds = 0;
    CHECK_HIP(hipEventElapsedTime(&milliseconds, start, stop));
    
    float avg_ms = milliseconds / num_iters;

    std::cout << "FFT Size: " << N << std::endl;
    std::cout << "Iterations: " << num_iters << std::endl;
    std::cout << "Total Time: " << milliseconds << " ms" << std::endl;
    std::cout << "Average Time per FFT: " << avg_ms << " ms" << std::endl;

    // 释放资源
    CHECK_HIP(hipEventDestroy(start));
    CHECK_HIP(hipEventDestroy(stop));
    CHECK_FFT(hipfftDestroy(plan));
    CHECK_HIP(hipFree(x));
    CHECK_HIP(hipFree(y));

    return 0;
}