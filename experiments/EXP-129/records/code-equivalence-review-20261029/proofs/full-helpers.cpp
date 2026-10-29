
#include <vector>
#include <array>
#include <string>
#include <memory>
#include <optional>
#include <map>
#include <tuple>
#include <iostream>
#include <cstdlib>
#include <stdexcept>
#include <random>
#include <algorithm>
using rocfft_precision=int;
constexpr int rocfft_precision_half=0,rocfft_precision_single=1,rocfft_precision_double=2;
constexpr int rocfft_placement_notinplace=0,rocfft_placement_inplace=1;
constexpr int rocfft_array_type_real=0,rocfft_array_type_hermitian_interleaved=1,rocfft_array_type_complex_interleaved=2,rocfft_array_type_hermitian_planar=3;
constexpr int CS_NONE=0,CS_L1D_CC=1,CS_KERNEL_STOCKHAM_BLOCK_CC=2,CS_KERNEL_STOCKHAM_BLOCK_RC=3,CS_L1D_CRT=4,CS_L1D_TRTRT=5;
constexpr int BFT_NONE=0,TILE_ALIGNED=1,TILE_UNALIGNED=2;
namespace EmbeddedType{constexpr int NONE=0;}
struct Device{std::string arch="gfx936";int warpSize=64;size_t sharedMemPerBlock=65536;};
bool is_device_gcn_arch(const Device& d,const char* arch){return d.arch==arch;}
bool IsPo2(size_t n){return n && !(n&(n-1));}
struct FMKey{size_t length;int precision,scheme,tile;FMKey(size_t l,int p,int s,int t=0):length(l),precision(p),scheme(s),tile(t){}};
struct FFTKernel{size_t transforms_per_block=8;bool direct_to_from_reg=true,half_lds=true;std::array<int,2> threads_per_transform{32,0};int workgroup_size=256;std::vector<size_t> factors{4,4,4,4};};
struct function_pool{
 FFTKernel cc;bool ccPresent=true,alignedPresent=true,unalignedPresent=true;size_t largest=4096;int rowVariant=0;
 bool has_function(FMKey k)const{return k.scheme==CS_KERNEL_STOCKHAM_BLOCK_CC?ccPresent:(k.tile==TILE_UNALIGNED?unalignedPresent:alignedPresent);}
 FFTKernel get_kernel(FMKey k)const{if(k.scheme==CS_KERNEL_STOCKHAM_BLOCK_CC)return cc;FFTKernel x;x.half_lds=false;if(k.length==512){x.transforms_per_block=4;x.threads_per_transform[0]=128;x.workgroup_size=512;x.factors={8,8,8};}if(rowVariant==1)x.workgroup_size+=1;if(rowVariant==2)x.factors={2,2};if(rowVariant==3)x.transforms_per_block=3;if(rowVariant==4)x.threads_per_transform[0]+=1;return x;}
 bool has_SBCC_kernel(size_t,int)const{return ccPresent;}
 bool has_SBRC_kernel(size_t,int)const{return alignedPresent;}
 size_t get_largest_pow2_length(int)const{return largest;}
};

