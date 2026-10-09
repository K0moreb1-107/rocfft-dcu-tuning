// EXP-126: generic CC/RC boundaries. Existing EXP-125 kernels stay separate.
#pragma once

#include "real_pair_layout.h"
#include "stockham_gen_cc.h"
#include "stockham_gen_rc.h"

static Expression real_pair_size(size_t value)
{
    return Literal{std::to_string(value) + "ul"};
}

static Expression real_pair_row_expr(size_t axis, unsigned int slots,
                                    Expression slot, Expression block)
{
    return CallExpr{"real_pair_row", {real_pair_size(axis), Literal{slots}, slot, block}};
}

// Pair input columns before the original C-point transform and its M-point phase.
struct StockhamKernelPairedPreColumns : StockhamKernelCC
{
    const size_t columns, rows, m;
    Variable pair_twiddles{"real_pair_twiddles", "const scalar_type", true, true};

    explicit StockhamKernelPairedPreColumns(const StockhamGeneratorSpecs& specs)
        : StockhamKernelCC(specs, false, false)
        , columns(specs.real_io.columns), rows(specs.real_io.rows), m(specs.real_io.n / 2)
    {
        if(specs.real_io.role != RealBlockRole::PairedPreColumns || length != columns
           || columns * rows != m || specs.real_io.pitch != rows
           || transforms_per_block < 2 || transforms_per_block % 2 != 0
           || half_lds || direct_to_from_reg)
            throw std::runtime_error("invalid paired real pre geometry");
    }

    Expression get_lds_padding() override { return Literal{0}; }

    ArgumentList global_arguments() override
    {
        auto args = StockhamKernelCC::global_arguments();
        args.append(pair_twiddles);
        return args;
    }

    StatementList calculate_offsets() override
    {
        auto stmts = StockhamKernelCC::calculate_offsets();
        // offset_lds already denotes the local slot. Only the cross-stage
        // phase uses the mapped global column, rather than the old tile index.
        stmts += Assign{transform, real_pair_row_expr(rows, transforms_per_block,
                                                     thread_id / threads_per_transform, tile_index)};
        return stmts;
    }

    StatementList load_from_global(bool) override
    {
        const auto t = transforms_per_block;
        Variable slot{"pre_slot", "const unsigned int"};
        Variable column{"pre_column", "const unsigned int"};
        Variable peer{"pre_peer", "const unsigned int"};
        Variable a{"pre_a", "unsigned int"}, k{"pre_k", "size_t"};
        Variable p{"pre_p", "scalar_type"}, q{"pre_q", "scalar_type"};
        Variable own{"pre_own", "scalar_type"}, other{"pre_other", "scalar_type"};
        StatementList stmts{
            Declaration{slot, thread_id % t},
            Declaration{column, real_pair_row_expr(rows, t, slot, tile_index)},
            Declaration{peer, CallExpr{"real_pair_peer", {real_pair_size(rows), Literal{t}, slot, column}}},
            Declaration{a}, Declaration{k}, Declaration{p}, Declaration{q},
            Declaration{own}, Declaration{other}};
        const unsigned int steps = (length * t + workgroup_size - 1) / workgroup_size;
        for(unsigned int i = 0; i < steps; ++i)
        {
            stmts += Assign{a, thread_id / t + i * threads_per_transform};
            stmts += Assign{k, a * real_pair_size(rows) + column};
            StatementList values;
            StatementList endpoints{
                Assign{p, LoadGlobal{buf, Literal{0}}},
                Assign{q, LoadGlobal{buf, real_pair_size(m)}},
                Assign{lds_complex[slot * length + a], ComplexLiteral{p.x() + q.x(), p.x() - q.x()}}};
            values += If{k == 0, endpoints};
            if(m % 2 == 0)
            {
                values += If{k == real_pair_size(m / 2),
                             {Assign{p, LoadGlobal{buf, k}},
                              Assign{lds_complex[slot * length + a], ComplexLiteral{2 * p.x(), -2 * p.y()}}}};
            }
            // Canonical owners populate both packed LDS destinations once.
            auto other_a = Parens{(Literal{length} - a
                                    - Ternary{Expression{column == 0}, Expression{Literal{0}}, Expression{Literal{1}}})
                                   % Literal{length}};
            values += If{And{k > 0, 2 * k < real_pair_size(m)},
                         {Assign{p, LoadGlobal{buf, k}},
                          Assign{q, LoadGlobal{buf, real_pair_size(m) - k}},
                          Call{"real_pair_pre", {scalar_type}, {p, q, pair_twiddles[k], own, other}},
                          Assign{lds_complex[slot * length + a], own},
                          Assign{lds_complex[peer * length + other_a], other}}};
            // Invalid slots do not share a destination with a valid pair.
            // The original LDS-to-register barrier follows this whole load.
            stmts += If{a < length,
                        {If{column < real_pair_size(rows), values},
                         Else{{Assign{lds_complex[slot * length + a], ComplexLiteral{Literal{0}, Literal{0}}}}}}};
        }
        return stmts;
    }

    StatementList store_to_global(bool) override
    {
        const auto t = transforms_per_block;
        Variable slot{"pre_store_slot", "const unsigned int"};
        Variable column{"pre_store_column", "const unsigned int"};
        Variable a{"pre_store_a", "unsigned int"};
        StatementList stmts{Declaration{slot, thread_id % t},
                            Declaration{column, real_pair_row_expr(rows, t, slot, tile_index)},
                            Declaration{a}};
        const unsigned int steps = (length * t + workgroup_size - 1) / workgroup_size;
        for(unsigned int i = 0; i < steps; ++i)
        {
            stmts += Assign{a, thread_id / t + i * threads_per_transform};
            stmts += If{And{a < length, column < real_pair_size(rows)},
                         {StoreGlobal{buf, a * real_pair_size(rows) + column,
                                      lds_complex[slot * length + a]}}};
        }
        return stmts;
    }
};

