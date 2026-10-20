// HIP/rocFFT port of supplied fft_test_1d.cu (f48f5212); the event loop is mechanically preserved.
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

#include <cmath>
#include <limits>
#include <memory>
#include <stdexcept>
#include <hip/hip_complex.h>
#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>

#define CHECK_HIP(x)                                                       \
    do {                                                                    \
        hipError_t err = (x);                                              \
        if (err != hipSuccess) {                                           \
            std::cerr << "HIP error: " << hipGetErrorString(err)          \
                      << " (" << __FILE__ << ":" << __LINE__ << ")\n";      \
            std::exit(EXIT_FAILURE);                                        \
        }                                                                   \
    } while (0)

#define CHECK_FFT(x)                                                        \
    do {                                                                    \
        rocfft_status err = (x);                                              \
        if (err != rocfft_status_success) {                                         \
            std::cerr << "rocFFT error: " << static_cast<int>(err)            \
                      << " (" << __FILE__ << ":" << __LINE__ << ")\n";      \
            std::exit(EXIT_FAILURE);                                        \
        }                                                                   \
    } while (0)

#include "rocfft_measurement_support_v3.h"

// ====================== Configuration ======================
constexpr bool ENABLE_TIMING = true;
constexpr bool ENABLE_CSV = true;
constexpr int test_times = 30;      // Number of measured FFT executions.
constexpr int warmup_times = 10;   // Number of warmup executions when enabled.
std::string OUTPUT_PATH; // Explicit managed output directory, set before any library call.
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

    hipEvent_t start = nullptr;
    hipEvent_t stop = nullptr;
    if (ENABLE_TIMING) {
        CHECK_HIP(hipEventCreate(&start));
        CHECK_HIP(hipEventCreate(&stop));
    }

    std::vector<float> measured_ms;
    if (ENABLE_TIMING) {
        measured_ms.reserve(test_times);
    }

    // Identical execution path for warmup and tests, including event timing.
    for (int i = 0; i < total_iterations; ++i) {
        if (ENABLE_TIMING) {
            CHECK_HIP(hipEventRecord(start, 0));
        }

        test_fn();

        if (ENABLE_TIMING) {
            CHECK_HIP(hipEventRecord(stop, 0));
            CHECK_HIP(hipEventSynchronize(stop));

            if (i >= warmup_count) {
                float current_ms = 0.0f;
                CHECK_HIP(hipEventElapsedTime(&current_ms, start, stop));
                measured_ms.push_back(current_ms);
            }
        }
    }

    // Catch asynchronous FFT errors when event synchronization is disabled.
    if (!ENABLE_TIMING) {
        CHECK_HIP(hipDeviceSynchronize());
    }
    if (ENABLE_TIMING) {
        CHECK_HIP(hipEventDestroy(start));
        CHECK_HIP(hipEventDestroy(stop));
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

    const std::filesystem::path file_path =
        std::filesystem::path(OUTPUT_PATH) / "fft_test_1d.csv";

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


bool writeEvidence(const std::string& func, int n, const Check& check,
                   const std::vector<float>& times)
{
    const auto directory = std::filesystem::path(OUTPUT_PATH);
    std::ofstream checked(directory / "fft_test_1d.check.csv");
    checked << std::setprecision(std::numeric_limits<double>::max_digits10)
            << "func,N,batch,check,err_a,err_b\n"
            << func << ',' << n << ",1," << (check.pass ? "PASS" : "FAIL")
            << ',' << check.err_a << ',' << check.err_b << '\n';
    checked.close();
    if(!checked) return false;
    if(times.empty()) return true;
    std::ofstream samples(directory / "fft_test_1d.samples.csv");
    samples << std::setprecision(std::numeric_limits<double>::max_digits10)
            << "func,N,batch,sample_index,elapsed_ms\n";
    for(size_t i = 0; i < times.size(); ++i)
        samples << func << ',' << n << ",1," << i + 1 << ','
                << static_cast<double>(times[i]) << '\n';
    samples.close();
    return bool(samples);
}

int benchmark(int argc, char** argv)
{
    if(argc != 4) throw std::runtime_error("usage: fft_test_1d N is_warmup func (batch=1)");
    size_t consumed = 0;
    const long parsed = std::stol(argv[1], &consumed);
    if(consumed != std::string(argv[1]).size() || parsed < 1 || parsed > 2147483647L)
        throw std::runtime_error("N must be a positive int");
    const int n = static_cast<int>(parsed);
    const std::string warmup_arg = argv[2];
    if(warmup_arg != "0" && warmup_arg != "1") throw std::runtime_error("is_warmup must be 0 or 1");
    const bool is_warmup = warmup_arg == "1";
    const std::string func = argv[3];
    const bool z2z = func == "z2z_1d", d2z = func == "d2z_1d";
    if(!z2z && !d2z && func != "z2d_1d") throw std::runtime_error("unknown transform");
    const char* output = std::getenv("FFT_TEST_OUT");
    if(!output || !*output) throw std::runtime_error("explicit FFT_TEST_OUT required");
    OUTPUT_PATH = output;
    std::filesystem::create_directories(OUTPUT_PATH);
    for(const char* name : {"fft_test_1d.csv", "fft_test_1d.samples.csv", "fft_test_1d.check.csv"})
        if(std::filesystem::exists(std::filesystem::path(OUTPUT_PATH) / name))
            throw std::runtime_error("process output already exists");
    if(const char* iterations = std::getenv("FFT_TEST_ITERS"))
        if(std::string(iterations) != "30") throw std::runtime_error("this source records exactly 30 samples");

    std::vector<float> measured_ms;
    Check check;
    {
        RocFFTSession session;
        const auto kind = z2z ? TransformKind::z2z_forward : d2z ? TransformKind::d2z : TransformKind::z2d;
        // One target plan, reused by correctness, all warmups and all samples.
        std::unique_ptr<RocPlan> plan(create_plan(n, 1, kind));
        const size_t nc = static_cast<size_t>(n) / 2 + 1;
        const size_t in_count = (z2z || d2z) ? n : nc;
        const size_t out_count = (z2z || !d2z) ? n : nc;
        DeviceBuffer input(in_count * (d2z ? sizeof(double) : sizeof(hipDoubleComplex)));
        DeviceBuffer result(out_count * (!z2z && !d2z ? sizeof(double) : sizeof(hipDoubleComplex)));
        check.ran = true;
        // The retained strict checks are outside the event loop. Restore the
        // supplied source's complete ramp input once before its ten warmups.
        if(z2z)
        {
            std::vector<hipDoubleComplex> host(n), expected(n);
            check.err_a = check_tone_z2z(n, 1, *plan, static_cast<hipDoubleComplex*>(input.data),
                                       static_cast<hipDoubleComplex*>(result.data), host, expected);
            std::unique_ptr<RocPlan> inverse(create_plan(n, 1, TransformKind::z2z_inverse));
            check.err_b = check_roundtrip_z2z(n, 1, *plan, *inverse, static_cast<hipDoubleComplex*>(input.data),
                                            static_cast<hipDoubleComplex*>(result.data), host, expected);
        }
        else if(d2z)
        {
            std::vector<double> host(n);
            std::vector<hipDoubleComplex> expected(nc);
            check.err_a = check_tone_d2z(n, 1, *plan, static_cast<double*>(input.data),
                                       static_cast<hipDoubleComplex*>(result.data), host, expected);
        }
        else
        {
            std::vector<hipDoubleComplex> host(nc);
            std::vector<double> expected(n);
            check.err_a = check_z2d(n, 1, *plan, static_cast<hipDoubleComplex*>(input.data),
                                  static_cast<double*>(result.data), host, expected);
        }
        check.pass = std::isfinite(check.err_a) && check.err_a >= 0 && check.err_a < CHECK_TOL
                     && (check.err_b == -1 || (std::isfinite(check.err_b) && check.err_b >= 0 && check.err_b < CHECK_TOL));
        if(!check.pass)
        {
            writeEvidence(func, n, check, {});
            return 2;
        }
        if(d2z)
        {
            std::vector<double> host(in_count);
            for(size_t i = 0; i < in_count; ++i) host[i] = static_cast<double>(i);
            CHECK_HIP(hipMemcpy(input.data, host.data(), sizeof(double) * in_count, hipMemcpyHostToDevice));
        }
        else
        {
            std::vector<hipDoubleComplex> host(in_count);
            for(size_t i = 0; i < in_count; ++i) host[i] = cmplx(static_cast<double>(i));
            CHECK_HIP(hipMemcpy(input.data, host.data(), sizeof(hipDoubleComplex) * in_count, hipMemcpyHostToDevice));
        }
        measured_ms = runBenchmark(is_warmup, [&] { execute(*plan, input.data, result.data); });
    }
    const auto stats = calculateStats(measured_ms);
    if(!writeCsv(func, n, is_warmup, measured_ms, stats) || !writeEvidence(func, n, check, measured_ms))
        throw std::runtime_error("cannot write process evidence");
    std::cout << func << " N=" << n << " warmup_times=" << (is_warmup ? warmup_times : 0)
              << " test_times=" << test_times << " check=PASS\n";
    return 0;
}

int main(int argc, char** argv)
{
    try { return benchmark(argc, argv); }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
