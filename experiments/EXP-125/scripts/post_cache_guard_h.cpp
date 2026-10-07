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


struct CheckedPlan
{
    size_t n, batch, work_bytes = 0;
    rocfft_plan plan = nullptr;
    explicit CheckedPlan(size_t length, size_t count) : n(length), batch(count)
    {
        fft_check(rocfft_plan_create(&plan, rocfft_placement_notinplace,
                                    rocfft_transform_type_real_forward,
                                    rocfft_precision_double, 1, &n, batch, nullptr));
        fft_check(rocfft_plan_get_print(plan));
        fft_check(rocfft_plan_get_work_buffer_size(plan, &work_bytes));
    }
    void destroy()
    {
        if(plan) fft_check(rocfft_plan_destroy(plan));
        plan = nullptr;
    }
    void check(const char* phase)
    {
        const size_t m = n / 2;
        GuardedBuffer input(batch*n*sizeof(double)), output(batch*(m+1)*sizeof(double2)), work(work_bytes);
        std::vector<double> values(batch*n), recovered(batch*n);
        uint64_t state = 0x9b46d784eb29f101ULL;
        for(auto& value : values)
        {
            state ^= state << 13; state ^= state >> 7; state ^= state << 17;
            value = (static_cast<int>(state & 0xffff) - 32768) / 65536.0;
        }
        hip_check(hipMemcpy(input.data(), values.data(), input.bytes, hipMemcpyHostToDevice));
        hip_check(hipMemset(output.data(), 0xff, output.bytes));
        hip_check(hipMemset(work.data(), 0xff, work.bytes));
        rocfft_execution_info info = nullptr;
        fft_check(rocfft_execution_info_create(&info));
        if(work_bytes) fft_check(rocfft_execution_info_set_work_buffer(info, work.data(), work_bytes));
        void* in[] = {input.data()}, *out[] = {output.data()};
        fft_check(rocfft_execute(plan, in, out, info));
        hip_check(hipDeviceSynchronize());
        std::vector<double2> actual(batch*(m+1));
        hip_check(hipMemcpy(actual.data(), output.data(), output.bytes, hipMemcpyDeviceToHost));
        hip_check(hipMemcpy(recovered.data(), input.data(), input.bytes, hipMemcpyDeviceToHost));
        std::vector<std::complex<double>> rotations(m);
        const long double pi = std::acos(-1.0L);
        for(size_t k=0; k<m; ++k)
        {
            const auto angle=-2*pi*k/n;
            rotations[k]={static_cast<double>(std::cos(angle)), static_cast<double>(std::sin(angle))};
        }
        double error=0;
        for(size_t b=0; b<batch; ++b)
        {
            std::vector<double> one(values.begin()+b*n,values.begin()+(b+1)*n);
            const auto expected=reference_fft(one,rotations);
            for(size_t k=0; k<=m; ++k)
            {
                const auto v=actual[b*(m+1)+k];
                if(!std::isfinite(v.x) || !std::isfinite(v.y)) {error=INFINITY;break;}
                error=std::max(error,std::abs(std::complex<double>{v.x,v.y}-expected[k]));
            }
        }
        const bool pass=error<1e-9 && input.check() && output.check() && work.check()
                        && std::memcmp(values.data(),recovered.data(),input.bytes)==0;
        fft_check(rocfft_execution_info_destroy(info));
        std::cout << "POST_CACHE_CHECK N=" << n << " batch=" << batch << " phase=" << phase
                  << " max_error=" << std::setprecision(17) << error
                  << " status=" << (pass?"PASS":"FAIL") << '\n';
        if(!pass) throw std::runtime_error("post cache coexistence failed");
    }
    ~CheckedPlan() {if(plan) (void)rocfft_plan_destroy(plan);}
};

int main(int argc,char** argv)
{
    try
    {
        if(argc!=2) return 2;
        const size_t n=std::stoull(argv[1]);
        fft_check(rocfft_setup());
        // Check both insertion and release orders, including repeated packed plans.
        for(bool natural_first : {false,true})
        {
            CheckedPlan first(n,natural_first?2:1), second(n,natural_first?1:2), shared(n,1);
            first.check("coexist-first"); second.check("coexist-second"); shared.check("shared-packed");
            first.destroy(); second.check("after-first-release"); shared.check("after-first-release-shared");
            second.destroy(); shared.check("after-second-release"); shared.destroy();
        }
        fft_check(rocfft_cleanup());
        std::cout << "POST_CACHE_ALL_PASS N=" << n << '\n';
    }
    catch(const std::exception& e) {std::cerr << e.what() << '\n'; return 4;}
}
