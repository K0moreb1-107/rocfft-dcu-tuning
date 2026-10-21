// EXP128: row-local inverse preprocessing and forward folded half-spectrum stores.
#pragma once
#include "stockham_gen_rc.h"
#include "stockham_gen_cc_real_common.h"

inline bool cc_local_register_pre(const StockhamGeneratorSpecs& specs)
{
    return RealBlockIO::CanRegisterPre(
        specs.length, specs.factors.front(), specs.threads_per_transform);
}

struct StockhamKernelCCRealRows : StockhamKernelRC
{
    RealBlockIO io;
    Variable phases { "cc_real_twiddles", "const scalar_type", true, true };
    Variable boundary_phases { "cc_boundary_large_twiddles", "const scalar_type", true, true };
    explicit StockhamKernelCCRealRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelRC(specs, false)
        , io(specs.real_io)
    {
    }
    bool use_static_initial_reg_load() const override { return true; }
    ArgumentList global_arguments() override
    {
        auto a = StockhamKernelRC::global_arguments();
        a.append(phases);
        if (io.HasBoundaryLargePhase())
            a.append(boundary_phases);
        return a;
    }
    StatementList set_direct_to_from_registers() override
    {
        return { Declaration { direct_load_to_reg, Literal { "true" } },
            Declaration { direct_store_from_reg, Literal { "false" } },
            Declaration { lds_linear, Literal { "true" } } };
    }
    StatementList initialize_registers() const
    {
        StatementList s;
        for (unsigned int i = 0; i < nregisters; ++i)
            s += Assign { R[i], ComplexLiteral { 0, 0 } };
        return s;
    }
    StatementList reload_input() const
    {
        Expression lane = thread_id % threads_per_transform,
                   slot = thread_id / threads_per_transform;
        StatementList s = initialize_registers();
        s += sync_threads();
        auto loads = pass_io(true, lane, [&](Expression j, unsigned int reg)
            { return StatementList { Assign { R[reg], lds_complex[slot * length + j] } }; });
        s += If { tile_index_in_plane * transforms_per_block + slot
                < static_cast<unsigned int>(io.columns),
            loads };
        s += sync_threads();
        return s;
    }
};

