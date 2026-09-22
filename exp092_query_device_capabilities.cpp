#include <hip/hip_runtime.h>

#include <cstddef>
#include <iostream>
#include <type_traits>
#include <utility>

template <typename T, typename = void>
struct has_cluster_launch : std::false_type
{
};

template <typename T>
struct has_cluster_launch<T, std::void_t<decltype(std::declval<T>().clusterLaunch)>>
    : std::true_type
{
};

template <typename T, typename = void>
struct has_l2_cache_size : std::false_type
{
};

template <typename T>
struct has_l2_cache_size<T, std::void_t<decltype(std::declval<T>().l2CacheSize)>>
    : std::true_type
{
};

template <typename T, typename = void>
struct has_shared_mem_per_cu : std::false_type
{
};

template <typename T>
struct has_shared_mem_per_cu<
    T,
    std::void_t<decltype(std::declval<T>().maxSharedMemoryPerMultiProcessor)>>
    : std::true_type
{
};

template <typename T, typename = void>
struct has_shared_mem_per_block_optin : std::false_type
{
};

template <typename T>
struct has_shared_mem_per_block_optin<
    T,
    std::void_t<decltype(std::declval<T>().sharedMemPerBlockOptin)>>
    : std::true_type
{
};

template <typename T>
void print_optional_properties(const T& prop)
{
    if constexpr(has_cluster_launch<T>::value)
        std::cout << "clusterLaunch=" << static_cast<long long>(prop.clusterLaunch) << '\n';
    else
        std::cout << "clusterLaunch_field=absent\n";

    if constexpr(has_l2_cache_size<T>::value)
        std::cout << "l2CacheSize=" << static_cast<unsigned long long>(prop.l2CacheSize) << '\n';
    else
        std::cout << "l2CacheSize_field=absent\n";

    if constexpr(has_shared_mem_per_cu<T>::value)
        std::cout << "maxSharedMemoryPerMultiProcessor="
                  << static_cast<unsigned long long>(prop.maxSharedMemoryPerMultiProcessor)
                  << '\n';
    else
        std::cout << "maxSharedMemoryPerMultiProcessor_field=absent\n";

    if constexpr(has_shared_mem_per_block_optin<T>::value)
        std::cout << "sharedMemPerBlockOptin="
                  << static_cast<unsigned long long>(prop.sharedMemPerBlockOptin) << '\n';
    else
        std::cout << "sharedMemPerBlockOptin_field=absent\n";
    return;
}

int main()
{
    int runtime_version = 0;
    int driver_version  = 0;
    int device_count    = 0;

    hipError_t status = hipRuntimeGetVersion(&runtime_version);
    if(status != hipSuccess)
    {
        std::cerr << "hipRuntimeGetVersion_error=" << hipGetErrorString(status) << '\n';
        return 1;
    }
    status = hipDriverGetVersion(&driver_version);
    if(status != hipSuccess)
    {
        std::cerr << "hipDriverGetVersion_error=" << hipGetErrorString(status) << '\n';
        return 1;
    }
    status = hipGetDeviceCount(&device_count);
    if(status != hipSuccess)
    {
        std::cerr << "hipGetDeviceCount_error=" << hipGetErrorString(status) << '\n';
        return 1;
    }
    if(device_count < 1)
    {
        std::cerr << "device_count=0\n";
        return 2;
    }

    hipDeviceProp_t prop{};
    status = hipGetDeviceProperties(&prop, 0);
    if(status != hipSuccess)
    {
        std::cerr << "hipGetDeviceProperties_error=" << hipGetErrorString(status) << '\n';
        return 1;
    }

    std::cout << "experiment=EXP-092\n";
    std::cout << "phase=gfx936-device-capability-query\n";
    std::cout << "hip_runtime_version=" << runtime_version << '\n';
    std::cout << "hip_driver_version=" << driver_version << '\n';
    std::cout << "device_count=" << device_count << '\n';
    std::cout << "name=" << prop.name << '\n';
    std::cout << "gcnArchName=" << prop.gcnArchName << '\n';
    std::cout << "warpSize=" << prop.warpSize << '\n';
    std::cout << "multiProcessorCount=" << prop.multiProcessorCount << '\n';
    std::cout << "maxThreadsPerBlock=" << prop.maxThreadsPerBlock << '\n';
    std::cout << "maxThreadsPerMultiProcessor=" << prop.maxThreadsPerMultiProcessor << '\n';
    std::cout << "sharedMemPerBlock="
              << static_cast<unsigned long long>(prop.sharedMemPerBlock) << '\n';
    std::cout << "cooperativeLaunch=" << prop.cooperativeLaunch << '\n';
    std::cout << "cooperativeMultiDeviceLaunch=" << prop.cooperativeMultiDeviceLaunch << '\n';
    print_optional_properties(prop);

    std::cout << "required_hierarchical_owner_fan_in=8\n";
    std::cout << "required_note=cooperativeLaunch alone supplies grid synchronization, not remote LDS\n";
    return 0;
}
