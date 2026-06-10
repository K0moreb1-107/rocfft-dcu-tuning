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
            std::cerr << "HIP error\n"; \
            exit(1); \
        } \
    } while(0)

#define CHECK_FFT(x) \
    do { \
        if((x) != HIPFFT_SUCCESS){ \
            std::cerr << "HIPFFT error\n"; \
            exit(1); \
        } \
    } while(0)

int main()
{
    int N = 64;
    auto p = std::filesystem::current_path();
    std::vector<std::complex<double>> h(N);
    
    for(int i = 0; i < N; i++)
        h[i] = i;

    hipfftDoubleComplex *x, *y;
    hipfftDoubleComplex *xw, *yw;

    CHECK_HIP(
        hipMalloc(&x, sizeof(*x) * N));
    return 0;
}
