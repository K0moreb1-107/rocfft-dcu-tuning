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
    bool use_single_row_output() const
    {
        return transforms_per_block == 1
            && threads_per_transform == length / factors.back();
    }
    StatementList set_direct_to_from_registers() override
    {
        return { Declaration { direct_load_to_reg, Literal { "true" } },
            Declaration { direct_store_from_reg,
                Literal { use_single_row_output() ? "true" : "false" } },
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
    bool use_packed_output() const
    {
        return io.columns % 2 == 0 && transforms_per_block % 2 == 0
            && io.columns % transforms_per_block == 0;
    }
    StatementList packed_output() const
    {
        const unsigned int rows = transforms_per_block;
        Variable slot { "cc_packed_slot", "const unsigned int" },
            component { "cc_packed_component", "const unsigned int" },
            pair { "cc_packed_pair", "const unsigned int" };
        Variable value { "cc_packed_value", "scalar_type" };
        StatementList s { Declaration { slot, thread_id % rows },
            Declaration { component, slot / (rows / 2) },
            Declaration { pair, slot % (rows / 2) }, Declaration { value } };
        for (unsigned int i = 0; i * threads_per_transform < length; ++i)
        {
            Expression j = thread_id / rows + i * threads_per_transform;
            Expression left = 2 * (2 * pair * length + j) + component;
            StatementList stores {
                Assign { value, ComplexLiteral { lds_real[left], lds_real[left + 2 * length] } },
                StoreGlobal { buf, tile_index_in_plane * (rows / 2) + pair
                    + static_cast<unsigned int>(io.columns) * j
                    + component * static_cast<unsigned int>(io.columns / 2), value } };
            if ((i + 1) * threads_per_transform > length)
                s += If { j < length, stores };
            else
                s += stores;
        }
        return s;
    }
    StatementList store_to_global(bool) override
    {
        if (use_single_row_output())
        {
            Variable row { "cc_direct_row", "const unsigned int" },
                lane { "cc_direct_lane", "const unsigned int" };
            StatementList s { Declaration { row, tile_index_in_plane },
                Declaration { lane, thread_id % threads_per_transform } };
            s += pass_io(false, lane, [&](Expression j, unsigned int reg)
                {
                    Expression index = row + static_cast<unsigned int>(2 * io.columns) * j;
                    return StatementList {
                        StoreGlobal { cc_real_pointer(buf), index, R[reg].x() },
                        StoreGlobal { cc_real_pointer(buf),
                            index + static_cast<unsigned int>(io.columns), R[reg].y() } };
                });
            return s;
        }
        if (use_packed_output())
            return packed_output();
        Variable first { "cc_output_first", "const unsigned int" },
            valid { "cc_output_valid", "const unsigned int" },
            slot { "cc_output_slot", "const unsigned int" },
            p0 { "cc_output_p0", "const unsigned int" };
        StatementList s { Declaration { first, tile_index_in_plane * transforms_per_block } };
        if (io.columns % transforms_per_block == 0)
            s += Declaration { valid, Literal { transforms_per_block } };
        else
            s += Declaration { valid,
                CallExpr { "min",
                    { Literal { transforms_per_block },
                        Literal { static_cast<unsigned int>(io.columns) } - first } } };
        s += Declaration { slot, thread_id % transforms_per_block };
        s += Declaration { p0, thread_id / transforms_per_block };
        // WGS = threads_per_transform * transforms_per_block, so row ownership
        // and real-output alignment are invariant across the frequency unroll.
        StatementList active;
        for (unsigned int component = 0; component < 2; ++component)
        {
            const auto suffix = std::to_string(component);
            Variable head { "cc_output_head_" + suffix, "const unsigned int" },
                base { "cc_output_base_" + suffix, "const unsigned int" };
            active += Declaration { head,
                (first + static_cast<unsigned int>(io.columns * component)) % 2 };
            active += Declaration { base,
                first + slot + static_cast<unsigned int>(io.columns * component) };
            StatementList vector_stores, scalar_stores;
            for (unsigned int i = 0; i * threads_per_transform < length; ++i)
            {
                Expression p = p0 + i * threads_per_transform,
                           index = base + static_cast<unsigned int>(2 * io.columns) * p;
                auto left = lds_complex[slot * length + p],
                     right = lds_complex[(slot + 1) * length + p];
                Expression x = component ? left.y() : left.x(),
                           y = component ? right.y() : right.x();
                StatementList vector_store {
                    StoreGlobal { buf, index / 2, ComplexLiteral { x, y } } };
                StatementList scalar_store { StoreGlobal { cc_real_pointer(buf), index, x } };
                if ((i + 1) * threads_per_transform <= length)
                {
                    vector_stores += vector_store;
                    scalar_stores += scalar_store;
                }
                else
                {
                    vector_stores += If { p < length, vector_store };
                    scalar_stores += If { p < length, scalar_store };
                }
            }
            active += If { And { slot >= head, And { (slot - head) % 2 == 0, slot + 1 < valid } },
                vector_stores };
            active += ElseIf { Or { And { slot == 0, head == 1 },
                                   And { slot + 1 == valid, (base % 2) == 0 } },
                scalar_stores };
        }
        s += If { slot < valid, active };
        return s;
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
    Expression boundary_phase(const Expression& index) const
    {
        return CallExpr { "TW_NSteps",
            { scalar_type, Variable { "cc_boundary_phase_base", "size_t" },
                Variable { "cc_boundary_phase_steps", "size_t" } },
            { boundary_phases, index } };
    }
    bool use_phase_recurrence() const
    {
        if (io.load != RealBlockLoad::Registers || factors.empty() || !factors.front())
            return false;
        const unsigned int count = length / factors.front();
        // One initial phase per butterfly and one step per active thread.
        return length > count + std::min(count, threads_per_transform);
    }
    StatementList phased_input(const Expression& j,
                              const Expression& row,
                              const Variable& value,
                              const Variable& phase) const
    {
        return { Assign { value, LoadGlobal { buf, row * length + j } },
            Assign { value, TwiddleMultiply { value, phase } } };
    }
    StatementList recurrent_input(const Expression& j,
                                 const Expression& row,
                                 const Variable& value,
                                 unsigned int reg,
                                 const Variable& phase,
                                 const Variable& delta,
                                 bool declare_phase) const
    {
        const unsigned int w = reg % factors.front();
        StatementList s;
        if (w == 0)
        {
            if (declare_phase)
                s += Declaration { phase, boundary_phase(row * j) };
            else
                s += Assign { phase, boundary_phase(row * j) };
        }
        s += phased_input(j, row, value, phase);
        if (w + 1 < factors.front())
            s += Assign { phase, TwiddleMultiply { phase, delta } };
        return s;
    }
    StatementList ordinary_register_input(const Expression& lane, const Expression& row) const
    {
        Variable delta { "cc_phase_delta", "const scalar_type" };
        StatementList s { Declaration { delta,
            boundary_phase(row * static_cast<unsigned int>(length / factors.front())) } };
        s += pass_io(true, lane, [&](Expression j, unsigned int reg)
            {
                Variable phase { "cc_phase_current_" + std::to_string(reg / factors.front()),
                    "scalar_type" };
                return recurrent_input(j, row, R[reg], reg, phase, delta, true);
            });
        return s;
    }
    StatementList input_value(const Expression& j,
                              const Expression& row,
                              const Variable& value,
                              bool carrier_row,
                              unsigned int reg = 0) const
    {
        if (carrier_row)
            return { Assign { value, ComplexLiteral { carrier(2 * j), carrier(2 * j + 1) } } };
        // Native pass_io may emit adjacent registers without additional scopes.
        Variable phase { "cc_row_phase_" + std::to_string(reg), "const scalar_type" };
        StatementList s { Declaration { phase, boundary_phase(row * j) } };
        s += phased_input(j, row, value, phase);
        return s;
    }
    StatementList input_value(
        const Expression& j, const Expression& row, const Variable& value) const
    {
        return { If { row == 0, input_value(j, row, value, true) },
                 Else { input_value(j, row, value, false) } };
    }
    StatementList grouped_register_input(const Expression& lane, const Expression& row) const
    {
        const unsigned int width = factors.front(), count = length / width;
        StatementList groups;
        Variable phase { "cc_phase_current", "scalar_type" },
            delta { "cc_phase_delta", "scalar_type" };
        if (use_phase_recurrence())
        {
            groups += Declaration { phase };
            groups += Declaration { delta };
            groups += If { row != 0,
                { Assign { delta, boundary_phase(row * count) } } };
        }
        // With fewer first-pass butterflies than lanes, pass_io has only h=0:
        // j=lane+w*count maps to R[w]. Keep its single active-lane guard.
        for (unsigned int first = 0; first < width; first += 2)
        {
            StatementList carrier_values, ordinary_values;
            for (unsigned int reg = first; reg < std::min(first + 2, width); ++reg)
            {
                Expression j = lane + reg * count;
                carrier_values += input_value(j, row, R[reg], true, reg);
                ordinary_values += use_phase_recurrence()
                    ? recurrent_input(j, row, R[reg], reg, phase, delta, false)
                    : input_value(j, row, R[reg], false, reg);
            }
            groups += If { row == 0, carrier_values };
            groups += Else { ordinary_values };
        }
        return { If { lane < count, groups } };
    }
    StatementList load_from_global(bool) override
    {
        Expression slot = thread_id / threads_per_transform,
                   lane = thread_id % threads_per_transform;
        StatementList s = initialize_registers();
        if (io.load == RealBlockLoad::Registers)
        {
            Variable row { "cc_input_row", "const unsigned int" };
            s += Declaration { row, tile_index_in_plane * transforms_per_block + slot };
            auto loads = [&](bool carrier_row)
            {
                if (!carrier_row && use_phase_recurrence())
                    return ordinary_register_input(lane, row);
                return pass_io(true, lane, [&](Expression j, unsigned int reg)
                    { return input_value(j, row, R[reg], carrier_row, reg); });
            };
            if (threads_per_transform > length / factors.front())
                s += If { row < static_cast<unsigned int>(io.columns),
                    grouped_register_input(lane, row) };
            else
                s += If { row < static_cast<unsigned int>(io.columns),
                    { If { row == 0, loads(true) }, Else { loads(false) } } };
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
    StatementList terminal_output() const
    {
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
        return terminal;
    }
    StatementList single_row_output() const
    {
        Variable row { "cc_direct_row", "const unsigned int" },
            lane { "cc_direct_lane", "const unsigned int" };
        StatementList s { Declaration { row, tile_index_in_plane },
            Declaration { lane, thread_id % threads_per_transform } };
        auto ordinary = pass_io(false, lane, [&](Expression j, unsigned int reg)
            {
                const auto suffix = std::to_string(reg);
                Variable k { "cc_spectrum_k_" + suffix, "unsigned int" },
                    value { "cc_spectrum_value_" + suffix, "scalar_type" };
                return StatementList {
                    Declaration { k, static_cast<unsigned int>(2 * io.columns) * j + row },
                    Declaration { value, R[reg] },
                    If { j >= (length + 1) / 2,
                        { Assign { value, CallExpr { "cc_conjugate", { value } } },
                            Assign { k, static_cast<unsigned int>(io.n) - k } } },
                    StoreGlobal { buf, k, value } };
            });
        // This branch is uniform across the block. Only the terminal row
        // reuses core LDS and needs the two output barriers.
        StatementList terminal { sync_threads() };
        terminal += pass_io(false, lane, [&](Expression j, unsigned int reg)
            { return StatementList { Assign { lds_complex[j], R[reg] } }; });
        terminal += sync_threads();
        terminal += terminal_output();
        s += If { row != 0, ordinary };
        s += Else { terminal };
        return s;
    }
    StatementList store_to_global(bool) override
    {
        if (use_single_row_output())
            return single_row_output();
        Variable slot { "cc_spectrum_slot", "const unsigned int" },
            row { "cc_spectrum_row", "const unsigned int" },
            p0 { "cc_spectrum_p0", "const unsigned int" };
        StatementList s { Declaration { slot, thread_id % transforms_per_block },
            Declaration { row, tile_index_in_plane * transforms_per_block + slot },
            Declaration { p0, thread_id / transforms_per_block } };
        StatementList ordinary;
        for (unsigned int i = 0; i * threads_per_transform < length; ++i)
        {
            Expression j = p0 + i * threads_per_transform;
            Variable k { "cc_spectrum_k", "unsigned int" };
            Variable value { "cc_spectrum_value", "scalar_type" };
            // For 0 < row < C, 2*C*j+row > C*Q iff j >= ceil(Q/2).
            ordinary += If { j < length,
                { Declaration { k, static_cast<unsigned int>(2 * io.columns) * j + row },
                    Declaration { value, lds_complex[slot * length + j] },
                    If { j >= (length + 1) / 2,
                        { Assign { value, CallExpr { "cc_conjugate", { value } } },
                            Assign { k, static_cast<unsigned int>(io.n) - k } } },
                    StoreGlobal { buf, k, value } } };
        }
        s += If { And { row != 0, row < static_cast<unsigned int>(io.columns) }, ordinary };
        s += If { tile_index_in_plane == 0, terminal_output() };
        return s;
    }
};
