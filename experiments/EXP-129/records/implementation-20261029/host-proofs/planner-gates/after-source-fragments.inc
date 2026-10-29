namespace after {

int ROCFFT_CC_REAL_FUSION=1,ROCFFT_CC_LOCAL_REAL_FUSION=1;
struct RealTransEvenNode:TreeNode{
 int dimension=1,direction=1,precision=rocfft_precision_double,placement=rocfft_placement_notinplace,inArrayType=rocfft_array_type_hermitian_interleaved,outArrayType=rocfft_array_type_real;
 size_t batch=1,iOffset=0,oOffset=0;std::vector<size_t> inStride{1},outStride{1};Device deviceProp;function_pool pool;int selected=0;bool built=false;
 bool CanFuseCCReal()const;bool CCRealKernelsAvailable(size_t,size_t)const;
 bool TryBuildCCLocalTree(const TreeNode&,size_t);bool TryBuildLocalRealTree(size_t);bool TryFusePairedPost(TreeNode&,size_t);
 void Route(TreeNode&,size_t,bool);
};
struct NodeFactory{static Map1DLength map1DLengthSingle,map1DLengthDouble;static bool Get1DBlockComputeDivisor(const function_pool&,int,size_t,size_t&,bool&);static std::tuple<int,bool,size_t> Planner(const function_pool&,NodeMetaData);};
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
    const auto transpose
        = columns % rc.transforms_per_block ? TILE_UNALIGNED : TILE_ALIGNED;
    if(!pool.has_function(FMKey(rows, precision, CS_KERNEL_STOCKHAM_BLOCK_RC, transpose)))
        return false;

    const size_t lds_divisor = cc.half_lds ? 2 : 1;
    if(!cc.direct_to_from_reg || rows < cc.transforms_per_block
       || cc.transforms_per_block < lds_divisor)
        return false;

    const size_t complex_bytes = 2 * sizeof(double);
    const size_t cc_bytes = columns * cc.transforms_per_block * complex_bytes / lds_divisor;
    const size_t rc_bytes = rows * rc.transforms_per_block * complex_bytes;
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
selected=1; return true;
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

selected=2; return true;
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

selected=3; return true;
}

void RealTransEvenNode::Route(TreeNode& cfft, size_t n, bool noSolution) {
const std::vector<size_t> real_lengths{n};const auto* realLength=&real_lengths; TreeNode* cfftPlan=&cfft; selected=0; built=false;
    // Fastest moving dimension must be even:
    if(realLength->at(0) % 2 != 0)
        throw std::runtime_error("fastest dimension is not even in RealTransEvenNode");

    const bool try_cc_real
        = noSolution && ROCFFT_CC_REAL_FUSION && CanFuseCCReal();
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
