#include <hip/hip_runtime.h>
#include <hipfft.h>
#include <iostream>
#include <vector>

using namespace std;

int main() {
    int N_real = 65536;
    
    cout << "Profiling hipFFT D2Z for N = " << N_real << "..." << endl;
    
    vector<double> h_a(N_real, 1.0);
    double *d_a;
    hipfftDoubleComplex *d_comp;
    
    hipMalloc(&d_a, N_real * sizeof(double));
    hipMalloc(&d_comp, (N_real / 2 + 1) * sizeof(hipfftDoubleComplex));
    
    hipMemcpy(d_a, h_a.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    
    hipfftHandle plan_d2z;
    hipfftPlan1d(&plan_d2z, N_real, HIPFFT_D2Z, 1);
    
    // Warm up - 不会被 profiler 重点统计
    hipfftExecD2Z(plan_d2z, d_a, d_comp);
    hipDeviceSynchronize();
    
    // 循环100次以获得稳定的 Profiling 数据
    for(int i = 0; i < 100; i++) {
        hipfftExecD2Z(plan_d2z, d_a, d_comp);
    }
    hipDeviceSynchronize();
    
    hipfftDestroy(plan_d2z);
    hipFree(d_a);
    hipFree(d_comp);
    
    cout << "Done." << endl;
    
    return 0;
}
