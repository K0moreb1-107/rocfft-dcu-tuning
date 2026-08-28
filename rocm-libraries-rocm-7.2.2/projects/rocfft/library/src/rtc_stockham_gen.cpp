// Copyright (C) 2022 - 2023 Advanced Micro Devices, Inc. All rights reserved.
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

#include <functional>
#include <set>
#include <sstream>

#include "../../shared/array_predicate.h"
#include "rtc_stockham_gen.h"
#include "rtc_test_harness.h"

using namespace std::placeholders;

#include "device/generator/bluestein_generator.h"
#include "device/generator/generator.h"
#include "device/generator/stockham_gen.h"
#include "device/generator/stockham_gen_base.h"

#include "device/generator/stockham_gen_cc.h"
#include "device/generator/stockham_gen_cr.h"
#include "device/generator/stockham_gen_rc.h"
#include "device/generator/stockham_gen_rr.h"
#include "device/generator/stockham_pp_gen_cc.h"
#include "device/generator/stockham_pp_gen_rr.h"

#include "device/generator/stockham_gen_2d.h"

#include "tree_node_1D.h"

#include "device/kernel-generator-embed.h"

namespace
{
bool is_callback_argument(const std::string& name)
{
    return name == "load_cb_fn" || name == "load_cb_data" || name == "load_cb_lds_bytes"
           || name == "store_cb_fn" || name == "store_cb_data";
}

// The producer and consumer global functions are placed in separate lexical
// blocks, so their local offset/tile variables can remain unchanged.  Only
// arguments and stage-specific template constants need distinct names.
struct FusedGlobalVariableVisitor : public BaseVisitor
{
    FusedGlobalVariableVisitor(const std::string& prefix,
                               const Function&   global,
                               const std::string& block_id_name)
        : prefix(prefix)
        , block_id_name(block_id_name)
    {
        for(const auto& arg : global.arguments.arguments)
            renamed.insert(arg.name);

        static const std::set<std::string> stage_constants = {
            "sb",
            "drtype",
            "intrinsic_mode",
            "apply_large_twiddle",
            "large_twiddle_steps",
            "large_twiddle_base",
            "sbrc_type",
            "transpose_type",
            "cbtype",
        };
        renamed.insert(stage_constants.begin(), stage_constants.end());
    }

    Expression visit_Variable(const Variable& x) override
    {
        if(x.name == "blockIdx.x")
        {
            auto y = x;
            y.name = block_id_name;
            return y;
        }

        // Callback declarations render their ABI names literally
        // (load_cb_fn/load_cb_data/store_cb_fn/store_cb_data).  Keep these
        // shared outer-kernel arguments unprefixed; all stage data arguments
        // remain private to their lexical block.
        if(!renamed.count(x.name)
           || x.name.rfind(prefix, 0) == 0
           || x.name == "scalar_type"
           || is_callback_argument(x.name))
        {
            auto y = x;
            if(x.index)
                y.index = std::visit(*this, *x.index);
            if(x.index2D)
                y.index2D = std::visit(*this, *x.index2D);
            if(x.size)
                y.size = std::visit(*this, *x.size);
            if(x.size2D)
                y.size2D = std::visit(*this, *x.size2D);
            return y;
        }

        auto y = x;
        y.name = prefix + x.name;
        if(x.index)
            y.index = std::visit(*this, *x.index);
        if(x.index2D)
            y.index2D = std::visit(*this, *x.index2D);
        if(x.size)
            y.size = std::visit(*this, *x.size);
        if(x.size2D)
            y.size2D = std::visit(*this, *x.size2D);
        return y;
    }

    StatementList visit_CallbackLoadDeclaration(const CallbackLoadDeclaration& x) override
    {
        auto y = x;
        y.cbtype = prefix + "cbtype";
        return {y};
    }

    StatementList visit_CallbackStoreDeclaration(const CallbackStoreDeclaration& x) override
    {
        auto y = x;
        y.cbtype = prefix + "cbtype";
        return {y};
    }

    std::string       prefix;
    std::string       block_id_name;
    std::set<std::string> renamed;
};

struct FusedFunctionPrefixVisitor : public BaseVisitor
{
    FusedFunctionPrefixVisitor(const std::string& prefix, const std::set<std::string>& names)
        : prefix(prefix)
        , names(names)
    {
    }

    Expression visit_CallExpr(const CallExpr& x) override
    {
        auto y = x;
        if(names.count(x.name))
            y.name = prefix + x.name;
        return BaseVisitor::visit_CallExpr(y);
    }

    Function visit_Function(const Function& x) override
    {
        auto y = x;
        if(names.count(x.name))
            y.name = prefix + x.name;
        return BaseVisitor::visit_Function(y);
    }

    std::string       prefix;
    std::set<std::string> names;
};

// A streaming fused launch may use the consumer workgroup size for both
// stages.  When the producer has fewer threads, fold the extra lanes onto the
// producer's local lane space so every lane still reaches the producer's
// barriers.  The duplicated lanes write identical LDS values; the handoff
// guard filters the producer rows that belong to the current consumer tile.
struct FusedProducerThreadVisitor : public BaseVisitor
{
    explicit FusedProducerThreadVisitor(unsigned int producer_wgs)
        : producer_wgs(producer_wgs)
    {
    }

    Expression visit_Variable(const Variable& x) override
    {
        if(x.name == "threadIdx.x" && producer_wgs != 0)
        {
            return Expression{Variable{"threadIdx.x", "unsigned int"}
                               % Literal{producer_wgs}};
        }
        return x;
    }

    unsigned int producer_wgs;
};

struct FusedStageRewriteVisitor : public BaseVisitor
{
    FusedStageRewriteVisitor(bool   producer,
                             bool   streaming_producer,
                             size_t consumer_tile_width,
                             size_t consumer_tiles_per_plane,
                             size_t consumer_length,
                             bool   global_handoff,
                             bool   consumer_handoff_lds = false)
        : producer(producer)
        , streaming_producer(streaming_producer)
        , consumer_tile_width(consumer_tile_width)
        , consumer_tiles_per_plane(consumer_tiles_per_plane)
        , consumer_length(consumer_length)
        , global_handoff(global_handoff)
        , consumer_handoff_lds(consumer_handoff_lds)
        , consumer_load_phase(!producer)
    {
    }

