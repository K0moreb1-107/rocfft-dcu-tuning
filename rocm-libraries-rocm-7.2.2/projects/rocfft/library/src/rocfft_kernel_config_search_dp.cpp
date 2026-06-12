// Copyright (C) 2023 - 2024 Advanced Micro Devices, Inc. All rights reserved.
// ... (license)

#include "../../shared/CLI11.hpp"
#include "../../shared/arithmetic.h"
#include "../../shared/gpubuf.h"
#include "../../shared/hip_object_wrapper.h"
#include "device/generator/stockham_gen.h"
#include "rtc_compile.h"
#include "rtc_stockham_gen.h"
#include "rtc_stockham_kernel.h"

#include <iostream>
#include <fstream>
#include <iterator>
#include <map>
#include <random>
#include <set>

static const std::vector<unsigned int> supported_factors
    = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 16, 17};
// Modified: 彻底解放 WGS 限制，加入 512 和 1024 支持
static const std::vector<unsigned int> supported_wgs{64, 128, 256, 512, 1024}; 

// recursively find all unique factorizations of given length.  each
// factorization is a vector of ints, sorted so they're uniquified in
// a set.
std::set<std::vector<unsigned int>> factorize(unsigned int length)
{
    std::set<std::vector<unsigned int>> ret;
    for(auto factor : supported_factors)
    {
        if(length % factor == 0)
        {
            unsigned int remain = length / factor;
            if(remain == 1)
                ret.insert({factor});
            else
            {
                // recurse into remainder
                auto remain_factorization = factorize(remain);
                for(auto& remain_factors : remain_factorization)
                {
                    std::vector<unsigned int> factors{factor};
                    std::copy(
                        remain_factors.begin(), remain_factors.end(), std::back_inserter(factors));
                    std::sort(factors.begin(), factors.end());
                    ret.insert(factors);
                }
            }
        }
    }
    return ret;
}

// recursively return power set of a range of ints
std::set<std::vector<unsigned int>> power_set(std::vector<unsigned int>::const_iterator begin,
                                              std::vector<unsigned int>::const_iterator end)
{
    std::set<std::vector<unsigned int>> ret;
    // either include the front element in the output, or don't
    if(std::distance(begin, end) == 1)
    {
        ret.insert({*begin});
        ret.insert({});
    }
    else
    {
        // recurse into the remainder
        auto remain = power_set(begin + 1, end);
        for(auto r : remain)
        {
            ret.insert(r);
            r.push_back(*begin);
            ret.insert(r);
        }
    }
    return ret;
}

std::set<unsigned int, std::greater<unsigned int>>
    supported_threads_per_transform(const std::vector<unsigned int>& factorization)
{
    std::set<unsigned int, std::greater<unsigned int>> tpts;
    auto tpt_candidates = power_set(factorization.begin(), factorization.end());
    for(auto tpt : tpt_candidates)
    {
        if(tpt.empty())
            continue;
        tpts.insert(product(tpt.begin(), tpt.end()));
    }
    return tpts;
}

std::string test_kernel_name(unsigned int                     length,
                             const std::vector<unsigned int>& factorization,
                             unsigned int                     wgs,
                             unsigned int                     tpt,
                             bool                             half_lds,
                             bool                             direct_to_from_reg)
{
    std::string ret = "fft_test_len_";
    ret += std::to_string(length);
    ret += "_factors";
    for(auto f : factorization)
    {
        ret += "_";
        ret += std::to_string(f);
    }
    ret += "_wgs_";
    ret += std::to_string(wgs);
    ret += "_tpt_";
    ret += std::to_string(tpt);
    if(half_lds)
        ret += "_halfLds";
    if(direct_to_from_reg)
        ret += "_dirReg";

    return ret;
}