#include <sstream>
#include <iomanip>
#include "/public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/include/real_block_io.h"
constexpr int OB_TEMP=1,OB_USER_OUT=2;
struct TreeNode {
 int scheme=CS_L1D_CC,fuseBlue=BFT_NONE,ebtype=EmbeddedType::NONE,dimension=1;
 std::vector<size_t> length{128,256},outputLength,inStride,outStride;
 size_t large1D=0,iDist=65536,oDist=65536;
 bool largeTwdBatchIsTransformCount=true,allowInplace=true;
 int allowedOutBuf=0,assignCalls=0;
 std::vector<int> allowedOutArrayTypes;
 std::vector<std::string> comments;
 RealBlockIO real_io;
 TreeNode* parent=nullptr;
 std::vector<std::shared_ptr<TreeNode>> childNodes;
 void AssignParams(){++assignCalls;}
};
template<class T> void sequence(std::ostream& out,const std::vector<T>& values){
 out<<'[';for(const auto& x:values)out<<x<<',';out<<']';
}
std::string signature(const TreeNode& n){
 std::ostringstream out;
 out<<n.scheme<<'|'<<n.fuseBlue<<'|'<<n.ebtype<<'|'<<n.dimension<<'|';
 sequence(out,n.length);sequence(out,n.outputLength);sequence(out,n.inStride);sequence(out,n.outStride);
 out<<'|'<<n.large1D<<'|'<<n.iDist<<'|'<<n.oDist<<'|'<<n.largeTwdBatchIsTransformCount<<'|'<<n.allowInplace<<'|'<<n.allowedOutBuf<<'|'<<n.assignCalls;
 sequence(out,n.allowedOutArrayTypes);for(const auto& text:n.comments)out<<std::quoted(text);
 const auto& io=n.real_io;
 out<<'|'<<int(io.role)<<'|'<<int(io.load)<<'|'<<io.n<<'|'<<io.columns<<'|'<<io.rows<<'|'<<io.pitch;
 for(const auto& child:n.childNodes)out<<"{parent="<<(child->parent==&n)<<':'<<signature(*child)<<'}';
 return out.str();
}
struct NodeMetaData{std::vector<size_t> length;int precision=rocfft_precision_double;Device deviceProp;};
using Map1DLength=std::map<size_t,size_t>;
namespace before {

int ROCFFT_CC_REAL_FUSION=1,ROCFFT_CC_LOCAL_REAL_FUSION=1;
struct RealTransEvenNode:TreeNode{
 int dimension=1,direction=1,precision=rocfft_precision_double,placement=rocfft_placement_notinplace,inArrayType=rocfft_array_type_hermitian_interleaved,outArrayType=rocfft_array_type_real;
 size_t batch=1,iOffset=0,oOffset=0;std::vector<size_t> inStride{1},outStride{1};Device deviceProp;function_pool pool;int selected=0;bool built=false;bool local_real_pipeline=false,cc_local_pipeline=false;
 bool CanFuseCCReal()const;bool CCRealKernelsAvailable(size_t,size_t)const;
 bool TryBuildCCLocalTree(const TreeNode&,size_t);bool TryBuildLocalRealTree(size_t);bool TryFusePairedPost(TreeNode&,size_t);
 void AssignCCLocalParams();void AssignLocalRealParams();void Route(TreeNode&,size_t,bool);
};
struct NodeFactory{
 static std::unique_ptr<TreeNode> CreateNodeFromScheme(int s,TreeNode* parent){
  auto node=std::make_unique<TreeNode>();node->scheme=s;node->parent=parent;node->length.clear();return node;
 }
static Map1DLength map1DLengthSingle,map1DLengthDouble;static bool Get1DBlockComputeDivisor(const function_pool&,int,size_t,size_t&,bool&);static std::tuple<int,bool,size_t> Planner(const function_pool&,NodeMetaData);};
Map1DLength NodeFactory::map1DLengthSingle,NodeFactory::map1DLengthDouble;

bool RealTransEvenNode::TryBuildCCLocalTree(const TreeNode& cfft, size_t n)
{
    if(!ROCFFT_CC_REAL_FUSION || !ROCFFT_CC_LOCAL_REAL_FUSION || n < 65536 || n % 2
        || dimension != 1 || length.size() != 1 || batch != 1
        || precision != rocfft_precision_double || placement != rocfft_placement_notinplace
        || inStride != std::vector<size_t> { 1 } || outStride != std::vector<size_t> { 1 }
        || iOffset || oOffset || !is_device_gcn_arch(deviceProp, "gfx936")
        || deviceProp.warpSize != 64 || cfft.scheme != CS_L1D_CC || cfft.childNodes.size() != 2)
        return false;
    const bool inverse = direction == 1;
    if((inverse
           && (inArrayType != rocfft_array_type_hermitian_interleaved
               || outArrayType != rocfft_array_type_real))
        || (!inverse
            && (inArrayType != rocfft_array_type_real
                || outArrayType != rocfft_array_type_hermitian_interleaved)))
        return false;
    const auto& col = *cfft.childNodes.front();
    const auto& row = *cfft.childNodes.back();
    if(col.scheme != CS_KERNEL_STOCKHAM_BLOCK_CC || row.scheme != CS_KERNEL_STOCKHAM_BLOCK_RC
        || col.length.size() != 2 || row.length.size() != 2 || col.ebtype != EmbeddedType::NONE
        || row.ebtype != EmbeddedType::NONE || col.fuseBlue != BFT_NONE || row.fuseBlue != BFT_NONE)
        return false;
    const size_t c = col.length[0], q = col.length[1];
    if(!c || !q || c * q != n / 2 || row.length != std::vector<size_t> { q, c }
        || n > (size_t(1) << 24))
        return false;
    const FMKey cc_key(c, precision, CS_KERNEL_STOCKHAM_BLOCK_CC);
    const FMKey aligned(q, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, TILE_ALIGNED);
    if(!pool.has_function(cc_key) || !pool.has_function(aligned))
        return false;
    const auto cc = pool.get_kernel(cc_key), rc = pool.get_kernel(aligned);
    const auto transpose = c % rc.transforms_per_block ? TILE_UNALIGNED : TILE_ALIGNED;
    if(!pool.has_function(FMKey(q, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, transpose))
        || !cc.direct_to_from_reg || q < cc.transforms_per_block
        || c * cc.transforms_per_block / (cc.half_lds ? 2 : 1) < c)
        return false;
    const size_t cc_bytes = c * cc.transforms_per_block * 16 / (cc.half_lds ? 2 : 1);
    if(cc_bytes > deviceProp.sharedMemPerBlock
        || q * rc.transforms_per_block * 16 > deviceProp.sharedMemPerBlock)
        return false;

    RealBlockIO io { RealBlockRole::None, RealBlockLoad::LDS, n, c, q, q };
    auto first = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_CC, this);
    first->dimension = 1;
    first->length = { c, q + (inverse ? 1 : 0) };
    first->outputLength = { c, q };
    first->real_io = io;
    first->real_io.role
        = inverse ? RealBlockRole::FoldedPackedColumns : RealBlockRole::LocalPostColumns;
    first->large1D = inverse ? n : 0;
    first->largeTwdBatchIsTransformCount = false;
    first->allowInplace = false;
    first->allowedOutBuf = OB_TEMP;
    first->allowedOutArrayTypes = { rocfft_array_type_complex_interleaved };
    first->comments.push_back(
        inverse ? "EXP128 folded packed columns" : "EXP128 column-local real post");
    auto last = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_RC, this);
    last->dimension = 1;
    last->length = { q, c };
    last->outputLength = { c, q };
    last->real_io = io;
    last->real_io.role
        = inverse ? RealBlockRole::PackedInverseRows : RealBlockRole::FoldedSpectrumRows;
    last->allowInplace = false;
    last->allowedOutBuf = OB_USER_OUT;
    last->allowedOutArrayTypes = { rocfft_array_type_complex_interleaved };
    last->comments.push_back(
        inverse ? "EXP128 row-local real pre" : "EXP128 folded half spectrum and terminal row");
    childNodes.emplace_back(std::move(first));
    childNodes.emplace_back(std::move(last));
    cc_local_pipeline = true;
    return true;
}
bool RealTransEvenNode::TryBuildLocalRealTree(size_t n)
{
    auto geometry = RealBlockIO::ForLength(n);
    if(!geometry || dimension != 1 || length.size() != 1 || batch != 1
       || direction != 1 || precision != rocfft_precision_double
       || placement != rocfft_placement_notinplace
       || inArrayType != rocfft_array_type_hermitian_interleaved
       || outArrayType != rocfft_array_type_real
       || inStride != std::vector<size_t>{1} || outStride != std::vector<size_t>{1}
       || iOffset != 0 || oOffset != 0)
        return false;

    auto io = *geometry;
    const char* mode = std::getenv("ROCFFT_EXP125_LOCAL_REAL_LOAD");
    if(mode && std::string(mode) == "lds")
        io.load = RealBlockLoad::LDS;
    else if(mode && std::string(mode) != "registers")
        throw std::runtime_error("invalid EXP125 local real load mode");
    // The Q=512 producer map requires a complete 64-lane subgroup.
    if(io.rows == 512 && deviceProp.warpSize < 64)
        io.load = RealBlockLoad::LDS;

    FMKey cc_key(io.columns, precision, CS_KERNEL_STOCKHAM_BLOCK_CC);
    FMKey rc_key(io.rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, TILE_ALIGNED);
    if(!pool.has_function(cc_key) || !pool.has_function(rc_key))
        return false;
    const auto rc = pool.get_kernel(rc_key);
    const size_t expected_threads = io.rows == 256 ? 32 : 128;
    const std::vector<size_t> expected_factors
        = io.rows == 256 ? std::vector<size_t>{4, 4, 4, 4}
                         : std::vector<size_t>{8, 8, 8};
    if(rc.threads_per_transform[0] != expected_threads || rc.factors != expected_factors
       || rc.workgroup_size % expected_threads != 0
       || (rc.workgroup_size / expected_threads) % 2 != 0
       || io.columns % rc.transforms_per_block != 0)
        return false;

    auto first = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_CC, this);
    first->dimension = 1;
    first->length = {io.columns, io.rows + 1};
    first->outputLength = first->length;
    first->real_io = io;
    first->real_io.role = RealBlockRole::HermitianColumns;
    first->large1D = io.n;
    first->largeTwdBatchIsTransformCount = false;
    first->allowInplace = false;
    first->allowedOutBuf = OB_TEMP;
    first->allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    first->comments.push_back("EXP125 local real: folded Hermitian columns");

    auto last = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_RC, this);
    last->dimension = 1;
    last->length = {io.rows, io.columns};
    last->outputLength = {io.columns, io.rows};
    last->real_io = io;
    last->real_io.role = RealBlockRole::LocalRealRows;
    last->allowInplace = false;
    last->allowedOutBuf = OB_USER_OUT;
    last->allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    last->comments.push_back("EXP125 local real: paired rows and adjacent real stores");
    childNodes.emplace_back(std::move(first));
    childNodes.emplace_back(std::move(last));
    local_real_pipeline = true;
    return true;
}
bool RealTransEvenNode::TryFusePairedPost(TreeNode& cfft, size_t n)
{
    auto geometry = RealBlockIO::ForLength(n);
    if(!geometry || dimension != 1 || length.size() != 1 || batch != 1
       || direction != -1 || precision != rocfft_precision_double
       || placement != rocfft_placement_notinplace
       || inArrayType != rocfft_array_type_real
       || outArrayType != rocfft_array_type_hermitian_interleaved
       || inStride != std::vector<size_t>{1} || outStride != std::vector<size_t>{1}
       || iOffset != 0 || oOffset != 0 || !is_device_gcn_arch(deviceProp, "gfx936")
       || deviceProp.warpSize != 64 || cfft.scheme != CS_L1D_CC
       || cfft.childNodes.size() != 2)
        return false;

    auto io = *geometry;
    io.role = RealBlockRole::PairedPostRows;
    io.pitch = io.rows; // Keep the ordinary packed CC intermediate matrix.
    const char* mode = std::getenv("ROCFFT_EXP125_REAL_POST_LOAD");
    if(mode && std::string(mode) == "lds")
        io.load = RealBlockLoad::LDS;
    else if(mode && std::string(mode) != "registers")
        throw std::runtime_error("invalid EXP125 real post load mode");

    auto& first = *cfft.childNodes.front();
    auto& last = *cfft.childNodes.back();
    if(first.scheme != CS_KERNEL_STOCKHAM_BLOCK_CC
       || last.scheme != CS_KERNEL_STOCKHAM_BLOCK_RC
       || first.length != std::vector<size_t>{io.columns, io.rows}
       || last.length != std::vector<size_t>{io.rows, io.columns}
       || first.large1D != n / 2 || last.ebtype != EmbeddedType::NONE)
        return false;
    FMKey rc_key(io.rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, TILE_ALIGNED);
    if(!pool.has_function(rc_key))
        return false;
    const auto rc = pool.get_kernel(rc_key);
    const size_t threads = io.rows == 256 ? 32 : 128;
    const size_t workgroup = io.rows == 256 ? 256 : 512;
    const std::vector<size_t> factors = io.rows == 256 ? std::vector<size_t>{4, 4, 4, 4}
                                                     : std::vector<size_t>{8, 8, 8};
    if(rc.threads_per_transform[0] != threads || rc.workgroup_size != workgroup
       || rc.factors != factors || rc.transforms_per_block != workgroup / threads
       || io.columns % rc.transforms_per_block != 0)
        return false;

    first.allowInplace = false;
    first.allowedOutBuf = OB_TEMP;
    first.allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    last.real_io = io;
    last.allowInplace = false;
    last.allowedOutBuf = OB_USER_OUT;
    last.allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    last.comments.push_back("EXP125 real post: paired mirror rows and fused half spectrum stores");
    cfft.allowInplace = false;
    cfft.outputLength = {n / 2 + 1};
    return true;
}
void RealTransEvenNode::AssignCCLocalParams()
{
    auto& first = childNodes.front();
    auto& last = childNodes.back();
    const auto& io = first->real_io;
    first->inStride = { direction == 1 ? 2 * io.rows : io.rows, 1 };
    first->iDist = direction == 1 ? iDist : iDist / 2;
    first->outStride = { io.rows, 1 };
    first->oDist = io.columns * io.rows;
    last->inStride = { 1, io.rows };
    last->iDist = first->oDist;
    last->outStride = { 1, io.columns };
    last->oDist = direction == 1 ? oDist / 2 : oDist;
    first->AssignParams();
    last->AssignParams();
}
void RealTransEvenNode::AssignLocalRealParams()
{
    const auto& io = childNodes.front()->real_io;
    auto& first = childNodes.front();
    auto& last = childNodes.back();
    first->inStride = {2 * io.rows, 1};
    first->iDist = iDist;
    first->outStride = {io.pitch, 1};
    first->oDist = io.columns * io.pitch;
    last->inStride = {1, io.pitch};
    last->iDist = first->oDist;
    last->outStride = {1, io.columns};
    last->oDist = oDist / 2;
    first->AssignParams();
    last->AssignParams();
}
void RealTransEvenNode::Route(TreeNode& cfft, size_t n, bool noSolution) {
const std::vector<size_t> real_lengths{n};const auto* realLength=&real_lengths; TreeNode* cfftPlan=&cfft; selected=0; built=false;
    // Fastest moving dimension must be even:
    if(realLength->at(0) % 2 != 0)
        throw std::runtime_error("fastest dimension is not even in RealTransEvenNode");

    if(noSolution && ROCFFT_CC_REAL_FUSION && !ROCFFT_CC_LOCAL_REAL_FUSION
       && TryBuildLocalRealTree(realLength->at(0)))
        return;

built=true;
    if(noSolution && TryBuildCCLocalTree(*cfftPlan,realLength->at(0)))
        return;
    if(noSolution && ROCFFT_CC_REAL_FUSION && ROCFFT_CC_LOCAL_REAL_FUSION
       && TryBuildLocalRealTree(realLength->at(0)))
        return;
    if(noSolution && ROCFFT_CC_REAL_FUSION && TryFusePairedPost(*cfftPlan, realLength->at(0)))
    {

        return;
    }

}