    StatementList visit_Call(const Call& x) override
    {
        auto result = BaseVisitor::visit_Call(x);
        if(!producer && x.expr.name.rfind("lds_to_reg_input_", 0) == 0)
            consumer_load_phase = false;
        return result;
    }
    Expression visit_Variable(const Variable& x) override
    {
        // The producer stage is rendered inside the fused outer-kernel ABI.
        // Bind its stride array before the later lexical variable rewrite so
        // handoff expressions cannot retain the standalone name stride_out.
        auto y = x;
        if(producer && x.name == "stride_out")
            y.name = "producer_stride_out";
        if(!producer && consumer_handoff_lds && x.name == "lds_complex")
            y.name = "fused_handoff_lds";
        if(!producer && consumer_handoff_lds && x.name == "lds_real")
            y.name = "fused_handoff_lds_real";
        if(x.index)
            y.index = std::visit(*this, *x.index);
        if(x.index2D)
            y.index2D = std::visit(*this, *x.index2D);
        if(x.size)
            y.size = std::visit(*this, *x.size);
        if(x.size2D)
            y.size2D = std::visit(*this, *x.size2D);
        return y;
    }


    Expression handoff_index(const Expression& physical_offset) const
    {
        const Variable producer_stride0_out{"producer_stride_out[0]", "size_t"};
        const Variable consumer_block_id{"consumer_block_id", "unsigned int"};
        const Literal  consumer_tile_count{
            static_cast<unsigned int>(consumer_tiles_per_plane)};
        const Literal consumer_tile_width_literal{
            static_cast<unsigned int>(consumer_tile_width)};
        const Literal consumer_length_literal{static_cast<unsigned int>(consumer_length)};

        const Variable producer_batch_stride{"producer_stride_out[2]", "size_t"};
        const Expression batch_local_offset = physical_offset % producer_batch_stride;
        const Expression producer_row = batch_local_offset / producer_stride0_out;
        const Expression producer_col = batch_local_offset % producer_stride0_out;
        const Expression consumer_tile
            = consumer_block_id % consumer_tile_count;
        const Expression consumer_tile_start = consumer_tile * consumer_tile_width_literal;
        const Expression lds_index
            // Keep the EXP-029 producer-tile layout while the consumer's
            // generated LDS-to-register mapping is audited from RTC output.
            = producer_col
              + (producer_row - consumer_tile_start) * consumer_length_literal;

        // Each producer block covers a contiguous slice in the transposed
        // output.  Only the rows owned by this consumer block are retained.
        return Expression{lds_index};
    }

    If handoff_store(const Expression& physical_offset,
                     const Expression& value,
                     const OptionalExpression& rw_flag = {}) const
    {
        const Variable producer_stride0_out{"producer_stride_out[0]", "size_t"};
        const Variable consumer_block_id{"consumer_block_id", "unsigned int"};
        const Literal  consumer_tile_count{
            static_cast<unsigned int>(consumer_tiles_per_plane)};
        const Literal consumer_tile_width_literal{
            static_cast<unsigned int>(consumer_tile_width)};
        const Literal consumer_length_literal{static_cast<unsigned int>(consumer_length)};

        const Variable producer_batch_stride{"producer_stride_out[2]", "size_t"};
        const Expression batch_local_offset = physical_offset % producer_batch_stride;
        const Expression producer_row = batch_local_offset / producer_stride0_out;
        const Expression producer_col = batch_local_offset % producer_stride0_out;
        const Expression consumer_tile
            = consumer_block_id % consumer_tile_count;
        const Expression consumer_tile_start = consumer_tile * consumer_tile_width_literal;
        const Expression consumer_tile_end
            = consumer_tile_start + consumer_tile_width_literal;
        Expression       guard
            = (producer_row >= consumer_tile_start && producer_row < consumer_tile_end)
              && (producer_col < consumer_length_literal);
        if(rw_flag)
            guard = guard && *rw_flag;
        // The producer ABI is folded onto a larger consumer workgroup.  Keep
        // the handoff single-writer so duplicated producer lanes do not race
        // while still participating in every producer barrier.
        guard = guard && Variable{"fused_producer_owner", "bool"};

        Variable lds_complex{"fused_handoff_lds", "scalar_type", true, true};
        return If{guard,
                  {Assign{lds_complex[handoff_index(physical_offset)], value}}};
    }

    StatementList visit_LDSDeclaration(const LDSDeclaration&) override
    {
        return {};
    }

    StatementList visit_StoreGlobal(const StoreGlobal& x) override
    {
        if(producer)
        {
            if(global_handoff)
            {
                auto stores = BaseVisitor::visit_StoreGlobal(x);
                if(streaming_producer)
                    return {If{Variable{"fused_producer_owner", "bool"}, stores}};
                return stores;
            }

            // The SBCC reg-to-LDS phase has already produced this value in the
            // same LDS tile.  Dropping the global store keeps that value alive.
            if(!streaming_producer)
                return {};

            return {handoff_store(std::visit(*this, x.index),
                                  std::visit(*this, x.value))};
        }
        return BaseVisitor::visit_StoreGlobal(x);
    }

    StatementList visit_IntrinsicStore(const IntrinsicStore& x) override
    {
        if(!producer)
            return BaseVisitor::visit_IntrinsicStore(x);

        if(global_handoff)
        {
            auto stores = BaseVisitor::visit_IntrinsicStore(x);
            if(streaming_producer)
                return {If{Variable{"fused_producer_owner", "bool"}, stores}};
            return stores;
        }

        if(!streaming_producer)
            return BaseVisitor::visit_IntrinsicStore(x);

        const auto physical_offset
            = std::visit(*this, x.voffset) + std::visit(*this, x.soffset);
        const auto value = std::visit(*this, x.value);
        const auto rw_flag = std::visit(*this, x.rw_flag);
        return {handoff_store(physical_offset, value, OptionalExpression{rw_flag})};
    }

    StatementList visit_StoreGlobalPlanar(const StoreGlobalPlanar& x) override
    {
        if(producer && !global_handoff)
            return {};
        return BaseVisitor::visit_StoreGlobalPlanar(x);
    }

    StatementList visit_Assign(const Assign& x) override
    {
        // SBRC's regular global-load path writes the same LDS locations that
        // the producer just filled.  Remove those writes, while leaving the
        // following LDS-to-register helper call intact.
        if(!producer && !global_handoff && consumer_load_phase && x.lhs.name == "lds_complex"
           && x.lhs.index)
            return {};
        return BaseVisitor::visit_Assign(x);
    }

