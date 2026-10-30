// Host-only comparison of the retained CC boundary generators.
#include "rtc_stockham_gen.h"
#include "rtc_bluestein_gen.h"
#include <set>
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>

static std::vector<unsigned int> factors(std::string text)
{
    for(auto& value : text)
        if(value == ',')
            value = ' ';
    std::istringstream        input(text);
    std::vector<unsigned int> result;
    unsigned int              value;
    while(input >> value)
        result.push_back(value);
    return result;
}

int main(int argc, char** argv)
try
{
    if(argc != 5)
        return 2;
    const bool scaled = std::string(argv[4]) == "scaled";
    const std::set<size_t> samples{65536, 65856, 67600, 69938, 75000, 2725888};
    const std::array<RealBlockRole, 4> roles{RealBlockRole::FoldedPackedColumns,
                                            RealBlockRole::PackedInverseRows,
                                            RealBlockRole::LocalPostColumns,
                                            RealBlockRole::FoldedSpectrumRows};
    std::ifstream manifest(argv[1]);
    size_t        n, c, q, cp, ct, rp, rt;
    bool          ch, rh, keep;
    std::string   cf, rf;
    size_t        total = 0;
    while(manifest >> n >> c >> q >> cp >> ct >> ch >> cf >> rp >> rt >> rh >> rf >> keep)
        for(const auto role : roles)
            for(int cb = 0; cb < 2; ++cb)
            {

                const int role_id = static_cast<int>(role);
                const bool column = role == RealBlockRole::FoldedPackedColumns
                                    || role == RealBlockRole::LocalPostColumns;
                const auto scheme
                    = column ? CS_KERNEL_STOCKHAM_BLOCK_CC : CS_KERNEL_STOCKHAM_BLOCK_RC;
                const int direction = role == RealBlockRole::FoldedPackedColumns
                                              || role == RealBlockRole::PackedInverseRows
                                          ? 1 : -1;
                const auto transpose = column ? NONE : (c % rt ? TILE_UNALIGNED : TILE_ALIGNED);
                StockhamGeneratorSpecs specs(factors(column ? cf : rf), {},
                    {static_cast<unsigned int>(rocfft_precision_double)},
                    column ? cp * ct : rp * rt, PrintScheme(scheme));
                specs.threads_per_transform = column ? cp : rp;
                specs.wgs_is_derived = true;
                specs.half_lds = column ? ch : rh;
                specs.direct_to_from_reg = true;
                specs.static_initial_reg_load = true;
                specs.static_initial_reg_load_linear = !column;
                specs.static_dim = 2;
                specs.real_io.role = role;
                specs.real_io.load = RealBlockLoad::LDS;
                specs.real_io.n = n;
                specs.real_io.columns = c;
                specs.real_io.rows = q;
                if(column || (role == RealBlockRole::PackedInverseRows
                              && RealBlockIO::CanRegisterPre(q, specs.factors.front(), rp))
                   || (role == RealBlockRole::FoldedSpectrumRows
                       && RealBlockIO::CanRegisterInput(rp, rp * rt)))
                    specs.real_io.load = RealBlockLoad::Registers;

                auto cbtype = CallbackType::NONE;
                if(cb)
                    cbtype = role == RealBlockRole::LocalPostColumns
                                 ? CallbackType::USER_LOAD_STORE_R2C
                                 : role == RealBlockRole::PackedInverseRows
                                       ? CallbackType::USER_LOAD_STORE_C2R
                                       : CallbackType::USER_LOAD_STORE;
                const size_t base = role == RealBlockRole::FoldedPackedColumns
                                        ? ((c & (c - 1)) && n <= (1 << 18) ? 6 : 8) : 0;
                const size_t steps = role == RealBlockRole::FoldedPackedColumns
                                         ? (base == 8 && n <= 65536 ? 2 : 3) : 0;
                StockhamGeneratorSpecs empty({}, {}, {}, 0, "");
                StockhamPartialPassParams pp;
                StoreOps store;
                store.scale_factor = scaled && !column ? 0.5 : 1.;
                const auto name = stockham_rtc_kernel_name(specs, empty, scheme, direction,
                    rocfft_precision_double, rocfft_placement_notinplace,
                    rocfft_array_type_complex_interleaved, rocfft_array_type_complex_interleaved,
                    false, base, steps, false, DirectRegType::TRY_ENABLE_IF_SUPPORT,
                    IntrinsicAccessType::DISABLE_BOTH, transpose, cbtype, BFT_NONE, PPT_NONE, pp,
                    std::nullopt, store);
                const auto code = stockham_rtc(specs, empty, pp, nullptr, name, scheme, direction,
                    rocfft_precision_double, rocfft_placement_notinplace,
                    rocfft_array_type_complex_interleaved, rocfft_array_type_complex_interleaved,
                    false, base, steps, false, DirectRegType::TRY_ENABLE_IF_SUPPORT,
                    IntrinsicAccessType::DISABLE_BOTH, transpose, cbtype, BFT_NONE, PPT_NONE,
                    std::nullopt, store);
                if(code.find("cc_boundary_load<") == std::string::npos
                   || code.find("cc_boundary_store<") == std::string::npos)
                    throw std::runtime_error("typed boundary visitor missing");
                const auto file = std::filesystem::path(argv[2])
                                  / (std::to_string(c) + "-" + std::to_string(q) + "-"
                                     + std::to_string(role_id) + "-" + std::to_string(cb) + ".cpp");
                if(!scaled)
                {
                    std::ifstream reference(std::filesystem::path(argv[3]) / file.filename());
                    const std::string retained((std::istreambuf_iterator<char>(reference)), {});
                    if(retained != code)
                        throw std::runtime_error("unit-scale generated code changed: " + file.string());
                }
                if(scaled && !column)
                {
                    const auto entry = code.find("void " + name + "(");
                    const auto end = code.find(")", entry);
                    const auto signature = code.substr(entry, end - entry);
                    const auto pos = signature.find("scale_factor");
                    if(pos == std::string::npos || signature.find("scale_factor", pos + 1) != std::string::npos
                       || code.find(",({") != std::string::npos)
                        throw std::runtime_error("invalid scaled CC store: " + name);
                    if(samples.count(n))
                        std::ofstream(file) << code;
                }
                std::cout << n << ' ' << c << ' ' << q << ' ' << role_id << ' ' << cb << ' '
                          << code.size() << ' ' << name << '\n';
                ++total;
            }
    if(!manifest.eof() || total == 0)
        throw std::runtime_error("incomplete generation matrix");
    if(scaled)
        for(const auto precision : {rocfft_precision_single, rocfft_precision_double})
            for(const auto input : {rocfft_array_type_complex_interleaved, rocfft_array_type_complex_planar})
                for(const auto output : {rocfft_array_type_complex_interleaved, rocfft_array_type_complex_planar})
                    for(const auto cb : {CallbackType::NONE, CallbackType::USER_LOAD_STORE,
                                         CallbackType::USER_LOAD_STORE_C2R, CallbackType::USER_LOAD_STORE_R2C})
                        for(const auto scheme : {CS_KERNEL_PAD_MUL, CS_KERNEL_FFT_MUL, CS_KERNEL_RES_MUL})
                            for(const double scale : {1., 0.5})
                            {
                                StoreOps store;
                                store.scale_factor = scale;
                                BluesteinMultiSpecs specs{scheme, precision, input, output, cb, std::nullopt, store};
                                const auto name = bluestein_multi_rtc_kernel_name(specs);
                                const auto code = bluestein_multi_rtc(name, specs);
                                const auto entry = code.find("void " + name + "(");
                                const auto end = code.find(")", entry);
                                const auto signature = code.substr(entry, end - entry);
                                size_t count = 0, pos = 0;
                                while((pos = signature.find("scale_factor", pos)) != std::string::npos)
                                {
                                    ++count;
                                    ++pos;
                                }
                                if(count != size_t(scale != 1.))
                                    throw std::runtime_error("invalid Bluestein argument count: " + name);
                                if(scheme == CS_KERNEL_RES_MUL && precision == rocfft_precision_double
                                   && input == rocfft_array_type_complex_interleaved
                                   && output == rocfft_array_type_complex_interleaved
                                   && (cb == CallbackType::NONE || cb == CallbackType::USER_LOAD_STORE_C2R))
                                    std::ofstream(std::filesystem::path(argv[2]) / (name + ".cpp")) << code;
                                std::cout << "BLUE_ARGUMENT_PASS " << name << '\n';
                            }
    std::cerr << "GENERATION_MATRIX_PASS " << total << std::endl;
    return 0;
}
catch(const std::exception& error)
{
    std::cerr << error.what() << std::endl;
    return 1;
}
