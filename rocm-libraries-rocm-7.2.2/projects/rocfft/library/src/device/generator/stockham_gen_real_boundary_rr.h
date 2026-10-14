// Paired real-transform boundaries around an ordinary row FFT.
#pragma once

#include "real_pair_layout.h"
#include "stockham_gen_rr.h"

struct StockhamKernelRealBoundaryRows : StockhamKernelRR
{
    Variable real_phase{"real_boundary_phase", "const scalar_type", true, true};
    Variable axis{"boundary_axis", "const size_t"};
    Variable half_length{"boundary_m", "const size_t"};
    Variable slot{"boundary_core_slot", "const unsigned int"};
    Variable row{"boundary_core_row", "const size_t"};

    explicit StockhamKernelRealBoundaryRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelRR(specs)
    {
        if(!real_boundary.Valid() || real_boundary.container != RealBoundaryContainer::Rows
           || length == 0 || factors.empty() || real_boundary.HalfLength() % length != 0
           || real_io.role != RealBlockRole::None || ebtype != EmbeddedType::NONE
           || transforms_per_block < 4 || transforms_per_block % 2 != 0
           || workgroup_size != transforms_per_block * threads_per_transform
           || !direct_to_from_reg || !static_initial_reg_load)
            throw std::runtime_error("invalid paired real row boundary geometry");
    }

    Expression span() const { return Literal{std::to_string(length) + "ul"}; }
    Expression exchange_cell(Expression local_slot, Expression index) const
    {
        return local_slot * (span() + 1) + index;
    }
    Expression paired_row(Expression local_slot) const
    {
        return CallExpr{"real_pair_row",
                        {axis, Literal{transforms_per_block}, local_slot, block_id}};
    }
    Expression mirrored_index(const Variable& j, const Variable& tag) const
    {
        const auto zero_row = Ternary{Expression{j == 0}, Expression{Literal{0}},
                                     Expression{span() - j}};
        return Ternary{Expression{tag == 0}, Expression{zero_row},
                       Expression{span() - 1 - j}};
    }

    std::string load_callback_type_name() const override
    {
        return real_boundary.Pre() ? callback_type.name : "CallbackType::NONE";
    }
    std::string store_callback_type_name() const override
    {
        return real_boundary.Post() ? callback_type.name : "CallbackType::NONE";
    }
    ArgumentList global_arguments() override
    {
        auto args = StockhamKernelRR::global_arguments();
        args.append(real_phase);
        return args;
    }
    StatementList set_direct_to_from_registers() override
    {
        return {Declaration{direct_load_to_reg, Literal{"true"}},
                Declaration{direct_store_from_reg, Literal{"true"}},
                Declaration{lds_linear, Literal{"true"}}};
    }
    StatementList calculate_offsets() override
    {
        // Core storage stays tight; only the temporary boundary view has padding.
        return {Declaration{thread}, Declaration{axis, lengths[1]},
                Declaration{half_length, span() * axis},
                Declaration{slot, thread_id / threads_per_transform},
                Declaration{row, paired_row(slot)},
                Assign{transform, row}, Assign{batch, Literal{0}},
                Assign{offset, row * stride[1]}, Assign{stride_lds, span()},
                Assign{offset_lds, slot * span()}, Declaration{inbound, row < axis}};
    }
    StatementList initial_registers_ready() override
    {
        // No first-pass reader may overlap the core's first reuse of shared memory.
        return real_boundary.Pre() ? StatementList{SyncThreads{}} : StatementList{};
    }