    bool   producer;
    bool   streaming_producer;
    size_t consumer_tile_width;
    size_t consumer_tiles_per_plane;
    size_t consumer_length;
    bool   global_handoff;
    bool   consumer_handoff_lds;
    bool   consumer_load_phase;
};

std::set<std::string> function_names(const std::vector<Function>& funcs)
{
    std::set<std::string> names;
    for(const auto& f : funcs)
        names.insert(f.name);
    return names;
}

ArgumentList prefixed_arguments(const Function& global,
                                const std::string& prefix,
                                bool               include_callback_arguments)
{
    ArgumentList args;
    for(const auto& arg : global.arguments.arguments)
    {
        if(!include_callback_arguments && is_callback_argument(arg.name))
            continue;
        auto renamed = arg;
        if(!is_callback_argument(arg.name))
            renamed.name = prefix + arg.name;
        args.append(renamed);
    }
    return args;
}

std::vector<unsigned int> to_uint_factors(const std::vector<size_t>& factors)
{
    std::vector<unsigned int> result;
    result.reserve(factors.size());
    for(auto factor : factors)
        result.push_back(static_cast<unsigned int>(factor));
    return result;
}

StockhamGeneratorSpecs make_fused_specs(const FusedSBCCSBRCNode& node, bool producer)
{
    const auto factors = producer ? to_uint_factors(node.kernelFactors)
                                  : to_uint_factors(node.consumerKernelFactors);
    const auto wgs      = producer ? node.producerWgs : node.consumerWgs;
    const auto tpt      = producer ? node.producerThreadsPerTransform
                                   : node.consumerThreadsPerTransform;
    const auto aot      = producer ? node.producerAotRtc : node.consumerAotRtc;
    const auto scheme   = producer ? CS_KERNEL_STOCKHAM_BLOCK_CC : CS_KERNEL_STOCKHAM_BLOCK_RC;

    StockhamGeneratorSpecs specs(factors,
                                 {},
                                 {static_cast<unsigned int>(node.precision)},
                                 wgs,
                                 PrintScheme(scheme));
    specs.threads_per_transform = tpt;
    specs.half_lds              = producer ? node.producerHalfLds : false;
    specs.direct_to_from_reg    = producer ? node.producerDirectToFromReg : true;
    specs.static_dim            = aot ? 0 : static_cast<unsigned int>(node.length.size());
    specs.ebtype                = EmbeddedType::NONE;
    specs.wgs_is_derived        = true;
    return specs;
}

std::string fused_transpose_name(SBRC_TRANSPOSE_TYPE type)
{
    switch(type)
    {
    case NONE:
        return "none";
    case DIAGONAL:
        return "diagonal";
    case TILE_ALIGNED:
        return "aligned";
    case TILE_UNALIGNED:
        return "unaligned";
    }
    return "unknown";
}

std::string fused_transpose_constant_name(SBRC_TRANSPOSE_TYPE type)
{
    switch(type)
    {
    case NONE:
        return "NONE";
    case DIAGONAL:
        return "DIAGONAL";
    case TILE_ALIGNED:
        return "TILE_ALIGNED";
    case TILE_UNALIGNED:
        return "TILE_UNALIGNED";
    }
    return "NONE";
}

std::string fused_intrinsic_name(IntrinsicAccessType type)
{
    switch(type)
    {
    case IntrinsicAccessType::DISABLE_BOTH:
        return "disabled";
    case IntrinsicAccessType::ENABLE_LOAD_ONLY:
        return "load";
    case IntrinsicAccessType::ENABLE_BOTH:
        return "readwrite";
    }
    return "unknown";
}

std::vector<Function> prefix_fused_functions(std::vector<Function> functions,
                                             const std::string&  prefix)
{
    const auto names = function_names(functions);
    FusedFunctionPrefixVisitor visitor(prefix, names);
    for(auto& function : functions)
        function = visitor(function);
    return functions;
}

void append_fused_function_source(std::string& src, const std::vector<Function>& functions)
{
    for(const auto& function : functions)
        src += function.render();
}

void append_fused_stage_constants(std::string&                         src,
                                  const std::string&                   prefix,
                                  bool                                  unit_stride,
                                  DirectRegType                         dir2reg_mode,
                                  IntrinsicAccessType                   intrinsic_mode,
                                  bool                                  apply_large_twiddle,
                                  size_t                                large_twiddle_base,
                                  size_t                                large_twiddle_steps,
                                  SBRC_TRANSPOSE_TYPE                   transpose_type)
{
    src += "static const StrideBin " + prefix + "sb = "
           + (unit_stride ? "SB_UNIT;\n" : "SB_NONUNIT;\n");
    src += "static const SBRC_TYPE " + prefix + "sbrc_type = SBRC_2D;\n";
    src += "static const SBRC_TRANSPOSE_TYPE " + prefix + "transpose_type = "
           + fused_transpose_constant_name(transpose_type) + ";\n";
    src += "static const CallbackType " + prefix + "cbtype = CallbackType::NONE;\n";
    src += "static const DirectRegType " + prefix + "drtype = "
           + (dir2reg_mode == DirectRegType::TRY_ENABLE_IF_SUPPORT
                  ? "DirectRegType::TRY_ENABLE_IF_SUPPORT;\n"
                  : "DirectRegType::FORCE_OFF_OR_NOT_SUPPORT;\n");
    src += "static const IntrinsicAccessType " + prefix + "intrinsic_mode = ";
    switch(intrinsic_mode)
    {
    case IntrinsicAccessType::DISABLE_BOTH:
        src += "IntrinsicAccessType::DISABLE_BOTH;\n";
        break;
    case IntrinsicAccessType::ENABLE_LOAD_ONLY:
        src += "IntrinsicAccessType::ENABLE_LOAD_ONLY;\n";
        break;
    case IntrinsicAccessType::ENABLE_BOTH:
        src += "IntrinsicAccessType::ENABLE_BOTH;\n";
        break;
    }
    src += "static const bool " + prefix + "apply_large_twiddle = "
           + (apply_large_twiddle ? "true;\n" : "false;\n");
    src += "static const size_t " + prefix + "large_twiddle_base = "
           + std::to_string(large_twiddle_base) + ";\n";
    src += "static const size_t " + prefix + "large_twiddle_steps = "
           + std::to_string(large_twiddle_steps) + ";\n";
}
}

