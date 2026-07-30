#include <hip/hip_runtime.h>

#include <iostream>

int main()
{
    hipDeviceProp_t prop{};
    if(hipGetDeviceProperties(&prop, 0) != hipSuccess)
        return 1;
    std::cout << "name=" << prop.name << '\n';
    std::cout << "arch=" << prop.gcnArchName << '\n';
    std::cout << "maxThreadsPerBlock=" << prop.maxThreadsPerBlock << '\n';
    std::cout << "maxThreadsDim=" << prop.maxThreadsDim[0] << ',' << prop.maxThreadsDim[1]
              << ',' << prop.maxThreadsDim[2] << '\n';
    std::cout << "warpSize=" << prop.warpSize << '\n';
    std::cout << "sharedMemPerBlock=" << prop.sharedMemPerBlock << '\n';
    std::cout << "regsPerBlock=" << prop.regsPerBlock << '\n';
    std::cout << "multiProcessorCount=" << prop.multiProcessorCount << '\n';
}
