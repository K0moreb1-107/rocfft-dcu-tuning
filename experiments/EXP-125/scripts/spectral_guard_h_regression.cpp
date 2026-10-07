#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>

static void hip_check(hipError_t status)
{
    if(status != hipSuccess) throw std::runtime_error(hipGetErrorString(status));
}
static void fft_check(rocfft_status status)
{
    if(status != rocfft_status_success) throw std::runtime_error("rocfft status " + std::to_string(status));
}

struct GuardedBuffer
{
    static constexpr size_t guard = 2048;
    static constexpr unsigned char canary = 0xa5;
    unsigned char* device = nullptr;
    size_t bytes;
    explicit GuardedBuffer(size_t bytes) : bytes(std::max<size_t>(bytes, 1))
    {
        hip_check(hipMalloc(&device, this->bytes + 2 * guard));
        hip_check(hipMemset(device, canary, this->bytes + 2 * guard));
    }
    void* data() const { return device + guard; }
    bool check() const
    {
        std::vector<unsigned char> host(2 * guard);
        hip_check(hipMemcpy(host.data(), device, guard, hipMemcpyDeviceToHost));
        hip_check(hipMemcpy(host.data() + guard, device + guard + bytes, guard, hipMemcpyDeviceToHost));
        return std::all_of(host.begin(), host.end(), [](unsigned char b) { return b == canary; });
    }
    ~GuardedBuffer() { (void)hipFree(device); }
};

struct Bin { size_t k; double real, imag; };

int main(int argc, char** argv)
{
    try
    {
        if(argc != 2) return 2;
        const size_t n = std::stoull(argv[1]);
        const size_t m = n / 2, q = n <= 131072 ? 256 : 512;
        fft_check(rocfft_setup());
        rocfft_plan plan = nullptr;
        fft_check(rocfft_plan_create(&plan, rocfft_placement_notinplace,
                                    rocfft_transform_type_real_inverse,
                                    rocfft_precision_double, 1, &n, 1, nullptr));
        fft_check(rocfft_plan_get_print(plan));
        size_t work_bytes = 0;
        fft_check(rocfft_plan_get_work_buffer_size(plan, &work_bytes));
        GuardedBuffer input((m + 1) * sizeof(double2)), output(n * sizeof(double)), work(work_bytes);
        rocfft_execution_info info = nullptr;
        fft_check(rocfft_execution_info_create(&info));
        if(work_bytes)
            fft_check(rocfft_execution_info_set_work_buffer(info, work.data(), work_bytes));
        std::vector<std::vector<Bin>> cases{
            {{0, 0.5, 0}}, {{m, 0.375, 0}}, {{n/4, 0.25, -0.125}},
            {{1, 0.25, 0.125}, {q-1, -0.375, 0.0625}, {q, 0.125, -0.25}, {q+1, 0.25, 0.125}},
            {{m-1, 0.375, -0.125}, {m-q, -0.25, 0.0625}, {m-q-1, 0.125, -0.25}},
            {{0, 0.125, 0}, {m, -0.25, 0}, {n/4, 0.125, -0.125},
             {q/2, 0.0625, 0.125}, {2*q, -0.125, -0.0625}},
        };
        double maximum = 0;
        const long double pi = std::acos(-1.0L);
        for(size_t test = 0; test < cases.size(); ++test)
        {
            std::vector<double2> host_in(m + 1, double2{0, 0}), recovered(m + 1);
            for(const auto& b : cases[test]) host_in[b.k] = double2{b.real, b.imag};
            hip_check(hipMemcpy(input.data(), host_in.data(), input.bytes, hipMemcpyHostToDevice));
            // A bad read of unwritten output or temporary padding propagates NaNs.
            hip_check(hipMemset(output.data(), 0xff, output.bytes));
            hip_check(hipMemset(work.data(), 0xff, work.bytes));
            void* in[] = {input.data()};
            void* out[] = {output.data()};
            fft_check(rocfft_execute(plan, in, out, info));
            hip_check(hipDeviceSynchronize());
            std::vector<double> actual(n);
            hip_check(hipMemcpy(actual.data(), output.data(), output.bytes, hipMemcpyDeviceToHost));
            hip_check(hipMemcpy(recovered.data(), input.data(), input.bytes, hipMemcpyDeviceToHost));
            const bool unchanged = std::memcmp(host_in.data(), recovered.data(), input.bytes) == 0;
            const bool guards = input.check() && output.check() && work.check();
            double error = 0;
            for(size_t x = 0; x < n; ++x)
            {
                long double expected = 0;
                for(const auto& b : cases[test])
                {
                    if(b.k == 0) expected += b.real;
                    else if(b.k == m) expected += (x % 2 ? -b.real : b.real);
                    else
                    {
                        // Reduce integer phase before evaluating trigonometry.
                        const auto phase = (b.k * x) % n;
                        const auto angle = 2 * pi * phase / n;
                        expected += 2 * (b.real * std::cos(angle) - b.imag * std::sin(angle));
                    }
                }
                if(!std::isfinite(actual[x])) { error = INFINITY; break; }
                error = std::max(error, std::abs(actual[x] - static_cast<double>(expected)));
            }
            const bool pass = error < 1e-9 && guards && unchanged;
            maximum = std::max(maximum, error);
            std::cout << "LOCAL_REAL_CHECK N=" << n << " case=" << test
                      << " max_error=" << std::setprecision(17) << error
                      << " guards=" << guards << " input_unchanged=" << unchanged
                      << " status=" << (pass ? "PASS" : "FAIL") << '\n';
            if(!pass) return 3;
        }
        fft_check(rocfft_execution_info_destroy(info));
        fft_check(rocfft_plan_destroy(plan));
        fft_check(rocfft_cleanup());
        std::cout << "LOCAL_REAL_ALL_PASS N=" << n << " work_bytes=" << work_bytes
                  << " max_error=" << std::setprecision(17) << maximum << '\n';
        return 0;
    }
    catch(const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 4;
    }
}
