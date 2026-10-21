// EXP-125: local real rows, based on the clean EXP-123 source.
#pragma once

#include <cstddef>
#include <algorithm>
#include <optional>
#include <vector>

enum class RealBlockRole
{
    None,
    HermitianColumns,
    LocalRealRows,
    PairedPostRows,
    FoldedPackedColumns,
    PackedInverseRows,
    LocalPostColumns,
    FoldedSpectrumRows,
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
    size_t n = 0, columns = 0, rows = 0, pitch = 0;

    bool IsCCLocal() const
    {
        return role == RealBlockRole::FoldedPackedColumns
            || role == RealBlockRole::PackedInverseRows || role == RealBlockRole::LocalPostColumns
            || role == RealBlockRole::FoldedSpectrumRows;
    }
    bool IsInputBoundary() const
    {
        return role == RealBlockRole::FoldedPackedColumns
            || role == RealBlockRole::LocalPostColumns;
    }
    bool IsOutputBoundary() const
    {
        return role == RealBlockRole::PackedInverseRows
            || role == RealBlockRole::FoldedSpectrumRows;
    }
    bool HasBoundaryLargePhase() const { return role == RealBlockRole::FoldedSpectrumRows; }
    size_t SmallPhaseLength() const
    {
        if (role == RealBlockRole::LocalPostColumns)
            return columns;
        if (role == RealBlockRole::PackedInverseRows || role == RealBlockRole::FoldedSpectrumRows)
            return rows;
        return 0;
    }
    // The native first-pass map covers lane+h*threads+w*(length/first_factor).
    // pass_io guards its final partial group; no power-of-two condition is needed.
    static bool CanRegisterInput(size_t length, const std::vector<unsigned int>& factors,
        size_t threads, size_t workgroup)
    {
        if (!length || factors.empty() || !threads || !workgroup || workgroup % threads)
            return false;
        size_t product = 1;
        for (const auto factor : factors)
        {
            if (!factor || product > length / factor)
                return false;
            product *= factor;
        }
        return product == length;
    }
    static bool CanRegisterPre(size_t length, size_t first_factor, size_t threads)
    {
        if (!first_factor || !threads)
            return false;
        const auto k = length / first_factor, lanes = std::min(k, threads);
        return first_factor % 2 == 0 && lanes && lanes <= 64 && (lanes & (lanes - 1)) == 0
            && k % lanes == 0 && threads % lanes == 0;
    }

    static std::optional<RealBlockIO> ForLength(size_t n)
    {
        size_t columns = 0, rows = 0;
        switch (n)
        {
        case 65536:
            columns = 128;
            rows = 256;
            break;
        case 131072:
            columns = 256;
            rows = 256;
            break;
        case 262144:
            columns = 256;
            rows = 512;
            break;
        case 524288:
            columns = 512;
            rows = 512;
            break;
        case 1048576:
            columns = 1024;
            rows = 512;
            break;
        default:
            return std::nullopt;
        }
        return RealBlockIO { RealBlockRole::None, RealBlockLoad::Registers, n, columns, rows,
            rows + 8 };
    }
};

struct RealBufferView
{
    std::vector<size_t> length, stride;
    size_t dist;
};