// Finish the ordinary Q-point row FFT, then pair its complete LDS results.
struct StockhamKernelGenericPairedPostRows : StockhamKernelRC
{
    const size_t columns, rows, m;
    Variable pair_twiddles{"real_pair_twiddles", "const scalar_type", true, true};

    explicit StockhamKernelGenericPairedPostRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelRC(specs, false)
        , columns(specs.real_io.columns), rows(specs.real_io.rows), m(specs.real_io.n / 2)
    {
        if(specs.real_io.role != RealBlockRole::GenericPairedPostRows || length != rows
           || columns * rows != m || specs.real_io.pitch != rows
           || transforms_per_block < 2 || transforms_per_block % 2 != 0
           || half_lds || direct_to_from_reg)
            throw std::runtime_error("invalid paired real post geometry");
    }

    Expression get_lds_padding() override { return Literal{0}; }

    ArgumentList global_arguments() override
    {
        auto args = StockhamKernelRC::global_arguments();
        args.append(pair_twiddles);
        return args;
    }

    StatementList load_from_global(bool) override
    {
        const auto t = transforms_per_block;
        Variable slot{"post_load_slot", "const unsigned int"};
        Variable row{"post_load_row", "const unsigned int"};
        Variable column{"post_load_column", "unsigned int"};
        StatementList stmts{Declaration{slot, thread_id % t},
                            Declaration{row, real_pair_row_expr(columns, t, slot, tile_index_in_plane)},
                            Declaration{column}};
        const unsigned int steps = (length * t + workgroup_size - 1) / workgroup_size;
        for(unsigned int i = 0; i < steps; ++i)
        {
            stmts += Assign{column, thread_id / t + i * threads_per_transform};
            stmts += If{column < length,
                        {If{row < real_pair_size(columns),
                            {Assign{lds_complex[slot * length + column],
                                    LoadGlobal{buf, row * real_pair_size(rows) + column}}}},
                         Else{{Assign{lds_complex[slot * length + column],
                                      ComplexLiteral{Literal{0}, Literal{0}}}}}}};
        }
        return stmts;
    }

    StatementList store_to_global(bool) override
    {
        const auto t = transforms_per_block;
        const unsigned int half_row = (length + 1) / 2;
        Variable slot{"post_slot", "const unsigned int"};
        Variable row{"post_row", "const unsigned int"};
        Variable peer{"post_peer", "const unsigned int"};
        Variable column{"post_column", "unsigned int"}, k{"post_k", "size_t"};
        Variable p{"post_p", "scalar_type"}, q{"post_q", "scalar_type"};
        Variable own{"post_own", "scalar_type"}, other{"post_other", "scalar_type"};
        StatementList stmts{
            Declaration{slot, thread_id % t},
            Declaration{row, real_pair_row_expr(columns, t, slot, tile_index_in_plane)},
            Declaration{peer, CallExpr{"real_pair_peer", {real_pair_size(columns), Literal{t}, slot, row}}},
            Declaration{column}, Declaration{k}, Declaration{p}, Declaration{q},
            Declaration{own}, Declaration{other}};
        const unsigned int steps = (half_row * t + workgroup_size - 1) / workgroup_size;
        for(unsigned int i = 0; i < steps; ++i)
        {
            stmts += Assign{column, thread_id / t + i * threads_per_transform};
            stmts += Assign{k, row + real_pair_size(columns) * column};
            StatementList values;
            values += If{k == 0,
                         {Assign{p, lds_complex[slot * length + column]},
                          StoreGlobal{buf, Literal{0}, ComplexLiteral{p.x() + p.y(), Literal{0}}},
                          StoreGlobal{buf, real_pair_size(m), ComplexLiteral{p.x() - p.y(), Literal{0}}}}};
            auto other_column = Parens{(Literal{length} - column
                                        - Ternary{Expression{row == 0}, Expression{Literal{0}}, Expression{Literal{1}}})
                                       % Literal{length}};
            auto phase = tile_index_in_plane * real_pair_size(t * half_row)
                         + column * t + slot;
            values += If{And{k > 0, 2 * k < real_pair_size(m)},
                         {Assign{p, lds_complex[slot * length + column]},
                          Assign{q, lds_complex[peer * length + other_column]},
                          Call{"real_pair_post", {scalar_type}, {p, q, pair_twiddles[phase], own, other}},
                          StoreGlobal{buf, k, own}, StoreGlobal{buf, real_pair_size(m) - k, other}}};
            stmts += If{And{column < half_row, row < real_pair_size(columns)}, values};
        }
        // Independent midpoint owner. For odd Q and even C it is in slot T/2.
        if(m % 2 == 0)
        {
            const unsigned int midpoint_slot = rows % 2 == 0 ? 0 : t / 2;
            stmts += If{And{tile_index_in_plane == 0, thread_id == 0},
                         {Assign{p, lds_complex[midpoint_slot * length + length / 2]},
                          StoreGlobal{buf, real_pair_size(m / 2), ComplexLiteral{p.x(), -p.y()}}}};
        }
        return stmts;
    }
};
