#pragma once

#include <cstddef>
#include <string>

enum class RealBoundaryDirection { None, Pre, Post };
enum class RealBoundaryContainer { None, Bluestein, Transpose, Rows };

// Complete real-transform boundary, independent of a local FFT kernel's shape.
// Only final boundary nodes own device resources; this descriptor owns none.
struct RealBoundaryIO
{
    RealBoundaryDirection direction = RealBoundaryDirection::None;
    RealBoundaryContainer container = RealBoundaryContainer::None;
    size_t n = 0;
    static constexpr unsigned int layout_version = 1;

    bool Active() const { return direction != RealBoundaryDirection::None; }
    bool Pre() const { return direction == RealBoundaryDirection::Pre; }
    bool Post() const { return direction == RealBoundaryDirection::Post; }
    size_t HalfLength() const { return n / 2; }
    size_t PairTasks() const { return HalfLength() / 2 + 1; }
    size_t TableLength() const { return n / 4 + (n % 4 != 0); }

    bool Valid() const
    {
        return Active() && container != RealBoundaryContainer::None && n >= 2 && n % 2 == 0;
    }
    std::string NameSuffix() const
    {
        if(!Active()) return {};
        const char* name = container == RealBoundaryContainer::Bluestein ? "blue"
                         : container == RealBoundaryContainer::Transpose ? "transpose" : "rows";
        return std::string("_real_") + (Pre() ? "pre_" : "post_") + name
               + "_v" + std::to_string(layout_version);
    }
};