std::string test_kernel_src(const std::string&               kernel_name,
                            hipDeviceProp_t                  device_prop,
                            unsigned int&                    transforms_per_block,
                            unsigned int                     length,
                            ComputeScheme                    compute_scheme,
                            rocfft_precision                 precision,
                            const std::vector<unsigned int>& factorization,
                            unsigned int                     wgs,
                            unsigned int                     tpt,
                            bool                             half_lds,
                            bool                             direct_to_from_reg)
{
    // Modified: 取消写死的 single 精度，将 precision 真正传给代码生成器
    StockhamGeneratorSpecs specs{factorization,
                                 {},
                                 {static_cast<unsigned int>(precision)},
                                 wgs,
                                 PrintScheme(compute_scheme)};

    auto ppParams = StockhamPartialPassParams();

    specs.threads_per_transform = tpt;
    specs.half_lds              = half_lds;
    specs.direct_to_from_reg    = direct_to_from_reg;
    // aim for occupancy-2
    specs.lds_byte_limit = device_prop.sharedMemPerBlock / 2;

    return stockham_rtc(specs,
                        specs,
                        ppParams,
                        &transforms_per_block,
                        kernel_name,
                        compute_scheme,
                        -1,
                        precision,
                        rocfft_placement_notinplace,
                        rocfft_array_type_complex_interleaved,
                        rocfft_array_type_complex_interleaved,
                        true,
                        0,
                        0,
                        false,
                        direct_to_from_reg ? DirectRegType::TRY_ENABLE_IF_SUPPORT
                                           : DirectRegType::FORCE_OFF_OR_NOT_SUPPORT,
                        IntrinsicAccessType::DISABLE_BOTH,
                        SBRC_TRANSPOSE_TYPE::NONE,
                        CallbackType::NONE,
                        BluesteinFuseType::BFT_NONE,
                        PartialPassType::PPT_NONE,
                        {},
                        {});
}

// things that we need to remember between kernel launches
// Modified: 缓冲区全部改为 double 双精度
struct device_data_t
{
    std::vector<rocfft_complex<double>> host_input_buf;
    gpubuf_t<rocfft_complex<double>>    fake_twiddles;
    gpubuf_t<rocfft_complex<double>>    input_buf;
    gpubuf_t<rocfft_complex<double>>    output_buf;
    gpubuf_t<size_t>                   lengths;
    gpubuf_t<size_t>                   stride_in;
    gpubuf_t<size_t>                   stride_out;
    size_t                             batch;
    hipEvent_wrapper_t                 start;
    hipEvent_wrapper_t                 stop;

    device_data_t()
    {
        start.alloc();
        stop.alloc();
    }
    ~device_data_t() = default;
};

// run the kernel, returning the median execution time
float launch_kernel(RTCKernel&             kernel,
                    unsigned int           blocks,
                    unsigned int           wgs,
                    unsigned int           lds_bytes,
                    unsigned int           ntrial,
                    const hipDeviceProp_t& prop,
                    device_data_t&         data)
{
    RTCKernelArgs kargs;
    kargs.append_ptr(data.fake_twiddles.data());
    kargs.append_size_t(1);
    kargs.append_ptr(data.lengths.data());
    kargs.append_ptr(data.stride_in.data());
    kargs.append_ptr(data.stride_out.data());
    kargs.append_size_t(data.batch);
    kargs.append_ptr(nullptr);
    kargs.append_ptr(nullptr);
    kargs.append_unsigned_int(0);
    kargs.append_ptr(nullptr);
    kargs.append_ptr(nullptr);
    kargs.append_ptr(data.input_buf.data());
    kargs.append_ptr(data.output_buf.data());
    std::vector<float> times;
    for(unsigned int i = 0; i < ntrial; ++i)
    {
        // simulate rocfft-bench behaviour - memcpy input to device
        // before each execution
        // Modified: Memcpy 大小按 double 双精度计算
        if(hipMemcpy(data.input_buf.data(),
                     data.host_input_buf.data(),
                     data.host_input_buf.size() * sizeof(rocfft_complex<double>),
                     hipMemcpyHostToDevice)
           != hipSuccess)
            throw std::runtime_error("failed to hipMemcpy");

        if(hipEventRecord(data.start) != hipSuccess)
            throw std::runtime_error("hipEventRecord start failed");
        kernel.launch(kargs, {blocks}, {wgs}, lds_bytes, prop);
        if(hipEventRecord(data.stop) != hipSuccess)
            throw std::runtime_error("hipEventRecord stop failed");
        if(hipEventSynchronize(data.stop) != hipSuccess)
            throw std::runtime_error("hipEventSynchronize failed");
        float time;
        if(hipEventElapsedTime(&time, data.start, data.stop) != hipSuccess)
            throw std::runtime_error("hipEventElapsedTime failed");
        times.push_back(time);
    }
    std::sort(times.begin(), times.end());
    return times[times.size() / 2];
}

unsigned int get_lds_bytes(unsigned int length, unsigned int transforms_per_block, bool half_lds)
{
    // Modified: LDS 估算彻底采用 double 双精度
    return length * transforms_per_block * sizeof(rocfft_complex<double>) / (half_lds ? 2 : 1);
}

