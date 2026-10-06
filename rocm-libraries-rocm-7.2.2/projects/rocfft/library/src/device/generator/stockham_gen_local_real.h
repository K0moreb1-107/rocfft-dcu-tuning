// EXP-125: keep real I/O rules outside the ordinary Stockham kernels.
#pragma once

#include "stockham_gen_cc.h"
#include "stockham_gen_rc.h"

// This is device source, appended only for the two specialized roles.
// Helpers consume values; all user-buffer access remains represented by
// LoadGlobal/StoreGlobal so out-of-place and callback visitors still apply.
inline std::string local_real_device_helpers()
{
    return R"src(
template <typename T>
__device__ __forceinline__ T local_real_hermitian_value(T value, bool mirror)
{
    if(mirror)
        value.y = -value.y;
    return value;
}

template <typename T>
__device__ __forceinline__ void local_real_pair(T p, T q, T w, T& own, T& other)
{
    const auto ux = p.x + q.x;
    const auto uy = p.y + q.y;
    const auto vx = p.x - q.x;
    const auto vy = p.y - q.y;
    const auto a = vx * w.y - uy * w.x;
    const auto b = uy * w.y + vx * w.x;
    own = T{ux + a, vy + b};
    other = T{ux - a, b - vy};
}
)src";
}

struct LocalRealFoldVisitor : BaseVisitor
{
    const RealBlockIO io;
    Variable          raw{"local_real_raw", "scalar_type"};

    explicit LocalRealFoldVisitor(const RealBlockIO& io) : io(io) {}

    Expression folded(const Expression& k) const
    {
        return Ternary{Expression{k > Literal{static_cast<unsigned int>(io.n / 2)}},
                       Expression{Literal{static_cast<unsigned int>(io.n)} - k}, Expression{k}};
    }

    StatementList visit_Assign(const Assign& x) override
    {
        Expression k = Literal{0}, load = Literal{0};
        if(const auto* ordinary = std::get_if<LoadGlobal>(&x.rhs))
        {
            k = ordinary->args[1];
            load = LoadGlobal{ordinary->args[0], folded(k)};
        }
        else if(const auto* intrinsic = std::get_if<IntrinsicLoad>(&x.rhs))
        {
            k = intrinsic->args[1] + intrinsic->args[2];
            load = IntrinsicLoad{{intrinsic->args[0], folded(k), Literal{0},
                                  intrinsic->args[3]}};
        }
        else
            return BaseVisitor::visit_Assign(x);

        // LoadGlobal sets the input context in the out-of-place visitor before
        // it visits the mirror predicate. Do not hide the load in a raw string.
        return {Assign{raw, load},
                Assign{x.lhs,
                       CallExpr{"local_real_hermitian_value", {scalar_type},
                                {raw, k > Literal{static_cast<unsigned int>(io.n / 2)}}}, x.oper}};
    }

    Variable scalar_type{"scalar_type", "typename"};
};

struct StockhamKernelHermitianColumns : StockhamKernelCC
{
    const RealBlockIO io;

    explicit StockhamKernelHermitianColumns(const StockhamGeneratorSpecs& specs,
                                            bool large_batch_count)
        : StockhamKernelCC(specs, large_batch_count, false), io(specs.real_io)
    {
    }

    StatementList load_from_global(bool registers) override
    {
        LocalRealFoldVisitor visitor(io);
        StatementList body{Declaration{visitor.raw}};
        body += visitor.visit_StatementList(StockhamKernelCC::load_from_global(registers));
        return body;
    }
};

struct StockhamKernelLocalRealRows : StockhamKernelRC
{
    const RealBlockIO io;
    Variable pre_twiddles{"local_real_twiddles", "const scalar_type", true, true};

    explicit StockhamKernelLocalRealRows(const StockhamGeneratorSpecs& specs)
        : StockhamKernelRC(specs, false), io(specs.real_io)
    {
        const auto first = factors.front();
        const auto k = length / first;
        const auto lanes = std::min(threads_per_transform, k);
        if((length != 256 && length != 512) || k != 64 || k % lanes != 0
           || workgroup_size % threads_per_transform != 0
           || transforms_per_block % 2 != 0)
            throw std::runtime_error("unsupported local real register map");
    }

    ArgumentList global_arguments() override
    {
        auto args = StockhamKernelRC::global_arguments();
        args.append(pre_twiddles);
        return args;
    }

    bool use_static_initial_reg_load() const override { return true; }

    StatementList set_direct_to_from_registers() override
    {
        // Both entry variants fully initialize R. The LDS variant also protects
        // its final reads before the core reuses LDS, including scalar LDS.
        return {Declaration{direct_load_to_reg, Literal{"true"}},
                Declaration{direct_store_from_reg, Literal{"false"}},
                Declaration{lds_linear, Literal{"true"}}};
    }

