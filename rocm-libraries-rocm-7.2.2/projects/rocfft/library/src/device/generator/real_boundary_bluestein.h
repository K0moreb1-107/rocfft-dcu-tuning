#pragma once

#include "generator.h"
#include "real_pair_layout.h"

// The launcher retains ordinary Bluestein offsets: PAD's output starts at L,
// and this kernel writes at output[L+k]; RES reads input[2*L+k].
static Function real_boundary_bluestein_kernel(const std::string& kernel_name,
                                                const BluesteinMultiSpecs& specs)
{
    const bool pre = specs.real_boundary.Pre();
    Variable half_length{"half_length", "size_t"}, blue_length{"blue_length", "size_t"};
    Variable phase{"real_phase", "const scalar_type", true, true};
    Variable input{"input", "scalar_type", true, true};
    Variable output{"output", "scalar_type", true, true};
    Function func{kernel_name};
    func.qualifier = "extern \"C\" __global__";
    func.launch_bounds = LAUNCH_BOUNDS_BLUESTEIN_MULTI_KERNEL;
    for(const auto& arg : {half_length, blue_length, phase, input, output})
        func.arguments.append(arg);
    for(const auto& arg : get_callback_args().arguments)
        func.arguments.append(arg);

    Variable task{"task", "size_t"}, pairs{"pairs", "size_t"};
    Variable k{"k", "size_t"}, peer{"peer", "size_t"};
    Variable p{"p", "scalar_type"}, q{"q", "scalar_type"};
    Variable own{"own", "scalar_type"}, other{"other", "scalar_type"};
    Variable chirp{"chirp", "scalar_type"}, peer_chirp{"peer_chirp", "scalar_type"};
    Variable inv_length{"inv_length", "real_type_t<scalar_type>"};
    func.body += Declaration{task, Literal{"size_t(blockIdx.x) * blockDim.x + threadIdx.x"}};
    func.body += Declaration{pairs, half_length / 2 + 1};
    const Expression total = pre ? Expression{pairs + blue_length - half_length}
                                 : Expression{pairs};
    func.body += If{task >= total, {Return{}}};
    if(pre)
    {
        // Padding has no user reads, callbacks or coefficient loads.
        func.body += If{task >= pairs,
                        {Assign{output[blue_length + half_length + task - pairs],
                                CallExpr{"scalar_type", {0, 0}}}, Return{}}};
    }
    func.body += CallbackLoadDeclaration("scalar_type", "cbtype");
    func.body += CallbackStoreDeclaration("scalar_type", "cbtype");
    if(!pre)
        func.body += Declaration{inv_length, Literal{"1.0"}
                                     / CallExpr{"real_type_t<scalar_type>", {blue_length}}};
    func.body += Declaration{k, task};

    // DC/Nyquist have unique ownership; chirp[0] is exactly (1,0).
    If endpoints{k == 0, {}};
    if(pre)
    {
        endpoints.body += Declaration{p, LoadGlobal{input, 0}};
        endpoints.body += Declaration{q, LoadGlobal{input, half_length}};
        endpoints.body += Assign{output[blue_length],
                                 CallExpr{"scalar_type", {p.x() + q.x(), p.x() - q.x()}}};
    }
    else
    {
        endpoints.body += Declaration{p, input[2 * blue_length]};
        endpoints.body += StoreGlobal{output, 0,
            CallExpr{"scalar_type", {inv_length * (p.x() + p.y()), 0}}};
        endpoints.body += StoreGlobal{output, half_length,
            CallExpr{"scalar_type", {inv_length * (p.x() - p.y()), 0}}};
    }
    endpoints.body += Return{};
    func.body += endpoints;
    func.body += Declaration{chirp, pre ? output[k] : input[k]};

    // Even M has one self-mirror frequency. Odd M has only ordinary pairs.
    If middle{(half_length % 2 == 0) && (k == half_length / 2), {}};
    if(pre)
    {
        middle.body += Declaration{p, LoadGlobal{input, k}};
        middle.body += Assign{output[blue_length + k],
            CallExpr{"real_blue_multiply", {CallExpr{"scalar_type", {2 * p.x(), -2 * p.y()}},
                                              chirp, 1}}};
    }
    else
    {
        middle.body += Declaration{p,
            CallExpr{"real_blue_multiply", {input[2 * blue_length + k], chirp, inv_length}}};
        middle.body += StoreGlobal{output, k, CallExpr{"scalar_type", {p.x(), -p.y()}}};
    }
    middle.body += Return{};
    func.body += middle;

    func.body += Declaration{peer, half_length - k};
    func.body += Declaration{peer_chirp, chirp};
    func.body += If{half_length % 2 != 0,
                   {Assign{peer_chirp.x(), -peer_chirp.x()},
                    Assign{peer_chirp.y(), -peer_chirp.y()}}};
    if(pre)
    {
        func.body += Declaration{p, LoadGlobal{input, k}};
        func.body += Declaration{q, LoadGlobal{input, peer}};
    }
    else
    {
        func.body += Declaration{p,
            CallExpr{"real_blue_multiply", {input[2 * blue_length + k], chirp, inv_length}}};
        func.body += Declaration{q,
            CallExpr{"real_blue_multiply", {input[2 * blue_length + peer], peer_chirp, inv_length}}};
    }
    func.body += Declaration{own};
    func.body += Declaration{other};
    func.body += Call{pre ? "real_pair_pre" : "real_pair_post", {p, q, phase[k], own, other}};
    if(pre)
    {
        func.body += Assign{output[blue_length + k],
                            CallExpr{"real_blue_multiply", {own, chirp, 1}}};
        func.body += Assign{output[blue_length + peer],
                            CallExpr{"real_blue_multiply", {other, peer_chirp, 1}}};
    }
    else
    {
        func.body += StoreGlobal{output, k, own};
        func.body += StoreGlobal{output, peer, other};
    }
    make_load_store_ops(func, specs.loadOps, specs.storeOps);
    return make_callback_realcomplex(func, specs.cbtype);
}

static std::string real_boundary_bluestein_helpers()
{
    return real_pair_layout_device_helpers() + R"src(
template <typename T>
__device__ __forceinline__ T real_blue_multiply(T value, T chirp, real_type_t<T> scale)
{
    return T{scale * (value.x * chirp.x + value.y * chirp.y),
             scale * (value.y * chirp.x - value.x * chirp.y)};
}
)src";
}
