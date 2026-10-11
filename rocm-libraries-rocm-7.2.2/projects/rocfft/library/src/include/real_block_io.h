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
    // Select complete verified kernel families, never individual FFT sizes.
    template<class Factors>
    void SelectPairExchange(bool pre, const Factors& factors, size_t p, size_t slots,
                            size_t base, size_t steps, bool scalar_capacity)
    {
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
        load = DirectPairIO() ? RealBlockLoad::Registers : RealBlockLoad::LDS;
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