// generate name for RTC stockham kernel
std::string stockham_rtc_kernel_name(const StockhamGeneratorSpecs&    specs,
                                     const StockhamGeneratorSpecs&    specs2d,
                                     ComputeScheme                    scheme,
                                     int                              direction,
                                     rocfft_precision                 precision,
                                     rocfft_result_placement          placement,
                                     rocfft_array_type                inArrayType,
                                     rocfft_array_type                outArrayType,
                                     bool                             unitstride,
                                     size_t                           largeTwdBase,
                                     size_t                           largeTwdSteps,
                                     bool                             largeTwdBatchIsTransformCount,
                                     DirectRegType                    dir2regMode,
                                     IntrinsicAccessType              intrinsicMode,
                                     SBRC_TRANSPOSE_TYPE              transpose_type,
                                     CallbackType                     cbtype,
                                     BluesteinFuseType                fuseBlue,
                                     PartialPassType                  ppType,
                                     const StockhamPartialPassParams& ppParams,
                                     const std::optional<LoadOps>&    loadOps,
                                     const std::optional<StoreOps>&   storeOps)
{
    std::string kernel_name = "fft_rtc";

    if(direction == -1)
        kernel_name += "_fwd";
    else
        kernel_name += "_back";

    switch(ppType)
    {
    case PPT_NONE:
        break;
    case PPT_SBCC:
    case PPT_SBRR:
        kernel_name += "_partial_pass";
        kernel_name += "_parent_len";
        for(auto f : ppParams.parent_length)
            kernel_name += "_" + std::to_string(f);
        break;
    }

    kernel_name += "_len_";
    kernel_name += std::to_string(specs.length);
    if(scheme == CS_KERNEL_2D_SINGLE)
        kernel_name += "x" + std::to_string(specs2d.length);

    // need to save the kernel configurations in name,
    kernel_name += "_factors";
    for(auto f : specs.factors)
    {
        kernel_name += "_";
        kernel_name += std::to_string(f);
    }
    if(scheme == CS_KERNEL_2D_SINGLE)
    {
        kernel_name += "_x";
        for(auto f : specs2d.factors)
        {
            kernel_name += "_";
            kernel_name += std::to_string(f);
        }
    }
    kernel_name += "_wgs_";
    kernel_name += std::to_string(specs.workgroup_size);
    kernel_name += "_tpt_";
    kernel_name += std::to_string(specs.threads_per_transform);
    if(scheme == CS_KERNEL_2D_SINGLE)
        kernel_name += "x" + std::to_string(specs2d.threads_per_transform);

    if(specs.half_lds && ppType == PPT_NONE)
        kernel_name += "_halfLds";

    if(specs.static_dim)
    {
        kernel_name += "_dim_";
        kernel_name += std::to_string(specs.static_dim);
    }

    kernel_name += rtc_precision_name(precision);

    if(placement == rocfft_placement_inplace)
    {
        kernel_name += "_ip";
        kernel_name += rtc_array_type_name(inArrayType);
    }
    else
    {
        kernel_name += "_op";
        kernel_name += rtc_array_type_name(inArrayType);
        kernel_name += rtc_array_type_name(outArrayType);
    }

    if(unitstride)
        kernel_name += "_unitstride";

    switch(scheme)
    {
    case CS_KERNEL_STOCKHAM:
    case CS_KERNEL_STOCKHAM_PP:
        kernel_name += "_sbrr";
        break;
    case CS_KERNEL_STOCKHAM_BLOCK_CC:
    case CS_KERNEL_STOCKHAM_PP_BLOCK_CC:
        kernel_name += "_sbcc";
        break;
    case CS_KERNEL_STOCKHAM_BLOCK_CR:
        kernel_name += "_sbcr";
        break;
    case CS_KERNEL_2D_SINGLE:
        // both lengths were already added above, which indicates it's
        // 2D_SINGLE
        break;
    case CS_KERNEL_STOCKHAM_BLOCK_RC:
    {
        kernel_name += "_sbrc";
        break;
    }
    case CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z:
    {
        auto transpose_type = kernel_name += "_sbrc_xy_z";
        break;
    }
    case CS_KERNEL_STOCKHAM_TRANSPOSE_Z_XY:
    {
        kernel_name += "_sbrc_z_xy";
        break;
    }
    case CS_KERNEL_STOCKHAM_R_TO_CMPLX_TRANSPOSE_Z_XY:
    {
        kernel_name += "_sbrc_erc_z_xy";
        break;
    }
    default:
        throw std::runtime_error("unsupported scheme in stockham_rtc_kernel_name");
    }

    switch(fuseBlue)
    {
    case BFT_NONE:
        break;
    case BFT_FWD_CHIRP:
        kernel_name += "_fwd_chirp";
        break;
    case BFT_FWD_CHIRP_MUL:
        kernel_name += "_fwd_chirp_mul";
        break;
    case BFT_INV_CHIRP_MUL:
        kernel_name += "_inv_chirp_mul";
        break;
    }

    switch(transpose_type)
    {
    case NONE:
        break;
    case DIAGONAL:
        kernel_name += "_diag";
        break;
    case TILE_ALIGNED:
        kernel_name += "_aligned";
        break;
    case TILE_UNALIGNED:
        kernel_name += "_unaligned";
        break;
    }

    if(largeTwdBase > 0 && largeTwdSteps > 0)
    {
        kernel_name += "_twdbase" + std::to_string(largeTwdBase);
        kernel_name += "_" + std::to_string(largeTwdSteps) + "step";
        if(largeTwdBatchIsTransformCount)
            kernel_name += "_batchcount";
    }

    switch(specs.ebtype)
    {
    case EmbeddedType::NONE:
        break;
    case EmbeddedType::C2Real_PRE:
        kernel_name += "_C2R";
        break;
    case EmbeddedType::Real2C_POST:
        kernel_name += "_R2C";
        break;
    }

    if(dir2regMode == DirectRegType::TRY_ENABLE_IF_SUPPORT)
        kernel_name += "_dirReg";

    // callback kernels need to disable buffer load/store
    if(cbtype != CallbackType::NONE || dir2regMode == DirectRegType::FORCE_OFF_OR_NOT_SUPPORT)
        intrinsicMode = IntrinsicAccessType::DISABLE_BOTH;

    switch(intrinsicMode)
    {
    case IntrinsicAccessType::DISABLE_BOTH:
        break;
    case IntrinsicAccessType::ENABLE_BOTH:
        kernel_name += "_intrinsicReadWrite";
        break;
    case IntrinsicAccessType::ENABLE_LOAD_ONLY:
        kernel_name += "_intrinsicRead";
        break;
    }

    kernel_name += load_store_name_suffix(loadOps, storeOps);
    kernel_name += rtc_cbtype_name(cbtype);
    return kernel_name;
}

