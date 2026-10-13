#include "plan.h"
#include "precision_type.h"
#include <array>
#include <cassert>
#include <cstddef>
#include <iostream>

// Native host checks use the actual descriptor and pointer helper. No GPU
// allocation, setup, plan creation or transform is performed.
int main()
{
    const std::array<rocfft_array_type,5> types = {
        rocfft_array_type_real,rocfft_array_type_complex_interleaved,
        rocfft_array_type_hermitian_interleaved,rocfft_array_type_complex_planar,
        rocfft_array_type_hermitian_planar};
    const std::array<size_t,5> units = {1,2,2,1,1};
    const std::array<rocfft_precision,3> precisions = {
        rocfft_precision_half,rocfft_precision_single,rocfft_precision_double};
    const std::array<size_t,3> scalar_bytes = {2,4,8};
    size_t descriptors=0,pointers=0;
    for(size_t in=0;in<types.size();++in)
        for(size_t out=0;out<types.size();++out)
            for(unsigned int mask=0;mask<16;++mask)
            {
                rocfft_plan_description_t description;
                description.inArrayType=types[in];description.outArrayType=types[out];
                description.inOffset={mask&1u ? 3u : 0u,mask&2u ? 7u : 0u};
                description.outOffset={mask&4u ? 5u : 0u,mask&8u ? 9u : 0u};
                const bool expected=(mask&5u) || (in>=3 && (mask&2u)) || (out>=3 && (mask&8u));
                assert(description.has_user_offsets()==expected);++descriptors;
            }
    alignas(64) std::array<unsigned char,1024> storage{};
    for(size_t type=0;type<types.size();++type)
        for(size_t precision=0;precision<precisions.size();++precision)
            for(size_t offset : {size_t{0},size_t{1},size_t{3},size_t{7}})
            {
                const auto actual=ptr_offset(storage.data(),offset,precisions[precision],
                    rocfft_plan_description_t::buffer_element_type(types[type]));
                const auto expected=storage.data()+offset*scalar_bytes[precision]*units[type];
                assert(actual==expected);++pointers;
            }
    assert(descriptors==400 && pointers==60);
    std::cout << "USER_OFFSET_CONTRACT_PASS descriptors=" << descriptors
              << " pointers=" << pointers << " gpu_execution=0\n";
}
