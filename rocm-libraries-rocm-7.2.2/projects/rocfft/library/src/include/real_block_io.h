#pragma once

#include <algorithm>
#include <cstddef>
#include <vector>

enum class RealBlockRole
{
    None                = 0,
    FoldedPackedColumns = 4,
    PackedInverseRows   = 5,
    LocalPostColumns    = 6,
    FoldedSpectrumRows  = 7,
};

enum class RealBlockLoad
{
    Registers,
    LDS,
};

// One geometry shared by planning, physical buffer views and code generation.
// N = 2 * columns * rows.
struct RealBlockIO
{
    RealBlockRole role    = RealBlockRole::None;
    RealBlockLoad load    = RealBlockLoad::Registers;
    size_t        n       = 0;
    size_t        columns = 0;
    size_t        rows    = 0;

    bool IsCCLocal() const
    {
        return role != RealBlockRole::None;
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
    bool HasBoundaryLargePhase() const
    {
        return role == RealBlockRole::FoldedSpectrumRows;
    }
    size_t SmallPhaseLength() const
    {
        if(role == RealBlockRole::LocalPostColumns)
            return columns;
        if(role == RealBlockRole::PackedInverseRows || role == RealBlockRole::FoldedSpectrumRows)
            return rows;
        return 0;
    }
    // The native first-pass map covers lane+h*threads+w*(length/first_factor).
    // pass_io guards its final partial group; no power-of-two condition is needed.
    static bool CanRegisterInput(size_t threads, size_t workgroup)
    {
        return threads && workgroup && workgroup % threads == 0;
    }
    static bool CanRegisterPre(size_t length, size_t first_factor, size_t threads)
    {
        if(!first_factor || !threads)
            return false;
        const auto k = length / first_factor, lanes = std::min(k, threads);
        return first_factor % 2 == 0 && lanes && lanes <= 64 && (lanes & (lanes - 1)) == 0
               && k % lanes == 0 && threads % lanes == 0;
    }
};

struct RealBufferView
{
    std::vector<size_t> length, stride;
    size_t              dist;
};
