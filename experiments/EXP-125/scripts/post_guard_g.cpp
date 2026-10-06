#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>

static void hip_check(hipError_t s)
{
    if(s != hipSuccess) throw std::runtime_error(hipGetErrorString(s));
}
static void fft_check(rocfft_status s)
{
    if(s != rocfft_status_success) throw std::runtime_error("rocfft status " + std::to_string(s));
}
struct GuardedBuffer
{
    static constexpr size_t guard = 2048;
    static constexpr unsigned char canary = 0xa5;
    unsigned char* device = nullptr;
    size_t bytes;
    explicit GuardedBuffer(size_t size) : bytes(std::max<size_t>(size, 1))
    {
        hip_check(hipMalloc(&device, bytes + 2 * guard));
        hip_check(hipMemset(device, canary, bytes + 2 * guard));
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

// Independent full-N complex radix-2 reference; no real post-processing formula.
static std::vector<std::complex<double>> reference_fft(
    const std::vector<double>& input, const std::vector<std::complex<double>>& rotations)
{
    const size_t n = input.size();
    std::vector<std::complex<double>> a(input.begin(), input.end());
    for(size_t i = 1, j = 0; i < n; ++i)
    {
        size_t bit = n >> 1;
        for(; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if(i < j) std::swap(a[i], a[j]);
    }
    for(size_t length = 2; length <= n; length <<= 1)
        for(size_t start = 0; start < n; start += length)
            for(size_t j = 0; j < length / 2; ++j)
            {
                const auto p = a[start + j];
                const auto q = a[start + j + length / 2] * rotations[j * (n / length)];
                a[start + j] = p + q;
                a[start + j + length / 2] = p - q;
            }
    return a;
}

int main(int argc, char** argv)
{
    try
    {
        if(argc != 2) return 2;
        const size_t n = std::stoull(argv[1]), m = n / 2;
        const size_t q = n <= 131072 ? 256 : 512, a = m / q;
        const long double pi = std::acos(-1.0L);
        std::vector<std::complex<double>> rotations(m);
        for(size_t k = 0; k < m; ++k)
        {
            const auto angle = -2 * pi * k / n;
            rotations[k] = {static_cast<double>(std::cos(angle)), static_cast<double>(std::sin(angle))};
        }
        fft_check(rocfft_setup());
        rocfft_plan plan = nullptr;
        fft_check(rocfft_plan_create(&plan, rocfft_placement_notinplace,
                                    rocfft_transform_type_real_forward,
                                    rocfft_precision_double, 1, &n, 1, nullptr));
        fft_check(rocfft_plan_get_print(plan));
        size_t work_bytes = 0;
        fft_check(rocfft_plan_get_work_buffer_size(plan, &work_bytes));
        GuardedBuffer input(n * sizeof(double)), output((m + 1) * sizeof(double2)), work(work_bytes);
        rocfft_execution_info info = nullptr;
        fft_check(rocfft_execution_info_create(&info));
        if(work_bytes) fft_check(rocfft_execution_info_set_work_buffer(info, work.data(), work_bytes));
        double maximum = 0;
        for(size_t test = 0; test < 7; ++test)
        {
            std::vector<double> host_in(n, 0), recovered(n);
            if(test == 0) host_in[0] = 0.5;
            else if(test == 1) host_in[n - 1] = -0.375;
            else if(test == 2) std::fill(host_in.begin(), host_in.end(), 0.25);
            else if(test == 3)
                for(size_t x = 0; x < n; ++x) host_in[x] = x % 2 ? -0.375 : 0.375;
            else if(test == 4)
                for(size_t x = 0; x < n; ++x) host_in[x] = (x % 4 < 2 ? 1 : -1) * (x % 2 ? -0.25 : 0.5);
            else if(test == 5)
                for(size_t x = 0; x < n; ++x)
                {
                    long double value = 0.0625 + (x % 2 ? -0.03125 : 0.03125);
                    for(size_t k : {size_t(1), a / 2, a - 1, a, a + 1, m / 2, m - a, m - 1})
                    {
                        const auto angle = 2 * pi * ((k * x) % n) / n;
                        value += (0.125 * std::cos(angle) - 0.0625 * std::sin(angle)) / 8;
                    }
                    host_in[x] = static_cast<double>(value);
                }
            else
            {
                uint64_t state = 0x63f2e19417bc09d5ULL;
                for(auto& value : host_in)
                {
                    state ^= state << 13; state ^= state >> 7; state ^= state << 17;
                    value = (static_cast<int>(state & 0xffff) - 32768) / 65536.0;
                }
            }
            const auto expected = reference_fft(host_in, rotations);
            hip_check(hipMemcpy(input.data(), host_in.data(), input.bytes, hipMemcpyHostToDevice));
            hip_check(hipMemset(output.data(), 0xff, output.bytes));
            hip_check(hipMemset(work.data(), 0xff, work.bytes));
            void* in[] = {input.data()};
            void* out[] = {output.data()};
            fft_check(rocfft_execute(plan, in, out, info));
            hip_check(hipDeviceSynchronize());
            std::vector<double2> actual(m + 1);
            hip_check(hipMemcpy(actual.data(), output.data(), output.bytes, hipMemcpyDeviceToHost));
            hip_check(hipMemcpy(recovered.data(), input.data(), input.bytes, hipMemcpyDeviceToHost));
            const bool unchanged = std::memcmp(host_in.data(), recovered.data(), input.bytes) == 0;
            const bool guards = input.check() && output.check() && work.check();
            double error = 0;
            for(size_t k = 0; k <= m; ++k)
            {
                if(!std::isfinite(actual[k].x) || !std::isfinite(actual[k].y)) { error = INFINITY; break; }
                error = std::max(error, std::abs(std::complex<double>{actual[k].x, actual[k].y} - expected[k]));
            }
            const bool pass = error < 1e-9 && guards && unchanged;
            maximum = std::max(maximum, error);
            std::cout << "REAL_POST_CHECK N=" << n << " case=" << test
                      << " max_error=" << std::setprecision(17) << error
                      << " guards=" << guards << " input_unchanged=" << unchanged
                      << " status=" << (pass ? "PASS" : "FAIL") << '\n';
            if(!pass) return 3;
        }
        fft_check(rocfft_execution_info_destroy(info));
        fft_check(rocfft_plan_destroy(plan));
        fft_check(rocfft_cleanup());
        std::cout << "REAL_POST_ALL_PASS N=" << n << " work_bytes=" << work_bytes
                  << " max_error=" << std::setprecision(17) << maximum << '\n';
        return 0;
    }
    catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 4; }
}
