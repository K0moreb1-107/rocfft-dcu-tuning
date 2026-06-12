// Simple benchmark for rocFFT Z2D N=65536 DP
// Build: hipcc -o bench_z2d bench_z2d.cpp -lrocfft
// Usage: ./bench_z2d

#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

#define CHECK(x) do { auto e = (x); if (e != hipSuccess) { std::cerr << "hip error " << e << " at " << __LINE__ << std::endl; exit(1); } } while(0)
#define CHECK_FFT(x) do { auto e = (x); if (e != rocfft_status_success) { std::cerr << "rocfft error " << e << " at " << __LINE__ << std::endl; exit(1); } } while(0)

int main(int argc, char* argv[])
{
    int ntrial = 10000;

    const size_t N = 65536;
    const size_t ncomplex = N / 2 + 1;

    // Allocate host: complex input (ncomplex * 2 doubles), real output (N doubles)
    std::vector<double> h_in(ncomplex * 2);
    for (size_t i = 0; i < ncomplex; ++i) {
        h_in[2 * i] = std::sin(2.0 * M_PI * i / N);       // real part
        h_in[2 * i + 1] = 0.5 * std::cos(6.0 * M_PI * i / N); // imag part
    }
    // 注意：Z2D（共轭复数转实数）有严格的厄米特对称性要求。
    // 我们手动把直流（DC）分量和奈奎斯特（Nyquist）分量的虚部设为 0，防止算法算出来出现 NaN
    h_in[1] = 0.0;
    if (N % 2 == 0) h_in[2 * (N / 2) + 1] = 0.0;

    std::vector<double> h_out(N);

    // Device buffers
    double *d_in = nullptr, *d_out = nullptr;
    CHECK(hipMalloc(&d_in, ncomplex * sizeof(double) * 2));
    CHECK(hipMalloc(&d_out, N * sizeof(double)));
    CHECK(hipMemcpy(d_in, h_in.data(), ncomplex * sizeof(double) * 2, hipMemcpyHostToDevice));

    // FFT plan: 1D, N=65536, Z2D, in-place=false
    rocfft_setup();

    rocfft_plan plan = nullptr;
    size_t length = N;
    CHECK_FFT(rocfft_plan_create(&plan,
        rocfft_placement_notinplace,
        rocfft_transform_type_real_inverse,    // Z2D 使用实数逆变换
        rocfft_precision_double,
        1, &length,
        1, nullptr));

    // Get work buffer size
    size_t work_buf_size = 0;
    void* d_work = nullptr;
    CHECK_FFT(rocfft_plan_get_work_buffer_size(plan, &work_buf_size));
    if (work_buf_size > 0)
        CHECK(hipMalloc(&d_work, work_buf_size));

    // Info
    std::cout << "N=" << N << " Z2D DP, work_buf=" << work_buf_size << " bytes" << std::endl;

    rocfft_execution_info info = nullptr;
    CHECK_FFT(rocfft_execution_info_create(&info));
    if (d_work)
        CHECK_FFT(rocfft_execution_info_set_work_buffer(info, d_work, work_buf_size));

    // Warmup
    CHECK_FFT(rocfft_execute(plan, (void**)&d_in, (void**)&d_out, info));
    CHECK(hipDeviceSynchronize());

    // Benchmark
    auto t0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < ntrial; ++i)
    {
        CHECK_FFT(rocfft_execute(plan, (void**)&d_in, (void**)&d_out, info));
    }
    CHECK(hipDeviceSynchronize());
    auto t1 = std::chrono::high_resolution_clock::now();

    double total_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    std::cout << "ntrial=" << ntrial << ", total=" << total_ms << " ms, avg=" << (total_ms / ntrial) << " ms" << std::endl;

    // Copy result back and print first few
    CHECK(hipMemcpy(h_out.data(), d_out, N * sizeof(double), hipMemcpyDeviceToHost));
    std::cout << "out[0]=" << h_out[0] << std::endl;

    // Cleanup
    CHECK_FFT(rocfft_execution_info_destroy(info));
    CHECK_FFT(rocfft_plan_destroy(plan));
    rocfft_cleanup();
    if (d_work) hipFree(d_work);
    hipFree(d_in);
    hipFree(d_out);

    return 0;
}