    StatementList load_from_global(bool) override
    {
        const auto f = factors.front();
        const auto k = length / f;
        const auto lanes = std::min(threads_per_transform, k);
        const auto butterflies = k / lanes;
        const bool registers = io.load == RealBlockLoad::Registers;
        Variable lane{"local_lane", "const unsigned int"};
        Variable row{"local_row", "const unsigned int"};
        Variable j{"local_j", "unsigned int"};
        Variable p{"local_p", "scalar_type"}, q{"local_q", "scalar_type"};
        Variable own{"local_own", "scalar_type"}, other{"local_other", "scalar_type"};
        Variable exchanged{"local_exchanged", "scalar_type"};
        StatementList stmts{Declaration{lane, thread_id % threads_per_transform},
                            Declaration{row, thread_id / threads_per_transform}};
        StatementList active{Declaration{j}, Declaration{p}, Declaration{q},
                             Declaration{own}, Declaration{other}};
        if(registers)
            active += Declaration{exchanged};

        const auto base = offset_in + row * stride_load_in;
        for(unsigned int h = 0; h < butterflies; ++h)
        {
            for(unsigned int w = 0; w < f / 2; ++w)
            {
                active += Assign{j, lane + h * threads_per_transform + w * k};
                active += Assign{p, LoadGlobal{buf, base + j}};
                active += Assign{q, LoadGlobal{buf, base + length - j}};
                active += If{j == 0,
                             {Assign{own, ComplexLiteral{p.x() + q.x(), p.x() - q.x()}},
                              Assign{other, ComplexLiteral{0, 0}}}};
                active += Else{{Call{"local_real_pair", {scalar_type},
                                      {p, q, pre_twiddles[j], own, other}}}};

                if(!registers)
                {
                    active += Assign{lds_complex[offset_lds + j], own};
                    active += If{j != 0,
                                 {Assign{lds_complex[offset_lds + length - j], other}}};
                    continue;
                }

                active += Assign{R[h * f + w], own};
                const auto source = Parens{lanes - lane} % lanes;
                active += Assign{exchanged.x(), CallExpr{"__shfl", {other.x(), source, lanes}}};
                active += Assign{exchanged.y(), CallExpr{"__shfl", {other.y(), source, lanes}}};
                active += If{lane != 0,
                             {Assign{R[(butterflies - 1 - h) * f + f - 1 - w], exchanged}}};
                if(h == 0 && w > 0)
                    active += Else{{Assign{R[f - w], other}}};
                else if(h > 0)
                    active += Else{{Assign{R[(butterflies - h) * f + f - 1 - w], other}}};
            }
        }

        StatementList self{Assign{p, LoadGlobal{buf, base + length / 2}}};
        self += Assign{registers ? R[f / 2] : lds_complex[offset_lds + length / 2],
                       ComplexLiteral{2 * p.x(), -2 * p.y()}};
        active += If{lane == 0, self};
        stmts += If{lane < lanes, active};

        if(!registers)
        {
            stmts += SyncThreads{};
            StatementList reload;
            for(unsigned int h = 0; h < butterflies; ++h)
                for(unsigned int w = 0; w < f; ++w)
                    reload += Assign{R[h * f + w],
                                     lds_complex[offset_lds + lane
                                                 + h * threads_per_transform + w * k]};
            stmts += If{lane < lanes, reload};
            // Scalar-LDS core exchanges have no first-store barrier.
            stmts += SyncThreads{};
        }
        return stmts;
    }

    StatementList store_to_global(bool) override
    {
        const auto rows = transforms_per_block;
        const auto steps = length * rows / workgroup_size;
        Variable u{"local_output_lane", "const unsigned int"};
        Variable parity{"local_output_parity", "const unsigned int"};
        Variable pair{"local_output_pair", "const unsigned int"};
        Variable even{"local_output_even", "const unsigned int"};
        Variable p{"local_output_p", "unsigned int"};
        Variable value{"local_output_value", "scalar_type"};
        StatementList stmts{Declaration{u, thread_id % rows},
                            Declaration{parity, u / (rows / 2)},
                            Declaration{pair, u % (rows / 2)},
                            Declaration{even, 2 * pair}, Declaration{p}, Declaration{value}};
        for(unsigned int i = 0; i < steps; ++i)
        {
            stmts += Assign{p, thread_id / rows + i * workgroup_size / rows};
            const auto scalar = 2 * Parens{even * length + p} + parity;
            stmts += Assign{value, ComplexLiteral{lds_real[scalar], lds_real[scalar + 2 * length]}};
            // Absolute complex index of two adjacent real output elements.
            // Eligibility guarantees batch=1 and zero user offsets.
            stmts += StoreGlobal{buf,
                                  tile_index_in_plane * (rows / 2) + pair
                                      + static_cast<unsigned int>(io.columns) * p
                                      + parity * static_cast<unsigned int>(io.columns / 2), value};
        }
        return stmts;
    }
};
