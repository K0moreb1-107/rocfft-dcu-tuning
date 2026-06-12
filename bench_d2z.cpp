// Simple benchmark for rocFFT D2Z N=65536 DP
// Build: hipcc -o bench_d2z bench_d2z.cpp -lrocfft
// Usage: ./bench_d2z [ntrial]

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

    // Allocate host: real input (N doubles), complex output (ncomplex * 2 doubles)
    std::vector<double> h_in(N);
    for (size_t i = 0; i < N; ++i)
        h_in[i] = std::sin(2.0 * M_PI * i / N) + 0.5 * std::cos(6.0 * M_PI * i / N);

    std::vector<double> h_out(ncomplex * 2);

    // Device buffers
    double *d_in = nullptr, *d_out = nullptr;
    CHECK(hipMalloc(&d_in, N * sizeof(double)));
    CHECK(hipMalloc(&d_out, ncomplex * sizeof(double) * 2));
    CHECK(hipMemcpy(d_in, h_in.data(), N * sizeof(double), hipMemcpyHostToDevice));

    // FFT plan: 1D, N=65536, D2Z, in-place=false
    rocfft_setup();

    rocfft_plan plan = nullptr;
    size_t length = N;
    CHECK_FFT(rocfft_plan_create(&plan,
        rocfft_placement_notinplace,
        rocfft_transform_type_real_forward,
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
    std::cout << "N=" << N << " D2Z DP, work_buf=" << work_buf_size << " bytes" << std::endl;

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
    CHECK(hipMemcpy(h_out.data(), d_out, ncomplex * sizeof(double) * 2, hipMemcpyDeviceToHost));
    std::cout << "out[0]=" << h_out[0] << "+" << h_out[1] << "i" << std::endl;

    // Cleanup
    CHECK_FFT(rocfft_execution_info_destroy(info));
    CHECK_FFT(rocfft_plan_destroy(plan));
    rocfft_cleanup();
    if (d_work) hipFree(d_work);
    hipFree(d_in);
    hipFree(d_out);

    return 0;
}
