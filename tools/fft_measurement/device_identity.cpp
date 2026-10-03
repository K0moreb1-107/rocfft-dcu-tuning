// Separate preflight helper; the frozen measurement source stays unchanged.
#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void check(hipError_t status) {
    if (status != hipSuccess) {
        std::fprintf(stderr, "HIP identity failed: %s\n", hipGetErrorString(status));
        std::exit(1);
    }
}
int main() {
    int count = 0, runtime = 0, driver = 0;
    check(hipGetDeviceCount(&count));
    if (count != 1) { std::fprintf(stderr, "require exactly one HIP-visible GPU\n"); return 1; }
    hipDevice_t device;
    check(hipDeviceGet(&device, 0));
    hipUUID uuid{};
    check(hipDeviceGetUuid(&uuid, device));
    hipDeviceProp_t prop{};
    check(hipGetDeviceProperties(&prop, 0));
    check(hipRuntimeGetVersion(&runtime));
    check(hipDriverGetVersion(&driver));
    unsigned nonzero = 0;
    for (unsigned char b : uuid.bytes) nonzero |= b;
    if (!nonzero) { std::fprintf(stderr, "zero UUID is not valid evidence\n"); return 1; }
    std::printf("{\"count\":1,\"uuid\":\"");
    for (unsigned char b : uuid.bytes) std::printf("%02x", b);
    // Architecture strings are runtime-controlled alphanumeric/colon flags.
    if (std::strpbrk(prop.gcnArchName, "\"\\\n\r")) return 1;
    std::printf("\",\"arch\":\"%s\",\"runtime_version\":%d,\"driver_version\":%d}\n", prop.gcnArchName, runtime, driver);
}
