// Shared address mapping for the EXP-126 data and phase-table generators.
#pragma once

#include <string>

inline std::string real_pair_layout_device_helpers()
{
    return R"src(
__device__ __forceinline__ size_t real_pair_row(
    size_t axis, unsigned int slots, unsigned int slot, size_t block)
{
    const unsigned int half = slots / 2;
    const size_t p = block * half + slot % half;
    if(p >= (axis + 1) / 2)
        return axis;
    if(slot < half)
        return p;
    if(p == 0)
        return axis % 2 == 0 ? axis / 2 : axis;
    return axis - p;
}
__device__ __forceinline__ unsigned int real_pair_peer(
    size_t axis, unsigned int slots, unsigned int slot, size_t row)
{
    if(row == 0 || (axis % 2 == 0 && row == axis / 2))
        return slot;
    return slot < slots / 2 ? slot + slots / 2 : slot - slots / 2;
}
template <typename T>
__device__ __forceinline__ void real_pair_pre(T p, T q, T w, T& own, T& other)
{
    const auto ux = p.x + q.x, uy = p.y + q.y;
    const auto vx = p.x - q.x, vy = p.y - q.y;
    const auto a = vx * w.y - uy * w.x, b = uy * w.y + vx * w.x;
    own = T{ux + a, vy + b};
    other = T{ux - a, b - vy};
}
template <typename T>
__device__ __forceinline__ void real_pair_post(T p, T q, T w, T& own, T& other)
{
    const auto ux = 0.5 * (p.x + q.x), uy = 0.5 * (p.y + q.y);
    const auto vx = 0.5 * (p.x - q.x), vy = 0.5 * (p.y - q.y);
    const auto a = vx * w.y + uy * w.x, b = uy * w.y - vx * w.x;
    own = T{ux + a, vy + b};
    other = T{ux - a, b - vy};
}
)src";
}
