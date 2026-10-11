// EXP-126: generic paired CC boundaries; legacy EXP-125 generators stay separate.
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

struct StockhamKernelPairedPreColumns : StockhamKernelCC
{
    const size_t columns, rows, m;
    Variable pair_twiddles{"real_pair_twiddles", "const scalar_type", true, true};

    explicit StockhamKernelPairedPreColumns(const StockhamGeneratorSpecs& specs)
        : StockhamKernelCC(specs, false, false)
        , columns(specs.real_io.columns), rows(specs.real_io.rows), m(specs.real_io.n / 2)
    {
        if(real_io.role != RealBlockRole::PairedPreColumns || length != columns
           || columns * rows != m || real_io.pitch != rows
           || transforms_per_block < 2 || transforms_per_block % 2 != 0
           || half_lds != real_io.ScalarPairIO()
           || direct_to_from_reg != real_io.DirectPairIO()
           || (real_io.final_phase == RealPairFinalPhase::AtStore && factors != std::vector<unsigned int>{17,17}))
            throw std::runtime_error("invalid paired real pre geometry");
    }

    Expression get_lds_padding() override { return Literal{0}; }
    std::string store_callback_type_name() const override { return "CallbackType::NONE"; }

    ArgumentList global_arguments() override
    {
        auto args = StockhamKernelCC::global_arguments(); args.append(pair_twiddles); return args;
    }

    StatementList set_direct_to_from_registers() override
    {
        if(!real_io.DirectPairIO()) return StockhamKernelCC::set_direct_to_from_registers();
        return {Declaration{direct_load_to_reg, Literal{"true"}},
                Declaration{direct_store_from_reg, Literal{"true"}},
                Declaration{lds_linear, Literal{"false"}}};
    }

    StatementList calculate_offsets() override
    {
        auto body = StockhamKernelCC::calculate_offsets();
        auto slot = real_io.DirectPairIO() ? Expression{thread_id % transforms_per_block}
                                          : Expression{thread_id / threads_per_transform};
        body += Assign{transform, real_pair_row_expr(rows, transforms_per_block, slot, tile_index)};
        return body;
    }

    StatementList initial_registers_ready() override
    {
        // All staged first-pass reads finish before the core reuses this memory.
        return real_io.DirectPairIO() ? StatementList{SyncThreads{}} : StatementList{};
    }

    TemplateList device_call_templates() override
    {
        auto args = StockhamKernelCC::device_call_templates();
        if(real_io.final_phase == RealPairFinalPhase::AtStore)
            args.set_value(apply_large_twiddle.name, "false");
        return args;
    }