std::string stockham_rtc(const StockhamGeneratorSpecs&    specs,
                         const StockhamGeneratorSpecs&    specs2d,
                         const StockhamPartialPassParams& params_pp,
                         unsigned int*                    transforms_per_block,
                         const std::string&               kernel_name,
                         ComputeScheme                    scheme,
                         int                              direction,
                         rocfft_precision                 precision,
                         rocfft_result_placement          placement,
                         rocfft_array_type                inArrayType,
                         rocfft_array_type                outArrayType,
                         bool                             unit_stride,
                         size_t                           largeTwdBase,
                         size_t                           largeTwdSteps,
                         bool                             largeTwdBatchIsTransformCount,
                         DirectRegType                    dir2regMode,
                         IntrinsicAccessType              intrinsicMode,
                         SBRC_TRANSPOSE_TYPE              transpose_type,
                         CallbackType                     cbtype,
                         const BluesteinFuseType&         fuseBlue,
                         const PartialPassType&           ppType,
                         const std::optional<LoadOps>&    loadOps,
                         const std::optional<StoreOps>&   storeOps)
{
    std::unique_ptr<Function> lds2reg, reg2lds, device;
    std::unique_ptr<Function> lds2reg_pp_steps, reg2lds_pp_steps;
    std::unique_ptr<Function> twiddle_multiply_pp, local_transpose_pp;
    std::unique_ptr<Function> lds2reg1, reg2lds1, device1;
    std::unique_ptr<Function> bluestein_load, bluestein_intrinsic_load;
    std::unique_ptr<Function> bluestein_store, bluestein_intrinsic_store;
    std::unique_ptr<Function> global;

    std::vector<unsigned int> all_factors;

    auto fuseBluestein = (fuseBlue != BFT_NONE);

    if(scheme == CS_KERNEL_2D_SINGLE)
    {
        StockhamKernelFused2D kernel(specs, specs2d);
        if(transforms_per_block)
            *transforms_per_block = kernel.transforms_per_block;
        lds2reg = std::make_unique<Function>(kernel.kernel0.generate_lds_to_reg_input_function());
        reg2lds
            = std::make_unique<Function>(kernel.kernel0.generate_lds_from_reg_output_function());
        device = std::make_unique<Function>(kernel.kernel0.generate_device_function());
        if(kernel.kernel0.length != kernel.kernel1.length)
        {
            lds2reg1
                = std::make_unique<Function>(kernel.kernel1.generate_lds_to_reg_input_function());
            reg2lds1 = std::make_unique<Function>(
                kernel.kernel1.generate_lds_from_reg_output_function());
            device1 = std::make_unique<Function>(kernel.kernel1.generate_device_function());
        }
        global = std::make_unique<Function>(kernel.generate_global_function());

        // get all factors by concat two vectors
        all_factors = kernel.kernel0.factors;
        all_factors.insert(
            all_factors.end(), kernel.kernel1.factors.begin(), kernel.kernel1.factors.end());
    }
    else
    {
        std::unique_ptr<StockhamKernel> kernel;
        if(scheme == CS_KERNEL_STOCKHAM)
            kernel = std::make_unique<StockhamKernelRR>(specs);
        else if(scheme == CS_KERNEL_STOCKHAM_PP)
            kernel = std::make_unique<StockhamPartialPassKernelRR>(specs, params_pp);
        else if(scheme == CS_KERNEL_STOCKHAM_BLOCK_CC)
            kernel = std::make_unique<StockhamKernelCC>(
                specs, largeTwdBatchIsTransformCount, fuseBluestein);
        else if(scheme == CS_KERNEL_STOCKHAM_PP_BLOCK_CC)
            kernel = std::make_unique<StockhamPartialPassKernelCC>(
                specs, params_pp, largeTwdBatchIsTransformCount);
        else if(scheme == CS_KERNEL_STOCKHAM_BLOCK_CR)
            kernel = std::make_unique<StockhamKernelCR>(specs);
        else if(scheme == CS_KERNEL_STOCKHAM_BLOCK_RC)
            kernel = std::make_unique<StockhamKernelRC>(specs, fuseBluestein);
        else if(scheme == CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z)
            kernel = std::make_unique<StockhamKernelRC>(specs, false);
        else if(scheme == CS_KERNEL_STOCKHAM_TRANSPOSE_Z_XY)
            kernel = std::make_unique<StockhamKernelRC>(specs, false);
        else if(scheme == CS_KERNEL_STOCKHAM_R_TO_CMPLX_TRANSPOSE_Z_XY)
            kernel = std::make_unique<StockhamKernelRC>(specs, false);
        else
            throw std::runtime_error("unhandled scheme");
        if(transforms_per_block)
            *transforms_per_block = kernel->transforms_per_block;

        switch(ppType)
        {
        case PPT_NONE:
        {
            lds2reg = std::make_unique<Function>(kernel->generate_lds_to_reg_input_function());
            reg2lds = std::make_unique<Function>(kernel->generate_lds_from_reg_output_function());
            device  = std::make_unique<Function>(kernel->generate_device_function());
            break;
        }
        case PPT_SBRR:
        {
            auto kernel_pp = static_cast<StockhamPartialPassKernelRR*>(kernel.get());

            lds2reg = std::make_unique<Function>(kernel_pp->generate_lds_to_reg_input_function());
            reg2lds
                = std::make_unique<Function>(kernel_pp->generate_lds_from_reg_output_function());
            lds2reg_pp_steps = std::make_unique<Function>(
                kernel_pp->generate_lds_to_reg_input_step_1_2_function());
            reg2lds_pp_steps = std::make_unique<Function>(
                kernel_pp->generate_lds_from_reg_output_pp_step_1_2_function());
            twiddle_multiply_pp = std::make_unique<Function>(
                kernel_pp->generate_twiddle_multiply_pp_function(direction));
            device = std::make_unique<Function>(kernel_pp->generate_device_function());
            break;
        }
        case PPT_SBCC:
        {
            auto kernel_pp = static_cast<StockhamPartialPassKernelCC*>(kernel.get());

            lds2reg
                = std::make_unique<Function>(kernel_pp->generate_lds_to_reg_input_pp_function());
            reg2lds
                = std::make_unique<Function>(kernel_pp->generate_lds_from_reg_output_pp_function());
            lds2reg_pp_steps = std::make_unique<Function>(
                kernel_pp->generate_lds_to_reg_input_step_3_4_function());
            reg2lds_pp_steps = std::make_unique<Function>(
                kernel_pp->generate_lds_from_reg_output_pp_step_3_4_function());
            local_transpose_pp
                = std::make_unique<Function>(kernel_pp->generate_local_transpose_pp_function());
            device = std::make_unique<Function>(kernel_pp->generate_device_function());
            break;
        }
        default:
            throw std::runtime_error("unhandled partial pass type");
        }

        if(fuseBluestein)
        {
            auto planar_blue_load = array_type_is_planar(inArrayType);
            bluestein_load = std::make_unique<Function>(generate_bluestein_device_load_function(
                scheme, fuseBlue, direction, planar_blue_load, false));
            bluestein_intrinsic_load
                = std::make_unique<Function>(generate_bluestein_device_load_function(
                    scheme, fuseBlue, direction, planar_blue_load, true));

            auto planar_blue_store = array_type_is_planar(outArrayType);
            bluestein_store = std::make_unique<Function>(generate_bluestein_device_store_function(
                scheme, fuseBlue, direction, planar_blue_store, false));
            bluestein_intrinsic_store
                = std::make_unique<Function>(generate_bluestein_device_store_function(
                    scheme, fuseBlue, direction, planar_blue_store, true));
        }

        global = std::make_unique<Function>(kernel->generate_global_function());

        // get factors vector
        all_factors = kernel->factors;

        if(ppType != PPT_NONE)
            all_factors.insert(all_factors.end(),
                               params_pp.pp_factors_curr.begin(),
                               params_pp.pp_factors_curr.end());
    }

    // generated functions default to forward in-place interleaved.
    // adjust for direction, placement, format.
    if(direction == 1)
    {
        *device = make_inverse(*device);
        if(device1)
            *device1 = make_inverse(*device1);
        *global = make_inverse(*global);
    }

    make_load_store_ops(*global, loadOps, storeOps);

    if(placement == rocfft_placement_notinplace)
    {
        *global = make_outofplace(*global);
        if(array_type_is_planar(inArrayType))
            *global = make_planar(*global, "buf_in");
        if(array_type_is_planar(outArrayType))
            *global = make_planar(*global, "buf_out");
    }
    else
    {
        if(array_type_is_planar(inArrayType))
            *global = make_planar(*global, "buf");
    }

    if(fuseBluestein)
        *global = make_bluestein(scheme, fuseBlue, *global);

    // start off with includes
    std::string src;
    src += rocfft_complex_h;
    src += common_h;
    src += device_enum_h;
    src += memory_gfx_h;
    src += callback_h;
    src += butterfly_constant_h;

    // only SBCCs need this
    if(scheme == CS_KERNEL_STOCKHAM_BLOCK_CC || scheme == CS_KERNEL_STOCKHAM_PP_BLOCK_CC)
        src += large_twiddles_h;
    // append the neccessary functions only
    append_radix_h(src, all_factors);
    // SBCCs don't need this
    if(scheme != CS_KERNEL_STOCKHAM_BLOCK_CC && scheme != CS_KERNEL_STOCKHAM_PP_BLOCK_CC)
        src += real2complex_device_h;

    src += lds2reg->render();
    src += reg2lds->render();
    src += device->render();

    if(ppType != PPT_NONE)
    {
        src += lds2reg_pp_steps->render();
        src += reg2lds_pp_steps->render();

        if(ppType == PPT_SBRR)
            src += twiddle_multiply_pp->render();

        if(ppType == PPT_SBCC)
            src += local_transpose_pp->render();
    }

    if(lds2reg1)
        src += lds2reg1->render();
    if(reg2lds1)
        src += reg2lds1->render();
    if(device1)
        src += device1->render();
    if(bluestein_load)
        src += bluestein_load->render();
    if(bluestein_intrinsic_load)
        src += bluestein_intrinsic_load->render();
    if(bluestein_store)
        src += bluestein_store->render();
    if(bluestein_intrinsic_store)
        src += bluestein_intrinsic_store->render();

    // make_rtc removes templates from global function - add typedefs
    // and constants to replace them
    src += rtc_precision_type_decl(precision);
    if(unit_stride)
        src += "static const StrideBin sb = SB_UNIT;\n";
    else
        src += "static const StrideBin sb = SB_NONUNIT;\n";

    // SBRC-specific template parameters that are ignored for other kernels
    switch(scheme)
    {
    case CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z:
        src += "static const SBRC_TYPE sbrc_type = SBRC_3D_FFT_TRANS_XY_Z;\n";
        break;
    case CS_KERNEL_STOCKHAM_TRANSPOSE_Z_XY:
        src += "static const SBRC_TYPE sbrc_type = SBRC_3D_FFT_TRANS_Z_XY;\n";
        break;
    case CS_KERNEL_STOCKHAM_R_TO_CMPLX_TRANSPOSE_Z_XY:
        src += "static const SBRC_TYPE sbrc_type = SBRC_3D_FFT_ERC_TRANS_Z_XY;\n";
        break;
    default:
        src += "static const SBRC_TYPE sbrc_type = SBRC_2D;\n";
    }
    switch(transpose_type)
    {
    case NONE:
        src += "static const SBRC_TRANSPOSE_TYPE transpose_type = NONE;\n";
        break;
    case DIAGONAL:
        src += "static const SBRC_TRANSPOSE_TYPE transpose_type = DIAGONAL;\n";
        break;
    case TILE_ALIGNED:
        src += "static const SBRC_TRANSPOSE_TYPE transpose_type = TILE_ALIGNED;\n";
        break;
    case TILE_UNALIGNED:
        src += "static const SBRC_TRANSPOSE_TYPE transpose_type = TILE_UNALIGNED;\n";
        break;
    }

    src += rtc_const_cbtype_decl(cbtype);

    switch(dir2regMode)
    {
    case DirectRegType::FORCE_OFF_OR_NOT_SUPPORT:
        src += "static const DirectRegType drtype = DirectRegType::FORCE_OFF_OR_NOT_SUPPORT;\n";
        break;
    case DirectRegType::TRY_ENABLE_IF_SUPPORT:
        src += "static const DirectRegType drtype = DirectRegType::TRY_ENABLE_IF_SUPPORT;\n";
        break;
    }

    src += "static const bool apply_large_twiddle = ";
    src += (largeTwdBase > 0 && largeTwdSteps > 0) ? "true;\n" : "false;\n";

    // callback kernels need to disable buffer load/store
    if(cbtype != CallbackType::NONE || dir2regMode == DirectRegType::FORCE_OFF_OR_NOT_SUPPORT)
        intrinsicMode = IntrinsicAccessType::DISABLE_BOTH;

    switch(intrinsicMode)
    {
    case IntrinsicAccessType::DISABLE_BOTH:
        src += "static const IntrinsicAccessType intrinsic_mode = "
               "IntrinsicAccessType::DISABLE_BOTH;\n";
        break;
    case IntrinsicAccessType::ENABLE_BOTH:
        src += "static const IntrinsicAccessType intrinsic_mode = "
               "IntrinsicAccessType::ENABLE_BOTH;\n";
        break;
    case IntrinsicAccessType::ENABLE_LOAD_ONLY:
        src += "static const IntrinsicAccessType intrinsic_mode = "
               "IntrinsicAccessType::ENABLE_LOAD_ONLY;\n";
        break;
    }

    src += "static const size_t large_twiddle_base = " + std::to_string(largeTwdBase) + ";\n";
    src += "static const size_t large_twiddle_steps = " + std::to_string(largeTwdSteps) + ";\n";

    *global = make_callback_realcomplex(*global, cbtype);

    *global = make_rtc(*global, kernel_name);
    src += global->render();
    write_standalone_test_harness(*global, src);
    return src;
}

