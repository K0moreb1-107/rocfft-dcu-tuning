#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdio>
#include <numeric>
#include <optional>
#include <vector>
#include <cstdint>
using Output = std::array<size_t, 8>;
enum ComputeScheme { CS_KERNEL_STOCKHAM_BLOCK_RC, CS_KERNEL_STOCKHAM_BLOCK_CC, CS_KERNEL_STOCKHAM, CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z };
enum { TILE_ALIGNED, TILE_UNALIGNED };
enum { rocfft_precision_double, rocfft_precision_single, rocfft_precision_half };
enum class EmbeddedType { NONE, OTHER };
enum class CallbackType { NONE, USER };
enum class DirectRegType { TRY_ENABLE_IF_SUPPORT, FORCE_OFF_OR_NOT_SUPPORT };
static bool IsPo2(size_t value) {return value && !(value & (value - 1));}
namespace before {
#include "/public/home/zhangkewei/zr/experiments/EXP-129/artifacts/rtc-gates/real_block_io.before.h"

struct StockhamGeneratorSpecs {
 std::vector<unsigned int> factors;
 unsigned int length, workgroup_size, threads_per_transform;
 bool half_lds, direct_to_from_reg;
 bool static_initial_reg_load=false, static_initial_reg_load_linear=false;
 bool sbrc_ordinary_twiddle_recurrence=false;
 RealBlockIO real_io;
};
struct TreeNode {
 int scheme=CS_KERNEL_STOCKHAM_BLOCK_RC, sbrcTranstype=TILE_ALIGNED, precision=rocfft_precision_double;
 EmbeddedType ebtype=EmbeddedType::NONE;
 DirectRegType dir2regMode=DirectRegType::TRY_ENABLE_IF_SUPPORT;
 CallbackType callback_type=CallbackType::NONE;
 RealBlockIO real_io;
 const TreeNode* parent=nullptr;
 int dimension=1;
 std::vector<size_t> length={131072};
 CallbackType GetCallbackType(bool enable) const {return enable?callback_type:CallbackType::NONE;}
};
Output run(const std::vector<unsigned int>& factors, unsigned int workgroup, unsigned int threads, int scheme, int role, int precision, int embedded, int callback, int mode, bool half, bool direct, int rootkind, int tile, int load) {

 std::optional<StockhamGeneratorSpecs> specs;
 specs.emplace();
 specs->factors=factors;
 specs->length=std::accumulate(factors.begin(),factors.end(),1u,std::multiplies<unsigned int>());
 specs->workgroup_size=workgroup;
 specs->threads_per_transform=threads;
 specs->half_lds=half;
 specs->direct_to_from_reg=direct;
 TreeNode root;
 if(rootkind==1) root.length={65536};
 if(rootkind==2) root.dimension=2;
 if(rootkind==3) root.length={131072,1};
 TreeNode parent;parent.parent=&root;
 TreeNode node;
 node.parent=&parent;
 node.scheme=scheme;
 node.sbrcTranstype=tile;
 node.precision=precision;
 node.ebtype=static_cast<EmbeddedType>(embedded);
 node.callback_type=static_cast<CallbackType>(callback);
 node.dir2regMode=static_cast<DirectRegType>(mode);
 node.real_io.role=static_cast<RealBlockRole>(role);
 node.real_io.load=static_cast<RealBlockLoad>(load);
 const bool enable_callbacks=true;
 auto pool_scheme=scheme==CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z?CS_KERNEL_STOCKHAM_BLOCK_RC:scheme;
        const auto callback_type = node.GetCallbackType(enable_callbacks);
        const auto is_power_of_two = [](size_t value) {
            return value != 0 && (value & (value - 1)) == 0;
        };
        const bool static_pow2_sbrc_map = [&]() {
            if(!is_power_of_two(specs->length) || specs->factors.empty()
               || specs->threads_per_transform == 0
               || specs->workgroup_size % specs->threads_per_transform != 0
               || specs->length % specs->factors.front() != 0)
                return false;

            size_t factor_product = 1;
            for(const auto factor : specs->factors)
            {
                if(!is_power_of_two(factor) || factor_product > specs->length / factor)
                    return false;
                factor_product *= factor;
            }
            return factor_product == specs->length;
        }();
        specs->static_initial_reg_load
            = pool_scheme == CS_KERNEL_STOCKHAM_BLOCK_RC
              && node.scheme == CS_KERNEL_STOCKHAM_BLOCK_RC
              && node.sbrcTranstype == TILE_ALIGNED
              && node.precision == rocfft_precision_double
              && node.ebtype == EmbeddedType::NONE
              && callback_type == CallbackType::NONE
              && specs->direct_to_from_reg
              && static_pow2_sbrc_map;
        specs->static_initial_reg_load_linear
            = specs->static_initial_reg_load
              && node.dir2regMode != DirectRegType::TRY_ENABLE_IF_SUPPORT;

        // The local SBRC-512 kernel is shared by several large 1D FFTs.
        // Select the recurrence using the complete plan length, not the
        // local transform length, and carry that decision into the RTC key.
        const TreeNode* plan_root = &node;
        while(plan_root->parent != nullptr)
            plan_root = plan_root->parent;
        const bool full_transform_is_128k = plan_root->dimension == 1
                                             && plan_root->length.size() == 1
                                             && plan_root->length.front() == 131072;
        specs->sbrc_ordinary_twiddle_recurrence
            = specs->static_initial_reg_load && full_transform_is_128k
              && specs->length == 512 && specs->workgroup_size == 512
              && specs->threads_per_transform == 128
              && specs->factors == std::vector<unsigned int>{8, 8, 8};

        specs->real_io = node.real_io;
        if(node.real_io.IsCCLocal())
        {
            specs->direct_to_from_reg=true;
            specs->static_initial_reg_load=true;
            specs->static_initial_reg_load_linear=pool_scheme==CS_KERNEL_STOCKHAM_BLOCK_RC;
            if(node.real_io.IsInputBoundary())
                specs->real_io.load=RealBlockLoad::Registers;
            else if(node.real_io.role==RealBlockRole::PackedInverseRows)
                specs->real_io.load=RealBlockIO::CanRegisterPre(specs->length,specs->factors.front(),specs->threads_per_transform)
                    ?RealBlockLoad::Registers:RealBlockLoad::LDS;
            else
                specs->real_io.load=RealBlockIO::CanRegisterInput(specs->length,specs->factors,
                    specs->threads_per_transform,specs->workgroup_size)
                    ?RealBlockLoad::Registers:RealBlockLoad::LDS;
        }
        // The ordinary CC LDS entry uses an unswizzled complex staging layout.
        if(node.real_io.role == RealBlockRole::HermitianColumns
           && node.dir2regMode != DirectRegType::TRY_ENABLE_IF_SUPPORT)
            specs->half_lds = false;
        if(node.real_io.role == RealBlockRole::LocalRealRows)
        {
            specs->direct_to_from_reg = true;
            specs->static_initial_reg_load = true;
            specs->static_initial_reg_load_linear = true;
            specs->sbrc_ordinary_twiddle_recurrence = false;
        }

        if(node.real_io.role == RealBlockRole::PairedPostRows)
        {
            // Preserve Q=512 scalar LDS exchanges in both initial load modes.
            specs->direct_to_from_reg = true;
            specs->static_initial_reg_load = node.real_io.load == RealBlockLoad::Registers
                                             && callback_type == CallbackType::NONE;
            specs->static_initial_reg_load_linear = specs->static_initial_reg_load;
            specs->sbrc_ordinary_twiddle_recurrence = false;
        }


 return {specs->half_lds,specs->direct_to_from_reg,specs->static_initial_reg_load,specs->static_initial_reg_load_linear,specs->sbrc_ordinary_twiddle_recurrence,static_cast<size_t>(specs->real_io.role),static_cast<size_t>(specs->real_io.load),specs->length};
}
}
namespace after {
#include "/public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/include/real_block_io.h"

struct StockhamGeneratorSpecs {
 std::vector<unsigned int> factors;
 unsigned int length, workgroup_size, threads_per_transform;
 bool half_lds, direct_to_from_reg;
 bool static_initial_reg_load=false, static_initial_reg_load_linear=false;
 bool sbrc_ordinary_twiddle_recurrence=false;
 RealBlockIO real_io;
};
struct TreeNode {
 int scheme=CS_KERNEL_STOCKHAM_BLOCK_RC, sbrcTranstype=TILE_ALIGNED, precision=rocfft_precision_double;
 EmbeddedType ebtype=EmbeddedType::NONE;
 DirectRegType dir2regMode=DirectRegType::TRY_ENABLE_IF_SUPPORT;
 CallbackType callback_type=CallbackType::NONE;
 RealBlockIO real_io;
 const TreeNode* parent=nullptr;
 int dimension=1;
 std::vector<size_t> length={131072};
 CallbackType GetCallbackType(bool enable) const {return enable?callback_type:CallbackType::NONE;}
};
static bool sbrc_static_load_available(const StockhamGeneratorSpecs& specs)
{
    if(!IsPo2(specs.length) || specs.factors.empty() || !specs.threads_per_transform
       || specs.workgroup_size % specs.threads_per_transform)
        return false;

    return std::all_of(specs.factors.begin(), specs.factors.end(), [](unsigned int factor) {
        return IsPo2(factor);
    });
}

Output run(const std::vector<unsigned int>& factors, unsigned int workgroup, unsigned int threads, int scheme, int role, int precision, int embedded, int callback, int mode, bool half, bool direct, int rootkind, int tile, int load) {

 std::optional<StockhamGeneratorSpecs> specs;
 specs.emplace();
 specs->factors=factors;
 specs->length=std::accumulate(factors.begin(),factors.end(),1u,std::multiplies<unsigned int>());
 specs->workgroup_size=workgroup;
 specs->threads_per_transform=threads;
 specs->half_lds=half;
 specs->direct_to_from_reg=direct;
 TreeNode root;
 if(rootkind==1) root.length={65536};
 if(rootkind==2) root.dimension=2;
 if(rootkind==3) root.length={131072,1};
 TreeNode parent;parent.parent=&root;
 TreeNode node;
 node.parent=&parent;
 node.scheme=scheme;
 node.sbrcTranstype=tile;
 node.precision=precision;
 node.ebtype=static_cast<EmbeddedType>(embedded);
 node.callback_type=static_cast<CallbackType>(callback);
 node.dir2regMode=static_cast<DirectRegType>(mode);
 node.real_io.role=static_cast<RealBlockRole>(role);
 node.real_io.load=static_cast<RealBlockLoad>(load);
 const bool enable_callbacks=true;
 auto pool_scheme=scheme==CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z?CS_KERNEL_STOCKHAM_BLOCK_RC:scheme;
        const auto callback_type = node.GetCallbackType(enable_callbacks);
        const bool ordinary_sbrc
            = node.scheme == CS_KERNEL_STOCKHAM_BLOCK_RC && node.sbrcTranstype == TILE_ALIGNED
              && node.precision == rocfft_precision_double && node.ebtype == EmbeddedType::NONE
              && callback_type == CallbackType::NONE && specs->direct_to_from_reg;

        specs->real_io = node.real_io;
        switch(node.real_io.role)
        {
        case RealBlockRole::FoldedPackedColumns:
        case RealBlockRole::PackedInverseRows:
        case RealBlockRole::LocalPostColumns:
        case RealBlockRole::FoldedSpectrumRows:
            specs->direct_to_from_reg             = true;
            specs->static_initial_reg_load        = true;
            specs->static_initial_reg_load_linear = pool_scheme == CS_KERNEL_STOCKHAM_BLOCK_RC;
            specs->real_io.load                   = RealBlockLoad::Registers;
            if(node.real_io.role == RealBlockRole::PackedInverseRows
               && !RealBlockIO::CanRegisterPre(
                   specs->length, specs->factors.front(), specs->threads_per_transform))
                specs->real_io.load = RealBlockLoad::LDS;
            if(node.real_io.role == RealBlockRole::FoldedSpectrumRows
               && !RealBlockIO::CanRegisterInput(specs->threads_per_transform,
                                                 specs->workgroup_size))
                specs->real_io.load = RealBlockLoad::LDS;
            break;
        case RealBlockRole::LocalRealRows:
            specs->direct_to_from_reg             = true;
            specs->static_initial_reg_load        = true;
            specs->static_initial_reg_load_linear = true;
            break;
        case RealBlockRole::PairedPostRows:
            // Preserve scalar LDS exchanges when callbacks require the ordinary load.
            specs->direct_to_from_reg = true;
            specs->static_initial_reg_load
                = node.real_io.load == RealBlockLoad::Registers && callback_type == CallbackType::NONE;
            specs->static_initial_reg_load_linear = specs->static_initial_reg_load;
            break;
        case RealBlockRole::HermitianColumns:
            // The ordinary CC LDS entry uses an unswizzled complex staging layout.
            if(node.dir2regMode != DirectRegType::TRY_ENABLE_IF_SUPPORT)
                specs->half_lds = false;
            [[fallthrough]];
        default:
            specs->static_initial_reg_load = ordinary_sbrc && sbrc_static_load_available(*specs);
            specs->static_initial_reg_load_linear
                = specs->static_initial_reg_load
                  && node.dir2regMode != DirectRegType::TRY_ENABLE_IF_SUPPORT;
            break;
        }

        // This exact map already satisfies the static-load geometry.  CC-local
        // kernels retain the ordinary recurrence selected before overriding loads.
        if(ordinary_sbrc && node.real_io.role != RealBlockRole::LocalRealRows
           && node.real_io.role != RealBlockRole::PairedPostRows && specs->length == 512
           && specs->workgroup_size == 512 && specs->threads_per_transform == 128
           && specs->factors == std::vector<unsigned int>{8, 8, 8})
        {
            const TreeNode* plan_root = &node;
            while(plan_root->parent != nullptr)
                plan_root = plan_root->parent;
            specs->sbrc_ordinary_twiddle_recurrence
                = plan_root->dimension == 1 && plan_root->length.size() == 1
                  && plan_root->length.front() == 131072;
        }


 return {specs->half_lds,specs->direct_to_from_reg,specs->static_initial_reg_load,specs->static_initial_reg_load_linear,specs->sbrc_ordinary_twiddle_recurrence,static_cast<size_t>(specs->real_io.role),static_cast<size_t>(specs->real_io.load),specs->length};
}
}