    StatementList load_from_global(bool) override
    {
        const auto slots = transforms_per_block;
        const unsigned int half_column = (length + 1) / 2;
        const unsigned int extent = real_io.ScalarPairIO() ? half_column : length;
        const unsigned int count = (extent + threads_per_transform - 1) / threads_per_transform;
        Variable slot{"pre_slot", "const unsigned int"};
        Variable column{"pre_column", "const unsigned int"};
        Variable peer{"pre_peer", "const unsigned int"};
        Variable a{"pre_a", "unsigned int"}, k{"pre_k", "size_t"};
        Variable p{"pre_p", "scalar_type"}, q{"pre_q", "scalar_type"};
        Variable own{"pre_own", "scalar_type"}, other{"pre_other", "scalar_type"};
        Variable imag_own{"pre_imag_own", "real_type_t<scalar_type>"};
        Variable imag_other{"pre_imag_other", "real_type_t<scalar_type>"};
        Variable midpoint_imag{"pre_midpoint_imag", "real_type_t<scalar_type>"};
        imag_own.size = Literal{count}; imag_other.size = Literal{count};
        StatementList body{
            Declaration{slot, thread_id % slots},
            Declaration{column, real_pair_row_expr(rows, slots, slot, tile_index)},
            Declaration{peer, CallExpr{"real_pair_peer", {real_pair_size(rows), Literal{slots}, slot, column}}},
            Declaration{a}, Declaration{k}, Declaration{p}, Declaration{q},
            Declaration{own}, Declaration{other}};
        if(real_io.ScalarPairIO())
            body += StatementList{Declaration{imag_own}, Declaration{imag_other}, Declaration{midpoint_imag}};

        const auto cell = [&](Expression s, Expression coordinate) -> Expression {
            return real_io.DirectPairIO() ? coordinate * slots + s : s * length + coordinate;
        };
        const auto other_a = Parens{(Literal{length} - a
            - Ternary{Expression{column == 0}, Expression{Literal{0}}, Expression{Literal{1}}}) % Literal{length}};
        const auto phase = tile_index * real_pair_size(slots * half_column) + a * slots + slot;
        const auto canonical = And{k > 0, 2 * k < real_pair_size(m)};
        for(unsigned int i = 0; i < count; ++i)
        {
            body += Assign{a, thread_id / slots + i * threads_per_transform};
            body += Assign{k, a * real_pair_size(rows) + column};
            const auto save = [&](Expression coordinate, const Variable& value, bool mirror) {
                if(!real_io.ScalarPairIO())
                    return StatementList{Assign{lds_complex[coordinate], value}};
                return StatementList{Assign{lds_real[coordinate], value.x()},
                    Assign{mirror ? imag_other[i] : imag_own[i], value.y()}};
            };
            StatementList values;
            values += If{k == 0,
                {Assign{p, LoadGlobal{buf, Literal{0}}}, Assign{q, LoadGlobal{buf, real_pair_size(m)}},
                 Assign{own, ComplexLiteral{p.x()+q.x(),p.x()-q.x()}}}};
            values += If{k == 0, save(cell(slot,a),own,false)};
            if(m % 2 == 0)
            {
                values += If{k == real_pair_size(m/2),
                    {Assign{p, LoadGlobal{buf,k}}, Assign{own, ComplexLiteral{2*p.x(),-2*p.y()}}}};
                values += If{k == real_pair_size(m/2),save(cell(slot,a),own,false)};
            }
            values += If{canonical,
                {Assign{p,LoadGlobal{buf,k}},Assign{q,LoadGlobal{buf,real_pair_size(m)-k}},
                 Call{"real_pair_pre", {scalar_type}, {p,q,pair_twiddles[phase],own,other}}}};
            StatementList pairs = save(cell(slot,a),own,false);
            pairs += save(cell(peer,other_a),other,true);
            values += If{canonical,pairs};
            StatementList invalid;
            if(real_io.ScalarPairIO())
                invalid = {Assign{lds_real[cell(slot,a)],Literal{0}},
                    Assign{lds_real[cell(slot,length-1-a)],Literal{0}},
                    Assign{imag_own[i],Literal{0}},Assign{imag_other[i],Literal{0}}};
            else invalid = {Assign{lds_complex[cell(slot,a)],ComplexLiteral{Literal{0},Literal{0}}}};
            body += If{a < extent,{If{column < real_pair_size(rows),values},Else{invalid}}};
        }
        // The even local midpoint is outside the canonical half-column loop.
        if(real_io.ScalarPairIO() && length % 2 == 0)
            body += If{And{tile_index == 0,thread_id == 0},
                {Assign{p,LoadGlobal{buf,real_pair_size(m/2)}},
                 Assign{lds_real[cell(Literal{0},Literal{length/2})],2*p.x()},
                 Assign{midpoint_imag,-2*p.y()}}};
        if(!real_io.DirectPairIO()) return body;

        body += clear_initial_registers();
        body += Assign{thread,thread_id / slots};
        body += SyncThreads{};
        const auto load_field = [&](bool imaginary) {
            return first_pass_io([&](Expression index,Variable reg) {
                const auto source = offset_lds + index * stride_lds;
                if(!real_io.ScalarPairIO()) return StatementList{Assign{reg,lds_complex[source]}};
                return StatementList{Assign{imaginary ? reg.y() : reg.x(),lds_real[source]}};
            });
        };
        body += load_field(false);
        if(real_io.ScalarPairIO())
        {
            body += SyncThreads{};
            for(unsigned int i = 0; i < count; ++i)
            {
                body += Assign{a,thread_id / slots+i*threads_per_transform};
                body += Assign{k,a*real_pair_size(rows)+column};
                Expression own_valid = Or{k == 0,canonical};
                if(length%2 != 0 && m%2 == 0) own_valid = Or{own_valid,k == real_pair_size(m/2)};
                StatementList values{If{own_valid,{Assign{lds_real[cell(slot,a)],imag_own[i]}}},
                    If{canonical,{Assign{lds_real[cell(peer,other_a)],imag_other[i]}}}};
                StatementList invalid{Assign{lds_real[cell(slot,a)],Literal{0}},
                    Assign{lds_real[cell(slot,length-1-a)],Literal{0}}};
                body += If{a < half_column,{If{column < real_pair_size(rows),values},Else{invalid}}};
            }
            if(length%2 == 0)
                body += If{And{tile_index == 0,thread_id == 0},
                    {Assign{lds_real[cell(Literal{0},Literal{length/2})],midpoint_imag}}};
            body += SyncThreads{};
            body += load_field(true);
        }
        // initial_registers_ready() supplies the final read-before-reuse barrier.
        return body;
    }

