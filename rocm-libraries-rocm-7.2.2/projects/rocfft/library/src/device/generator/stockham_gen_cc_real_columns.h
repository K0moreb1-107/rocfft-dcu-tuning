// EXP128: boundary adapters around the unchanged C-point Stockham core.
#pragma once
#include "stockham_gen_cc.h"
#include "stockham_gen_cc_real_common.h"

struct StockhamKernelFoldedPackedColumns : StockhamKernelCC
{
    RealBlockIO io;
    bool callbacks;
    StockhamKernelFoldedPackedColumns(const StockhamGeneratorSpecs& specs, bool callbacks)
        : StockhamKernelCC(specs, false, false)
        , io(specs.real_io)
        , callbacks(callbacks)
    {
        if (length * transforms_per_block / (half_lds ? 2 : 1) < length)
            throw std::runtime_error("CC callback cache exceeds reusable core workspace");
    }
    bool use_static_initial_reg_load() const override { return true; }
    StatementList set_direct_to_from_registers() override
    {
        return { Declaration { direct_load_to_reg, Literal { "true" } },
            Declaration { direct_store_from_reg, Literal { "true" } },
            Declaration { lds_linear, Literal { "false" } } };
    }
    StatementList load_from_global(bool) override
    {
        Variable lane { "cc_lane", "const unsigned int" },
            col { "cc_column", "const unsigned int" };
        Variable cache { "cc_boundary_cache", "scalar_type", true };
        StatementList s { Declaration { lane, thread_id / transforms_per_block },
            Declaration {
                col, tile_index * transforms_per_block + thread_id % transforms_per_block } };
        if (callbacks)
        {
            s += Declaration { cache, lds_complex };
            Variable b { "cc_boundary_column", "const unsigned int" };
            Variable a { "cc_cache_index", "const unsigned int" },
                peer { "cc_cache_peer", "const unsigned int" };
            Variable k { "cc_cache_k", "const unsigned int" },
                raw { "cc_cache_raw", "scalar_type" };
            Expression boundary
                = Ternary { Expression { tile_index == 0 }, Expression { Literal { 0 } },
                      Expression { Literal { static_cast<unsigned int>(io.rows) } } };
            StatementList fill { Declaration { b, boundary } };
            for (unsigned int i = 0; i < (io.columns + workgroup_size - 1) / workgroup_size; ++i)
            {
                StatementList item { Declaration { a, thread_id + i * workgroup_size },
                    Declaration { peer,
                        Ternary { Expression { b == 0 },
                            Expression { (Literal { static_cast<unsigned int>(io.columns) } - a)
                                % static_cast<unsigned int>(io.columns) },
                            Expression {
                                Literal { static_cast<unsigned int>(io.columns - 1) } - a } } },
                    Declaration { k, a * static_cast<unsigned int>(2 * io.rows) + b },
                    Declaration { raw } };
                Expression physical
                    = Ternary { Expression { k > static_cast<unsigned int>(io.n / 2) },
                          Expression { Literal { static_cast<unsigned int>(io.n) } - k },
                          Expression { k } };
                item += If { a <= peer,
                    { Assign { raw, LoadGlobal { buf, physical } }, Assign { cache[a], raw },
                        Assign { cache[peer], raw } } };
                fill += If { thread_id + i * workgroup_size < static_cast<unsigned int>(io.columns),
                    item };
            }
            s += If { Or { tile_index == 0,
                          tile_index == static_cast<unsigned int>(io.rows / transforms_per_block) },
                fill };
            s += sync_threads();
        }
        for (unsigned int i = 0; i < nregisters; ++i)
            s += Assign { R[i], ComplexLiteral { 0, 0 } };
        s += pass_io(true, lane,
            [&](Expression a, unsigned int reg)
            {
                Expression k = a * static_cast<unsigned int>(2 * io.rows) + col;
                Expression physical
                    = Ternary { Expression { k > static_cast<unsigned int>(io.n / 2) },
                          Expression { Literal { static_cast<unsigned int>(io.n) } - k },
                          Expression { k } };
                Expression value = LoadGlobal { buf, physical };
                if (callbacks)
                    value = Ternary { Expression { Or {
                                          col == 0, col == static_cast<unsigned int>(io.rows) } },
                        Expression { cache[a] }, Expression { value } };
                Expression folded = CallExpr { "cc_folded_value", { scalar_type },
                    { value, k, Literal { static_cast<unsigned int>(io.n) } } };
                StatementList load { Assign { R[reg], folded } };
                return StatementList { If { col <= static_cast<unsigned int>(io.rows), load } };
            });
        // The boundary cache occupies core workspace only until all input R
        // values are ready. No FFT wave may reuse it before its peers finish.
        if (callbacks)
            s += sync_threads();
        return s;
    }
    StatementList store_to_global(bool) override
    {
        Variable lane { "cc_store_lane", "const unsigned int" },
            col { "cc_store_column", "const unsigned int" };
        StatementList s { Declaration { lane, thread_id / transforms_per_block },
            Declaration {
                col, tile_index * transforms_per_block + thread_id % transforms_per_block } };
        s += pass_io(false, lane,
            [&](Expression a, unsigned int reg)
            {
                Expression base = a * static_cast<unsigned int>(io.rows);
                return StatementList {
                    If { col == 0, { StoreGlobal { cc_real_pointer(buf), 2 * base, R[reg].x() } } },
                    ElseIf { col == static_cast<unsigned int>(io.rows),
                        { StoreGlobal { cc_real_pointer(buf), 2 * base + 1, R[reg].x() } } },
                    Else { { If { col < static_cast<unsigned int>(io.rows),
                        { StoreGlobal { buf, base + col, R[reg] } } } } }
                };
            });
        return s;
    }
};

