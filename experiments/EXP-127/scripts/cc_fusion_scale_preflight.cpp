#include "rtc_stockham_gen.h"
#include <filesystem>
#include <fstream>
#include <iostream>

static void emit(const std::filesystem::path& directory, size_t n, bool columns,
                 bool lds, bool callbacks, bool paired, bool single, bool scaled)
{
    const unsigned int q = n <= 131072 ? 256 : 512, a = n / (2 * q);
    std::vector<unsigned int> factors;
    unsigned int wgs = 256, threads = 0;
    bool half = false;
    if(columns)
    {
        switch(a)
        {
        case 128: factors = {16, 8}; threads = 16; break;
        case 256: factors = {8, 4, 8}; threads = 32; half = true; break;
        case 512: factors = {8, 8, 8}; threads = 64; half = true; break;
        default: factors = {8, 8, 4, 4}; threads = 64; half = true; break;
        }
    }
    else if(q == 256) { factors = {4, 4, 4, 4}; threads = 32; }
    else { factors = {8, 8, 8}; threads = 128; wgs = 512; }
    const auto precision = single ? rocfft_precision_single : rocfft_precision_double;
    StoreOps ops; ops.scale_factor = scaled ? 0.375 : 1.0;
    const std::optional<StoreOps> storeOps{ops};
    const auto scheme = columns ? CS_KERNEL_STOCKHAM_BLOCK_CC : CS_KERNEL_STOCKHAM_BLOCK_RC;
    StockhamGeneratorSpecs specs(factors, {}, {precision}, wgs, PrintScheme(scheme));
    specs.threads_per_transform = threads;
    specs.wgs_is_derived = true;
    specs.direct_to_from_reg = true;
    specs.half_lds = half;
    specs.static_dim = 2;
    if(!columns)
    {
        specs.static_initial_reg_load = !callbacks;
        specs.static_initial_reg_load_linear = true;
    }
    if(paired)
    {
#ifdef PAIRED_POST_CANDIDATE
        specs.real_io = *RealBlockIO::ForLength(n);
        specs.real_io.role = RealBlockRole::PairedPostRows;
        specs.real_io.pitch = q;
        specs.real_io.load = lds ? RealBlockLoad::LDS : RealBlockLoad::Registers;
        specs.static_initial_reg_load = !lds && !callbacks;
        specs.static_initial_reg_load_linear = specs.static_initial_reg_load;
#else
        return;
#endif
    }
    const auto cb = callbacks ? CallbackType::USER_LOAD_STORE : CallbackType::NONE;
    const auto dr = lds || !columns ? DirectRegType::FORCE_OFF_OR_NOT_SUPPORT
                                   : DirectRegType::TRY_ENABLE_IF_SUPPORT;
    const size_t base = columns ? (a == 128 ? 6 : 8) : 0, steps = columns ? 3 : 0;
    const auto name = stockham_rtc_kernel_name(specs, specs, scheme, -1, precision,
        rocfft_placement_notinplace, rocfft_array_type_complex_interleaved,
        rocfft_array_type_complex_interleaved, !columns, base, steps, false, dr,
        IntrinsicAccessType::DISABLE_BOTH, columns ? NONE : TILE_ALIGNED, cb,
        BFT_NONE, PPT_NONE, {}, {}, storeOps);
    const auto source = stockham_rtc(specs, specs, {}, nullptr, name, scheme, -1,
        precision, rocfft_placement_notinplace, rocfft_array_type_complex_interleaved,
        rocfft_array_type_complex_interleaved, !columns, base, steps, false, dr,
        IntrinsicAccessType::DISABLE_BOTH, columns ? NONE : TILE_ALIGNED, cb, BFT_NONE, PPT_NONE, {}, storeOps);
    const auto filename = std::to_string(n) + "_forward" + (columns ? "_columns" : "_rows")
        + (lds ? "_lds" : "_reg") + (callbacks ? "_callback" : "_plain")
        + (paired ? "_paired_post" : "_ordinary") + (single ? "_sp" : "_dp")
        + (scaled ? "_scaled" : "_unscaled") + ".cpp";
    std::ofstream(directory / filename) << source;
    std::cout << filename << ' ' << name << '\n';
}
int main(int argc, char** argv)
{
    if(argc != 2) return 2;
    const std::filesystem::path directory(argv[1]);
    std::filesystem::create_directories(directory);
    for(size_t n : {65536, 131072, 262144, 524288, 1048576})
        for(bool lds : {false,true})
            for(bool cb : {false,true})
                for(bool single : {false,true})
                    for(bool scaled : {false,true})
                        for(bool paired : {false,true})
                            emit(directory,n,false,lds,cb,paired,single,scaled);
}
