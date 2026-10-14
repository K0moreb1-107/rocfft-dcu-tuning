// Host-only source exporter.  No plan creation, library execution, or device API calls.
#include "rtc_bluestein_gen.h"
#include "rtc_stockham_gen.h"
#include "rtc_transpose_gen.h"
#include "rtc_test_harness.h"

#include <algorithm>
#include <array>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

void write_standalone_test_harness(const Function&, const std::string&) {}

namespace
{
std::string quote(const std::string& value)
{
    std::string out = "\"";
    for(unsigned char c : value)
    {
        switch(c)
        {
        case '\\': out += "\\\\"; break;
        case '"': out += "\\\""; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if(c < 32)
                throw std::runtime_error("unexpected control character in exporter metadata");
            out += static_cast<char>(c);
        }
    }
    return out + '"';
}

struct Config
{
    unsigned int length, requested_workgroup, threads;
    std::vector<unsigned int> factors;
    bool half, direct;
};

// The requested geometry and factors come from config_sbrr.py in 7942bf0.
const std::vector<Config> configs{
    {169, 256, 13, {13, 13}, true, true},
    {187, 128, 17, {17, 11}, true, true},
    {231, 256, 33, {11, 7, 3}, false, false},
    {384, 128, 32, {6, 4, 4, 4}, true, true},
    {512, 256, 64, {16, 16, 2}, true, true},
    {765, 256, 51, {17, 3, 5, 3}, true, true},
    {96, 128, 16, {6, 16}, false, false},
    {63, 256, 21, {3, 3, 7}, false, true},
    {125, 256, 25, {5, 5, 5}, false, false}};

unsigned int slots_for(const Config& cfg, bool half)
{
    const auto factor_product
        = std::accumulate(cfg.factors.begin(), cfg.factors.end(), 1U, std::multiplies<unsigned int>());
    if(factor_product != cfg.length || cfg.threads == 0)
        throw std::runtime_error("invalid exporter fixture factors");
    // This is StockhamKernel's default double-precision, 32-KiB derivation.
    return std::min(32768U / (cfg.length * (half ? 8U : 16U)),
                    cfg.requested_workgroup / cfg.threads);
}

StockhamGeneratorSpecs rr_specs(const Config& cfg, bool half, bool paired = false)
{
    auto slots = slots_for(cfg, half);
    if(paired) slots -= slots % 2;
    if(slots == 0 || (paired && slots < 4))
        throw std::runtime_error("unsupported exporter fixture block geometry");
    StockhamGeneratorSpecs specs(cfg.factors, {}, {static_cast<unsigned int>(rocfft_precision_double)},
                                 slots * cfg.threads, "CS_KERNEL_STOCKHAM");
    specs.threads_per_transform = cfg.threads;
    specs.half_lds = half;
    specs.direct_to_from_reg = paired || half || cfg.direct;
    specs.wgs_is_derived = true;
    specs.static_dim = 2;
    return specs;
}

std::optional<StoreOps> scale_ops(bool enabled)
{
    if(!enabled) return std::nullopt;
    StoreOps ops;
    ops.scale_factor = 0.375;
    return ops;
}

struct Generated
{
    std::string name, source;
    unsigned int slots = 0;
};

Generated generate_rr(const StockhamGeneratorSpecs& specs, int direction,
                      rocfft_array_type input, rocfft_array_type output,
                      CallbackType callback, bool scale)
{
    const StockhamPartialPassParams pp;
    const auto reg = specs.direct_to_from_reg ? DirectRegType::TRY_ENABLE_IF_SUPPORT
                                              : DirectRegType::FORCE_OFF_OR_NOT_SUPPORT;
    const auto ops = scale_ops(scale);
    const auto unit_stride = input == rocfft_array_type_complex_planar;
    Generated result;
    result.name = stockham_rtc_kernel_name(specs, specs, CS_KERNEL_STOCKHAM, direction,
        rocfft_precision_double, rocfft_placement_notinplace, input, output, unit_stride,
        0, 0, false, reg, IntrinsicAccessType::DISABLE_BOTH, SBRC_TRANSPOSE_TYPE::NONE,
        callback, BFT_NONE, PPT_NONE, pp, std::nullopt, ops);
    result.source = stockham_rtc(specs, specs, pp, &result.slots, result.name,
        CS_KERNEL_STOCKHAM, direction, rocfft_precision_double, rocfft_placement_notinplace,
        input, output, unit_stride, 0, 0, false, reg, IntrinsicAccessType::DISABLE_BOTH,
        SBRC_TRANSPOSE_TYPE::NONE, callback, BFT_NONE, PPT_NONE, std::nullopt, ops);
    if(result.slots != specs.workgroup_size / specs.threads_per_transform)
        throw std::runtime_error("returned transforms-per-block differs from requested geometry");
    return result;
}

struct Exporter
{
    const std::string directory;
    std::ofstream metadata;
    std::map<std::string, unsigned int> counts;
    unsigned int total = 0;

