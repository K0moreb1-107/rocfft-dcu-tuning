#include <hip/hip_runtime.h>
template<unsigned int Q>
__device__ __forceinline__ double carrier_value(const double2* data,unsigned int t) {
    const unsigned int high=t>=Q;
    const unsigned int b=t-high*Q;
    return reinterpret_cast<const double*>(data)[2*b+high];
}
extern "C" __global__ void carrier_odd(double2* out,const double2* in) {
    const unsigned int j=blockIdx.x*blockDim.x+threadIdx.x;
    if(j<125) out[j]=double2{carrier_value<125>(in,2*j),carrier_value<125>(in,2*j+1)};
    return;
}
extern "C" __global__ void carrier_even(double2* out,const double2* in) {
    const unsigned int j=blockIdx.x*blockDim.x+threadIdx.x;
    if(j<128) out[j]=double2{carrier_value<128>(in,2*j),carrier_value<128>(in,2*j+1)};
    return;
}