size_t batch_size(unsigned int length)
{
    // target 2 GiB memory usage (2^31), assume double precision so
    // each element is 16 bytes (2^4 bytes)
    // 2^31 / 2^4 = 2^27
    size_t target_elems = 1U << 27;
    return target_elems / length;
}

// Modified: 初始化采用 double 双精度
std::vector<rocfft_complex<double>> create_input_buf(unsigned int length, size_t batch)
{
    auto                               elems = length * batch;
    std::vector<rocfft_complex<double>> buf;
    buf.reserve(elems);
    std::mt19937 gen;
    for(unsigned int i = 0; i < elems; ++i)
    {
        double x = static_cast<double>(gen()) / static_cast<double>(gen.max());
        double y = static_cast<double>(gen()) / static_cast<double>(gen.max());
        buf.push_back({x, y});
    }
    return buf;
}

// Modified: 显存分配采用 double 双精度
gpubuf_t<rocfft_complex<double>> create_device_buf(unsigned int length, size_t batch)
{
    auto                            elems = length * batch;
    gpubuf_t<rocfft_complex<double>> device_buf;
    if(device_buf.alloc(elems * sizeof(rocfft_complex<double>)) != hipSuccess)
        throw std::runtime_error("failed to hipMalloc");
    if(hipMemset(device_buf.data(), 0, elems * sizeof(rocfft_complex<double>)) != hipSuccess)
        throw std::runtime_error("failed to hipMemset");

    return device_buf;
}

gpubuf_t<size_t> create_lengths(unsigned int length)
{
    gpubuf_t<size_t> device_buf;
    if(device_buf.alloc(sizeof(size_t)) != hipSuccess)
        throw std::runtime_error("failed to hipMalloc");

    if(hipMemcpy(device_buf.data(), &length, sizeof(size_t), hipMemcpyHostToDevice) != hipSuccess)
        throw std::runtime_error("failed to hipMemcpy");
    return device_buf;
}

gpubuf_t<size_t> create_strides(unsigned int length)
{
    std::array<size_t, 2> strides{1, length};
    gpubuf_t<size_t>      device_buf;
    if(device_buf.alloc(sizeof(size_t) * 2) != hipSuccess)
        throw std::runtime_error("failed to hipMalloc");
    if(hipMemcpy(device_buf.data(), strides.data(), 2 * sizeof(size_t), hipMemcpyHostToDevice)
       != hipSuccess)
        throw std::runtime_error("failed to hipMemcpy");
    return device_buf;
}