struct StockhamKernelPackedInverseRows : StockhamKernelCCRealRows
{
    explicit StockhamKernelPackedInverseRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelCCRealRows(specs)
    {
    }
    StatementList load_from_global(bool) override
    {
        if (io.load == RealBlockLoad::Registers)
            return register_input();
        const unsigned int tasks = (length / 2 + 1) * transforms_per_block;
        StatementList s;
        for (unsigned int i = 0; i < (tasks + workgroup_size - 1) / workgroup_size; ++i)
        {
            Variable task { "cc_pre_task", "const unsigned int" },
                slot { "cc_pre_slot", "const unsigned int" };
            Variable j { "cc_pre_j", "const unsigned int" },
                row { "cc_pre_row", "const unsigned int" };
            Variable p { "cc_pre_p", "scalar_type" }, q { "cc_pre_q", "scalar_type" };
            Variable own { "cc_pre_own", "scalar_type" }, other { "cc_pre_other", "scalar_type" };
            StatementList a { Declaration { task, thread_id + i * workgroup_size },
                Declaration { slot, task % transforms_per_block },
                Declaration { j, task / transforms_per_block },
                Declaration { row, tile_index_in_plane * transforms_per_block + slot } };
            Expression base = row * length;
            StatementList active { Declaration { p, LoadGlobal { buf, base + j } },
                Declaration { q }, Declaration { own }, Declaration { other } };
            active += If { j == 0,
                { Assign { own, CallExpr { "cc_inverse_endpoints", { p } } },
                    Assign { lds_complex[slot * length], own } } };
            if (length % 2 == 0)
                active += ElseIf { j == length / 2,
                    { Assign { own, CallExpr { "cc_inverse_middle", { p } } },
                        Assign { lds_complex[slot * length + j], own } } };
            active += Else { { Assign { q, LoadGlobal { buf, base + length - j } },
                Call { "cc_pre_pair", { scalar_type }, { p, q, phases[j], own, other } },
                Assign { lds_complex[slot * length + j], own },
                Assign { lds_complex[slot * length + length - j], other } } };
            a += If { row < static_cast<unsigned int>(io.columns), active };
            s += If { thread_id + i * workgroup_size < tasks, a };
        }
        s += reload_input();
        return s;
    }
    StatementList register_input()
    {
        if (!cc_local_register_pre(*this))
            throw std::runtime_error("unproved CC real register pre map");
        const unsigned int f = factors.front(), k = length / f;
        const unsigned int lanes = std::min(k, threads_per_transform), butterflies = k / lanes;
        Variable lane { "cc_pre_lane", "const unsigned int" },
            row { "cc_pre_row", "const unsigned int" };
        Variable j { "cc_pre_j", "unsigned int" }, p { "cc_pre_p", "scalar_type" },
            q { "cc_pre_q", "scalar_type" };
        Variable own { "cc_pre_own", "scalar_type" }, other { "cc_pre_other", "scalar_type" };
        Variable phase { "cc_pre_phase", "scalar_type" },
            exchanged { "cc_pre_exchange", "scalar_type" };
        StatementList s = initialize_registers();
        s += Declaration { lane, thread_id % threads_per_transform };
        s += Declaration { row,
            tile_index_in_plane * transforms_per_block + thread_id / threads_per_transform };
        StatementList a { Declaration { j }, Declaration { p }, Declaration { q },
            Declaration { own }, Declaration { other }, Declaration { phase },
            Declaration { exchanged } };
        Expression base = row * length;
        for (unsigned int h = 0; h < butterflies; ++h)
            for (unsigned int w = 0; w < f / 2; ++w)
            {
                a += Assign { j, lane + h * threads_per_transform + w * k };
                a += Assign { phase,
                    Ternary { Expression { j == 0 }, Expression { Literal { "scalar_type{0,0}" } },
                        Expression { phases[j] } } };
                a += Assign { p, LoadGlobal { buf, base + j } };
                a += If { j == 0,
                    { Assign { own, CallExpr { "cc_inverse_endpoints", { p } } },
                        Assign { other, ComplexLiteral { 0, 0 } } } };
                a += Else { { Assign { q, LoadGlobal { buf, base + length - j } },
                    Call { "cc_pre_pair", { scalar_type }, { p, q, phase, own, other } } } };
                a += Assign { R[h * f + w], own };
                Expression source = (Literal { lanes } - lane) % lanes;
                a += Assign { exchanged.x(),
                    CallExpr { "__shfl", { other.x(), source, Literal { lanes } } } };
                a += Assign { exchanged.y(),
                    CallExpr { "__shfl", { other.y(), source, Literal { lanes } } } };
                a += If { lane != 0,
                    { Assign { R[(butterflies - 1 - h) * f + f - 1 - w], exchanged } } };
                if (h == 0 && w > 0)
                    a += Else { { Assign { R[f - w], other } } };
                else if (h > 0)
                    a += Else { { Assign { R[(butterflies - h) * f + f - 1 - w], other } } };
            }
        a += If { lane == 0,
            { Assign { p, LoadGlobal { buf, base + length / 2 } },
                Assign { R[f / 2], CallExpr { "cc_inverse_middle", { p } } } } };
        s += If { And { lane < lanes, row < static_cast<unsigned int>(io.columns) }, a };
        return s;
    }
    StatementList store_to_global(bool) override
    {
        const unsigned int tasks = length * transforms_per_block;
        Variable first { "cc_output_first", "const unsigned int" },
            valid { "cc_output_valid", "const unsigned int" };
        StatementList s { Declaration { first, tile_index_in_plane * transforms_per_block },
            Declaration { valid,
                CallExpr { "min",
                    { Literal { transforms_per_block },
                        Literal { static_cast<unsigned int>(io.columns) } - first } } } };
        for (unsigned int component = 0; component < 2; ++component)
        {
            Variable head { "cc_output_head_" + std::to_string(component), "const unsigned int" };
            s += Declaration { head,
                (first + static_cast<unsigned int>(io.columns * component)) % 2 };
            for (unsigned int i = 0; i < (tasks + workgroup_size - 1) / workgroup_size; ++i)
            {
                Variable task { "cc_output_task", "const unsigned int" },
                    slot { "cc_output_slot", "const unsigned int" };
                Variable p { "cc_output_p", "const unsigned int" },
                    index { "cc_output_index", "const unsigned int" };
                Variable value { "cc_output_value", "scalar_type" };
                StatementList a { Declaration { task, thread_id + i * workgroup_size },
                    Declaration { slot, task % transforms_per_block },
                    Declaration { p, task / transforms_per_block },
                    Declaration { index,
                        first + slot
                            + static_cast<unsigned int>(io.columns) * (2 * p + component) },
                    Declaration { value } };
                auto left = lds_complex[slot * length + p],
                     right = lds_complex[(slot + 1) * length + p];
                Expression x = component ? left.y() : left.x(),
                           y = component ? right.y() : right.x();
                a += If { And { slot >= head, And { (slot - head) % 2 == 0, slot + 1 < valid } },
                    { Assign { value, ComplexLiteral { x, y } },
                        StoreGlobal { buf, index / 2, value } } };
                a += ElseIf { Or { And { slot == 0, head == 1 },
                                  And { slot + 1 == valid, (index % 2) == 0 } },
                    { StoreGlobal { cc_real_pointer(buf), index, x } } };
                s += If { thread_id + i * workgroup_size < tasks,
                    { If { slot_guard(i, valid), a } } };
            }
        }
        return s;
    }
    Expression slot_guard(unsigned int i, const Expression& valid) const
    {
        return (thread_id + i * workgroup_size) % transforms_per_block < valid;
    }
};