    StatementList store_to_global(bool registers) override
    {
        if(registers)
        {
            StatementList body{Assign{thread,thread_id/transforms_per_block}};
            Variable phase{"pre_final_phase","scalar_type"};
            if(real_io.final_phase == RealPairFinalPhase::AtStore) body += Declaration{phase};
            const auto output = last_pass_io([&](Expression index,Variable reg) {
                StatementList values;
                if(real_io.final_phase == RealPairFinalPhase::AtStore)
                {
                    auto table = Ternary{Expression{ltwd_in_lds},Expression{large_twd_lds},Expression{large_twiddles}};
                    values += If{apply_large_twiddle,
                        {Assign{phase,CallExpr{"TW_NSteps",{scalar_type,large_twiddle_base,large_twiddle_steps},
                            {table,index*transform}}},Assign{reg,TwiddleMultiply{reg,phase}}}};
                }
                values += StoreGlobal{buf,index*real_pair_size(rows)+transform,reg};
                return values;
            });
            body += If{transform < real_pair_size(rows),output};
            return body;
        }
        const auto slots = transforms_per_block;
        Variable slot{"pre_store_slot","const unsigned int"};
        Variable column{"pre_store_column","const unsigned int"};
        Variable a{"pre_store_a","unsigned int"};
        StatementList body{Declaration{slot,thread_id%slots},
            Declaration{column,real_pair_row_expr(rows,slots,slot,tile_index)},Declaration{a}};
        for(unsigned int i=0;i<(length+threads_per_transform-1)/threads_per_transform;++i)
        {
            body += Assign{a,thread_id/slots+i*threads_per_transform};
            body += If{And{a < length,column < real_pair_size(rows)},
                {StoreGlobal{buf,a*real_pair_size(rows)+column,lds_complex[slot*length+a]}}};
        }
        return body;
    }
};

struct StockhamKernelGenericPairedPostRows : StockhamKernelRC
{
    const size_t columns, rows, m;
    Variable pair_twiddles{"real_pair_twiddles","const scalar_type",true,true};

    explicit StockhamKernelGenericPairedPostRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelRC(specs,false)
        , columns(specs.real_io.columns),rows(specs.real_io.rows),m(specs.real_io.n/2)
    {
        if(real_io.role != RealBlockRole::GenericPairedPostRows || length != rows
           || columns*rows != m || real_io.pitch != rows
           || transforms_per_block < 2 || transforms_per_block%2 != 0
           || half_lds != real_io.ScalarPairIO() || direct_to_from_reg != real_io.DirectPairIO())
            throw std::runtime_error("invalid paired real post geometry");
    }

