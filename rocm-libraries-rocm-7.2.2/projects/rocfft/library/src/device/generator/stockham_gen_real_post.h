// EXP-125: pair ordinary half-length FFT rows in the final RC workgroup.
#pragma once

#include "stockham_gen_rc.h"

// Keep address permutation separate from the numerical post-processing.
static std::string real_post_device_helpers(const RealBlockIO& io, unsigned int rows_per_block)
{
    const auto half = rows_per_block / 2;
    return "__device__ __forceinline__ unsigned int real_post_row(unsigned int slot, unsigned int block) {\n"
           " const unsigned int s = block * " + std::to_string(half) + " + slot % " + std::to_string(half) + ";\n"
           " return slot < " + std::to_string(half) + " ? s : (s == 0 ? " + std::to_string(io.columns / 2) + " : " + std::to_string(io.columns) + " - s);\n}\n"
           "__device__ __forceinline__ unsigned int real_post_input(unsigned int k) {\n"
           " const unsigned int row = k / " + std::to_string(io.rows) + ";\n"
           " return real_post_row(row % " + std::to_string(rows_per_block) + ", row / " + std::to_string(rows_per_block) + ") * " + std::to_string(io.rows) + " + k % " + std::to_string(io.rows) + ";\n}\n"
           R"src(
template <typename T>
__device__ __forceinline__ void real_post_pair(T p, T q, T w, T& own, T& other)
{
    const auto ux = 0.5 * (p.x + q.x), uy = 0.5 * (p.y + q.y);
    const auto vx = 0.5 * (p.x - q.x), vy = 0.5 * (p.y - q.y);
    const auto a = vx * w.y + uy * w.x, b = uy * w.y - vx * w.x;
    own   = T{ux + a, vy + b};
    other = T{ux - a, b - vy};
}
)src";
}

struct RealPostLoadVisitor : BaseVisitor
{
    Expression visit_LoadGlobal(const LoadGlobal& x) override
    {
        return LoadGlobal{x.args[0], CallExpr{"real_post_input", {x.args[1]}}};
    }
};

struct StockhamKernelPairedPostRows : StockhamKernelRC
{
    const unsigned int columns, rows, rows_per_block;
    Variable post_twiddles{"real_post_twiddles", "const scalar_type", true, true};

    explicit StockhamKernelPairedPostRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelRC(specs, false)
        , columns(specs.real_io.columns)
        , rows(specs.real_io.rows)
        , rows_per_block(transforms_per_block)
    {
        if(specs.real_io.role != RealBlockRole::PairedPostRows || length != rows
           || specs.real_io.n != 2 * columns * rows || specs.real_io.pitch != rows
           || (rows != 256 && rows != 512) || rows_per_block % 2 != 0
           || columns % rows_per_block != 0 || workgroup_size % (2 * rows_per_block) != 0)
            throw std::runtime_error("unsupported paired real post-processing geometry");
    }

    ArgumentList global_arguments() override
    {
        auto args = StockhamKernelRC::global_arguments();
        args.append(post_twiddles);
        return args;
    }

    StatementList set_direct_to_from_registers() override
    {
        // Both entry paths share the existing full complex output LDS.
        return {Declaration{direct_load_to_reg, Literal{static_initial_reg_load ? "true" : "false"}},
                Declaration{direct_store_from_reg, Literal{"false"}},
                Declaration{lds_linear, Literal{"true"}}};
    }

    StatementList load_from_global(bool registers) override
    {
        RealPostLoadVisitor visitor;
        return visitor.visit_StatementList(StockhamKernelRC::load_from_global(registers));
    }

    StatementList store_to_global(bool) override
    {
        const auto half = rows_per_block / 2;
        const auto m = columns * rows;
        Variable slot{"post_slot", "const unsigned int"};
        Variable row{"post_row", "const unsigned int"};
        Variable peer{"post_peer", "const unsigned int"};
        Variable column{"post_column", "unsigned int"}, k{"post_index", "unsigned int"};
        Variable lhs{"post_lhs", "scalar_type"}, rhs{"post_rhs", "scalar_type"};
        Variable own{"post_own", "scalar_type"}, other{"post_other", "scalar_type"};
        StatementList stmts{
            Declaration{slot, thread_id % rows_per_block},
            Declaration{row, CallExpr{"real_post_row", {slot, tile_index_in_plane}}},
            Declaration{peer, Ternary{Expression{Or{row == 0, row == columns / 2}}, Expression{slot},
                                      Expression{Ternary{Expression{slot < half}, Expression{slot + half}, Expression{slot - half}}}}},
            Declaration{column}, Declaration{k}, Declaration{lhs}, Declaration{rhs},
            Declaration{own}, Declaration{other}};

        // Each row owns its lower half. The mirrored upper half is consumed once.
        for(unsigned int i = 0; i < rows * rows_per_block / (2 * workgroup_size); ++i)
        {
            stmts += Assign{column, thread_id / rows_per_block + i * workgroup_size / rows_per_block};
            stmts += Assign{k, row + columns * column};
            StatementList endpoints{
                Assign{lhs, lds_complex[0]},
                StoreGlobal{buf, Literal{0}, ComplexLiteral{lhs.x() + lhs.y(), Literal{0}}},
                StoreGlobal{buf, Literal{m}, ComplexLiteral{lhs.x() - lhs.y(), Literal{0}}},
                Assign{rhs, lds_complex[rows / 2]},
                StoreGlobal{buf, Literal{m / 2}, ComplexLiteral{rhs.x(), -rhs.y()}}};
            StatementList pair{
                Assign{lhs, lds_complex[slot * rows + column]},
                Assign{rhs, lds_complex[peer * rows + rows - column
                                       - Ternary{Expression{row == 0}, Expression{Literal{0}}, Expression{Literal{1}}}]},
                Call{"real_post_pair", {scalar_type}, {lhs, rhs, post_twiddles[k], own, other}},
                StoreGlobal{buf, k, own},
                StoreGlobal{buf, m - k, other}};
            // Test before forming the zero-row mirror address (which would be Q).
            stmts += If{And{row == 0, column == 0}, endpoints};
            stmts += Else{pair};
        }
        return stmts;
    }
};
