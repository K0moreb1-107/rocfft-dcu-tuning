#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>
#include "rocfft_complex.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
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
    const auto* cb = static_cast<CallbackData*>(userdata);
    const double imaginary = offset > 0 && offset + 1 < cb->length
                                 ? double(offset % 11) * 0.015625 : 0.0;
    return {value.x * 0.75 + double(offset % 7) * 0.03125, value.y * 0.75 + imaginary};
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

#include "node_factory.h"
#include "kernel_launch.h"
#include "rtc_stockham_kernel.h"

static void need(bool value, const std::string& message)
{
    if(!value) throw std::runtime_error(message);
}

// This fixture executes one boundary, not a forced full CC decomposition.
// The other axis may therefore exceed the pool's largest opposite FFT length.
static void boundary_case(const std::string& id, size_t n, bool pre, size_t c, size_t q,
                          size_t expected_p, size_t expected_t, size_t expected_base,
                          size_t expected_steps, bool callbacks, double scale,
                          const std::string& input_path, const std::string& expected_path,
                          RealPairPolicy policy, const hipDeviceProp_t& prop)
{
    const size_t m = n / 2, in_elements = m + size_t(pre), out_elements = m + size_t(!pre);
    const auto original = read_binary(input_path, in_elements * sizeof(Complex));
    const auto expected = read_binary(expected_path, out_elements * sizeof(Complex));

    NodeMetaData meta(nullptr);
    meta.rootIsC2C = false;
    meta.deviceProp = prop;
    meta.dimension = 1;
    meta.batch = 1;
    meta.precision = rocfft_precision_double;
    meta.direction = pre ? 1 : -1;
    meta.placement = rocfft_placement_notinplace;
    meta.length = pre ? std::vector<size_t>{c,q} : std::vector<size_t>{q,c};
    meta.inStride = pre ? std::vector<size_t>{q,1} : std::vector<size_t>{1,q};
    meta.outStride = pre ? std::vector<size_t>{q,1} : std::vector<size_t>{c,1};
    meta.iDist = in_elements;
    meta.oDist = out_elements;
    meta.inArrayType = pre ? rocfft_array_type_hermitian_interleaved
                          : rocfft_array_type_complex_interleaved;
    meta.outArrayType = pre ? rocfft_array_type_complex_interleaved
                           : rocfft_array_type_hermitian_interleaved;
    const auto scheme = pre ? CS_KERNEL_STOCKHAM_BLOCK_CC : CS_KERNEL_STOCKHAM_BLOCK_RC;
    auto owner = NodeFactory::CreateExplicitNode(meta, nullptr, scheme);
    auto* node = dynamic_cast<LeafNode*>(owner.get());
    need(node != nullptr, id + ": leaf missing");
    FMKey key(meta.length[0], meta.precision, scheme, pre ? NONE : TILE_ALIGNED);
    const auto ordinary = node->pool.get_kernel(key);
    need(ordinary.threads_per_transform[0] == int(expected_p), id + ": pool changed");
    auto geometry = RealBlockIO::ForDecomposition(n,c,q);
    need(bool(geometry), id + ": invalid geometry");
    auto io = *geometry;
    const size_t extra = pre && expected_base < 8 ? 3 * (size_t(1) << expected_base) * 16 : 0;
    auto slots = io.ConfigurePair(pre, ordinary.factors, expected_p,
        ordinary.transforms_per_block, pre ? expected_base : 0, pre ? expected_steps : 0,
        {size_t(prop.maxThreadsPerBlock),prop.sharedMemPerBlock,extra,sizeof(Complex)},policy,false);
    need(slots && *slots == expected_t, id + ": slot count changed");
    io.role = pre ? RealBlockRole::PairedPreColumns : RealBlockRole::GenericPairedPostRows;
    auto config = ordinary.get_kernel_config();
    config.transforms_per_block = *slots;
    config.workgroup_size = expected_p * *slots;
    config.half_lds = io.ScalarPairIO();
    config.direct_to_from_reg = io.DirectPairIO();
    config.intrinsic_buffer_inst = false;
    key.kernel_config = config;
    node->pool.add_new_kernel(key);
    node->specified_key = std::make_unique<FMKey>(key);
    node->real_io = io;
    node->obIn = pre ? OB_USER_IN : OB_TEMP;
    node->obOut = pre ? OB_TEMP : OB_USER_OUT;
    node->sbrcTranstype = pre ? NONE : TILE_ALIGNED;
    node->large1D = pre ? m : 0;
    node->dir2regMode = io.DirectPairIO() ? DirectRegType::TRY_ENABLE_IF_SUPPORT
                                         : DirectRegType::FORCE_OFF_OR_NOT_SUPPORT;
    node->intrinsicMode = IntrinsicAccessType::DISABLE_BOTH;
    node->inStrideUnit = meta.inStride[0] == 1;
    node->outStrideUnit = meta.outStride[0] == 1;
    StoreOps ops;
    ops.scale_factor = scale;
    node->storeOps = ops;
    need(node->KernelCheck(), id + ": kernel check failed");
    need(!pre || (node->largeTwdBase == expected_base && node->ltwdSteps == expected_steps),
         id + ": actual phase decomposition changed");
    need(node->CreateDevKernelArgs() && node->CreateDeviceResources(), id + ": device resources failed");
    GridParam gp;
    node->SetupGridParam(gp);
    need(gp.b_x == RealBlockIO::PairBlocks(pre ? q : c,*slots)
         && gp.wgs_x == expected_p * *slots
         && gp.lds_bytes == meta.length[0] * *slots * (io.ScalarPairIO() ? 8 : 16) + extra,
         id + ": launch geometry changed");
    std::string kernel_name;
    auto compiled = RTCKernel::runtime_compile(*node,"gfx936",kernel_name,callbacks);
    need(compiled.valid() && bool(compiled.get()), id + ": boundary did not compile");

    GuardedBuffer input(original.size()), output(expected.size());
    GuardedBuffer load_counts((in_elements+1)*sizeof(unsigned int));
    GuardedBuffer store_counts((out_elements+1)*sizeof(unsigned int));
    GuardedBuffer load_data(sizeof(CallbackData)), store_data(sizeof(CallbackData));
    const CallbackData lc{static_cast<unsigned int*>(load_counts.data()),in_elements};
    const CallbackData sc{static_cast<unsigned int*>(store_counts.data()),out_elements};
    hip_check(hipMemcpy(load_data.data(),&lc,sizeof(lc),hipMemcpyHostToDevice));
    hip_check(hipMemcpy(store_data.data(),&sc,sizeof(sc),hipMemcpyHostToDevice));
    DeviceCallIn call;
    call.node = node;
    call.bufIn[0] = input.data();
    call.bufOut[0] = output.data();
    call.gridParam = gp;
    call.deviceProp = prop;
    if(callbacks)
    {
        hip_check(hipMemcpyFromSymbol(&call.callbacks.load_cb_fn,HIP_SYMBOL(load_complex_pointer),sizeof(void*)));
        hip_check(hipMemcpyFromSymbol(&call.callbacks.store_cb_fn,HIP_SYMBOL(store_complex_pointer),sizeof(void*)));
        call.callbacks.load_cb_data = load_data.data();
        call.callbacks.store_cb_data = store_data.data();
    }
    double max_error = 0;
    for(unsigned int round=0; round<2; ++round)
    {
        hip_check(hipMemcpy(input.data(),original.data(),original.size(),hipMemcpyHostToDevice));
        hip_check(hipMemset(output.data(),0xff,expected.size()));
        hip_check(hipMemset(load_counts.data(),0,load_counts.bytes));
        hip_check(hipMemset(store_counts.data(),0,store_counts.bytes));
        compiled.get()->launch(call,prop);
        hip_check(hipDeviceSynchronize());
        std::vector<Complex> actual(out_elements), reference(out_elements);
        std::memcpy(reference.data(),expected.data(),expected.size());
        hip_check(hipMemcpy(actual.data(),output.data(),expected.size(),hipMemcpyDeviceToHost));
        double norm=1, error=0;
        for(size_t i=0;i<out_elements;++i)
        {
            need(std::isfinite(actual[i].x) && std::isfinite(actual[i].y),id+": nonfinite/unwritten output");
            norm=std::max(norm,std::hypot(reference[i].x,reference[i].y));
            error=std::max(error,std::hypot(actual[i].x-reference[i].x,actual[i].y-reference[i].y));
        }
        max_error=std::max(max_error,error/norm);
        need(error/norm<1e-9,id+": numerical mismatch "+std::to_string(error/norm));
        std::vector<unsigned char> unchanged(original.size());
        hip_check(hipMemcpy(unchanged.data(),input.data(),unchanged.size(),hipMemcpyDeviceToHost));
        need(unchanged==original,id+": input overwritten");
        for(bool load : {true,false})
        {
            const size_t count=load?in_elements:out_elements;
            std::vector<unsigned int> values(count+1);
            hip_check(hipMemcpy(values.data(),load?load_counts.data():store_counts.data(),
                                values.size()*sizeof(unsigned int),hipMemcpyDeviceToHost));
            const unsigned int wanted=callbacks && (load==pre) ? 1 : 0;
            need(std::all_of(values.begin(),values.end()-1,[&](unsigned int v){return v==wanted;})
                 && values.back()==0,id+": callback ownership mismatch");
        }
        need(input.check() && output.check() && load_counts.check() && store_counts.check()
             && load_data.check() && store_data.check(),id+": guard region changed");
    }
    std::cout<<"CC_BOUNDARY_PASS "<<id<<' '<<n<<' '<<pre<<' '<<c<<' '<<q<<' '
             <<expected_p<<' '<<*slots<<' '<<gp.b_x<<' '<<gp.wgs_x<<' '<<gp.lds_bytes<<' '
             <<io.ExchangeName()<<' '<<int(io.final_phase)<<' '<<callbacks<<' '<<scale<<' '
             <<std::setprecision(17)<<max_error<<' '<<kernel_name<<std::endl;
}

int main(int argc,char** argv)
try
{
    need(argc==3,"manifest policy");
    const int mode=std::stoi(argv[2]);
    need(mode>=0 && mode<=2,"invalid policy");
    fft_check(rocfft_setup());
    hipDeviceProp_t prop{};
    hip_check(hipGetDeviceProperties(&prop,0));
    need(std::string(prop.gcnArchName).find("gfx936")==0,"wrong architecture");
    std::ifstream manifest(argv[1]);
    std::string id,input,expected;
    size_t n,c,q,p,t,base,steps,count=0;
    bool pre,callbacks;
    double scale;
    while(manifest>>id>>n>>pre>>c>>q>>p>>t>>base>>steps>>callbacks>>scale>>input>>expected)
    {
        boundary_case(id,n,pre,c,q,p,t,base,steps,callbacks,scale,input,expected,
                      static_cast<RealPairPolicy>(mode),prop);
        ++count;
    }
    need(manifest.eof() && count>0,"incomplete manifest");
    fft_check(rocfft_cleanup());
    std::cout<<"CC_BOUNDARY_ALL_PASS "<<count<<std::endl;
    return 0;
}
catch(const std::exception& error)
{
    std::cerr<<error.what()<<std::endl;
    return 1;
}
