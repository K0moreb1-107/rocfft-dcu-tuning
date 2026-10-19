#include "real_block_io.h"
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

int main(int argc, char** argv)
{
    if(argc != 3) return 2;
    std::ifstream input(argv[1]);
    const int policy = std::stoi(argv[2]);
    std::string line;
    size_t count = 0;
    while(std::getline(input, line))
    {
        std::istringstream in(line);
        std::string id, factors_text;
        size_t n, c, q, p, requested, base, steps, expected_slots;
        bool pre;
        if(!(in >> id >> n >> pre >> c >> q >> p >> requested >> base >> steps >> factors_text >> expected_slots)) return 3;
        std::vector<unsigned int> factors;
        std::istringstream parts(factors_text);
        std::string value;
        while(std::getline(parts, value, ',')) factors.push_back(std::stoul(value));
        auto geometry = RealBlockIO::ForDecomposition(n, c, q);
        if(!geometry) return 4;
        auto io = *geometry;
        const size_t extra = pre && base < 8 ? 3 * (size_t(1) << base) * 16 : 0;
        const size_t length = pre ? c : q;
        size_t slots;
#ifdef RETAINED_HEADER
        if(policy != 0) return 5;
        slots = std::min(std::max<size_t>(2, requested), std::min(1024 / p, (65536 - extra) / 16 / length)) & ~size_t(1);
        if(slots < 2) return 6;
        io.SelectPairExchange(pre, factors, p, slots, base, steps, false);
#else
        const auto selected = io.ConfigurePair(pre, factors, p, requested, base, steps,
            {1024, 65536, extra, 16}, static_cast<RealPairPolicy>(policy), false);
        if(!selected) return 7;
        slots = *selected;
        if(policy != 0 && (!io.DirectPairIO() || io.ScalarPairIO() != (policy == 2))) return 8;
#endif
        if(slots != expected_slots) return 9;
        std::cout << id << ' ' << slots << ' ' << io.ExchangeName() << ' '
                  << int(io.final_phase) << ' ' << int(io.load) << ' '
                  << length * slots * (io.ScalarPairIO() ? 8 : 16) + extra << '\n';
        ++count;
    }
#ifndef RETAINED_HEADER
    auto small = *RealBlockIO::ForDecomposition(131072, 128, 512);
    const std::vector<unsigned int> factors{8, 16};
    for(auto mode : {RealPairPolicy::Retained, RealPairPolicy::DirectComplex, RealPairPolicy::DirectScalar})
    {
        auto g = small;
        auto result = g.ConfigurePair(true, factors, 16, 4, 8, 2, {1024, 2048, 0, 16}, mode, false);
        if(mode == RealPairPolicy::Retained ? bool(result) : !result || *result != 2 || !g.ScalarPairIO()) return 10;
        g = small;
        result = g.ConfigurePair(true, factors, 16, 4, 8, 2, {1024, 5000, 0, 16}, mode, false);
        if(!result || *result != 2) return 11; // Half storage cannot enlarge slots.
        if(g.ConfigurePair(true, factors, 0, 4, 8, 2, {1024, 65536, 0, 16}, mode, false)) return 12;
        if(g.ConfigurePair(true, factors, 16, 0, 8, 2, {1024, 65536, 0, 16}, mode, false)) return 13;
        if(g.ConfigurePair(true, factors, 16, 4, 8, 2, {1024, 65536, 65536, 16}, mode, false)) return 14;
        if(g.ConfigurePair(true, std::vector<unsigned int>{0,128}, 16, 4, 8, 2,
                           {1024, 65536, 0, 16}, mode, false)) return 15;
        auto overflow = *RealBlockIO::ForDecomposition(262144, 128, 1024);
        if(overflow.ConfigurePair(true, factors, 16, 4, 8, 2, {1024,65536,0,16}, mode, false)) return 16;
    }
#endif
    return count ? 0 : 17;
}
