// Diagnostic-only hipRTC source substitution. No launch hook or runtime FFT work.
#include <hip/hiprtc.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
struct Rule
{
    std::string name, original, replacement;
};
std::string read(const std::string& path)
{
    std::ifstream stream(path, std::ios::binary);
    if(!stream) throw std::runtime_error("cannot read diagnostic input");
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}
void audit(const std::string& status, const std::string& name)
{
    const char* path = std::getenv("CC_RTC_DIAG_LOG");
    if(!path) throw std::runtime_error("diagnostic audit path absent");
    const std::string line = status+"\t"+name+"\n";
    int file = ::open(path, O_CREAT|O_WRONLY|O_APPEND, 0600);
    if(file < 0) throw std::runtime_error("cannot create diagnostic audit");
    auto count = ::write(file,line.data(),line.size());
    ::close(file);
    if(count != static_cast<ssize_t>(line.size())) throw std::runtime_error("diagnostic audit incomplete");
}
const std::vector<Rule>& rules()
{
    static const auto result = [] {
        const char* path = std::getenv("CC_RTC_DIAG_RULES");
        if(!path) throw std::runtime_error("diagnostic rule path absent");
        std::istringstream stream(read(path));
        std::string line;
        std::vector<Rule> value;
        while(std::getline(stream,line))
        {
            const auto first = line.find('\t'), second = line.find('\t',first+1);
            if(first == std::string::npos || second == std::string::npos)
                throw std::runtime_error("invalid diagnostic rule");
            value.push_back({line.substr(0,first),read(line.substr(first+1,second-first-1)),
                             read(line.substr(second+1))});
        }
        return value;
    }();
    return result;
}
}

extern "C" hiprtcResult hiprtcCreateProgram(hiprtcProgram* program, const char* source,
    const char* name, int count, const char** headers, const char** includes)
{
    using Function = decltype(&hiprtcCreateProgram);
    static auto actual = reinterpret_cast<Function>(dlsym(RTLD_NEXT,"hiprtcCreateProgram"));
    if(!actual) return HIPRTC_ERROR_INTERNAL_ERROR;
    try
    {
        const std::string text = source ? source : "";
        for(const auto& rule : rules())
        {
            if(text == rule.original)
            {
                audit(rule.original == rule.replacement ? "identity" : "override",rule.name);
                return actual(program,rule.replacement.c_str(),name,count,headers,includes);
            }
        }
        for(const auto& rule : rules())
            if(text.find(rule.name) != std::string::npos)
            {
                audit("source_mismatch",rule.name);
                return HIPRTC_ERROR_INTERNAL_ERROR;
            }
        return actual(program,source,name,count,headers,includes);
    }
    catch(...)
    {
        return HIPRTC_ERROR_INTERNAL_ERROR;
    }
}
