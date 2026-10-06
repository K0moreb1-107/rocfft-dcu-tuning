// EXP-125: local real rows, based on the clean EXP-123 source.
#pragma once

#include <cstddef>
#include <optional>
#include <vector>

enum class RealBlockRole
{
    None,
    HermitianColumns,
    LocalRealRows,
    PairedPostRows,
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