bool NodeFactory::Get1DBlockComputeDivisor(const function_pool& pool,
                                           rocfft_precision     precision,
                                           size_t               length,
                                           size_t&              divLength1,
                                           bool&                mapEntryFound)
{
    mapEntryFound = false;
    const Map1DLength* map1DLength = nullptr;
    if(precision == rocfft_precision_single || precision == rocfft_precision_half)
        map1DLength = &NodeFactory::map1DLengthSingle;
    else if(precision == rocfft_precision_double)
        map1DLength = &NodeFactory::map1DLengthDouble;
    else
        return false;

    const auto it = map1DLength->find(length);
    if(it == map1DLength->end())
        return false;

    mapEntryFound = true;
    const auto candidate = it->second;
    if(candidate == 0 || length % candidate != 0)
        return false;

    if(!pool.has_SBCC_kernel(candidate, precision)
       || !pool.has_SBRC_kernel(length / candidate, precision))
        return false;

    divLength1 = candidate;
    return true;
}
std::tuple<int,bool,size_t> NodeFactory::Planner(const function_pool& pool, NodeMetaData nodeData) { int scheme=CS_NONE;
    constexpr size_t legacy_block_compute_map_threshold = 524288;
    size_t            divLength1                         = 1;
    bool              failed                             = false;

    if(IsPo2(nodeData.length[0])) // multiple kernels involving transpose
    {
        bool mapEntryFound = false;
        if(Get1DBlockComputeDivisor(pool,
                                    nodeData.precision,
                                    nodeData.length[0],
                                    divLength1,
                                    mapEntryFound))
        {
            // for gfx906, 512 CC/RC isn't as fast, so use CRT
            // with a nicer length
            if((is_device_gcn_arch(nodeData.deviceProp, "gfx906")) && nodeData.length[0] == 262144)
            {
                divLength1 = 64;
                scheme     = CS_L1D_CRT;
            }
            else
            {
                scheme = CS_L1D_CC;
            }
        }
        else if(!mapEntryFound
                && nodeData.length[0] <= legacy_block_compute_map_threshold)
        {
            // Preserve the legacy missing-map failure in the old block range.
            // A mapped pair that fails the LDS-aware kernel checks still falls
            // through to the TRTRT fallback below.
            scheme = CS_L1D_CC;
            failed = true;
        }
        else
        {
            // get largest pow2 1D length
            auto largest = pool.get_largest_pow2_length(nodeData.precision);

            // need to ignore len 1, or we're going into a infinity decompostion loop
            // basically not gonna happen unless someone builds only a len1 kernel...
            if(largest <= 1)
            {
                failed = true;
            }
            else if(nodeData.length[0] > largest * largest)
            {
                divLength1 = nodeData.length[0] / largest;
            }
            else
            {
                size_t in_x = 0;
                size_t len  = nodeData.length[0];
                while(len != 1)
                {
                    len >>= 1;
                    in_x++;
                }
                in_x /= 2;
                divLength1 = (size_t)1 << in_x;
            }
            scheme = CS_L1D_TRTRT;
        }
    }
return {scheme,failed,divLength1};}

}

