#include <algorithm>
#include <complex>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

#include <cufft.h>
#include <cuda_runtime.h>

#define CHECK_CUDA(x)                                                       \
    do {                                                                    \
        cudaError_t err = (x);                                              \
        if (err != cudaSuccess) {                                           \
            std::cerr << "CUDA error: " << cudaGetErrorString(err)          \
                      << " (" << __FILE__ << ":" << __LINE__ << ")\n";      \
            std::exit(EXIT_FAILURE);                                        \
        }                                                                   \
    } while (0)

#define CHECK_FFT(x)                                                        \
    do {                                                                    \
        cufftResult err = (x);                                              \
        if (err != CUFFT_SUCCESS) {                                         \
            std::cerr << "CUFFT error: " << static_cast<int>(err)            \
                      << " (" << __FILE__ << ":" << __LINE__ << ")\n";      \
            std::exit(EXIT_FAILURE);                                        \
        }                                                                   \
    } while (0)

// ====================== Configuration ======================
constexpr bool ENABLE_TIMING = true;
constexpr bool ENABLE_CSV = true;
constexpr int test_times = 30;      // Number of measured FFT executions.
constexpr int warmup_times = 10;   // Number of warmup executions when enabled.
const std::string OUTPUT_PATH = "../data/results/";
// ===========================================================

struct TimingStats {
    double tmax = 0.0;
    double tmin = 0.0;
    double tmean = 0.0;
    double tmedium = 0.0;  // Median, named tmedium to match the requested CSV field.
};

// Warmup and measured FFT calls share the same plan, buffers, stream, and loop.
// The first warmup_count iterations are executed but discarded; the following
// test_times iterations are recorded (time_1_ms through time_test_times_ms).
template <typename TestFn>
std::vector<float> runBenchmark(bool is_warmup, TestFn&& test_fn)
{
    const int warmup_count = is_warmup ? warmup_times : 0;
    const int total_iterations = warmup_count + test_times;

    cudaEvent_t start = nullptr;
    cudaEvent_t stop = nullptr;
    if (ENABLE_TIMING) {
        CHECK_CUDA(cudaEventCreate(&start));
        CHECK_CUDA(cudaEventCreate(&stop));
    }

    std::vector<float> measured_ms;
    if (ENABLE_TIMING) {
        measured_ms.reserve(test_times);
    }

    // Identical execution path for warmup and tests, including event timing.
    for (int i = 0; i < total_iterations; ++i) {
        if (ENABLE_TIMING) {
            CHECK_CUDA(cudaEventRecord(start, 0));
        }

        test_fn();

        if (ENABLE_TIMING) {
            CHECK_CUDA(cudaEventRecord(stop, 0));
            CHECK_CUDA(cudaEventSynchronize(stop));

            if (i >= warmup_count) {
                float current_ms = 0.0f;
                CHECK_CUDA(cudaEventElapsedTime(&current_ms, start, stop));
                measured_ms.push_back(current_ms);
            }
        }
    }

    // Catch asynchronous FFT errors when event synchronization is disabled.
    if (!ENABLE_TIMING) {
        CHECK_CUDA(cudaDeviceSynchronize());
    }
    if (ENABLE_TIMING) {
        CHECK_CUDA(cudaEventDestroy(start));
        CHECK_CUDA(cudaEventDestroy(stop));
    }
    return measured_ms;
}

TimingStats calculateStats(const std::vector<float>& measured_ms)
{
    TimingStats s;
    if (measured_ms.empty()) {
        return s;
    }

    const auto minmax = std::minmax_element(measured_ms.begin(), measured_ms.end());
    s.tmin = *minmax.first;
    s.tmax = *minmax.second;
    s.tmean = std::accumulate(measured_ms.begin(), measured_ms.end(), 0.0)
              / static_cast<double>(measured_ms.size());

    std::vector<float> sorted = measured_ms;
    std::sort(sorted.begin(), sorted.end());
    const size_t n = sorted.size();
    s.tmedium = (n % 2 != 0)
                    ? static_cast<double>(sorted[n / 2])
                    : (static_cast<double>(sorted[n / 2 - 1])
                       + static_cast<double>(sorted[n / 2])) / 2.0;
    return s;
}

bool writeCsv(const std::string& func,
              int N,
              bool is_warmup,
              const std::vector<float>& measured_ms,
              const TimingStats& s)
{
    std::error_code ec;
    std::filesystem::create_directories(OUTPUT_PATH, ec);
    if (ec) {
        std::cerr << "Cannot create CSV directory " << OUTPUT_PATH
                  << ": " << ec.message() << '\n';
        return false;
    }

    const std::filesystem::path source_path(__FILE__);
    const std::filesystem::path file_path =
        std::filesystem::path(OUTPUT_PATH) / (source_path.stem().string() + ".csv");

    std::ostringstream header_stream;
    header_stream << "func,N,is_warmup,warmup_times,test_times,"
                  << "tmax_ms,tmin_ms,tmean_ms,tmedium_ms";
    for (int t = 0; t < test_times; ++t) {
        header_stream << ",time_" << (t + 1) << "_ms";
    }
    const std::string expected_header = header_stream.str();

    bool write_header = true;
    {
        std::ifstream fin(file_path);
        if (fin) {
            std::string existing_header;
            if (std::getline(fin, existing_header)) {
                // Reject old CSV schemas to avoid mixing incompatible columns.
                if (existing_header != expected_header) {
                    std::cerr << "CSV header mismatch: " << file_path << '\n'
                              << "Move/rename the old CSV or select a new output path.\n";
                    return false;
                }
                write_header = false;
            }
        }
    }

    std::ofstream fout(file_path, std::ios::app);
    if (!fout) {
        std::cerr << "Cannot open CSV for writing: " << file_path << '\n';
        return false;
    }

    if (write_header) {
        fout << expected_header << '\n';
    }

    fout << std::fixed << std::setprecision(6);
    fout << func << ',' << N << ',' << (is_warmup ? 1 : 0) << ','
         << (is_warmup ? warmup_times : 0) << ',' << test_times;

    if (ENABLE_TIMING) {
        fout << ',' << s.tmax << ',' << s.tmin << ',' << s.tmean
             << ',' << s.tmedium;
    } else {
        fout << ",,,,";
    }

    for (int t = 0; t < test_times; ++t) {
        fout << ',';
        if (ENABLE_TIMING) {
            fout << measured_ms[t];
        }
    }
    fout << '\n';
    if (!fout) {
        std::cerr << "Error while writing CSV: " << file_path << '\n';
        return false;
    }
    return true;
}