struct StockhamKernelLocalPostColumns : StockhamKernelCC
{
    RealBlockIO io;
    Variable phases { "cc_real_twiddles", "const scalar_type", true, true };
    explicit StockhamKernelLocalPostColumns(const StockhamGeneratorSpecs& specs)
        : StockhamKernelCC(specs, false, false)
        , io(specs.real_io)
    {
    }
    bool use_static_initial_reg_load() const override { return true; }
    ArgumentList global_arguments() override
    {
        auto a = StockhamKernelCC::global_arguments();
        a.append(phases);
        return a;
    }
    StatementList set_direct_to_from_registers() override
    {
        return { Declaration { direct_load_to_reg, Literal { "true" } },
            Declaration { direct_store_from_reg, Literal { "true" } },
            Declaration { lds_linear, Literal { "false" } } };
    }
    StatementList load_from_global(bool) override
    {
        Variable lane { "cc_lane", "const unsigned int" },
            col { "cc_column", "const unsigned int" };
        StatementList s { Declaration { lane, thread_id / transforms_per_block },
            Declaration {
                col, tile_index * transforms_per_block + thread_id % transforms_per_block } };
        for (unsigned int i = 0; i < nregisters; ++i)
            s += Assign { R[i], ComplexLiteral { 0, 0 } };
        s += pass_io(true, lane,
            [&](Expression a, unsigned int reg)
            {
                Expression p = a * static_cast<unsigned int>(2 * io.rows) + col;
                Expression packed = ComplexLiteral { LoadGlobal { cc_real_pointer(buf), p },
                    LoadGlobal { cc_real_pointer(buf), p + static_cast<unsigned int>(io.rows) } };
                StatementList load { Assign { R[reg], packed } };
                return StatementList { If { col < static_cast<unsigned int>(io.rows), load } };
            });
        return s;
    }
    StatementList store_to_global(bool) override
    {
        Variable lane { "cc_post_lane", "const unsigned int" },
            slot { "cc_post_slot", "const unsigned int" };
        StatementList s { Declaration { lane, thread_id / transforms_per_block },
            Declaration { slot, thread_id % transforms_per_block } };
        const unsigned int tasks = (length / 2 + 1) * transforms_per_block;
        const unsigned int rounds = (tasks + workgroup_size - 1) / workgroup_size;
        Variable saved { "cc_saved_real", "real_type_t<scalar_type>" };
        saved.size = Expression { 2 * rounds };
        if (half_lds)
            s += Declaration { saved };
        s += sync_threads();
        auto scatter = [&](bool imaginary)
        {
            return pass_io(false, lane,
                [&](Expression a, unsigned int reg)
                {
                    Expression index = a * transforms_per_block + slot;
                    return half_lds ? StatementList { Assign {
                                          lds_real[index], imaginary ? R[reg].y() : R[reg].x() } }
                                    : StatementList { Assign { lds_complex[index], R[reg] } };
                });
        };
        s += scatter(false);
        s += sync_threads();
        auto consume = [&](unsigned int i, bool save)
        {
            Variable task { "cc_post_task", "const unsigned int" },
                j { "cc_post_j", "const unsigned int" };
            Variable b { "cc_post_b", "const unsigned int" },
                peer { "cc_post_peer", "const unsigned int" };
            StatementList a { Declaration { task, thread_id + i * workgroup_size },
                Declaration { j, task / transforms_per_block },
                Declaration { b, tile_index * transforms_per_block + task % transforms_per_block },
                Declaration { peer,
                    Ternary { Expression { j == 0 }, Expression { Literal { 0 } },
                        Expression { Literal { length } - j } } } };
            Expression left = j * transforms_per_block + task % transforms_per_block;
            Expression right = peer * transforms_per_block + task % transforms_per_block;
            StatementList active;
            if (save)
                active = { Assign { saved[2 * i], lds_real[left] },
                    Assign { saved[2 * i + 1], lds_real[right] } };
            else
            {
                Variable p { "cc_post_p", "scalar_type" }, q { "cc_post_q", "scalar_type" };
                Variable own { "cc_post_own", "scalar_type" },
                    other { "cc_post_other", "scalar_type" };
                active += Declaration { p,
                    half_lds ? Expression { ComplexLiteral { saved[2 * i], lds_real[left] } }
                             : Expression { lds_complex[left] } };
                active += Declaration { q,
                    half_lds ? Expression { ComplexLiteral { saved[2 * i + 1], lds_real[right] } }
                             : Expression { lds_complex[right] } };
                active += Declaration { own };
                active += Declaration { other };
                active += If { j == 0, { StoreGlobal { buf, b, p } } };
                if (length % 2 == 0)
                    active += ElseIf { j == length / 2,
                        { Assign { own, CallExpr { "cc_conjugate", { p } } },
                            StoreGlobal {
                                buf, j * static_cast<unsigned int>(io.rows) + b, own } } };
                active += Else {
                    { Call { "cc_post_pair", { scalar_type }, { p, q, phases[j], own, other } },
                        StoreGlobal { buf, j * static_cast<unsigned int>(io.rows) + b, own },
                        StoreGlobal { buf, peer * static_cast<unsigned int>(io.rows) + b, other } }
                };
            }
            a += If { And { task < tasks, b < static_cast<unsigned int>(io.rows) }, active };
            return StatementList { If { thread_id + i * workgroup_size < tasks, a } };
        };
        if (half_lds)
        {
            for (unsigned int i = 0; i < rounds; ++i)
                s += consume(i, true);
            s += sync_threads();
            s += scatter(true);
            s += sync_threads();
        }
        for (unsigned int i = 0; i < rounds; ++i)
            s += consume(i, false);
        return s;
    }
};
