#include "rtc_stockham_gen.h"
#include <filesystem>
#include <fstream>
#include <iostream>

static void emit(const std::filesystem::path& directory, size_t n, const std::string& role,
                 bool lds, bool callbacks, bool scaled)
{
    const unsigned int q = n <= 131072 ? 256 : 512, c = n / (2 * q);
    const bool columns = role == "ordinary_columns" || role == "hermitian_columns";
    std::vector<unsigned int> factors;
    unsigned int wgs = 256, threads = 0;
    bool half = false;
    if(columns)
    {
        switch(c)
        {
        case 128: factors = {16,8}; threads = 16; break;
        case 256: factors = {8,4,8}; threads = 32; half = true; break;
        case 512: factors = {8,8,8}; threads = 64; half = true; break;
        default: factors = {8,8,4,4}; threads = 64; half = true; break;
        }
        // Match the full-complex staging allocation used by the LDS entry.
        if(lds) half = false;
    }
    else if(q == 256) { factors = {4,4,4,4}; threads = 32; }
    else { factors = {8,8,8}; threads = 128; wgs = 512; }
    const auto scheme = columns ? CS_KERNEL_STOCKHAM_BLOCK_CC : CS_KERNEL_STOCKHAM_BLOCK_RC;
    const int direction = role == "paired_post_rows" ? -1 : 1;
    StockhamGeneratorSpecs specs(factors, {}, {rocfft_precision_double}, wgs, PrintScheme(scheme));
    specs.threads_per_transform = threads;
    specs.wgs_is_derived = true;
    specs.direct_to_from_reg = true;
    specs.half_lds = half;
    specs.static_dim = 2;
    if(role != "ordinary_columns" && role != "ordinary_rows")
    {
        specs.real_io = *RealBlockIO::ForLength(n);
        specs.real_io.load = lds ? RealBlockLoad::LDS : RealBlockLoad::Registers;
        if(role == "hermitian_columns") specs.real_io.role = RealBlockRole::HermitianColumns;
        if(role == "local_real_rows") specs.real_io.role = RealBlockRole::LocalRealRows;
        if(role == "paired_post_rows")
        {
            specs.real_io.role = RealBlockRole::PairedPostRows;
            specs.real_io.pitch = q;
            specs.static_initial_reg_load = !lds && !callbacks;
            specs.static_initial_reg_load_linear = specs.static_initial_reg_load;
        }
    }
    const auto cb = callbacks ? CallbackType::USER_LOAD_STORE : CallbackType::NONE;
    const auto dr = lds || !columns ? DirectRegType::FORCE_OFF_OR_NOT_SUPPORT
                                   : DirectRegType::TRY_ENABLE_IF_SUPPORT;
    const size_t base = columns ? (c == 128 ? 6 : 8) : 0, steps = columns ? 3 : 0;
    StoreOps ops; ops.scale_factor = scaled ? 0.375 : 1.0;
    const std::optional<StoreOps> store_ops{ops};
    const auto name = stockham_rtc_kernel_name(specs, specs, scheme, direction, rocfft_precision_double,
        rocfft_placement_notinplace, rocfft_array_type_complex_interleaved,
        rocfft_array_type_complex_interleaved, !columns, base, steps, false, dr,
        IntrinsicAccessType::DISABLE_BOTH, columns ? NONE : TILE_ALIGNED, cb,
        BFT_NONE, PPT_NONE, {}, {}, store_ops);
    const auto source = stockham_rtc(specs, specs, {}, nullptr, name, scheme, direction,
        rocfft_precision_double, rocfft_placement_notinplace, rocfft_array_type_complex_interleaved,
        rocfft_array_type_complex_interleaved, !columns, base, steps, false, dr,
        IntrinsicAccessType::DISABLE_BOTH, columns ? NONE : TILE_ALIGNED, cb,
        BFT_NONE, PPT_NONE, {}, store_ops);
    const auto filename = std::to_string(n) + "_" + role + (lds ? "_lds" : "_reg")
        + (callbacks ? "_callbacks" : "_plain") + (scaled ? "_scaled" : "_unscaled") + ".cpp";
    std::ofstream(directory / filename) << source;
    std::cout << filename << ' ' << name << '\n';
}

int main(int argc, char** argv)
{
    if(argc != 2) return 2;
    const std::filesystem::path directory(argv[1]);
    std::filesystem::create_directories(directory);
    for(size_t n : {65536,131072,262144,524288,1048576})
        for(const std::string role : {"ordinary_columns","hermitian_columns","ordinary_rows",
                                     "local_real_rows","paired_post_rows"})
            for(bool lds : {false,true})
                for(bool cb : {false,true})
                    for(bool scaled : {false,true})
                        emit(directory,n,role,lds,cb,scaled);
}
