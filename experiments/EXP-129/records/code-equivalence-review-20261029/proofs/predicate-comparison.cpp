#include <algorithm>
#include <initializer_list>
#include <vector>
#include <string>
#include <iostream>
enum { rocfft_precision_single, rocfft_precision_double };
struct State {
 unsigned int length, threads_per_transform, workgroup_size, transforms_per_block;
 std::vector<unsigned int> factors, precisions;
 bool half_lds, direct_to_from_reg, static_initial_reg_load, sbrc_ordinary_twiddle_recurrence;
 std::string scheme;
};
struct Before : State {
    bool use_register_local_exchange(unsigned int npass) const
    {
        return half_lds && precisions.size() == 1
               && precisions.front() == rocfft_precision_double && length == 1024
               && threads_per_transform == 64
               && factors == std::vector<unsigned int>{8, 8, 4, 4} && npass == 2;
    }
    bool use_ordinary_twiddle_recurrence()
    {
        const bool is_dp = precisions.size() == 1
                           && precisions.front() == rocfft_precision_double;
        const bool common_sbcc = half_lds && direct_to_from_reg && is_dp
                                 && workgroup_size == 256;
        const bool sbcc256 = length == 256 && threads_per_transform == 32
                             && factors == std::vector<unsigned int>{8, 4, 8};
        const bool sbcc512 = length == 512 && threads_per_transform == 64
                             && factors == std::vector<unsigned int>{8, 8, 8};
        const bool sbcc1024 = length == 1024 && threads_per_transform == 64
                              && factors == std::vector<unsigned int>{8, 8, 4, 4};
        const bool sbrc512 = sbrc_ordinary_twiddle_recurrence
                             && scheme == "CS_KERNEL_STOCKHAM_BLOCK_RC" && is_dp
                             && direct_to_from_reg && static_initial_reg_load
                             && length == 512 && workgroup_size == 512
                             && threads_per_transform == 128
                             && factors == std::vector<unsigned int>{8, 8, 8};
        return (common_sbcc && (sbcc256 || sbcc512 || sbcc1024)) || sbrc512;
    }
    bool use_late_large_twiddle_lds() const
    {
        const bool common = direct_to_from_reg && half_lds && precisions.size() == 1
                            && precisions.front() == rocfft_precision_double
                            && workgroup_size == 256;
        const bool sbcc256 = length == 256 && threads_per_transform == 32
                             && transforms_per_block == 8
                             && factors == std::vector<unsigned int>{8, 4, 8};
        const bool sbcc1024 = length == 1024 && threads_per_transform == 64
                              && transforms_per_block == 4
                              && factors == std::vector<unsigned int>{8, 8, 4, 4};
        return common && (sbcc256 || sbcc1024);
    }
    virtual bool use_large_twiddle_recurrence() const
    {
        const bool candidate_length = length == 256 || length == 512 || length == 1024;
        const bool supported_radix  = factors.back() == 4 || factors.back() == 8;
        return candidate_length && supported_radix && precisions.size() == 1
               && precisions.front() == rocfft_precision_double;
    }
};
struct After : State {
    bool matches_kernel_shape(unsigned int                        expected_length,
                              unsigned int                        expected_threads,
                              std::initializer_list<unsigned int> expected_factors) const
    {
        return length == expected_length && threads_per_transform == expected_threads
               && factors.size() == expected_factors.size()
               && std::equal(factors.begin(), factors.end(), expected_factors.begin());
    }
    bool use_register_local_exchange(unsigned int npass) const
    {
        return npass == 2 && half_lds && precisions.size() == 1
               && precisions.front() == rocfft_precision_double
               && matches_kernel_shape(1024, 64, {8, 8, 4, 4});
    }
    bool use_ordinary_twiddle_recurrence()
    {
        if(!direct_to_from_reg || precisions.size() != 1
           || precisions.front() != rocfft_precision_double)
            return false;

        if(half_lds && workgroup_size == 256
           && (matches_kernel_shape(256, 32, {8, 4, 8})
               || matches_kernel_shape(512, 64, {8, 8, 8})
               || matches_kernel_shape(1024, 64, {8, 8, 4, 4})))
            return true;

        return sbrc_ordinary_twiddle_recurrence && scheme == "CS_KERNEL_STOCKHAM_BLOCK_RC"
               && static_initial_reg_load && workgroup_size == 512
               && matches_kernel_shape(512, 128, {8, 8, 8});
    }
    bool use_late_large_twiddle_lds() const
    {
        if(!direct_to_from_reg || !half_lds || precisions.size() != 1
           || precisions.front() != rocfft_precision_double || workgroup_size != 256)
            return false;

        return (transforms_per_block == 8 && matches_kernel_shape(256, 32, {8, 4, 8}))
               || (transforms_per_block == 4
                   && matches_kernel_shape(1024, 64, {8, 8, 4, 4}));
    }
    virtual bool use_large_twiddle_recurrence() const
    {
        if(precisions.size() != 1 || precisions.front() != rocfft_precision_double)
            return false;
        if(length != 256 && length != 512 && length != 1024)
            return false;

        return factors.back() == 4 || factors.back() == 8;
    }
};

int main() {
 std::vector<std::vector<unsigned int>> factors_list={{8,4,8},{8,8,8},{8,8,4,4},{4,4,4,4},{4,8,8},{16,16},{8,8,4,4,1},{}};
 std::vector<std::vector<unsigned int>> precision_list={{},{rocfft_precision_single},{rocfft_precision_double},{rocfft_precision_double,rocfft_precision_double}};
 unsigned long long checked=0;
 for(unsigned int length:{128,256,512,1024,2048})
 for(unsigned int threads:{16,32,64,128,256})
 for(unsigned int wg:{128,256,512,1024})
 for(unsigned int tpb:{1,2,4,8,16})
 for(const auto& factors:factors_list)
 for(const auto& precisions:precision_list)
 for(unsigned int flags=0;flags<16;++flags)
 for(const auto& scheme:{"CS_KERNEL_STOCKHAM_BLOCK_CC","CS_KERNEL_STOCKHAM_BLOCK_RC","CS_KERNEL_STOCKHAM"}) {
  State s{length,threads,wg,tpb,factors,precisions,bool(flags&1),bool(flags&2),bool(flags&4),bool(flags&8),scheme};
  Before b; After a; static_cast<State&>(b)=s; static_cast<State&>(a)=s;
  bool same=b.use_ordinary_twiddle_recurrence()==a.use_ordinary_twiddle_recurrence() && b.use_late_large_twiddle_lds()==a.use_late_large_twiddle_lds();
  if(!factors.empty())same=same && b.use_large_twiddle_recurrence()==a.use_large_twiddle_recurrence();
  for(unsigned int pass=0;pass<6;++pass) same=same && b.use_register_local_exchange(pass)==a.use_register_local_exchange(pass);
  if(!same) {std::cerr<<"mismatch "<<length<<" "<<threads<<" "<<wg<<" "<<tpb<<" "<<flags<<" "<<scheme<<"\n";return 1;}
  ++checked;
 }
 std::cout<<"{\"complete\":true,\"state_combinations\":"<<checked<<",\"pass_variants\":6,\"methods\":4,\"actual_definitions_extracted\":true,\"device_execution\":false}\n";
}