namespace after {

int ROCFFT_CC_REAL_FUSION=1,ROCFFT_CC_LOCAL_REAL_FUSION=1;
struct RealTransEvenNode:TreeNode{
 int dimension=1,direction=1,precision=rocfft_precision_double,placement=rocfft_placement_notinplace,inArrayType=rocfft_array_type_hermitian_interleaved,outArrayType=rocfft_array_type_real;
 size_t batch=1,iOffset=0,oOffset=0;std::vector<size_t> inStride{1},outStride{1};Device deviceProp;function_pool pool;int selected=0;bool built=false;bool local_real_pipeline=false,cc_local_pipeline=false;
 bool CanFuseCCReal()const;bool CCRealKernelsAvailable(size_t,size_t)const;
 bool TryBuildCCLocalTree(const TreeNode&,size_t);bool TryBuildLocalRealTree(size_t);bool TryFusePairedPost(TreeNode&,size_t);
 void AssignCCLocalParams();void AssignLocalRealParams();void Route(TreeNode&,size_t,bool);
};
struct NodeFactory{
 static std::unique_ptr<TreeNode> CreateNodeFromScheme(int s,TreeNode* parent){
  auto node=std::make_unique<TreeNode>();node->scheme=s;node->parent=parent;node->length.clear();return node;
 }
static Map1DLength map1DLengthSingle,map1DLengthDouble;static bool Get1DBlockComputeDivisor(const function_pool&,int,size_t,size_t&,bool&);static std::tuple<int,bool,size_t> Planner(const function_pool&,NodeMetaData);};
Map1DLength NodeFactory::map1DLengthSingle,NodeFactory::map1DLengthDouble;

bool RealTransEvenNode::CanFuseCCReal() const
{
    if(dimension != 1 || length.size() != 1 || batch != 1
       || precision != rocfft_precision_double || placement != rocfft_placement_notinplace)
        return false;

    if(inStride.size() != 1 || outStride.size() != 1 || inStride.front() != 1
       || outStride.front() != 1 || iOffset || oOffset)
        return false;

    if(direction == 1)
        return inArrayType == rocfft_array_type_hermitian_interleaved
               && outArrayType == rocfft_array_type_real;

    return inArrayType == rocfft_array_type_real
           && outArrayType == rocfft_array_type_hermitian_interleaved;
}
bool RealTransEvenNode::CCRealKernelsAvailable(size_t columns, size_t rows) const
{
    const FMKey cc_key(columns, precision, CS_KERNEL_STOCKHAM_BLOCK_CC);
    const FMKey rc_key(rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, TILE_ALIGNED);
    if(!pool.has_function(cc_key) || !pool.has_function(rc_key))
        return false;

    const auto cc = pool.get_kernel(cc_key);
    const auto rc = pool.get_kernel(rc_key);
    const auto transpose = columns % rc.transforms_per_block ? TILE_UNALIGNED : TILE_ALIGNED;
    if(!pool.has_function(FMKey(rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, transpose)))
        return false;

    const size_t lds_divisor = cc.half_lds ? 2 : 1;
    if(!cc.direct_to_from_reg || rows < cc.transforms_per_block
       || cc.transforms_per_block < lds_divisor)
        return false;

    const size_t complex_bytes = 2 * sizeof(double);
    const size_t cc_bytes      = columns * cc.transforms_per_block * complex_bytes / lds_divisor;
    const size_t rc_bytes      = rows * rc.transforms_per_block * complex_bytes;
    return cc_bytes <= deviceProp.sharedMemPerBlock && rc_bytes <= deviceProp.sharedMemPerBlock;
}
static RealBlockLoad real_block_load(const char* variable, const char* error)
{
    const char* value = std::getenv(variable);
    if(!value)
        return RealBlockLoad::Registers;

    const std::string mode(value);
    if(mode == "registers")
        return RealBlockLoad::Registers;
    if(mode == "lds")
        return RealBlockLoad::LDS;
    throw std::runtime_error(error);
}
bool RealTransEvenNode::TryBuildCCLocalTree(const TreeNode& cfft, size_t n)
{
    if(n < 65536 || n > (size_t(1) << 24) || cfft.scheme != CS_L1D_CC
       || cfft.fuseBlue != BFT_NONE)
        return false;

    if(!is_device_gcn_arch(deviceProp, "gfx936") || deviceProp.warpSize != 64)
        return false;

    // CC construction has already established the two factors and leaf schemes.
    const auto& col = *cfft.childNodes.front();
    const size_t c = col.length[0], q = col.length[1];
    if(!CCRealKernelsAvailable(c, q))
        return false;

    const bool inverse = direction == 1;
    RealBlockIO io { RealBlockRole::None, RealBlockLoad::LDS, n, c, q, q };
    auto first = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_CC, this);
    first->dimension = 1;
    first->length = { c, q + (inverse ? 1 : 0) };
    first->outputLength = { c, q };
    first->real_io = io;
    first->real_io.role
        = inverse ? RealBlockRole::FoldedPackedColumns : RealBlockRole::LocalPostColumns;
    first->large1D = inverse ? n : 0;
    first->largeTwdBatchIsTransformCount = false;
    first->allowInplace = false;
    first->allowedOutBuf = OB_TEMP;
    first->allowedOutArrayTypes = { rocfft_array_type_complex_interleaved };
    first->comments.push_back(
        inverse ? "EXP128 folded packed columns" : "EXP128 column-local real post");
    auto last = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_RC, this);
    last->dimension = 1;
    last->length = { q, c };
    last->outputLength = { c, q };
    last->real_io = io;
    last->real_io.role
        = inverse ? RealBlockRole::PackedInverseRows : RealBlockRole::FoldedSpectrumRows;
    last->allowInplace = false;
    last->allowedOutBuf = OB_USER_OUT;
    last->allowedOutArrayTypes = { rocfft_array_type_complex_interleaved };
    last->comments.push_back(
        inverse ? "EXP128 row-local real pre" : "EXP128 folded half spectrum and terminal row");
    childNodes.emplace_back(std::move(first));
    childNodes.emplace_back(std::move(last));
    cc_local_pipeline = true;
    return true;
}
bool RealTransEvenNode::TryBuildLocalRealTree(size_t n)
{
    auto geometry = RealBlockIO::ForLength(n);
    if(!geometry || direction != 1)
        return false;

    auto io = *geometry;
    io.load = real_block_load("ROCFFT_EXP125_LOCAL_REAL_LOAD",
                             "invalid EXP125 local real load mode");
    // The Q=512 producer map requires a complete 64-lane subgroup.
    if(io.rows == 512 && deviceProp.warpSize < 64)
        io.load = RealBlockLoad::LDS;

    FMKey cc_key(io.columns, precision, CS_KERNEL_STOCKHAM_BLOCK_CC);
    FMKey rc_key(io.rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, TILE_ALIGNED);
    if(!pool.has_function(cc_key) || !pool.has_function(rc_key))
        return false;
    const auto rc = pool.get_kernel(rc_key);
    const size_t expected_threads = io.rows == 256 ? 32 : 128;
    const std::vector<size_t> expected_factors
        = io.rows == 256 ? std::vector<size_t>{4, 4, 4, 4}
                         : std::vector<size_t>{8, 8, 8};
    if(rc.threads_per_transform[0] != expected_threads || rc.factors != expected_factors
       || rc.workgroup_size % expected_threads != 0
       || (rc.workgroup_size / expected_threads) % 2 != 0
       || io.columns % rc.transforms_per_block != 0)
        return false;

    auto first = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_CC, this);
    first->dimension = 1;
    first->length = {io.columns, io.rows + 1};
    first->outputLength = first->length;
    first->real_io = io;
    first->real_io.role = RealBlockRole::HermitianColumns;
    first->large1D = io.n;
    first->largeTwdBatchIsTransformCount = false;
    first->allowInplace = false;
    first->allowedOutBuf = OB_TEMP;
    first->allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    first->comments.push_back("EXP125 local real: folded Hermitian columns");

    auto last = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_RC, this);
    last->dimension = 1;
    last->length = {io.rows, io.columns};
    last->outputLength = {io.columns, io.rows};
    last->real_io = io;
    last->real_io.role = RealBlockRole::LocalRealRows;
    last->allowInplace = false;
    last->allowedOutBuf = OB_USER_OUT;
    last->allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    last->comments.push_back("EXP125 local real: paired rows and adjacent real stores");
    childNodes.emplace_back(std::move(first));
    childNodes.emplace_back(std::move(last));
    local_real_pipeline = true;
    return true;
}
bool RealTransEvenNode::TryFusePairedPost(TreeNode& cfft, size_t n)
{
    auto geometry = RealBlockIO::ForLength(n);
    if(!geometry || direction != -1 || cfft.scheme != CS_L1D_CC)
        return false;

    if(!is_device_gcn_arch(deviceProp, "gfx936") || deviceProp.warpSize != 64)
        return false;

    auto io = *geometry;
    io.role = RealBlockRole::PairedPostRows;
    io.pitch = io.rows; // Keep the ordinary packed CC intermediate matrix.
    io.load = real_block_load("ROCFFT_EXP125_REAL_POST_LOAD",
                             "invalid EXP125 real post load mode");

    auto& first = *cfft.childNodes.front();
    auto& last = *cfft.childNodes.back();
    // The other factor and the row layout follow from the CC decomposition.
    if(first.length[0] != io.columns)
        return false;
    FMKey rc_key(io.rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, TILE_ALIGNED);
    if(!pool.has_function(rc_key))
        return false;
    const auto rc = pool.get_kernel(rc_key);
    const size_t threads = io.rows == 256 ? 32 : 128;
    const size_t workgroup = io.rows == 256 ? 256 : 512;
    const std::vector<size_t> factors = io.rows == 256 ? std::vector<size_t>{4, 4, 4, 4}
                                                     : std::vector<size_t>{8, 8, 8};
    if(rc.threads_per_transform[0] != threads || rc.workgroup_size != workgroup
       || rc.factors != factors || rc.transforms_per_block != workgroup / threads
       || io.columns % rc.transforms_per_block != 0)
        return false;

    first.allowInplace = false;
    first.allowedOutBuf = OB_TEMP;
    first.allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    last.real_io = io;
    last.allowInplace = false;
    last.allowedOutBuf = OB_USER_OUT;
    last.allowedOutArrayTypes = {rocfft_array_type_complex_interleaved};
    last.comments.push_back("EXP125 real post: paired mirror rows and fused half spectrum stores");
    cfft.allowInplace = false;
    cfft.outputLength = {n / 2 + 1};
    return true;
}
void RealTransEvenNode::AssignCCLocalParams()
{
    auto& first = childNodes.front();
    auto& last = childNodes.back();
    const auto& io = first->real_io;
    first->inStride = { direction == 1 ? 2 * io.rows : io.rows, 1 };
    first->iDist = direction == 1 ? iDist : iDist / 2;
    first->outStride = { io.rows, 1 };
    first->oDist = io.columns * io.rows;
    last->inStride = { 1, io.rows };
    last->iDist = first->oDist;
    last->outStride = { 1, io.columns };
    last->oDist = direction == 1 ? oDist / 2 : oDist;
    first->AssignParams();
    last->AssignParams();
}
void RealTransEvenNode::AssignLocalRealParams()
{
    const auto& io = childNodes.front()->real_io;
    auto& first = childNodes.front();
    auto& last = childNodes.back();
    first->inStride = {2 * io.rows, 1};
    first->iDist = iDist;
    first->outStride = {io.pitch, 1};
    first->oDist = io.columns * io.pitch;
    last->inStride = {1, io.pitch};
    last->iDist = first->oDist;
    last->outStride = {1, io.columns};
    last->oDist = oDist / 2;
    first->AssignParams();
    last->AssignParams();
}
void RealTransEvenNode::Route(TreeNode& cfft, size_t n, bool noSolution) {
const std::vector<size_t> real_lengths{n};const auto* realLength=&real_lengths; TreeNode* cfftPlan=&cfft; selected=0; built=false;
    // Fastest moving dimension must be even:
    if(realLength->at(0) % 2 != 0)
        throw std::runtime_error("fastest dimension is not even in RealTransEvenNode");

    const bool try_cc_real = noSolution && ROCFFT_CC_REAL_FUSION && CanFuseCCReal();
    if(try_cc_real && !ROCFFT_CC_LOCAL_REAL_FUSION
       && TryBuildLocalRealTree(realLength->at(0)))
        return;

built=true;
    if(try_cc_real)
    {
        if(ROCFFT_CC_LOCAL_REAL_FUSION && TryBuildCCLocalTree(*cfftPlan, realLength->at(0)))
            return;
        if(ROCFFT_CC_LOCAL_REAL_FUSION && TryBuildLocalRealTree(realLength->at(0)))
            return;
        if(TryFusePairedPost(*cfftPlan, realLength->at(0)))
        {
    
            return;
        }
    }

}

