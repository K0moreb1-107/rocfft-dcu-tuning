// Host-only generation preflight; no public plans or device execution.
#include "rtc_stockham_gen.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

static std::vector<unsigned int> factors(std::string text)
{
    for (auto& x : text)
        if (x == ',')
            x = ' ';
    std::istringstream in(text);
    std::vector<unsigned int> out;
    unsigned int x;
    while (in >> x)
        out.push_back(x);
    return out;
}

int main(int argc, char** argv)
try
{
    if (argc != 3)
        return 2;
    std::ifstream manifest(argv[1]);
    size_t n, c, q, cp, ct, rp, rt;
    bool ch, rh, keep;
    std::string cf, rf;
    size_t total = 0;
    while (manifest >> n >> c >> q >> cp >> ct >> ch >> cf >> rp >> rt >> rh >> rf >> keep)
        for (int role = 4; role <= 7; ++role)
            for (int cb = 0; cb < 2; ++cb)
            {
                const bool col = role == 4 || role == 6;
                const auto scheme = col ? CS_KERNEL_STOCKHAM_BLOCK_CC : CS_KERNEL_STOCKHAM_BLOCK_RC;
                const int direction = role <= 5 ? 1 : -1;
                const auto transpose = col ? NONE : (c % rt ? TILE_UNALIGNED : TILE_ALIGNED);
                StockhamGeneratorSpecs specs(factors(col ? cf : rf), { },
                    { static_cast<unsigned int>(rocfft_precision_double) }, col ? cp * ct : rp * rt,
                    PrintScheme(scheme));
                specs.threads_per_transform = col ? cp : rp;
                specs.wgs_is_derived = true;
                specs.half_lds = col ? ch : rh;
                specs.direct_to_from_reg = true;
                specs.static_initial_reg_load = true;
                specs.static_initial_reg_load_linear = !col;
                specs.static_dim = 2;
                specs.real_io
                    = { static_cast<RealBlockRole>(role), RealBlockLoad::LDS, n, c, q, q };
                if (col || (role == 5 && RealBlockIO::CanRegisterPre(q, specs.factors.front(), rp))
                    || (role == 7 && !(q & (q - 1)) && transpose == TILE_ALIGNED))
                    specs.real_io.load = RealBlockLoad::Registers;
                auto cbtype = CallbackType::NONE;
                if (cb)
                    cbtype = role == 6 ? CallbackType::USER_LOAD_STORE_R2C
                        : role == 5    ? CallbackType::USER_LOAD_STORE_C2R
                                       : CallbackType::USER_LOAD_STORE;
                const size_t base = role == 4 ? 8 : 0, steps = role == 4 ? 3 : 0;
                StockhamGeneratorSpecs empty({ }, { }, { }, 0, "");
                StockhamPartialPassParams pp;
                StoreOps store;
                store.scale_factor = .375;
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
                if (code.find("cc_boundary_load<") == std::string::npos
                    || code.find("cc_boundary_store<") == std::string::npos)
                    throw std::runtime_error("typed boundary visitor missing");
                if (keep)
                {
                    const auto file = std::filesystem::path(argv[2])
                        / (std::to_string(c) + "-" + std::to_string(q) + "-" + std::to_string(role)
                            + "-" + std::to_string(cb) + ".cpp");
                    std::ofstream(file) << code;
                }
                std::cout << n << ' ' << c << ' ' << q << ' ' << role << ' ' << cb << ' '
                          << code.size() << ' ' << name << '\n';
                ++total;
            }
    if (!manifest.eof() || total != 279 * 8)
        throw std::runtime_error("incomplete generation matrix");
    std::cerr << "GENERATION_MATRIX_PASS " << total << std::endl;
    return 0;
}
catch (const std::exception& e)
{
    std::cerr << e.what() << std::endl;
    return 1;
}