    explicit Exporter(const std::string& directory)
        : directory(directory), metadata(directory + "/metadata.jsonl", std::ios::binary)
    {
        if(!metadata) throw std::runtime_error("cannot open exporter metadata; create output directory first");
    }
    void save(const std::string& family, const Generated& value, const std::string& fields)
    {
        std::ostringstream filename;
        filename << family << '_' << std::setw(3) << std::setfill('0') << counts[family]++ << ".cpp";
        std::ofstream source(directory + '/' + filename.str(), std::ios::binary);
        source.write(value.source.data(), value.source.size());
        if(!source) throw std::runtime_error("cannot save generated source");
        metadata << "{\"family\":" << quote(family) << ",\"index\":" << counts[family] - 1
                 << ",\"file\":" << quote(filename.str())
                 << ",\"kernel_name\":" << quote(value.name)
                 << ",\"source_bytes\":" << value.source.size()
                 << ",\"returned_tpb\":" << value.slots << fields << "}\n";
        if(!metadata) throw std::runtime_error("cannot save metadata");
        ++total;
    }
};

std::string rr_fields(const Config& cfg, const StockhamGeneratorSpecs& specs,
                     int direction, CallbackType cb, bool scale, bool planar,
                     size_t axis = 0, const std::string& role = "none")
{
    std::ostringstream s;
    s << ",\"role\":" << quote(role) << ",\"span\":" << cfg.length
      << ",\"axis\":" << axis << ",\"real_n\":" << 2 * axis * cfg.length
      << ",\"threads_per_transform\":" << cfg.threads
      << ",\"original_default_tpb\":" << slots_for(cfg, cfg.half)
      << ",\"workgroup_size\":" << specs.workgroup_size
      << ",\"half_lds\":" << (specs.half_lds ? "true" : "false")
      << ",\"half_is_default\":" << (specs.half_lds == cfg.half ? "true" : "false")
      << ",\"direction\":" << direction << ",\"callback\":" << static_cast<int>(cb)
      << ",\"scale\":" << (scale ? "true" : "false")
      << ",\"planar\":" << (planar ? "true" : "false")
      << ",\"partial_first\":"
      << ((cfg.length / cfg.factors.front()) % cfg.threads != 0 ? "true" : "false")
      << ",\"partial_last\":"
      << ((cfg.length / cfg.factors.back()) % cfg.threads != 0 ? "true" : "false")
      << ",\"factors\":[";
    for(size_t i = 0; i < cfg.factors.size(); ++i)
        s << (i ? "," : "") << cfg.factors[i];
    return s.str() + ']';
}

void ordinary_rr(Exporter& out)
{
    for(const auto& cfg : configs)
        for(bool half : {false, true})
            for(int direction : {-1, 1})
                for(bool scale : {false, true})
                {
                    const auto specs = rr_specs(cfg, half);
                    for(auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE})
                        out.save("rr_normal", generate_rr(specs, direction,
                            rocfft_array_type_complex_interleaved, rocfft_array_type_complex_interleaved,
                            cb, scale), rr_fields(cfg, specs, direction, cb, scale, false));
                    out.save("rr_normal", generate_rr(specs, direction,
                        rocfft_array_type_complex_planar, rocfft_array_type_complex_planar,
                        CallbackType::NONE, scale),
                        rr_fields(cfg, specs, direction, CallbackType::NONE, scale, true));
                }
}