    Expression get_lds_padding() override { return Literal{0}; }
    std::string load_callback_type_name() const override { return "CallbackType::NONE"; }
    StatementList set_lds_is_real() override
    {
        return {Declaration{lds_is_real,Literal{real_io.ScalarPairIO() ? "true" : "false"}}};
    }
    StatementList set_direct_to_from_registers() override
    {
        if(!real_io.DirectPairIO()) return StockhamKernelRC::set_direct_to_from_registers();
        return {Declaration{direct_load_to_reg,Literal{"true"}},
                Declaration{direct_store_from_reg,Literal{real_io.ScalarPairIO() ? "true" : "false"}},
                Declaration{lds_linear,Literal{"true"}}};
    }
    ArgumentList global_arguments() override
    {
        auto args=StockhamKernelRC::global_arguments();args.append(pair_twiddles);return args;
    }

    StatementList load_from_global(bool registers) override
    {
        const auto slots=transforms_per_block;
        Variable row{"post_load_row","const unsigned int"};
        if(registers)
        {
            StatementList body{Declaration{row,real_pair_row_expr(columns,slots,
                thread_id/threads_per_transform,tile_index_in_plane)}};
            body += clear_initial_registers();
            body += Assign{thread,thread_id%threads_per_transform};
            body += If{row < real_pair_size(columns),first_pass_io([&](Expression index,Variable reg) {
                return StatementList{Assign{reg,LoadGlobal{buf,row*real_pair_size(rows)+index}}};
            })};
            return body;
        }
        Variable slot{"post_load_slot","const unsigned int"};
        Variable column{"post_load_column","unsigned int"};
        StatementList body{Declaration{slot,thread_id%slots},
            Declaration{row,real_pair_row_expr(columns,slots,slot,tile_index_in_plane)},Declaration{column}};
        for(unsigned int i=0;i<(length+threads_per_transform-1)/threads_per_transform;++i)
        {
            body += Assign{column,thread_id/slots+i*threads_per_transform};
            body += If{column < length,
                {If{row < real_pair_size(columns),{Assign{lds_complex[slot*length+column],
                    LoadGlobal{buf,row*real_pair_size(rows)+column}}}},
                 Else{{Assign{lds_complex[slot*length+column],ComplexLiteral{Literal{0},Literal{0}}}}}}};
        }
        return body;
    }