std::tuple<int,bool,size_t> NodeFactory::Planner(const function_pool& pool, NodeMetaData nodeData) { int scheme=CS_NONE;
    constexpr size_t legacy_block_compute_map_threshold = 524288;
    size_t            divLength1                         = 1;
    bool              failed                             = false;

    if(IsPo2(nodeData.length[0])) // multiple kernels involving transpose
    {
        const auto& lengthMap = nodeData.precision == rocfft_precision_double
                                    ? map1DLengthDouble
                                    : map1DLengthSingle;
        const auto it = lengthMap.find(nodeData.length[0]);
        const bool mapped = (nodeData.precision == rocfft_precision_single
                             || nodeData.precision == rocfft_precision_half
                             || nodeData.precision == rocfft_precision_double)
                            && it != lengthMap.end();
        const size_t divisor = mapped ? it->second : 0;
        if(divisor && nodeData.length[0] % divisor == 0
           && pool.has_SBCC_kernel(divisor, nodeData.precision)
           && pool.has_SBRC_kernel(nodeData.length[0] / divisor, nodeData.precision))
        {
            divLength1 = divisor;
            // for gfx906, 512 CC/RC isn't as fast, so use CRT
            // with a nicer length
            if((is_device_gcn_arch(nodeData.deviceProp, "gfx906")) && nodeData.length[0] == 262144)
            {
                divLength1 = 64;
                scheme     = CS_L1D_CRT;
            }
            else
            {
                scheme = CS_L1D_CC;
            }
        }
        else if(!mapped && nodeData.length[0] <= legacy_block_compute_map_threshold)
        {
            // Preserve the legacy missing-map failure in the old block range.
            // A mapped pair that fails the LDS-aware kernel checks still falls
            // through to the TRTRT fallback below.
            scheme = CS_L1D_CC;
            failed = true;
        }
        else
        {
            // get largest pow2 1D length
            auto largest = pool.get_largest_pow2_length(nodeData.precision);

            // need to ignore len 1, or we're going into a infinity decompostion loop
            // basically not gonna happen unless someone builds only a len1 kernel...
            if(largest <= 1)
            {
                failed = true;
            }
            else if(nodeData.length[0] > largest * largest)
            {
                divLength1 = nodeData.length[0] / largest;
            }
            else
            {
                size_t in_x = 0;
                size_t len  = nodeData.length[0];
                while(len != 1)
                {
                    len >>= 1;
                    in_x++;
                }
                in_x /= 2;
                divLength1 = (size_t)1 << in_x;
            }
            scheme = CS_L1D_TRTRT;
        }
    }
return {scheme,failed,divLength1};}

}

