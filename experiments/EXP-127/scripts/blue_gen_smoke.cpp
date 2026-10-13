#include "rtc_bluestein_gen.h"
#include "device/generator/generator.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

// This host-only exporter does not execute kernels or need a device.
void write_standalone_test_harness(const Function&, const std::string&) {}

int main(int argc,char** argv)
{
    if(argc!=2) return 2;
    const std::string out(argv[1]);
    unsigned int count=0;
    for(bool pre : {true,false})
        for(bool fused : {true,false})
            for(bool callbacks : {false,true})
                for(bool scaled : {false,true})
                {
                    BluesteinMultiSpecs spec{pre ? CS_KERNEL_PAD_MUL : CS_KERNEL_RES_MUL,
                        rocfft_precision_double,rocfft_array_type_complex_interleaved,
                        rocfft_array_type_complex_interleaved,CallbackType::NONE,
                        std::nullopt,std::nullopt,{}};
                    if(fused) spec.real_boundary={pre ? RealBoundaryDirection::Pre : RealBoundaryDirection::Post,
                                                  RealBoundaryContainer::Bluestein,65540};
                    if(callbacks) spec.cbtype=fused ? CallbackType::USER_LOAD_STORE
                            : pre ? CallbackType::USER_LOAD_STORE_R2C : CallbackType::USER_LOAD_STORE_C2R;
                    if(scaled && !pre){StoreOps ops;ops.scale_factor=0.375;spec.storeOps=ops;}
                    auto name=bluestein_multi_rtc_kernel_name(spec);
                    auto src=bluestein_multi_rtc(name,spec);
                    if(fused)
                    {
                        spec.real_boundary.n=65538;
                        if(bluestein_multi_rtc_kernel_name(spec)!=name || bluestein_multi_rtc(name,spec)!=src)
                            throw std::runtime_error("runtime parity changed generated identity/source");
                    }
                    const std::string path=out+"/generated-"+std::to_string(count++)+".cpp";
                    std::ofstream file(path);file<<src;
                    if(!file) throw std::runtime_error("cannot write generated source");
                    std::cout<<path<<" "<<name<<"\n";
                }
    return count==16 ? 0 : 1;
}