    StatementList load_from_global(bool) override
    {
        if(real_boundary.Post())
        {
            StatementList body = clear_initial_registers();
            body += Assign{thread, thread_id % threads_per_transform};
            body += If{inbound, first_pass_io([&](Expression index, Variable reg) {
                return StatementList{Assign{reg, LoadGlobal{buf, offset + index * stride0}}};
            })};
            return body;
        }

        Variable owner_slot{"pre_slot", "const unsigned int"};
        Variable owner_row{"pre_row", "const size_t"};
        Variable peer_slot{"pre_peer", "const unsigned int"};
        Variable j{"pre_j", "size_t"}, k{"pre_k", "size_t"};
        Variable p{"pre_p", "scalar_type"}, q{"pre_q", "scalar_type"};
        Variable own{"pre_own", "scalar_type"}, other{"pre_other", "scalar_type"};
        StatementList body{
            Declaration{owner_slot, thread_id % transforms_per_block},
            Declaration{owner_row, paired_row(owner_slot)},
            Declaration{peer_slot, CallExpr{"real_pair_peer",
                {axis, Literal{transforms_per_block}, owner_slot, owner_row}}},
            Declaration{j}, Declaration{k}, Declaration{p}, Declaration{q},
            Declaration{own}, Declaration{other}};
        const auto canonical = And{k > 0, k < half_length - k};
        for(unsigned int h = 0; h < (length + threads_per_transform - 1) / threads_per_transform; ++h)
        {
            body += Assign{j, thread_id / transforms_per_block + h * threads_per_transform};
            body += Assign{k, owner_row + axis * j};
            StatementList values{
                If{k == 0,
                    {Assign{p, LoadGlobal{buf, Literal{0}}},
                     Assign{q, LoadGlobal{buf, half_length}},
                     Assign{own, ComplexLiteral{p.x() + q.x(), p.x() - q.x()}},
                     Assign{lds_complex[exchange_cell(owner_slot, j)], own}}},
                If{And{half_length % 2 == 0, k == half_length / 2},
                    {Assign{p, LoadGlobal{buf, k}},
                     Assign{own, ComplexLiteral{2 * p.x(), -2 * p.y()}},
                     Assign{lds_complex[exchange_cell(owner_slot, j)], own}}},
                If{canonical,
                    {Assign{p, LoadGlobal{buf, k}},
                     Assign{q, LoadGlobal{buf, half_length - k}},
                     Call{"real_pair_pre", {scalar_type},
                          {p, q, real_phase[k], own, other}},
                     Assign{lds_complex[exchange_cell(owner_slot, j)], own},
                     Assign{lds_complex[exchange_cell(peer_slot, mirrored_index(j, owner_row))],
                            other}}}};
            body += If{And{j < span(), owner_row < axis}, values};
        }
        body += SyncThreads{};
        body += clear_initial_registers();
        body += Assign{thread, thread_id % threads_per_transform};
        body += If{inbound, first_pass_io([&](Expression index, Variable reg) {
            return StatementList{Assign{reg, lds_complex[exchange_cell(slot, index)]}};
        })};
        return body;
    }

    StatementList store_to_global(bool registers) override
    {
        if(real_boundary.Pre())
            return StockhamKernelRR::store_to_global(registers);

        // The half-capacity core and the full-complex boundary share one allocation.
        StatementList body{SyncThreads{}, Assign{thread, thread_id % threads_per_transform}};
        body += If{inbound, last_pass_io([&](Expression index, Variable reg) {
            return StatementList{Assign{lds_complex[exchange_cell(slot, index)], reg}};
        })};
        body += SyncThreads{};

        Variable owner_slot{"post_slot", "const unsigned int"};
        Variable owner_row{"post_row", "const size_t"};
        Variable peer_slot{"post_peer", "const unsigned int"};
        Variable j{"post_j", "size_t"}, k{"post_k", "size_t"};
        Variable p{"post_p", "scalar_type"}, q{"post_q", "scalar_type"};
        Variable own{"post_own", "scalar_type"}, other{"post_other", "scalar_type"};
        body += StatementList{
            Declaration{owner_slot, thread_id % transforms_per_block},
            Declaration{owner_row, paired_row(owner_slot)},
            Declaration{peer_slot, CallExpr{"real_pair_peer",
                {axis, Literal{transforms_per_block}, owner_slot, owner_row}}},
            Declaration{j}, Declaration{k}, Declaration{p}, Declaration{q},
            Declaration{own}, Declaration{other}};
        const auto canonical = And{k > 0, k < half_length - k};
        for(unsigned int h = 0; h < (length + threads_per_transform - 1) / threads_per_transform; ++h)
        {
            body += Assign{j, thread_id / transforms_per_block + h * threads_per_transform};
            body += Assign{k, owner_row + axis * j};
            StatementList values{
                If{k == 0,
                    {Assign{p, lds_complex[exchange_cell(owner_slot, j)]},
                     Assign{own, ComplexLiteral{p.x() + p.y(), Literal{0}}},
                     StoreGlobal{buf, Literal{0}, own},
                     Assign{own, ComplexLiteral{p.x() - p.y(), Literal{0}}},
                     StoreGlobal{buf, half_length, own}}},
                If{And{half_length % 2 == 0, k == half_length / 2},
                    {Assign{p, lds_complex[exchange_cell(owner_slot, j)]},
                     Assign{own, ComplexLiteral{p.x(), -p.y()}}, StoreGlobal{buf, k, own}}},
                If{canonical,
                    {Assign{p, lds_complex[exchange_cell(owner_slot, j)]},
                     Assign{q, lds_complex[exchange_cell(peer_slot, mirrored_index(j, owner_row))]},
                     Call{"real_pair_post", {scalar_type},
                          {p, q, real_phase[k], own, other}},
                     StoreGlobal{buf, k, own}, StoreGlobal{buf, half_length - k, other}}}};
            body += If{And{j < span(), owner_row < axis}, values};
        }
        return body;
    }
};