int main(int argc, char** argv)
{
    unsigned int  length         = 0;
    unsigned int  ntrial         = 0;
    unsigned int  nbatch         = 1;
    ComputeScheme compute_scheme = CS_KERNEL_STOCKHAM;

    // Modified: 默认精度提升为 double
    rocfft_precision                        precision = rocfft_precision_double;
    std::map<std::string, rocfft_precision> precision_map{
        {"single", rocfft_precision::rocfft_precision_single},
        {"double", rocfft_precision::rocfft_precision_double},
        {"half", rocfft_precision::rocfft_precision_half}};

    CLI::App app{"rocfft kernel config search (DP EDITION)"};

    auto brute_force = app.add_subcommand(
        "brute-force", "brute force tuning kernel config with build-in combinations");

    brute_force->add_option("-l, --length", length, "Select a 1D FFT problem size")->default_val(8);
    brute_force->add_option("-N, --ntrial", ntrial, "Trial size for tuning the problem")
        ->default_val(10);
    
    // Modified: 开放 brute-force 对 sbrc/sbcc 的测试支持
    std::string brute_kernel_type = "sbcc";
    brute_force->add_option("--kernel-type", brute_kernel_type, "The valid types are: sbcc/sbrc/sbcr")
        ->default_val("sbcc");

    auto manual_tuning = app.add_subcommand("manual", "manual tuning kernel config");

    std::string               kernel_type;
    std::string               output_file;
    std::vector<unsigned int> factorization;
    unsigned int              wgs;
    unsigned int              tpt;
    bool                      half_lds           = true;
    bool                      direct_to_from_reg = true;

    manual_tuning
        ->add_option("--kernel-type", kernel_type, "The valid types are: sbrr/sbcc/sbrc/sbcr")
        ->default_val("sbrr");
    manual_tuning->add_option("-l, --length", length, "Select a 1D FFT problem size")
        ->default_val(8);
    manual_tuning->add_option("-N, --ntrial", ntrial, "Trial size for tuning the problem")
        ->default_val(10);
    manual_tuning
        ->add_option(
            "--precision", precision, "Transform precision: single, double (default), half")
        ->transform(CLI::CheckedTransformer(precision_map, CLI::ignore_case));
    manual_tuning->add_option("-b, --batchSize", nbatch, "Batch size of FFT")->default_val(1);
    manual_tuning->add_option(
        "-f, --factorization", factorization, "Factorization for a given FFT problem");
    manual_tuning->add_option("-w, --wgs", wgs, "Work group size")->default_val(64);
    manual_tuning->add_option("--tpt", tpt, "Thread per transform")->default_val(1);
    manual_tuning->add_option("--half-lds", half_lds, "Use half LDS or not")->default_val(true);
    manual_tuning->add_option("--direct-reg", direct_to_from_reg, "Direct load to/from reg")
        ->default_val(true);

    app.add_option("-o, --output", output_file, "Output file to write results to");

    app.require_subcommand(0, 1);

    // Parse args and catch any errors here
    try
    {
        app.parse(argc, argv);
    }
    catch(const CLI::ParseError& e)
    {
        return app.exit(e);
    }

    if(hipInit(0) != hipSuccess)
        throw std::runtime_error("hipInit failure");

    hipDeviceProp_t device_prop;
    // Todo: support device id
    if(hipGetDeviceProperties(&device_prop, 0) != hipSuccess)
        throw std::runtime_error("hipGetDeviceProperties failure");

    std::ofstream out_file_stream;
    if(!output_file.empty())
    {
        out_file_stream.open(output_file);
        if(!out_file_stream.is_open())
            throw std::runtime_error("Failed to open output file");
    }
    std::ostream& out = output_file.empty() ? std::cout : out_file_stream;

    if(brute_force->parsed())
    {
        // Modified: 根据传入参数设置 compute_scheme，而不再写死
        if(brute_kernel_type == "sbcc")
            compute_scheme = CS_KERNEL_STOCKHAM_BLOCK_CC;
        else if(brute_kernel_type == "sbrc")
            compute_scheme = CS_KERNEL_STOCKHAM_BLOCK_RC;
        else if(brute_kernel_type == "sbcr")
            compute_scheme = CS_KERNEL_STOCKHAM_BLOCK_CR;
            
        // init device data
        device_data_t data;
        data.batch = batch_size(length);
        data.host_input_buf = create_input_buf(length, data.batch);
        data.input_buf      = create_device_buf(length, data.batch);
        data.output_buf     = create_device_buf(length, data.batch);
        auto host_twiddles = create_input_buf(length, 1);
        data.fake_twiddles = create_device_buf(length, 1);
        
        // Modified: twiddles size calculations use double precision
        if(hipMemcpy(data.fake_twiddles.data(),
                     host_twiddles.data(),
                     host_twiddles.size() * sizeof(rocfft_complex<double>),
                     hipMemcpyHostToDevice)
           != hipSuccess)
            throw std::runtime_error("failed to hipMemcpy");
        data.lengths    = create_lengths(length);
        data.stride_in  = create_strides(length);
        data.stride_out = create_strides(length);
        out << "length " << length << ", batch " << data.batch << " DP-Mode" << std::endl;

        const auto factorizations = factorize(length);

        float                     best_time               = std::numeric_limits<float>::max();
        unsigned int              best_wgs                = 0;
        unsigned int              best_tpt                = 0;
        bool                      best_half_lds           = true;
        bool                      best_direct_to_from_reg = true;
        std::vector<unsigned int> best_factorization;
        std::string               best_kernel_src;

        size_t count = 0;
        for(auto factorization : factorizations)
        {
            ++count;
            out << "factorization " << count << " of " << factorizations.size() << std::endl;

            auto tpts = supported_threads_per_transform(factorization);

            do
            {
                for(auto wgs : supported_wgs)
                {
                    for(auto tpt : tpts)
                    {
                        if(tpt > wgs)
                            continue;
                        if(tpt <= wgs / 2)
                            continue;

                        for(bool half_lds : {true, false})
                        {
                            for(bool direct_to_from_reg : {true, false})
                            {
                                if(half_lds && !direct_to_from_reg)
                                    continue;
                                auto kernel_name = test_kernel_name(
                                    length, factorization, wgs, tpt, half_lds, direct_to_from_reg);
                                unsigned int transforms_per_block = 0;
                                auto         kernel_src           = test_kernel_src(kernel_name,
                                                                  device_prop,
                                                                  transforms_per_block,
                                                                  length,
                                                                  compute_scheme,
                                                                  precision, // NOW USES DOUBLE!
                                                                  factorization,
                                                                  wgs,
                                                                  tpt,
                                                                  half_lds,
                                                                  direct_to_from_reg);

                                auto code = compile_inprocess(kernel_src, device_prop.gcnArchName);
                                RTCKernelStockham kernel(kernel_name, code);

                                float time = launch_kernel(
                                    kernel,
                                    DivRoundingUp<unsigned int>(data.batch, transforms_per_block),
                                    tpt * transforms_per_block,
                                    get_lds_bytes(length, transforms_per_block, half_lds),
                                    ntrial,
                                    device_prop,
                                    data);

                                out << length << ", " << kernel_name << ", "
                                          << std::setprecision(3) << static_cast<double>(time)
                                          << "ms " << std::endl;

                                if(time < best_time)
                                {
                                    best_time               = time;
                                    best_wgs                = wgs;
                                    best_tpt                = tpt;
                                    best_half_lds           = half_lds;
                                    best_direct_to_from_reg = direct_to_from_reg;
                                    best_factorization      = factorization;
                                    best_kernel_src         = std::move(kernel_src);
                                }
                            }
                        }
                        break;
                    }
                }
            } while(std::next_permutation(factorization.begin(), factorization.end()));
        }

        out << "  NS(length= " << length << ", workgroup_size= " << best_wgs
                  << ", threads_per_transform=" << best_tpt << ", factors=(";
        bool first_factor = true;
        for(auto f : best_factorization)
        {
            if(!first_factor)
                out << ", ";
            first_factor = false;
            out << f;
        }
        out << ")";
        if(!best_half_lds)
            out << ", half_lds=False";
        if(!best_direct_to_from_reg)
            out << ", direct_to_from_reg=False";
        out << " best_time," << best_time << std::endl;
    }
    else if(manual_tuning->parsed())
    {
        device_data_t data;
        data.batch = nbatch;
        data.host_input_buf = create_input_buf(length, data.batch);
        data.input_buf      = create_device_buf(length, data.batch);
        data.output_buf     = create_device_buf(length, data.batch);
        auto host_twiddles = create_input_buf(length, 1);
        data.fake_twiddles = create_device_buf(length, 1);
        
        // Modified: twiddles size calculations use double precision
        if(hipMemcpy(data.fake_twiddles.data(),
                     host_twiddles.data(),
                     host_twiddles.size() * sizeof(rocfft_complex<double>),
                     hipMemcpyHostToDevice)
           != hipSuccess)
            throw std::runtime_error("failed to hipMemcpy");
        data.lengths    = create_lengths(length);
        data.stride_in  = create_strides(length);
        data.stride_out = create_strides(length);

        if(kernel_type == "sbcc")
            compute_scheme = CS_KERNEL_STOCKHAM_BLOCK_CC;
        else if(kernel_type == "sbrc")
            compute_scheme = CS_KERNEL_STOCKHAM_BLOCK_RC;
        else if(kernel_type == "sbcr")
            compute_scheme = CS_KERNEL_STOCKHAM_BLOCK_CR;

        if(tpt < wgs)
        {
            auto kernel_name
                = test_kernel_name(length, factorization, wgs, tpt, half_lds, direct_to_from_reg);
            unsigned int transforms_per_block = 0;

            auto kernel_src = test_kernel_src(kernel_name,
                                              device_prop,
                                              transforms_per_block,
                                              length,
                                              compute_scheme,
                                              precision,
                                              factorization,
                                              wgs,
                                              tpt,
                                              half_lds,
                                              direct_to_from_reg);

            auto              code = compile_inprocess(kernel_src, device_prop.gcnArchName);
            RTCKernelStockham kernel(kernel_name, code);

            float time
                = launch_kernel(kernel,
                                DivRoundingUp<unsigned int>(data.batch, transforms_per_block),
                                tpt * transforms_per_block,
                                get_lds_bytes(length, transforms_per_block, half_lds),
                                ntrial,
                                device_prop,
                                data);

            out << kernel_name << ", " << std::setprecision(3) << static_cast<double>(time)
                      << std::endl;
        }
    }

    return 0;
}