struct Input{int dimension=1,direction=1,precision=2,placement=0,it=1,ot=0;size_t batch=1,io=0,oo=0;std::vector<size_t> len{65536},is{1},os{1};Device device;function_pool pool;size_t n=65536,c=128,q=256;int scheme=CS_L1D_CC,blue=0;};
template<class N> void init(N& n,const Input& in){n.dimension=in.dimension;n.direction=in.direction;n.precision=in.precision;n.placement=in.placement;n.inArrayType=in.it;n.outArrayType=in.ot;n.batch=in.batch;n.iOffset=in.io;n.oOffset=in.oo;n.length=in.len;n.inStride=in.is;n.outStride=in.os;n.deviceProp=in.device;n.pool=in.pool;}
TreeNode tree(const Input& in){TreeNode t;t.scheme=in.scheme;t.fuseBlue=in.blue;auto c=std::make_shared<TreeNode>();auto q=std::make_shared<TreeNode>();c->scheme=CS_KERNEL_STOCKHAM_BLOCK_CC;q->scheme=CS_KERNEL_STOCKHAM_BLOCK_RC;c->fuseBlue=q->fuseBlue=in.blue;c->length={in.c,in.q};q->length={in.q,in.c};c->large1D=in.n/2;t.childNodes={c,q};return t;}
template<class N> auto run(N& node,const Input& in,bool solution){init(node,in);auto t=tree(in);std::string error;try{node.Route(t,in.n,!solution);if(node.cc_local_pipeline)node.AssignCCLocalParams();if(node.local_real_pipeline)node.AssignLocalRealParams();}catch(const std::exception& e){error=e.what();}return std::make_tuple(node.selected,node.built,error,signature(node),signature(t),node.local_real_pipeline,node.cc_local_pipeline);}
size_t cases=0;
void compare(const Input& in){for(int f=0;f<2;f++)for(int l=0;l<2;l++)for(int s=0;s<2;s++){
 before::ROCFFT_CC_REAL_FUSION=after::ROCFFT_CC_REAL_FUSION=f;before::ROCFFT_CC_LOCAL_REAL_FUSION=after::ROCFFT_CC_LOCAL_REAL_FUSION=l;
 before::RealTransEvenNode a;after::RealTransEvenNode b;auto x=run(a,in,s),y=run(b,in,s);++cases;if(x!=y){std::cerr<<"route mismatch case "<<cases<<" N "<<in.n<<" c "<<in.c<<" q "<<in.q<<" f/l/s "<<f<<l<<s<<" old "<<std::get<0>(x)<<"/"<<std::get<1>(x)<<"/"<<std::get<2>(x)<<" new "<<std::get<0>(y)<<"/"<<std::get<1>(y)<<"/"<<std::get<2>(y)<<"\n";std::exit(1);}
 }}
