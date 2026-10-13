#include "rtc_stockham_gen.h"
#include "device/generator/generator.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

void write_standalone_test_harness(const Function&, const std::string&) {}

int main(int argc, char** argv)
{
    if(argc != 2) return 2;
    struct Config { std::vector<unsigned int> factors; unsigned int wgs, tpt; };
    const Config configs[] = {{{4,4,4},128,16}, {{8,4,4},128,16},
                              {{4,4,4,4},256,32}, {{8,8,8},512,128},
                              {{8,8,4,4},256,128}};
    unsigned int count = 0;
    for(const auto& config : configs)
        for(bool linear : {false,true})
            for(auto blue : {BFT_NONE,BFT_FWD_CHIRP,BFT_FWD_CHIRP_MUL,BFT_INV_CHIRP_MUL})
                for(bool planar : {false,true})
                {
                    StockhamGeneratorSpecs spec(config.factors, {}, {rocfft_precision_double},
                        config.wgs, "CS_KERNEL_STOCKHAM_BLOCK_RC");
                    spec.threads_per_transform = config.tpt;
                    spec.half_lds = true;
                    spec.direct_to_from_reg = true;
                    spec.static_initial_reg_load = true;
                    spec.static_initial_reg_load_linear = linear;
                    const auto array = planar ? rocfft_array_type_complex_planar
                                              : rocfft_array_type_complex_interleaved;
                    const auto direction = blue == BFT_INV_CHIRP_MUL ? 1 : -1;
                    const auto mode = linear ? DirectRegType::FORCE_OFF_OR_NOT_SUPPORT
                                             : DirectRegType::TRY_ENABLE_IF_SUPPORT;
                    const auto name = "rc_index_check_" + std::to_string(count);
                    const auto src = stockham_rtc(spec, spec, {}, nullptr, name,
                        CS_KERNEL_STOCKHAM_BLOCK_RC, direction, rocfft_precision_double,
                        rocfft_placement_notinplace, array, array, true, 8, 0, false,
                        mode, IntrinsicAccessType::DISABLE_BOTH, TILE_ALIGNED,
                        CallbackType::NONE, blue, PartialPassType::PPT_NONE, std::nullopt, std::nullopt);
                    const auto path = std::string(argv[1]) + "/" + name + ".cpp";
                    std::ofstream out(path); out << src;
                    if(!out) throw std::runtime_error("source write failed");
                    std::cout << count++ << ' ' << spec.length << ' ' << linear << ' '
                              << int(blue) << ' ' << planar << '\n';
                }
    return count == 80 ? 0 : 1;
}