TransposeSpecs transpose_specs(size_t dim, bool aligned, bool grid3d, size_t large,
                               int direction, bool diagonal, bool planar,
                               CallbackType cb, bool scale, bool single = false)
{
    const auto type = planar ? rocfft_array_type_complex_planar : rocfft_array_type_complex_interleaved;
    return {single ? 64U : 32U, single ? 16U : 32U, dim,
            single ? rocfft_precision_single : rocfft_precision_double,
            type, type, large, direction, diagonal, aligned, cb, std::nullopt,
            scale_ops(scale), grid3d};
}

Generated generate_transpose(const TransposeSpecs& specs)
{
    Generated result;
    result.name = transpose_rtc_kernel_name(specs);
    result.source = transpose_rtc(result.name, specs);
    return result;
}

void ordinary_transpose(Exporter& out)
{
    struct Variant {size_t dim, large; bool aligned, grid3d, diagonal; int direction;};
    const std::array<Variant, 8> variants{{
        {2, 0, false, true, false, -1}, {2, 0, true, true, true, -1},
        {2, 0, false, false, false, 1}, {3, 0, true, true, false, -1},
        {3, 0, false, false, false, 1}, {2, 2, false, true, false, -1},
        {2, 3, true, false, false, 1}, {3, 4, false, true, false, -1}}};
    for(const auto& v : variants)
        for(bool planar : {false, true})
            for(bool scale : {false, true})
                for(auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE})
                {
                    if(planar && cb != CallbackType::NONE) continue;
                    const auto specs = transpose_specs(v.dim, v.aligned, v.grid3d, v.large,
                        v.direction, v.diagonal, planar, cb, scale);
                    std::ostringstream fields;
                    fields << ",\"role\":\"none\",\"dim\":" << v.dim
                           << ",\"large_twiddle_steps\":" << v.large
                           << ",\"callback\":" << static_cast<int>(cb)
                           << ",\"scale\":" << (scale ? "true" : "false")
                           << ",\"planar\":" << (planar ? "true" : "false");
                    out.save("transpose_normal", generate_transpose(specs), fields.str());
                }
    for(bool scale : {false, true})
        out.save("transpose_normal", generate_transpose(transpose_specs(
            2, false, false, 0, -1, false, false, CallbackType::NONE, scale, true)),
            ",\"role\":\"none\",\"precision\":\"single\"");
}

void bluestein_unchanged(Exporter& out)
{
    for(const auto scheme : {CS_KERNEL_CHIRP, CS_KERNEL_PAD_MUL, CS_KERNEL_FFT_MUL, CS_KERNEL_RES_MUL})
        for(auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE})
            for(bool scale : {false, true})
            {
                if((scheme == CS_KERNEL_CHIRP || scheme == CS_KERNEL_FFT_MUL)
                   && (cb != CallbackType::NONE || scale)) continue;
                if(scheme == CS_KERNEL_PAD_MUL && scale) continue;
                BluesteinMultiSpecs specs{};
                specs.scheme = scheme; specs.precision = rocfft_precision_double;
                specs.inArrayType = specs.outArrayType = rocfft_array_type_complex_interleaved;
                specs.cbtype = cb; specs.storeOps = scale_ops(scale);
                Generated result;
                result.name = bluestein_multi_rtc_kernel_name(specs);
                result.source = bluestein_multi_rtc(result.name, specs);
                out.save("blue_normal", result, ",\"role\":\"none\"");
            }
    // Bluestein roles already existed at the matching reference commit.
    for(bool pre : {true, false})
        for(size_t n : {65538UL, 65540UL, 117652UL, 117654UL})
            for(auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE})
                for(bool scale : {false, true})
                {
                    if(pre && scale) continue;
                    BluesteinMultiSpecs specs{};
                    specs.scheme = pre ? CS_KERNEL_PAD_MUL : CS_KERNEL_RES_MUL;
                    specs.precision = rocfft_precision_double;
                    specs.inArrayType = pre ? rocfft_array_type_hermitian_interleaved
                                           : rocfft_array_type_complex_interleaved;
                    specs.outArrayType = pre ? rocfft_array_type_complex_interleaved
                                            : rocfft_array_type_hermitian_interleaved;
                    specs.cbtype = cb; specs.storeOps = scale_ops(scale);
                    specs.real_boundary.direction = pre ? RealBoundaryDirection::Pre : RealBoundaryDirection::Post;
                    specs.real_boundary.container = RealBoundaryContainer::Bluestein;
                    specs.real_boundary.n = n;
                    Generated result;
                    result.name = bluestein_multi_rtc_kernel_name(specs);
                    result.source = bluestein_multi_rtc(result.name, specs);
                    out.save("blue_real", result, ",\"role\":" + quote(pre ? "pre" : "post")
                             + ",\"real_n\":" + std::to_string(n));
                }
}