int main(int argc, char* argv[])
{
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0]
                  << " N is_warmup func\n"
                  << "func = z2z_1d | d2z_1d | z2d_1d\n";
        return EXIT_FAILURE;
    }

    const int N = std::atoi(argv[1]);
    if (N <= 0) {
        std::cerr << "N must be a positive integer.\n";
        return EXIT_FAILURE;
    }
    const bool is_warmup = std::atoi(argv[2]) != 0;
    const std::string func = argv[3];

    cufftType fft_type;
    if (func == "z2z_1d") {
        fft_type = CUFFT_Z2Z;
    } else if (func == "d2z_1d") {
        fft_type = CUFFT_D2Z;
    } else if (func == "z2d_1d") {
        fft_type = CUFFT_Z2D;
    } else {
        std::cerr << "Unknown func: " << func << '\n';
        return EXIT_FAILURE;
    }

    // Create the plan exactly once. The original dummy N=1 plan was leaked.
    cufftHandle plan;
    CHECK_FFT(cufftPlan1d(&plan, N, fft_type, 1));
    CHECK_FFT(cufftSetStream(plan, static_cast<cudaStream_t>(0)));

    std::vector<float> measured_ms;

    if (func == "z2z_1d") {
        std::vector<std::complex<double>> h(N);
        for (int i = 0; i < N; ++i) {
            h[i] = static_cast<double>(i);
        }

        cufftDoubleComplex *x, *y;
        CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&x), sizeof(*x) * N));
        CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&y), sizeof(*y) * N));

        CHECK_CUDA(cudaMemcpy(x, h.data(), sizeof(*x) * N, cudaMemcpyHostToDevice));

        measured_ms = runBenchmark(
            is_warmup,
            [&]() { CHECK_FFT(cufftExecZ2Z(plan, x, y, CUFFT_FORWARD)); });

        CHECK_CUDA(cudaFree(x));
        CHECK_CUDA(cudaFree(y));
    }
    else if (func == "d2z_1d") {
        const size_t Nc = static_cast<size_t>(N) / 2 + 1;
        std::vector<double> h(N);
        for (int i = 0; i < N; ++i) {
            h[i] = static_cast<double>(i);
        }

        double *x;
        cufftDoubleComplex *y;
        CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&x), sizeof(*x) * N));
        CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&y), sizeof(*y) * Nc));

        CHECK_CUDA(cudaMemcpy(x, h.data(), sizeof(*x) * N, cudaMemcpyHostToDevice));

        measured_ms = runBenchmark(
            is_warmup,
            [&]() { CHECK_FFT(cufftExecD2Z(plan, x, y)); });

        CHECK_CUDA(cudaFree(x));
        CHECK_CUDA(cudaFree(y));
    }
    else {  // z2d_1d
        const size_t Nc = static_cast<size_t>(N) / 2 + 1;
        std::vector<std::complex<double>> h(Nc);
        for (size_t i = 0; i < Nc; ++i) {
            h[i] = static_cast<double>(i);
        }

        cufftDoubleComplex *x;
        double *y;
        CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&x), sizeof(*x) * Nc));
        CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&y), sizeof(*y) * N));

        CHECK_CUDA(cudaMemcpy(x, h.data(), sizeof(*x) * Nc, cudaMemcpyHostToDevice));

        measured_ms = runBenchmark(
            is_warmup,
            [&]() { CHECK_FFT(cufftExecZ2D(plan, x, y)); });

        CHECK_CUDA(cudaFree(x));
        CHECK_CUDA(cudaFree(y));
    }

    CHECK_FFT(cufftDestroy(plan));

    const TimingStats s = calculateStats(measured_ms);

    if (ENABLE_TIMING) {
        std::cout << std::fixed << std::setprecision(6)
                  << func << " N=" << N
                  << " warmup_times=" << (is_warmup ? warmup_times : 0)
                  << " test_times=" << test_times
                  << " tmax=" << s.tmax << "ms"
                  << " tmin=" << s.tmin << "ms"
                  << " tmean=" << s.tmean << "ms"
                  << " tmedium=" << s.tmedium << "ms";
        for (size_t t = 0; t < measured_ms.size(); ++t) {
            std::cout << " time_" << (t + 1) << '=' << measured_ms[t] << "ms";
        }
        std::cout << '\n';
    } else {
        std::cout << func << " done, timing disabled (executed "
                  << (test_times + (is_warmup ? warmup_times : 0)) << " FFT executions)\n";
    }

    if (ENABLE_CSV && !writeCsv(func, N, is_warmup, measured_ms, s)) {
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}

