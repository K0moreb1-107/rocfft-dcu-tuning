// Exercise every native C/Q pair without changing the public plan selector.
#define main public_guard_main
#include "cc_fusion_ab_guard.cpp"
#undef main
#include "node_factory.h"
#include "kernel_launch.h"
#include "rtc_stockham_kernel.h"

static void need(bool ok, const std::string& message)
{
    if(!ok)
        throw std::runtime_error(message);
}

static void pipeline(size_t n, bool pre, size_t c, size_t q, double scale, bool callbacks,
    const std::string& input_path, const std::string& expected_path, const hipDeviceProp_t& prop)
{
    const size_t m = n / 2, in_count = pre ? m + 1 : n, out_count = pre ? n : m + 1;
    const auto original = read_binary(input_path, in_count * (pre ? 16 : 8));
    const auto expected = read_binary(expected_path, out_count * (pre ? 8 : 16));
    NodeMetaData meta(nullptr);
    meta.rootIsC2C = false;
    meta.deviceProp = prop;
    meta.dimension = 1;
    meta.batch = 1;
    meta.precision = rocfft_precision_double;
    meta.direction = pre ? 1 : -1;
    meta.placement = rocfft_placement_notinplace;
    meta.length = { c, q + size_t(pre) };
    meta.inStride = { pre ? 2 * q : q, 1 };
    meta.outStride = { q, 1 };
    meta.iDist = pre ? m + 1 : m;
    meta.oDist = m;
    meta.inArrayType = pre ? rocfft_array_type_hermitian_interleaved : rocfft_array_type_real;
    meta.outArrayType = rocfft_array_type_complex_interleaved;
    auto first_owner = NodeFactory::CreateExplicitNode(meta, nullptr, CS_KERNEL_STOCKHAM_BLOCK_CC);
    auto* first = dynamic_cast<LeafNode*>(first_owner.get());
    need(first, "first leaf missing");
    first->real_io = { pre ? RealBlockRole::FoldedPackedColumns : RealBlockRole::LocalPostColumns,
        RealBlockLoad::Registers, n, c, q, q };
    first->outputLength = { c, q };
    first->large1D = pre ? n : 0;
    first->obIn = OB_USER_IN;
    first->obOut = OB_TEMP;

    meta.length = { q, c };
    meta.inStride = { 1, q };
    meta.outStride = { 1, c };
    meta.iDist = m;
    meta.oDist = pre ? m : m + 1;
    meta.inArrayType = rocfft_array_type_complex_interleaved;
    meta.outArrayType = pre ? rocfft_array_type_real : rocfft_array_type_hermitian_interleaved;
    auto last_owner = NodeFactory::CreateExplicitNode(meta, nullptr, CS_KERNEL_STOCKHAM_BLOCK_RC);
    auto* last = dynamic_cast<LeafNode*>(last_owner.get());
    need(last, "last leaf missing");
    last->real_io = { pre ? RealBlockRole::PackedInverseRows : RealBlockRole::FoldedSpectrumRows,
        RealBlockLoad::LDS, n, c, q, q };
    last->outputLength = { c, q };
    last->obIn = OB_TEMP;
    last->obOut = OB_USER_OUT;
    StoreOps ops;
    ops.scale_factor = scale;
    last->storeOps = ops;

    std::vector<LeafNode*> nodes { first, last };
    std::vector<GridParam> grids(2);
    std::vector<std::shared_future<std::unique_ptr<RTCKernel>>> kernels;
    std::vector<std::string> names(2);
    for(size_t i = 0; i < 2; ++i)
    {
        auto* node = nodes[i];
        node->inStrideUnit = node->inStride[0] == 1;
        node->outStrideUnit = node->outStride[0] == 1;
        need(node->KernelCheck(), "kernel check failed");
        node->dir2regMode = DirectRegType::TRY_ENABLE_IF_SUPPORT;
        node->intrinsicMode = IntrinsicAccessType::DISABLE_BOTH;
        need(node->CreateDevKernelArgs() && node->CreateDeviceResources(), "resources failed");
        node->SetupGridParam(grids[i]);
        kernels.push_back(RTCKernel::runtime_compile(*node, "gfx936", names[i], callbacks));
        need(kernels.back().valid() && bool(kernels.back().get()), "RTC compilation failed");
        need(names[i].find("_cc_local_v1_role") != std::string::npos, "wrong adapter");
    }
    GuardedBuffer input(original.size()), output(expected.size()), middle(m * 16);
    GuardedBuffer lc((in_count + 1) * 4), sc((out_count + 1) * 4), ld(sizeof(CallbackData)),
        sd(sizeof(CallbackData));
    const CallbackData ldata { static_cast<unsigned int*>(lc.data()), in_count };
    const CallbackData sdata { static_cast<unsigned int*>(sc.data()), out_count };
    hip_check(hipMemcpy(ld.data(), &ldata, sizeof(ldata), hipMemcpyHostToDevice));
    hip_check(hipMemcpy(sd.data(), &sdata, sizeof(sdata), hipMemcpyHostToDevice));
    double maximum = 0;
    for(unsigned int round = 0; round < 2; ++round)
    {
        hip_check(hipMemcpy(input.data(), original.data(), original.size(), hipMemcpyHostToDevice));
        hip_check(hipMemset(output.data(), 0xff, expected.size()));
        hip_check(hipMemset(middle.data(), 0xff, middle.bytes));
        hip_check(hipMemset(lc.data(), 0, lc.bytes));
        hip_check(hipMemset(sc.data(), 0, sc.bytes));
        for(size_t i = 0; i < 2; ++i)
        {
            DeviceCallIn call;
            call.node = nodes[i];
            call.gridParam = grids[i];
            call.deviceProp = prop;
            call.bufIn[0] = i ? middle.data() : input.data();
            call.bufOut[0] = i ? output.data() : middle.data();
            if(callbacks && i == 0)
            {
                if(pre)
                    hip_check(hipMemcpyFromSymbol(&call.callbacks.load_cb_fn,
                        HIP_SYMBOL(load_complex_pointer), sizeof(void*)));
                else
                    hip_check(hipMemcpyFromSymbol(
                        &call.callbacks.load_cb_fn, HIP_SYMBOL(load_real_pointer), sizeof(void*)));
                call.callbacks.load_cb_data = ld.data();
            }
            if(callbacks && i == 1)
            {
                if(pre)
                    hip_check(hipMemcpyFromSymbol(&call.callbacks.store_cb_fn,
                        HIP_SYMBOL(store_real_pointer), sizeof(void*)));
                else
                    hip_check(hipMemcpyFromSymbol(&call.callbacks.store_cb_fn,
                        HIP_SYMBOL(store_complex_pointer), sizeof(void*)));
                call.callbacks.store_cb_data = sd.data();
            }
            kernels[i].get()->launch(call, prop);
        }
        hip_check(hipDeviceSynchronize());
        std::vector<unsigned char> actual(expected.size()), unchanged(original.size());
        hip_check(hipMemcpy(actual.data(), output.data(), actual.size(), hipMemcpyDeviceToHost));
        hip_check(
            hipMemcpy(unchanged.data(), input.data(), unchanged.size(), hipMemcpyDeviceToHost));
        need(unchanged == original, "input changed");
        double error = 0, norm = 1;
        for(size_t j = 0; j < actual.size() / 8; ++j)
        {
            double a, e;
            std::memcpy(&a, actual.data() + 8 * j, 8);
            std::memcpy(&e, expected.data() + 8 * j, 8);
            need(std::isfinite(a) && std::isfinite(e), "unwritten/nonfinite output");
            error = std::max(error, std::abs(a - e));
            norm = std::max(norm, std::abs(e));
        }
        need(error / norm < 1e-9, "numerical mismatch " + std::to_string(error / norm));
        maximum = std::max(maximum, error / norm);
        for(const auto* counts : { &lc, &sc })
        {
            std::vector<unsigned int> host(counts->bytes / 4);
            hip_check(hipMemcpy(host.data(), counts->data(), counts->bytes, hipMemcpyDeviceToHost));
            need(host.back() == 0
                    && std::all_of(host.begin(), host.end() - 1,
                        [&](unsigned int x) { return x == unsigned(callbacks); }),
                "callback ownership");
        }
        for(const auto* b : { &input, &output, &middle, &lc, &sc, &ld, &sd })
            need(b->check(), "guard changed");
    }
    std::cout << "CC_LOCAL_PIPELINE_PASS " << n << ' ' << pre << ' ' << c << ' ' << q << ' '
              << std::setprecision(17) << maximum << ' ' << names[0] << ' ' << names[1]
              << " grid=" << grids[0].b_x << ',' << grids[1].b_x << " lds=" << grids[0].lds_bytes
              << ',' << grids[1].lds_bytes << std::endl;
}

int main(int argc, char** argv)
try
{
    need(argc == 2, "manifest required");
    fft_check(rocfft_setup());
    hipDeviceProp_t prop { };
    hip_check(hipGetDeviceProperties(&prop, 0));
    std::ifstream file(argv[1]);
    size_t n, c, q, count = 0;
    bool pre, callbacks;
    double scale;
    std::string input, expected;
    while(file >> n >> pre >> c >> q >> scale >> callbacks >> input >> expected)
    {
        pipeline(n, pre, c, q, scale, callbacks, input, expected, prop);
        ++count;
    }
    need(file.eof() && count, "incomplete manifest");
    fft_check(rocfft_cleanup());
    std::cout << "CC_LOCAL_PIPELINE_ALL_PASS " << count << std::endl;
    return 0;
}
catch(const std::exception& e)
{
    std::cerr << e.what() << std::endl;
    return 1;
}
