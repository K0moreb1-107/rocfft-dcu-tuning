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
