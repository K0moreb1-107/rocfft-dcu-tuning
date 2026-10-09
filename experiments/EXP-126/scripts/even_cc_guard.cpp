#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>
#include "rocfft_complex.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <string>
#include <vector>

static void hip_check(hipError_t status)
{
    if(status != hipSuccess) throw std::runtime_error(hipGetErrorString(status));
}
static void fft_check(rocfft_status status)
{
    if(status != rocfft_status_success)
        throw std::runtime_error("rocfft status " + std::to_string(status));
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
    GuardedBuffer(const GuardedBuffer&) = delete;
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

using Complex = rocfft_complex<double>;
struct CallbackData { unsigned int* counts; size_t length; };

__device__ bool counted(CallbackData* cb, size_t offset)
{
    atomicAdd(cb->counts + (offset < cb->length ? offset : cb->length), 1u);
    return offset < cb->length;
}
__device__ double load_real(double* data, size_t offset, void* userdata, void*)
{
    if(!counted(static_cast<CallbackData*>(userdata), offset)) return 0;
    return data[offset] * 0.75 + double(offset % 7) * 0.03125;
}
__device__ Complex load_complex(Complex* data, size_t offset, void* userdata, void*)
{
    if(!counted(static_cast<CallbackData*>(userdata), offset)) return {0, 0};
    const auto value = data[offset];
    return {value.x * 0.75 + double(offset % 7) * 0.03125, value.y * 0.75};
}
__device__ void store_real(double* data, size_t offset, double value, void* userdata, void*)
{
    if(counted(static_cast<CallbackData*>(userdata), offset))
        data[offset] = value * 1.125 + double(offset % 5) * 0.015625;
}
__device__ void store_complex(Complex* data, size_t offset, Complex value, void* userdata, void*)
{
    if(counted(static_cast<CallbackData*>(userdata), offset))
        data[offset] = {value.x * 1.125 + double(offset % 5) * 0.015625, value.y * 1.125};
}

__device__ auto load_real_pointer = load_real;
__device__ auto load_complex_pointer = load_complex;
__device__ auto store_real_pointer = store_real;
__device__ auto store_complex_pointer = store_complex;

static std::vector<unsigned char> read_binary(const std::string& path, size_t bytes)
{
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if(!stream || size_t(stream.tellg()) != bytes) throw std::runtime_error("binary length mismatch: " + path);
    std::vector<unsigned char> result(bytes);
    stream.seekg(0);stream.read(reinterpret_cast<char*>(result.data()), bytes);
    if(!stream) throw std::runtime_error("binary read failed");
    return result;
}

struct Plan
{
    rocfft_plan value = nullptr;
    Plan(size_t n, bool post, rocfft_plan_description description)
    {
        fft_check(rocfft_plan_create(&value, rocfft_placement_notinplace,
            post ? rocfft_transform_type_real_forward : rocfft_transform_type_real_inverse,
            rocfft_precision_double, 1, &n, 1, description));
    }
    ~Plan() { if(value) (void)rocfft_plan_destroy(value); }
};

static void validate_case(size_t n, const std::string& direction, const std::string& input_path,
                          const std::string& expected_path, double scale, bool callbacks,
                          const std::string& pattern)
{
    const size_t m = n / 2;
    const bool post = direction == "d2z";
    const size_t in_elements = post ? n : m + 1;
    const size_t out_elements = post ? m + 1 : n;
    const size_t in_bytes = in_elements * (post ? sizeof(double) : sizeof(Complex));
    const size_t out_bytes = out_elements * (post ? sizeof(Complex) : sizeof(double));
    const auto original = read_binary(input_path, in_bytes);
    const auto expected = read_binary(expected_path, out_bytes);
    rocfft_plan_description description = nullptr;
    fft_check(rocfft_plan_description_create(&description));
    fft_check(rocfft_plan_description_set_scale_factor(description, scale));
    Plan first(n, post, description), second(n, post, description);
    // Both plans hold the same table cache entry. Release one owner first.
    fft_check(rocfft_plan_destroy(first.value)); first.value = nullptr;
    fft_check(rocfft_plan_description_destroy(description));
    fft_check(rocfft_plan_get_print(second.value));
    size_t work_bytes = 0;
    fft_check(rocfft_plan_get_work_buffer_size(second.value, &work_bytes));
    GuardedBuffer input(in_bytes), output(out_bytes), work(work_bytes);
    GuardedBuffer load_counts((in_elements + 1) * sizeof(unsigned int));
    GuardedBuffer store_counts((out_elements + 1) * sizeof(unsigned int));
    GuardedBuffer load_data(sizeof(CallbackData)), store_data(sizeof(CallbackData));
    const CallbackData load_cb{static_cast<unsigned int*>(load_counts.data()), in_elements};
    const CallbackData store_cb{static_cast<unsigned int*>(store_counts.data()), out_elements};
    hip_check(hipMemcpy(load_data.data(), &load_cb, sizeof(load_cb), hipMemcpyHostToDevice));
    hip_check(hipMemcpy(store_data.data(), &store_cb, sizeof(store_cb), hipMemcpyHostToDevice));
    rocfft_execution_info info = nullptr;
    fft_check(rocfft_execution_info_create(&info));
    if(work_bytes) fft_check(rocfft_execution_info_set_work_buffer(info, work.data(), work_bytes));
    if(callbacks)
    {
        void* load_fn = nullptr;void* store_fn = nullptr;
        if(post)
        {
            hip_check(hipMemcpyFromSymbol(&load_fn, HIP_SYMBOL(load_real_pointer), sizeof(load_fn)));
            hip_check(hipMemcpyFromSymbol(&store_fn, HIP_SYMBOL(store_complex_pointer), sizeof(store_fn)));
        }
        else
        {
            hip_check(hipMemcpyFromSymbol(&load_fn, HIP_SYMBOL(load_complex_pointer), sizeof(load_fn)));
            hip_check(hipMemcpyFromSymbol(&store_fn, HIP_SYMBOL(store_real_pointer), sizeof(store_fn)));
        }
        void* load_user = load_data.data();void* store_user = store_data.data();
        fft_check(rocfft_execution_info_set_load_callback(info, &load_fn, &load_user, 0));
        fft_check(rocfft_execution_info_set_store_callback(info, &store_fn, &store_user, 0));
    }
    double max_error = 0;
    for(unsigned int round = 0; round < 2; ++round)
    {
        hip_check(hipMemcpy(input.data(), original.data(), in_bytes, hipMemcpyHostToDevice));
        hip_check(hipMemset(output.data(), 0xff, out_bytes));
        hip_check(hipMemset(load_counts.data(), 0, load_counts.bytes));
        hip_check(hipMemset(store_counts.data(), 0, store_counts.bytes));
        void* in = input.data();void* out = output.data();
        fft_check(rocfft_execute(second.value, &in, &out, info));
        hip_check(hipDeviceSynchronize());
        std::vector<unsigned char> actual(out_bytes), unchanged(in_bytes);
        hip_check(hipMemcpy(actual.data(), output.data(), out_bytes, hipMemcpyDeviceToHost));
        hip_check(hipMemcpy(unchanged.data(), input.data(), in_bytes, hipMemcpyDeviceToHost));
        if(unchanged != original) throw std::runtime_error("input modified");
        double peak = 0, error = 0;
        for(size_t i = 0; i < out_bytes / sizeof(double); ++i)
        {
            double a, e;
            std::memcpy(&a, actual.data() + i * sizeof(double), sizeof(double));
            std::memcpy(&e, expected.data() + i * sizeof(double), sizeof(double));
            if(!std::isfinite(a) || !std::isfinite(e)) throw std::runtime_error("nonfinite output");
            peak = std::max(peak, std::abs(e));error = std::max(error, std::abs(a - e));
        }
        error /= std::max(1.0, peak);max_error = std::max(max_error, error);
        if(error >= 1e-9) throw std::runtime_error("reference mismatch " + std::to_string(error));
        if(callbacks)
            for(const auto* buffer : {&load_counts, &store_counts})
            {
                std::vector<unsigned int> counts(buffer->bytes / sizeof(unsigned int));
                hip_check(hipMemcpy(counts.data(), buffer->data(), buffer->bytes, hipMemcpyDeviceToHost));
                if(counts.back() != 0 || !std::all_of(counts.begin(), counts.end() - 1,
                                                   [](unsigned int v) { return v == 1; }))
                    throw std::runtime_error("callback ownership mismatch");
            }
        for(const auto* buffer : {&input, &output, &work, &load_counts, &store_counts, &load_data, &store_data})
            if(!buffer->check()) throw std::runtime_error("guard modified");
    }
    fft_check(rocfft_execution_info_destroy(info));
    std::cout << "EVEN_CC_GUARD_PASS pattern=" << pattern << " scale=" << scale << " rounds=2 error="
              << std::setprecision(17) << max_error << " callbacks=" << callbacks
              << " unique_counts=" << callbacks << " guards=1 input_unchanged=1 work_bytes=" << work_bytes << '\n';
}

int main(int argc, char** argv)
{
    try
    {
        if(argc != 5) return 2;
        const size_t n = std::stoull(argv[1]);
        const std::string direction(argv[2]);
        if(n <= 65536 || n % 2 || (direction != "d2z" && direction != "z2d")) return 2;
        const bool callbacks = std::string(argv[4]) == "callbacks";
        std::ifstream list(argv[3]);
        if(!list) throw std::runtime_error("missing reference list");
        fft_check(rocfft_setup());
        std::string line, pattern, input, expected;
        size_t count = 0;
        while(std::getline(list, line))
        {
            double scale;
            std::istringstream item(line);
            if(!(item >> pattern >> scale >> input >> expected)) throw std::runtime_error("bad reference list");
            validate_case(n, direction, input, expected, scale, callbacks, pattern);
            ++count;
        }
        if(count == 0) throw std::runtime_error("empty reference list");
        fft_check(rocfft_cleanup());
        std::cout << "EVEN_CC_ALL_PASS cases=" << count << '\n';
        return 0;
    }
    catch(const std::exception& error)
    {
        std::cerr << error.what() << '\n';return 1;
    }
}
