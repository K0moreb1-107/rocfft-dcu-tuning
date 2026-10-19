// EXP-125: local real rows, based on the clean EXP-123 source.
#pragma once

#include <algorithm>
#include <cstddef>
#include <initializer_list>
#include <optional>
#include <limits>
#include <stdexcept>
#include <vector>

enum class RealBlockRole
{
    None,
    HermitianColumns,
    LocalRealRows,
    PairedPostRows,
    PairedPreColumns,
    GenericPairedPostRows,
};

enum class RealBlockLoad
{
    Registers,
    LDS,
};

// Generic boundary modes are independent of the legacy load-path override.
enum class RealPairExchange { StagedComplex, DirectComplex, DirectScalar };
enum class RealPairFinalPhase { InTransform, AtStore };

// A build selects a complete generic backend, independently of FFT lengths.
// Retained preserves the accepted policy for controlled comparisons.
enum class RealPairPolicy { Retained, DirectComplex, DirectScalar };

struct RealPairResources
{
    size_t max_threads, shared_bytes, extra_shared_bytes, complex_bytes;
};

// One geometry shared by planning, physical buffer views and code generation.
// N = 2 * columns * rows; pitch counts complex elements.
struct RealBlockIO
{
    RealBlockRole role = RealBlockRole::None;
    RealBlockLoad load = RealBlockLoad::Registers;
    size_t        n = 0, columns = 0, rows = 0, pitch = 0;

    RealPairExchange exchange = RealPairExchange::StagedComplex;
    RealPairFinalPhase final_phase = RealPairFinalPhase::InTransform;

    bool IsGenericPair() const
    {
        return role == RealBlockRole::PairedPreColumns
               || role == RealBlockRole::GenericPairedPostRows;
    }
    bool DirectPairIO() const { return exchange != RealPairExchange::StagedComplex; }
    bool ScalarPairIO() const { return exchange == RealPairExchange::DirectScalar; }
    const char* ExchangeName() const
    {
        switch(exchange)
        {
        case RealPairExchange::StagedComplex: return "staged_complex";
        case RealPairExchange::DirectComplex: return "direct_complex";
        case RealPairExchange::DirectScalar: return "direct_scalar";
        }
        throw std::runtime_error("unknown real pair exchange");
    }
    // Keep the accepted selection only as the reference policy. Both direct
    // policies cover every legal generic CC geometry, with the same maps.
    template<class Factors>
    void SelectPairExchange(bool pre, const Factors& factors, size_t p, size_t slots,
                            size_t base, size_t steps, bool scalar_capacity,
                            RealPairPolicy policy = RealPairPolicy::Retained)
    {
        exchange = RealPairExchange::StagedComplex;
        final_phase = RealPairFinalPhase::InTransform;
        const auto matches = [&](std::initializer_list<size_t> f, size_t threads, size_t t) {
            return p == threads && slots == t && factors.size() == f.size()
                   && std::equal(f.begin(), f.end(), factors.begin());
        };
        bool selected = false;
        if(pre)
        {
            const bool base8 = base == 8 && (steps == 2 || steps == 3);
            selected = base8 && (matches({4,10,4},16,12) || matches({13,16},16,8)
                || matches({6,7,8},56,6) || matches({8,8,8},64,4)
                || matches({8,8,4,4},64,4));
            if((base == 6 || base == 8) && steps == 3 && matches({17,17},17,6))
            {
                selected = true;
                final_phase = RealPairFinalPhase::AtStore;
            }
            if(selected && scalar_capacity && matches({8,8,4,4},64,4))
                exchange = RealPairExchange::DirectScalar;
        }
        else if(base == 0 && steps == 0)
        {
            selected = matches({8,8,8},128,4) || matches({11,11,11},121,2);
            if(selected && scalar_capacity && matches({11,11,11},121,2))
                exchange = RealPairExchange::DirectScalar;
        }
        if(selected && !ScalarPairIO()) exchange = RealPairExchange::DirectComplex;
        if(policy != RealPairPolicy::Retained)
            exchange = policy == RealPairPolicy::DirectScalar
                           ? RealPairExchange::DirectScalar : RealPairExchange::DirectComplex;
        load = DirectPairIO() ? RealBlockLoad::Registers : RealBlockLoad::LDS;
    }

