// EXP-125: local real rows, based on the clean EXP-123 source.
#pragma once

#include <cstddef>
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

// One geometry shared by planning, physical buffer views and code generation.
// N = 2 * columns * rows; pitch counts complex elements.
struct RealBlockIO
{
    RealBlockRole role = RealBlockRole::None;
    RealBlockLoad load = RealBlockLoad::Registers;
    size_t        n = 0, columns = 0, rows = 0, pitch = 0;

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

    static size_t PostTableSize(size_t n, size_t rows, size_t slots)
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
