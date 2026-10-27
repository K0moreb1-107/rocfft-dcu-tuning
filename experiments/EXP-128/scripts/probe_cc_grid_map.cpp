// Read the already-constructed private divisor map in a controlled test library.
// The symbol offset comes from that library's ELF symbol table; no GPU is used.
#include <cstdint>
#include <cstdlib>
#include <dlfcn.h>
#include <iostream>
#include <map>
#include <string>

int main(int argc, char** argv)
{
    if(argc < 4)
        return 2;
    void* library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if(!library)
    {
        std::cerr << dlerror() << '\n';
        return 3;
    }
    void* version = dlsym(library, "rocfft_get_version_string");
    Dl_info origin{};
    if(!version || !dladdr(version, &origin))
        return 4;
    const auto address = reinterpret_cast<std::uintptr_t>(origin.dli_fbase)
                         + std::stoull(argv[2]);
    const auto& divisors = *reinterpret_cast<const std::map<std::size_t, std::size_t>*>(address);
    if(divisors.size() != static_cast<std::size_t>(argc - 3))
        return 5;
    for(int index = 3; index < argc; ++index)
    {
        const std::string pair(argv[index]);
        const auto split = pair.find(':');
        const auto length = std::stoull(pair.substr(0, split));
        const auto expected = std::stoull(pair.substr(split + 1));
        auto found = divisors.find(length);
        if(found == divisors.end() || found->second != expected)
        {
            std::cerr << "divisor mismatch: " << length << '\n';
            return 6;
        }
    }
    std::cout << "{\"complete\":true,\"entries\":" << divisors.size()
              << ",\"device_execution\":false}\n";
    dlclose(library);
}
