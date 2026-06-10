#include <complex>
#include <iostream>
#include <vector>
#include <string>
#include <fstream>
#include <cstdlib>
#include <sys/stat.h>
#include <filesystem>

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
    int N = 64;
    auto p = std::filesystem::current_path();
    
    // 1. 初始化 Host 数据
    std::vector<std::complex<double>> h(N);
    for(int i = 0; i < N; i++) {
        h[i] = { (double)i, 0.0 };  // 实部为 i，虚部为 0
    }

    // 2. 声明 Device 指针
    hipfftDoubleComplex *x, *y;

    // 3. 申请 Device 内存
    CHECK_HIP(hipMalloc(&x, sizeof(hipfftDoubleComplex) * N));
    CHECK_HIP(hipMalloc(&y, sizeof(hipfftDoubleComplex) * N));

    // 4. 将数据从 Host 拷贝到 Device
    CHECK_HIP(hipMemcpy(x, h.data(), sizeof(hipfftDoubleComplex) * N, hipMemcpyHostToDevice));

    // 5. 创建 FFT Plan
    hipfftHandle plan;
    CHECK_FFT(hipfftCreate(&plan));
    // 创建 1D 的双精度复数 FFT 计划
    CHECK_FFT(hipfftPlan1d(&plan, N, HIPFFT_Z2Z, 1));

    // 6. 执行 FFT (Forward)
    CHECK_FFT(hipfftExecZ2Z(plan, x, y, HIPFFT_FORWARD));

    // 7. 同步并把结果从 Device 拷贝回 Host
    CHECK_HIP(hipDeviceSynchronize());
    std::vector<std::complex<double>> out(N);
    CHECK_HIP(hipMemcpy(out.data(), y, sizeof(hipfftDoubleComplex) * N, hipMemcpyDeviceToHost));

    // 8. 打印前 5 个结果检查
    std::cout << "FFT Result (first 5 elements):" << std::endl;
    for(int i = 0; i < 5; i++) {
        std::cout << "out[" << i << "] = " 
                  << out[i].real() << " + " << out[i].imag() << "i" << std::endl;
    }

    // 9. 释放资源
    CHECK_FFT(hipfftDestroy(plan));
    CHECK_HIP(hipFree(x));
    CHECK_HIP(hipFree(y));

    std::cout << "\nTest passed successfully!" << std::endl;

    return 0;
}