std::string fused_stockham_rtc_kernel_name(const FusedSBCCSBRCNode& node)
{
    std::string kernel_name = "fft_rtc_fused_sbcc_sbrc";

    kernel_name += node.direction == -1 ? "_fwd" : "_back";
    kernel_name += "_len_" + std::to_string(node.length[0]);
    if(node.length.size() > 1)
        kernel_name += "x" + std::to_string(node.length[1]);

    kernel_name += "_factors";
    for(const auto factor : node.kernelFactors)
        kernel_name += "_" + std::to_string(factor);
    kernel_name += "_consumer_factors";
    for(const auto factor : node.consumerKernelFactors)
        kernel_name += "_" + std::to_string(factor);
    kernel_name += "_pwgs_" + std::to_string(node.producerWgs);
    kernel_name += "_cwgs_" + std::to_string(node.consumerWgs);
    kernel_name += "_ptpt_" + std::to_string(node.producerThreadsPerTransform);
    kernel_name += "_ctpt_" + std::to_string(node.consumerThreadsPerTransform);

    kernel_name += std::string{"_pdim_"} + (node.producerAotRtc ? "dynamic" : "static");
    kernel_name += std::string{"_cdim_"} + (node.consumerAotRtc ? "dynamic" : "static");

    kernel_name += rtc_precision_name(node.precision);
    kernel_name += std::string{"_op"} + rtc_array_type_name(node.inArrayType)
                   + rtc_array_type_name(node.outArrayType);
    kernel_name += node.producerUnitStride ? "_cc_unitstride" : "_cc_nonunitstride";
    kernel_name += node.consumerUnitStride ? "_rc_unitstride" : "_rc_nonunitstride";
    kernel_name += "_transpose_" + fused_transpose_name(node.consumerTransposeType);
    kernel_name += "_pintrinsic_" + fused_intrinsic_name(node.producerIntrinsicMode);
    kernel_name += "_ltwd_" + std::to_string(node.largeTwdBase) + "_"
                   + std::to_string(node.ltwdSteps);
    kernel_name += node.globalTileHandoff ? "_global" : "_lds";
    kernel_name += node.streamingTileHandoff ? "_stream" : "_strict";
    return kernel_name;
}