    StatementList store_to_global(bool) override
    {
        const auto slots=transforms_per_block;
        const unsigned int half_row=(length+1)/2;
        const unsigned int count=(half_row+threads_per_transform-1)/threads_per_transform;
        Variable slot{"post_slot","const unsigned int"};
        Variable row{"post_row","const unsigned int"};
        Variable peer{"post_peer","const unsigned int"};
        Variable column{"post_column","unsigned int"},k{"post_k","size_t"};
        Variable p{"post_p","scalar_type"},q{"post_q","scalar_type"};
        Variable own{"post_own","scalar_type"},other{"post_other","scalar_type"};
        Variable saved_p{"post_saved_p","real_type_t<scalar_type>"};
        Variable saved_q{"post_saved_q","real_type_t<scalar_type>"};
        Variable midpoint{"post_midpoint","real_type_t<scalar_type>"};
        saved_p.size=Literal{count};saved_q.size=Literal{count};
        StatementList body{Declaration{slot,thread_id%slots},
            Declaration{row,real_pair_row_expr(columns,slots,slot,tile_index_in_plane)},
            Declaration{peer,CallExpr{"real_pair_peer",{real_pair_size(columns),Literal{slots},slot,row}}},
            Declaration{column},Declaration{k},Declaration{p},Declaration{q},Declaration{own},Declaration{other}};
        const auto peer_column=Parens{(Literal{length}-column
            -Ternary{Expression{row == 0},Expression{Literal{0}},Expression{Literal{1}}})%Literal{length}};
        const auto own_cell=slot*length+column;
        const auto peer_cell=peer*length+peer_column;
        const auto canonical=And{k > 0,2*k < real_pair_size(m)};
        const unsigned int midpoint_slot=rows%2 == 0 ? 0 : slots/2;
        const auto midpoint_cell=Literal{midpoint_slot*length+length/2};
        const auto coordinate = [&](unsigned int i) {
            return StatementList{Assign{column,thread_id/slots+i*threads_per_transform},
                Assign{k,row+real_pair_size(columns)*column}};
        };
        const auto store_field = [&](bool imaginary) {
            StatementList stage{Assign{thread,thread_id%threads_per_transform}};
            stage += last_pass_io([&](Expression index,Variable reg) {
                // Post rows use linear LDS: stride_lds is the row pitch, not the element stride.
                return StatementList{Assign{lds_real[offset_lds+index],
                    imaginary ? reg.y() : reg.x()}};
            });
            return stage;
        };
        if(real_io.ScalarPairIO())
        {
            body += StatementList{Declaration{saved_p},Declaration{saved_q},Declaration{midpoint}};
            body += SyncThreads{};
            body += store_field(false);
            body += SyncThreads{};
            for(unsigned int i=0;i<count;++i)
            {
                body += coordinate(i);
                body += If{And{column < half_row,row < real_pair_size(columns)},
                    {If{Or{k == 0,canonical},{Assign{saved_p[i],lds_real[own_cell]}}},
                     If{canonical,{Assign{saved_q[i],lds_real[peer_cell]}}}}};
            }
            if(m%2 == 0)
                body += If{And{tile_index_in_plane == 0,thread_id == 0},
                    {Assign{midpoint,lds_real[midpoint_cell]}}};
            body += SyncThreads{};
            body += store_field(true);
            body += SyncThreads{};
        }
        for(unsigned int i=0;i<count;++i)
        {
            body += coordinate(i);
            const auto get_p = [&]() -> Expression {
                if(!real_io.ScalarPairIO()) return lds_complex[own_cell];
                return ComplexLiteral{saved_p[i],lds_real[own_cell]};
            };
            const auto get_q = [&]() -> Expression {
                if(!real_io.ScalarPairIO()) return lds_complex[peer_cell];
                return ComplexLiteral{saved_q[i],lds_real[peer_cell]};
            };
            StatementList values;
            values += If{k == 0,{Assign{p,get_p()},Assign{own,ComplexLiteral{p.x()+p.y(),Literal{0}}},
                StoreGlobal{buf,Literal{0},own},Assign{own,ComplexLiteral{p.x()-p.y(),Literal{0}}},
                StoreGlobal{buf,real_pair_size(m),own}}};
            const auto phase=tile_index_in_plane*real_pair_size(slots*half_row)+column*slots+slot;
            values += If{canonical,{Assign{p,get_p()},Assign{q,get_q()},
                Call{"real_pair_post",{scalar_type},{p,q,pair_twiddles[phase],own,other}},
                StoreGlobal{buf,k,own},StoreGlobal{buf,real_pair_size(m)-k,other}}};
            body += If{And{column < half_row,row < real_pair_size(columns)},values};
        }
        if(m%2 == 0)
        {
            Expression value=lds_complex[midpoint_cell];
            if(real_io.ScalarPairIO()) value=ComplexLiteral{midpoint,lds_real[midpoint_cell]};
            body += If{And{tile_index_in_plane == 0,thread_id == 0},
                {Assign{p,value},Assign{own,ComplexLiteral{p.x(),-p.y()}},
                 StoreGlobal{buf,real_pair_size(m/2),own}}};
        }
        return body;
    }
};