struct StockhamKernelFoldedSpectrumRows : StockhamKernelCCRealRows
{
    explicit StockhamKernelFoldedSpectrumRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelCCRealRows(specs)
    {
    }
    Expression carrier(const Expression& t) const
    {
        Expression high = t >= length, b = t - high * length;
        return LoadGlobal { cc_real_pointer(buf), 2 * b + high };
    }
    StatementList input_value(
        const Expression& j, const Expression& row, const Variable& value) const
    {
        Variable phase { "cc_row_phase", "const scalar_type" };
        Expression lookup = CallExpr { "TW_NSteps",
            { scalar_type, Variable { "cc_boundary_phase_base", "size_t" },
                Variable { "cc_boundary_phase_steps", "size_t" } },
            { boundary_phases, row * j } };
        StatementList ordinary { Declaration { phase, lookup },
            Assign { value, LoadGlobal { buf, row * length + j } },
            Assign { value, TwiddleMultiply { value, phase } } };
        return { If { row == 0,
                     { Assign { value, ComplexLiteral { carrier(2 * j), carrier(2 * j + 1) } } } },
            Else { ordinary } };
    }
    StatementList load_from_global(bool) override
    {
        Expression slot = thread_id / threads_per_transform,
                   lane = thread_id % threads_per_transform;
        Expression row = tile_index_in_plane * transforms_per_block + slot;
        StatementList s = initialize_registers();
        if (io.load == RealBlockLoad::Registers)
        {
            s += pass_io(true, lane,
                [&](Expression j, unsigned int reg)
                {
                    return StatementList { If { row < static_cast<unsigned int>(io.columns),
                        input_value(j, row, R[reg]) } };
                });
            return s;
        }
        const unsigned int tasks = length * transforms_per_block;
        for (unsigned int i = 0; i < (tasks + workgroup_size - 1) / workgroup_size; ++i)
        {
            Expression task = thread_id + i * workgroup_size;
            Expression a = tile_index_in_plane * transforms_per_block + task / length,
                       j = task % length;
            Variable value { "cc_row_input", "scalar_type" };
            StatementList active { Declaration { value } };
            active += input_value(j, a, value);
            active += Assign { lds_complex[task], value };
            s += If { And { task < tasks, a < static_cast<unsigned int>(io.columns) }, active };
        }
        s += reload_input();
        return s;
    }
    StatementList store_to_global(bool) override
    {
        const unsigned int tasks = length * transforms_per_block;
        StatementList s;
        for (unsigned int i = 0; i < (tasks + workgroup_size - 1) / workgroup_size; ++i)
        {
            Variable task { "cc_spectrum_task", "const unsigned int" },
                slot { "cc_spectrum_slot", "const unsigned int" };
            Variable row { "cc_spectrum_row", "const unsigned int" },
                k { "cc_spectrum_k", "const unsigned int" };
            Variable value { "cc_spectrum_value", "scalar_type" };
            StatementList a { Declaration { task, thread_id + i * workgroup_size },
                Declaration { slot, task % transforms_per_block },
                Declaration { row, tile_index_in_plane * transforms_per_block + slot },
                Declaration { k,
                    static_cast<unsigned int>(2 * io.columns) * (task / transforms_per_block)
                        + row },
                Declaration { value } };
            Expression physical = Ternary { Expression { k > static_cast<unsigned int>(io.n / 2) },
                Expression { Literal { static_cast<unsigned int>(io.n) } - k }, Expression { k } };
            a += If { And { row != 0, row < static_cast<unsigned int>(io.columns) },
                { Assign { value, lds_complex[slot * length + task / transforms_per_block] },
                    If { k > static_cast<unsigned int>(io.n / 2),
                        { Assign { value, CallExpr { "cc_conjugate", { value } } } } },
                    StoreGlobal { buf, physical, value } } };
            s += If { thread_id + i * workgroup_size < tasks, a };
        }
        StatementList terminal;
        for (unsigned int i = 0; i < (length / 2 + 1 + workgroup_size - 1) / workgroup_size; ++i)
        {
            Variable j { "cc_terminal_j", "const unsigned int" },
                p { "cc_terminal_p", "scalar_type" };
            Variable q { "cc_terminal_q", "scalar_type" }, own { "cc_terminal_own", "scalar_type" },
                other { "cc_terminal_other", "scalar_type" };
            StatementList a { Declaration { j, thread_id + i * workgroup_size },
                Declaration { p, lds_complex[j] }, Declaration { q }, Declaration { own },
                Declaration { other } };
            a += If { j == 0,
                { Assign { own, ComplexLiteral { p.x() + p.y(), Literal { 0 } } },
                    Assign { other, ComplexLiteral { p.x() - p.y(), Literal { 0 } } },
                    StoreGlobal { buf, Literal { 0 }, own },
                    StoreGlobal { buf, Literal { static_cast<unsigned int>(io.n / 2) }, other } } };
            if (length % 2 == 0)
                a += ElseIf { j == length / 2,
                    { Assign { own, CallExpr { "cc_conjugate", { p } } },
                        StoreGlobal { buf, static_cast<unsigned int>(io.columns) * j, own } } };
            a += Else { { Assign { q, lds_complex[length - j] },
                Call { "cc_post_pair", { scalar_type }, { p, q, phases[j], own, other } },
                StoreGlobal { buf, static_cast<unsigned int>(io.columns) * j, own },
                StoreGlobal {
                    buf, static_cast<unsigned int>(io.columns) * (length - j), other } } };
            terminal += If { thread_id + i * workgroup_size < length / 2 + 1, a };
        }
        s += If { tile_index_in_plane == 0, terminal };
        return s;
    }
};
