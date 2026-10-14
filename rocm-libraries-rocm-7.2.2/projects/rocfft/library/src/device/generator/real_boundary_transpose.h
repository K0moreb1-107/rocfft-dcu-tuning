#pragma once

#include "generator.h"
#include "real_pair_layout.h"

// Each owner reads a complete pair from finished input. Both output streams
// transpose through the same local coordinates; mirror coordinates may carry.
// Invalid owners and self-pairs never read an unwritten peer LDS cell.
static Function real_boundary_transpose_kernel(const std::string& kernel_name,
                                               const TransposeSpecs& specs)
{
    if(!specs.real_boundary.Valid()
       || specs.real_boundary.container != RealBoundaryContainer::Transpose
       || specs.dim != 2 || specs.tileX != 32 || specs.tileY != 32
       || specs.precision != rocfft_precision_double || specs.largeTwdSteps
       || !array_type_is_interleaved(specs.inArrayType)
       || !array_type_is_interleaved(specs.outArrayType))
        throw std::runtime_error("unsupported real transpose boundary");

    const bool pre = specs.real_boundary.Pre();
    Variable input{"input", "scalar_type", true, true};
    Variable output{"output", "scalar_type", true, true};
    Variable phase{"real_boundary_phase", "const scalar_type", true, true};
    Variable axis{"axis", "size_t"}, span{"span", "size_t"};
    Variable is0{"input_stride0", "size_t"}, is1{"input_stride1", "size_t"};
    Variable os0{"output_stride0", "size_t"}, os1{"output_stride1", "size_t"};
    Function func{kernel_name};
    func.qualifier = "extern \"C\" __global__";
    func.launch_bounds = 1024;
    for(const auto& arg : {input, output, phase, axis, span, is0, is1, os0, os1})
        func.arguments.append(arg);
    for(const auto& arg : get_callback_args().arguments)
        func.arguments.append(arg);

    Variable tile_own{"real_tile_own", "__shared__ scalar_type", false, false, 32};
    Variable tile_peer{"real_tile_peer", "__shared__ scalar_type", false, false, 32};
    tile_own.size2D = Literal{33};
    tile_peer.size2D = Literal{33};
    func.body += Declaration{tile_own};
    func.body += Declaration{tile_peer};
    func.body += CallbackLoadDeclaration("scalar_type", "cbtype");
    func.body += CallbackStoreDeclaration("scalar_type", "cbtype");

    Variable m{"half_length", "size_t"}, blocks{"axis_blocks", "size_t"};
    Variable a0{"axis_base", "size_t"}, b0{"span_base", "size_t"};
    Variable a{"row", "size_t"}, b{"element", "size_t"}, k{"natural_index", "size_t"};
    Variable ma{"mirror_row", "size_t"}, mb{"mirror_element", "size_t"};
    Variable p{"pair_first", "scalar_type"}, q{"pair_second", "scalar_type"};
    Variable own{"pair_own", "scalar_type"}, other{"pair_other", "scalar_type"};
    const Literal tx{"threadIdx.x"}, ty{"threadIdx.y"};
    func.body += Declaration{m, axis * span};
    func.body += Declaration{blocks, axis / 32 + (axis % 32 != 0)};
    func.body += Declaration{a0, Literal{"size_t(blockIdx.x)"} % blocks * 32};
    func.body += Declaration{b0, Literal{"size_t(blockIdx.x)"} / blocks * 32};
    func.body += Declaration{a, a0 + (pre ? Expression{tx} : Expression{ty})};
    func.body += Declaration{b, b0 + (pre ? Expression{ty} : Expression{tx})};
    func.body += Declaration{k, a + axis * b};
    func.body += Declaration{p};
    func.body += Declaration{q};
    func.body += Declaration{own};
    func.body += Declaration{other};

    const auto mirror_row = [&]() {
        return Ternary{Expression{a == 0}, Expression{0}, Expression{axis - a}};
    };
    const auto mirror_element = [&]() {
        return Ternary{Expression{a == 0},
                       Expression{Ternary{Expression{b == 0}, Expression{0}, Expression{span - b}}},
                       Expression{span - 1 - b}};
    };
    const auto owner_valid = [&]() { return (a < axis) && (b < span) && (k <= m / 2); };
    const auto ordinary_pair = [&]() { return (k != 0) && ((m % 2 != 0) || (k != m / 2)); };

    If load{owner_valid(), {}};
    if(!pre)
        load.body += Assign{p, input[b * is0 + a * is1]};
    If dc{k == 0, {}};
    if(pre)
    {
        dc.body += Assign{p, LoadGlobal{input, 0}};
        dc.body += Assign{q, LoadGlobal{input, m}};
        dc.body += Assign{own, CallExpr{"scalar_type", {p.x() + q.x(), p.x() - q.x()}}};
    }
    else
    {
        dc.body += Assign{own, CallExpr{"scalar_type", {p.x() + p.y(), 0}}};
        dc.body += Assign{other, CallExpr{"scalar_type", {p.x() - p.y(), 0}}};
    }
    If middle{(m % 2 == 0) && (k == m / 2), {}};
    if(pre)
    {
        middle.body += Assign{p, LoadGlobal{input, k}};
        middle.body += Assign{own, CallExpr{"scalar_type", {2 * p.x(), -2 * p.y()}}};
    }
    else
        middle.body += Assign{own, CallExpr{"scalar_type", {p.x(), -p.y()}}};

    StatementList regular;
    regular += Declaration{ma, mirror_row()};
    regular += Declaration{mb, mirror_element()};
    if(pre)
    {
        regular += Assign{p, LoadGlobal{input, k}};
        regular += Assign{q, LoadGlobal{input, m - k}};
    }
    else
        regular += Assign{q, input[mb * is0 + ma * is1]};
    regular += Call{pre ? "real_pair_pre" : "real_pair_post", {p, q, phase[k], own, other}};
    load.body += dc;
    load.body += ElseIf{(m % 2 == 0) && (k == m / 2), middle.body};
    load.body += Else{regular};
    load.body += Assign{tile_own.at(ty, tx), own};
    if(pre)
        load.body += If{ordinary_pair(), {Assign{tile_peer.at(ty, tx), other}}};
    else
        load.body += If{(k == 0) || ordinary_pair(), {Assign{tile_peer.at(ty, tx), other}}};
    func.body += load;

    // All threads, including tail tiles and invalid owners, reach the barrier.
    func.body += SyncThreads{};
    func.body += Assign{a, a0 + (pre ? Expression{ty} : Expression{tx})};
    func.body += Assign{b, b0 + (pre ? Expression{tx} : Expression{ty})};
    func.body += Assign{k, a + axis * b};
    If store{owner_valid(), {}};
    if(pre)
    {
        store.body += Assign{output[a * os0 + b * os1], tile_own.at(tx, ty)};
        If peer_store{ordinary_pair(), {}};
        peer_store.body += Declaration{ma, mirror_row()};
        peer_store.body += Declaration{mb, mirror_element()};
        peer_store.body += Assign{output[ma * os0 + mb * os1], tile_peer.at(tx, ty)};
        store.body += peer_store;
    }
    else
    {
        store.body += StoreGlobal{output, k, tile_own.at(tx, ty)};
        store.body += If{k == 0, {StoreGlobal{output, m, tile_peer.at(tx, ty)}}};
        store.body += If{ordinary_pair(), {StoreGlobal{output, m - k, tile_peer.at(tx, ty)}}};
    }
    func.body += store;
    make_load_store_ops(func, specs.loadOps, specs.storeOps);
    return make_callback_realcomplex(func, specs.cbtype);
}