#ifdef EXP127_REAL_TR_NEW_SOURCE
void paired_rows(Exporter& out)
{
    for(const auto& cfg : configs)
        for(bool pre : {true, false})
            for(auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE})
                for(bool scale : {false, true})
                {
                    if(pre && scale) continue; // The pre boundary writes intermediate data.
                    Generated first;
                    for(size_t axis : {1001UL, 1002UL})
                    {
                        auto specs = rr_specs(cfg, cfg.half, true);
                        specs.static_initial_reg_load = true;
                        specs.static_initial_reg_load_linear = true;
                        specs.real_boundary.direction = pre ? RealBoundaryDirection::Pre : RealBoundaryDirection::Post;
                        specs.real_boundary.container = RealBoundaryContainer::Rows;
                        specs.real_boundary.n = 2 * cfg.length * axis;
                        const auto input = pre ? rocfft_array_type_hermitian_interleaved
                                               : rocfft_array_type_complex_interleaved;
                        const auto output = pre ? rocfft_array_type_complex_interleaved
                                                : rocfft_array_type_hermitian_interleaved;
                        const auto generated = generate_rr(specs, pre ? 1 : -1, input, output, cb, scale);
                        if(!first.name.empty()
                           && (first.name != generated.name || first.source != generated.source
                               || first.slots != generated.slots))
                            throw std::runtime_error("rows source/name unexpectedly depends on complete N");
                        first = generated;
                        out.save("rr_real", generated, rr_fields(cfg, specs, pre ? 1 : -1,
                            cb, scale, false, axis, pre ? "pre" : "post"));
                    }
                }
}

void paired_transpose(Exporter& out)
{
    const std::array<std::array<size_t, 2>, 4> shapes{{
        {238, 147}, {441, 243}, {384, 352}, {765, 765}}};
    for(bool pre : {true, false})
        for(auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE})
            for(bool scale : {false, true})
            {
                if(pre && scale) continue;
                Generated first;
                for(const auto& shape : shapes)
                {
                    auto specs = transpose_specs(2, false, false, 0, pre ? 1 : -1,
                        false, false, cb, scale);
                    specs.inArrayType = pre ? rocfft_array_type_hermitian_interleaved
                                           : rocfft_array_type_complex_interleaved;
                    specs.outArrayType = pre ? rocfft_array_type_complex_interleaved
                                            : rocfft_array_type_hermitian_interleaved;
                    specs.real_boundary.direction = pre ? RealBoundaryDirection::Pre : RealBoundaryDirection::Post;
                    specs.real_boundary.container = RealBoundaryContainer::Transpose;
                    specs.real_boundary.n = 2 * shape[0] * shape[1];
                    const auto generated = generate_transpose(specs);
                    if(!first.name.empty() && (first.name != generated.name || first.source != generated.source))
                        throw std::runtime_error("transpose source/name unexpectedly depends on complete N");
                    first = generated;
                    out.save("transpose_real", generated, ",\"role\":" + quote(pre ? "pre" : "post")
                             + ",\"axis\":" + std::to_string(shape[0])
                             + ",\"span\":" + std::to_string(shape[1])
                             + ",\"real_n\":" + std::to_string(specs.real_boundary.n)
                             + ",\"callback\":" + std::to_string(static_cast<int>(cb))
                             + ",\"scale\":" + (scale ? "true" : "false"));
                }
            }
}
#endif
}

int main(int argc, char** argv)
{
    try
    {
        if(argc != 2) throw std::runtime_error("usage: trtrt_native_export EXISTING_OUTPUT_DIRECTORY");
        Exporter exporter(argv[1]);
        ordinary_rr(exporter);
        ordinary_transpose(exporter);
        bluestein_unchanged(exporter);
#ifdef EXP127_REAL_TR_NEW_SOURCE
        paired_rows(exporter);
        paired_transpose(exporter);
#endif
        std::cout << "exported=" << exporter.total;
        for(const auto& item : exporter.counts) std::cout << ' ' << item.first << '=' << item.second;
        std::cout << '\n';
        return 0;
    }
    catch(const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