int main() {
 const std::vector<std::vector<unsigned int>> factors={{1},{2,2},{8,4,8},{8,8,8},{8,8,4,4},{5,5,5,5},{11,11,11},{3,3,3},{7,7,7}};
 size_t checked=0;
 for(const auto& f:factors) for(unsigned int w:{128,256,512,224}) for(unsigned int t:{0,8,32,64,128})
 for(int scheme=0;scheme<4;++scheme) for(int role=0;role<8;++role) for(int p=0;p<3;++p)
 for(int e=0;e<2;++e) for(int c=0;c<2;++c) for(int mode=0;mode<2;++mode)
 for(int half=0;half<2;++half) for(int direct=0;direct<2;++direct) for(int root=0;root<4;++root)
 for(int tile=0;tile<2;++tile) for(int load=0;load<2;++load) {
  auto a=before::run(f,w,t,scheme,role,p,e,c,mode,half,direct,root,tile,load);
  auto b=after::run(f,w,t,scheme,role,p,e,c,mode,half,direct,root,tile,load);
  if(a!=b) {std::printf("MISMATCH w%u t%u scheme%d role%d precision%d embedded%d callback%d mode%d half%d direct%d root%d tile%d load%d\n",w,t,scheme,role,p,e,c,mode,half,direct,root,tile,load);return 1;}
  ++checked;
 }
 std::printf("{\"comparisons\":%zu,\"mismatches\":0}\n",checked);
}