    // Preserve the full-storage slot count when it fits. Scalar exchange must
    // not silently enlarge the workgroup and confound the backend comparison.
    // It may admit a two-slot pair that full complex storage cannot contain.
    template<class Factors>
    std::optional<size_t> ConfigurePair(bool pre, const Factors& factors, size_t p,
                                       size_t requested_slots, size_t base, size_t steps,
                                       const RealPairResources& limits, RealPairPolicy policy,
                                       bool retained_scalar_capacity)
    {
        const size_t length = pre ? columns : rows;
        if(p == 0 || requested_slots == 0 || length == 0 || factors.empty()
           || limits.complex_bytes < 2 || limits.complex_bytes % 2 != 0
           || limits.extra_shared_bytes >= limits.shared_bytes)
            return std::nullopt;
        size_t factor_product = 1;
        for(auto factor : factors)
        {
            if(factor < 2 || factor_product > length / factor)
                return std::nullopt;
            factor_product *= factor;
        }
        if(factor_product != length)
            return std::nullopt;
        if(pre && (base == 0 || base >= std::numeric_limits<size_t>::digits
                   || steps < 2 || steps > 3
                   || (base * steps < std::numeric_limits<size_t>::digits
                       && n / 2 > (size_t(1) << (base * steps)))))
            return std::nullopt;

        const size_t available = limits.shared_bytes - limits.extra_shared_bytes;
        const auto slots_for = [&](size_t element_bytes) {
            return std::min<size_t>(std::max<size_t>(2, requested_slots),
                       std::min(limits.max_threads / p, available / element_bytes / length))
                   & ~size_t(1);
        };
        size_t slots = slots_for(limits.complex_bytes);
        auto effective_policy = policy;
        if(slots < 2 && policy != RealPairPolicy::Retained)
        {
            slots = slots_for(limits.complex_bytes / 2);
            effective_policy = RealPairPolicy::DirectScalar;
        }
        if(slots < 2 || PairBlocks(pre ? rows : columns, slots)
                           > std::numeric_limits<unsigned int>::max())
            return std::nullopt;
        SelectPairExchange(pre, factors, p, slots, base, steps,
                           retained_scalar_capacity, effective_policy);
        return slots;
    }

    static std::optional<RealBlockIO> ForDecomposition(size_t n, size_t columns, size_t rows)
    {
        if(n <= 65536 || n % 2 != 0 || columns == 0 || rows == 0
           || columns > std::numeric_limits<unsigned int>::max()
           || rows > std::numeric_limits<unsigned int>::max()
           || n / 2 / columns != rows || n / 2 % columns != 0)
            return std::nullopt;
        return RealBlockIO{RealBlockRole::None, RealBlockLoad::LDS, n, columns, rows, rows};
    }

    static size_t PairBlocks(size_t axis, size_t slots)
    {
        if(axis == 0 || slots < 2 || slots % 2 != 0)
            throw std::runtime_error("invalid real pair block geometry");
        const size_t pairs = axis / 2 + axis % 2;
        return pairs / (slots / 2) + (pairs % (slots / 2) != 0);
    }

    static size_t PairTableSize(size_t n, size_t rows, size_t slots)
    {
        if(n == 0 || n % 2 != 0 || rows == 0 || (n / 2) % rows != 0)
            throw std::runtime_error("invalid real pair table geometry");
        const size_t blocks = PairBlocks(n / 2 / rows, slots);
        const size_t half_row = rows / 2 + rows % 2;
        if(blocks > std::numeric_limits<size_t>::max() / slots
           || blocks * slots > std::numeric_limits<size_t>::max() / half_row)
            throw std::runtime_error("real pair table length overflows");
        return blocks * slots * half_row;
    }

    static size_t PostTableSize(size_t n, size_t rows, size_t slots)
    {
        return PairTableSize(n, rows, slots);
    }

    static std::optional<RealBlockIO> ForLength(size_t n)
    {
        size_t columns = 0, rows = 0;
        switch(n)
        {
        case 65536:   columns = 128;  rows = 256; break;
        case 131072:  columns = 256;  rows = 256; break;
        case 262144:  columns = 256;  rows = 512; break;
        case 524288:  columns = 512;  rows = 512; break;
        case 1048576: columns = 1024; rows = 512; break;
        default: return std::nullopt;
        }
        return RealBlockIO{RealBlockRole::None, RealBlockLoad::Registers,
                           n, columns, rows, rows + 8};
    }
};

struct RealBufferView
{
    std::vector<size_t> length, stride;
    size_t             dist;
};