int main(){
 Input base;compare(base);
 for(int direction:{-1,1})for(int it=0;it<4;it++)for(int ot=0;ot<4;ot++){auto x=base;x.direction=direction;x.it=it;x.ot=ot;compare(x);}
 for(auto st:std::vector<std::vector<size_t>>{{},{0},{1},{2},{1,1},{1,2}}){auto x=base;x.is=st;compare(x);x=base;x.os=st;compare(x);x=base;x.len=st;compare(x);}
 for(auto n:{size_t(65534),size_t(65535),size_t(65536),size_t(131072),size_t(262144),size_t(524288),size_t(1048576),size_t(1)<<24,(size_t(1)<<24)+2})for(int shape=0;shape<2;shape++){auto x=base;x.n=n;x.c=shape?256:128;x.q=(n/2)/x.c;if(n%2||n/2%x.c){x.c=1;x.q=n/2;}x.len={n};compare(x);x.direction=-1;x.it=0;x.ot=1;compare(x);}
 for(size_t sh:std::vector<size_t>{0,8191,8192,32767,32768,65535,65536,size_t(1)<<30}){auto x=base;x.device.sharedMemPerBlock=sh;compare(x);}
 for(auto cq:std::vector<std::pair<size_t,size_t>>{{128,256},{1024,512},{121,343}})for(size_t tpb:std::vector<size_t>{1,2,4,8})for(bool half:{false,true}){auto x=base;x.c=cq.first;x.q=cq.second;x.n=2*x.c*x.q;x.len={x.n};x.pool.cc.transforms_per_block=tpb;x.pool.cc.half_lds=half;size_t bytes=std::max(x.c*tpb*16/(half?2:1),x.q*(x.q==512?4:8)*16);for(auto sh:std::vector<size_t>{bytes-1,bytes,bytes+1}){x.device.sharedMemPerBlock=sh;compare(x);}}
 for(size_t n:std::vector<size_t>{65534,65536,size_t(1)<<24,(size_t(1)<<24)+2}){auto x=base;x.n=n;x.c=1;x.q=n/2;x.len={n};x.device.sharedMemPerBlock=size_t(1)<<30;compare(x);}
 for(int m=0;m<9;m++){auto x=base;if(m==0)x.pool.ccPresent=false;if(m==1)x.pool.alignedPresent=false;if(m==2)x.pool.unalignedPresent=false;if(m==3)x.pool.cc.direct_to_from_reg=false;if(m==4)x.pool.cc.transforms_per_block=1;if(m==5)x.pool.cc.half_lds=false;if(m==6)x.pool.cc.transforms_per_block=257;if(m==7)x.device.arch="gfx906";if(m==8)x.device.warpSize=32;compare(x);}
 std::mt19937 rng(129);std::vector<std::pair<size_t,size_t>> shapes{{128,256},{256,128},{256,256},{256,512},{512,512},{1024,512},{121,343},{343,121},{50,1331},{128,625}};
 for(int i=0;i<5000;i++){auto x=base;auto cq=shapes[rng()%shapes.size()];x.c=cq.first;x.q=cq.second;x.n=2*x.c*x.q;x.len={x.n};x.direction=(rng()%2)?1:-1;x.it=x.direction==1?1:0;x.ot=x.direction==1?0:1;
 switch(rng()%20){case 0:x.dimension=2;break;case 1:x.batch=2;break;case 2:x.precision=1;break;case 3:x.placement=1;break;case 4:x.is={};break;case 5:x.os={1,1};break;case 6:x.io=1;break;case 7:x.oo=1;break;case 8:x.device.arch="gfx90a";break;case 9:x.device.warpSize=32;break;case 10:x.scheme=CS_NONE;break;case 11:x.blue=1;break;case 12:x.pool.ccPresent=false;break;case 13:x.pool.alignedPresent=false;break;case 14:x.pool.unalignedPresent=false;break;case 15:x.device.sharedMemPerBlock=(rng()%4)*8192;break;case 16:x.pool.rowVariant=1+rng()%4;break;case 17:x.pool.cc.half_lds=rng()%2;x.pool.cc.transforms_per_block=1+rng()%20;break;case 18:x.it=3;break;default:break;}compare(x);}
 for(const char* mode:{"registers","lds","bad",""}){setenv("ROCFFT_EXP125_LOCAL_REAL_LOAD",mode,1);setenv("ROCFFT_EXP125_REAL_POST_LOAD",mode,1);compare(base);auto x=base;x.direction=-1;x.it=0;x.ot=1;compare(x);x.it=3;compare(x);}unsetenv("ROCFFT_EXP125_LOCAL_REAL_LOAD");unsetenv("ROCFFT_EXP125_REAL_POST_LOAD");
 size_t planners=0;for(int precision:{0,1,2,3})for(size_t n:{1024,262144,524288,1048576})for(int shape=0;shape<4;shape++)for(int ck=0;ck<2;ck++)for(int rk=0;rk<2;rk++)for(int arch=0;arch<2;arch++)for(size_t largest:{size_t(1),size_t(4096)}){
 before::NodeFactory::map1DLengthSingle.clear();before::NodeFactory::map1DLengthDouble.clear();after::NodeFactory::map1DLengthSingle.clear();after::NodeFactory::map1DLengthDouble.clear();
 if(shape){size_t d=shape==1?256:shape==2?0:3;before::NodeFactory::map1DLengthSingle[n]=before::NodeFactory::map1DLengthDouble[n]=after::NodeFactory::map1DLengthSingle[n]=after::NodeFactory::map1DLengthDouble[n]=d;}
 NodeMetaData nd;nd.precision=precision;nd.length={n};nd.deviceProp.arch=arch?"gfx906":"gfx936";function_pool p;p.ccPresent=ck;p.alignedPresent=rk;p.largest=largest;auto x=before::NodeFactory::Planner(p,nd),y=after::NodeFactory::Planner(p,nd);++planners;if(x!=y){std::cerr<<"planner mismatch\n";return 2;}}
 std::cout<<"{\"complete\":true,\"route_cases\":"<<cases<<",\"planner_cases\":"<<planners<<",\"source\":\"extracted actual old/new function prefixes and call-order branches\",\"gpu_execution\":false}"<<std::endl;
}