std::string fused_stockham_rtc(const FusedSBCCSBRCNode& node,
                               const std::string&         kernel_name)
{
    auto producer_specs = make_fused_specs(node, true);
    auto consumer_specs = make_fused_specs(node, false);

    StockhamKernelCC producer_kernel(producer_specs,
                                     node.largeTwdBatchIsTransformCount,
                                     false);
    StockhamKernelRC consumer_kernel(consumer_specs, false);

    std::vector<Function> producer_helpers;
    producer_helpers.emplace_back(producer_kernel.generate_lds_to_reg_input_function());
    producer_helpers.emplace_back(producer_kernel.generate_lds_from_reg_output_function());
    producer_helpers.emplace_back(producer_kernel.generate_device_function());

    std::vector<Function> consumer_helpers;
    consumer_helpers.emplace_back(consumer_kernel.generate_lds_to_reg_input_function());
    consumer_helpers.emplace_back(consumer_kernel.generate_lds_from_reg_output_function());
    consumer_helpers.emplace_back(consumer_kernel.generate_device_function());

    auto producer_global = producer_kernel.generate_global_function();
    auto consumer_global = consumer_kernel.generate_global_function();

    if(node.direction == 1)
    {
        for(auto& helper : producer_helpers)
        {
            if(helper.name.rfind("forward_", 0) == 0)
                helper = make_inverse(helper);
        }
        for(auto& helper : consumer_helpers)
        {
            if(helper.name.rfind("forward_", 0) == 0)
                helper = make_inverse(helper);
        }
        producer_global = make_inverse(producer_global);
        consumer_global = make_inverse(consumer_global);
    }

    // Keep the original global load/store callback ABI for the external
    // input/output boundary.  Only the producer store and consumer load are
    // removed below; callback declarations remain inside each lexical stage
    // block and therefore do not collide.
    producer_global = make_outofplace(producer_global);
    consumer_global = make_outofplace(consumer_global);

    const auto producer_arguments
        = prefixed_arguments(producer_global, "producer_", true);
    const auto consumer_arguments
        = prefixed_arguments(consumer_global, "consumer_", false);

    const auto producer_helper_names = function_names(producer_helpers);
    const auto consumer_helper_names = function_names(consumer_helpers);
    auto producer_helpers_prefixed
        = prefix_fused_functions(std::move(producer_helpers), "fused_cc_");
    auto consumer_helpers_prefixed
        = prefix_fused_functions(std::move(consumer_helpers), "fused_rc_");

    FusedStageRewriteVisitor producer_rewrite(true,
                                              node.streamingTileHandoff,
                                              node.consumerTileWidth,
                                              node.consumerTilesPerPlane,
                                              node.consumerLength.front(),
                                              node.globalTileHandoff);
    FusedStageRewriteVisitor consumer_rewrite(false,
                                              false,
                                              0,
                                              1,
                                              0,
                                              node.globalTileHandoff,
                                              node.streamingTileHandoff && !node.globalTileHandoff);
    producer_global = producer_rewrite(producer_global);
    consumer_global = consumer_rewrite(consumer_global);
    if(node.streamingTileHandoff)
        producer_global = FusedProducerThreadVisitor(node.producerWgs)(producer_global);

    FusedGlobalVariableVisitor producer_variables(
        "producer_", producer_global, "producer_block_id");
    FusedGlobalVariableVisitor consumer_variables(
        "consumer_", consumer_global, "consumer_block_id");
    producer_global = producer_variables(producer_global);
    consumer_global = consumer_variables(consumer_global);

    FusedFunctionPrefixVisitor producer_calls("fused_cc_", producer_helper_names);
    FusedFunctionPrefixVisitor consumer_calls("fused_rc_", consumer_helper_names);
    producer_global = producer_calls(producer_global);
    consumer_global = consumer_calls(consumer_global);

    Function fused_global(kernel_name);
    fused_global.qualifier     = "__global__";
    fused_global.launch_bounds = node.streamingTileHandoff ? node.consumerWgs : node.producerWgs;
    fused_global.arguments     = producer_arguments;
    for(const auto& argument : consumer_arguments.arguments)
        fused_global.arguments.append(argument);

    fused_global.body += LDSDeclaration{"scalar_type"};
    if(node.streamingTileHandoff && !node.globalTileHandoff)
    {
        Variable lds_complex{"lds_complex", "scalar_type", true, true};
        Variable lds_real{"lds_real", "real_type_t<scalar_type>", true, true};
        fused_global.body += Declaration{
            Variable{"fused_handoff_lds", "scalar_type", true, true},
            lds_complex + Literal{std::to_string(node.producerLdsElements)}};
        fused_global.body += Declaration{
            Variable{"fused_handoff_lds_real", "real_type_t<scalar_type>", true, true},
            lds_real + Literal{std::to_string(node.producerLdsElements * 2)}};
    }
    fused_global.body += Declaration{
        Variable{"consumer_block_id", "unsigned int"}, Variable{"blockIdx.x", "unsigned int"}};
    if(node.streamingTileHandoff)
    {
        fused_global.body += Declaration{
            Variable{"fused_producer_owner", "bool"},
            Variable{"threadIdx.x", "unsigned int"}
                < Literal{static_cast<unsigned int>(node.producerWgs)}};
        fused_global.body += CommentLines{
            "Only the original producer lanes write the streamed LDS handoff"};
        Variable producer_tile_id{"producer_tile_id", "unsigned int"};
        Variable producer_block_id{"producer_block_id", "unsigned int"};
        const auto consumer_tiles_per_plane
            = Literal{static_cast<unsigned int>(node.consumerTilesPerPlane)};
        const auto producer_tiles_per_plane
            = Literal{static_cast<unsigned int>(node.producerTilesPerPlane)};

        fused_global.body += Declaration{producer_block_id, 0};
        fused_global.body += CommentLines{
            "SBCC producer: rerun each producer tile with a remapped block id"};
        StatementList producer_iteration;
        producer_iteration += Assign{
            producer_block_id,
            (Variable{"consumer_block_id", "unsigned int"} / consumer_tiles_per_plane)
                    * producer_tiles_per_plane
                + producer_tile_id};
        producer_iteration += producer_global.body;
        producer_iteration += SyncThreads{};
        fused_global.body += For{producer_tile_id,
                                 0,
                                 producer_tile_id
                                     < Literal{static_cast<unsigned int>(
                                           node.producerTilesPerConsumerTile)},
                                 1,
                                 producer_iteration};
    }
    else
    {
        fused_global.body += Declaration{
            Variable{"producer_block_id", "unsigned int"}, Variable{"blockIdx.x", "unsigned int"}};
        fused_global.body += CommentLines{
            "SBCC producer: global input -> LDS -> FFT -> shared LDS tile"};
        fused_global.body += If{Literal{"true"}, producer_global.body};
    }
    fused_global.body += CommentLines{"the producer tile is now visible to the SBRC stage"};
    if(!node.streamingTileHandoff)
        fused_global.body += SyncThreads{};
    fused_global.body += CommentLines{"SBRC consumer: shared LDS tile -> FFT -> global output"};
    fused_global.body += If{Literal{"true"}, consumer_global.body};

    std::vector<unsigned int> all_factors = producer_specs.factors;
    all_factors.insert(all_factors.end(),
                       consumer_specs.factors.begin(),
                       consumer_specs.factors.end());

    std::string src;
    src += rocfft_complex_h;
    src += common_h;
    src += device_enum_h;
    src += memory_gfx_h;
    src += callback_h;
    src += butterfly_constant_h;
    src += large_twiddles_h;
    src += real2complex_device_h;
    append_radix_h(src, all_factors);

    append_fused_function_source(src, producer_helpers_prefixed);
    append_fused_function_source(src, consumer_helpers_prefixed);

    src += rtc_precision_type_decl(node.precision);
    append_fused_stage_constants(src,
                                 "producer_",
                                 node.producerUnitStride,
                                 node.producerDir2regMode,
                                 node.producerIntrinsicMode,
                                 node.largeTwdBase > 0 && node.ltwdSteps > 0,
                                 node.largeTwdBase,
                                 node.ltwdSteps,
                                 NONE);
    append_fused_stage_constants(src,
                                 "consumer_",
                                 node.consumerUnitStride,
                                 DirectRegType::FORCE_OFF_OR_NOT_SUPPORT,
                                 IntrinsicAccessType::DISABLE_BOTH,
                                 false,
                                 0,
                                 0,
                                 node.consumerTransposeType);

    fused_global = make_rtc(fused_global, kernel_name);
    src += fused_global.render();
    write_standalone_test_harness(fused_global, src);
    return src;
}
