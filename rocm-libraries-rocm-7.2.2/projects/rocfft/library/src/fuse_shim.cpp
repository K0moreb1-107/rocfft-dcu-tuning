// Copyright (C) 2021 - 2022 Advanced Micro Devices, Inc. All rights reserved.
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

#include "fuse_shim.h"
#include "../../shared/arithmetic.h"
#include "../../shared/array_predicate.h"
#include "../../shared/ptrdiff.h"
#include "../../shared/environment.h"
#include "function_pool.h"
#include "node_factory.h"
#include "tree_node_1D.h"

bool canOptimizeWithStride(TreeNode* stockham)
{
    // for 3D pow2 sizes, manipulating strides looks like it loses to
    // diagonal transpose
    if(IsPo2(stockham->length[0]) && stockham->length.size() >= 3)
        return false;
    size_t numTrans = stockham->pool.get_kernel(stockham->GetKernelKey()).transforms_per_block;

    // ensure we are doing enough rows to coalesce properly. 4
    // seems to be enough for double-precision, whereas some
    // sizes that do 7 rows seem to be slower for single.
    // TODO: the threshold may be set dependent one what kind of transport is the fused kernel
    //   eg. different value for TRANSPOSE, Z_XY, and XY_Z...
    //   for example, 21504 -t 1 --precision double works quite good with minRows==2
    size_t minRows = (stockham->precision == rocfft_precision_single
                      || stockham->precision == rocfft_precision_half)
                         ? 8
                         : 4;
    return numTrans >= minRows;
}

/*****************************************************
 * SBCC + SBRC: LDS-resident tile handoff
 *****************************************************/
bool CCSBRCFuseShim::CheckSchemeFusable()
{
    if(nodes.size() != 2)
        return false;

    auto producer = nodes[0];
    auto consumer = nodes[1];

    // This first implementation intentionally covers only the regular 2D
    // interleaved path.  The final stride/grid checks happen after buffer
    // assignment in FuseKernels().
    if(producer->scheme != CS_KERNEL_STOCKHAM_BLOCK_CC
       || consumer->scheme != CS_KERNEL_STOCKHAM_BLOCK_RC)
        return false;
    if(producer->length.size() != 2 || consumer->length.size() != 2)
        return false;
    // The fused outer grid carries the batch serial in the same x dimension
    // used by the standalone SBCC/SBRC kernels.  Keep the two stages on the
    // same batch contract, but do not unnecessarily restrict the fusion to a
    // single transform.
    const bool batchFusionOptIn
        = rocfft_getenv("ROCFFT_ENABLE_SBCC_SBRC_FUSION") == "1";
    const bool diagnosticBatchFusion
        = rocfft_getenv("ROCFFT_EXPERIMENTAL_BATCH_FUSION") == "1";
    const bool batchFusionEnabled = batchFusionOptIn || diagnosticBatchFusion;
    if(producer->batch != consumer->batch || producer->GetPlanRoot() == nullptr
       // Batch-local handoff indexing is now validated for multiple batches.
       // Keep the wider batch path opt-in with the existing fusion switch.
       || (producer->GetPlanRoot()->batch != 1 && !batchFusionEnabled))
        return false;
    if(producer->precision == rocfft_precision_half)
        return false;
    if(producer->ebtype != EmbeddedType::NONE || consumer->ebtype != EmbeddedType::NONE)
        return false;
    if(producer->fuseBlue != BFT_NONE || consumer->fuseBlue != BFT_NONE)
        return false;
    if(producer->isPartialPassEnabled() || consumer->isPartialPassEnabled())
        return false;
    if(array_type_is_planar(producer->inArrayType)
       || array_type_is_planar(producer->outArrayType)
       || array_type_is_planar(consumer->inArrayType)
       || array_type_is_planar(consumer->outArrayType))
        return false;

    // A callback/load-store-op kernel needs the original global boundary.
    auto root = producer->GetPlanRoot();
    if((root->loadOps && root->loadOps->enabled())
       || (root->storeOps && root->storeOps->enabled()))
        return false;

    // The producer must carry the large-1D twiddle stage and the consumer
    // must be a plain SBRC stage.  This also rejects the strided batch
    // rearrangement that changes the tile ownership model.
    if(producer->large1D == 0 || consumer->large1D != 0
       || producer->largeTwdBatchIsTransformCount
       || consumer->largeTwdBatchIsTransformCount)
        return false;

    return true;
}

std::unique_ptr<TreeNode> CCSBRCFuseShim::FuseKernels()
{
    if(!CheckSchemeFusable())
        return nullptr;

    auto producer = nodes[0];
    auto consumer = nodes[1];

    // Analyze again at the parent so the shim consumes the planner's final
    // post-assignment ownership proof rather than duplicating its mapping.
    auto owner = producer->parent;
    if(owner)
        owner->AnalyzeTileLifetimes();

    if(!owner || !owner->tileLifetime)
        return nullptr;
    const auto& contract = *owner->tileLifetime;
    const bool globalTileHandoff
        = rocfft_getenv("ROCFFT_SBCC_SBRC_GLOBAL_HANDOFF") == "1";
    if(!contract.completeTileMapping
       || (!globalTileHandoff && !contract.canElideGlobalHandoff))
        return nullptr;

    auto producerKernel = producer->GetKernel();
    auto consumerKernel = consumer->GetKernel();

    // The original one-to-one path requires an identical LDS layout.  It is
    // still useful for square plans and remains the cheapest fused schedule.
    const bool strictFusable
        = contract.completeTileOwnership && contract.fusedResidentLdsFitsDevice
          && producer->length == consumer->length
          && producerKernel.factors == consumerKernel.factors
          && producerKernel.transforms_per_block == consumerKernel.transforms_per_block
          && producerKernel.workgroup_size == consumerKernel.workgroup_size
          && !producerKernel.direct_to_from_reg && !consumerKernel.direct_to_from_reg
          && !producerKernel.half_lds && !consumerKernel.half_lds;

    // Streaming path for the common large-1D CC decomposition.  Each fused
    // consumer workgroup owns one consumer tile and reruns the direct-register
    // producer for all producer tiles needed along the transposed FFT axis.
    // The store rewrite below converts producer output coordinates directly to
    // the consumer's row-major LDS tile.
    const bool transposedStrideLayout
        = producer->outStride.size() == 2 && consumer->inStride.size() == 2
          && producer->outStride[1] == 1 && consumer->inStride[0] == 1
          && producer->outStride[0] == consumer->length[0]
          && consumer->inStride[1] == producer->outStride[0];
    const bool streamingFusable
        = !strictFusable && contract.edgeTilesComplete
          && contract.fusedStreamingLdsFitsDevice
          && producerKernel.direct_to_from_reg
          && consumerKernel.workgroup_size >= producerKernel.workgroup_size
          && producer->length[0] == consumer->length[1]
          && producer->length[1] == consumer->length[0]
          && contract.producerTilesRequiredPerConsumerTile
                 == contract.producerTilesPerPlane
          && transposedStrideLayout
          && producer->largeTwdBase >= 8 && producer->ltwdSteps != 0
          && (consumer->sbrcTranstype == TILE_ALIGNED
              || consumer->sbrcTranstype == TILE_UNALIGNED);

    if(rocfft_getenv("ROCFFT_DEBUG_SBCC_SBRC_FUSION") == "1")
    {
        rocfft_cerr << "CCSBRC fusion [layout] producer_length=";
        for(const auto value : producer->length)
            rocfft_cerr << value << ",";
        rocfft_cerr << " producer_output_length=";
        for(const auto value : producer->GetOutputLength())
            rocfft_cerr << value << ",";
        rocfft_cerr << " producer_in_stride=";
        for(const auto value : producer->inStride)
            rocfft_cerr << value << ",";
        rocfft_cerr << " producer_out_stride=";
        for(const auto value : producer->outStride)
            rocfft_cerr << value << ",";
        rocfft_cerr << " consumer_length=";
        for(const auto value : consumer->length)
            rocfft_cerr << value << ",";
        rocfft_cerr << " consumer_in_stride=";
        for(const auto value : consumer->inStride)
            rocfft_cerr << value << ",";
        rocfft_cerr << " consumer_out_stride=";
        for(const auto value : consumer->outStride)
            rocfft_cerr << value << ",";
        rocfft_cerr << std::endl;
        rocfft_cerr << "CCSBRC fusion [fuse] strict="
                    << (strictFusable ? "true" : "false")
                    << " streaming=" << (streamingFusable ? "true" : "false")
                    << " ownership=" << (contract.completeTileOwnership ? "true" : "false")
                    << " edge=" << (contract.edgeTilesComplete ? "true" : "false")
                    << " resident_lds=" << contract.fusedResidentLdsBytes
                    << " buffer_connected="
                    << (contract.producerConsumerBufferConnected ? "true" : "false")
                    << " buffer_owned="
                    << (contract.intermediateBufferOwnershipProven ? "true" : "false")
                    << " external_rw=" << contract.intermediateBufferExternalReads << "/"
                    << contract.intermediateBufferExternalWrites
                    << " resident_lds_fits="
                    << (contract.fusedResidentLdsFitsDevice ? "true" : "false")
                    << " can_elide_global_handoff="
                    << (contract.canElideGlobalHandoff ? "true" : "false")
                    << " global_handoff="
                    << (globalTileHandoff ? "true" : "false")
                    << " streaming_lds=" << contract.fusedStreamingLdsBytes << "/"
                    << (contract.fusedStreamingLdsFitsDevice ? "true" : "false")
                    << " direct_reg="
                    << (producerKernel.direct_to_from_reg ? "true" : "false") << "/"
                    << (consumerKernel.direct_to_from_reg ? "true" : "false")
                    << " wgs/tpb=" << producerKernel.workgroup_size << "/"
                    << producerKernel.transforms_per_block << " -> "
                    << consumerKernel.workgroup_size << "/"
                    << consumerKernel.transforms_per_block
                    << " tile_req/plane=" << contract.producerTilesRequiredPerConsumerTile
                    << "/" << contract.producerTilesPerPlane
                    << " width=" << contract.producerTileWidth << "/"
                    << contract.consumerTileWidth
                    << " ltwd=" << producer->largeTwdBase << "/" << producer->ltwdSteps
                    << " transpose=" << static_cast<int>(consumer->sbrcTranstype)
                    << std::endl;
    }

    if(!strictFusable && !streamingFusable)
        return nullptr;

    const bool streaming = streamingFusable;
    // outStride is indexed by the kernel's internal length.  A transpose
    // node may expose a different row-major outputLength, but that length
    // must not be used to size the producer's physical handoff allocation.
    const auto producerPhysicalLength
        = producer->UseOutputLengthForPadding() ? producer->GetOutputLength()
                                                : producer->length;
    const size_t globalHandoffElements
        = globalTileHandoff
              ? compute_ptrdiff(producerPhysicalLength,
                                producer->outStride,
                                producer->batch,
                                producer->oDist)
              : 0;
    if(globalTileHandoff && globalHandoffElements == 0)
        return nullptr;

    if(!PlacementFusable(producer->obIn, producer->obOut, consumer->obOut))
        return nullptr;

    auto fused = std::unique_ptr<FusedSBCCSBRCNode>(
        new FusedSBCCSBRCNode(producer->parent, CS_KERNEL_STOCKHAM_BLOCK_CC));
    fused->CopyNodeData(*producer);

    // The fused leaf presents the producer input and consumer output to the
    // executor while retaining each stage's own launch metadata.
    fused->placement   = rocfft_placement_notinplace;
    fused->inArrayType = producer->inArrayType;
    fused->outArrayType = consumer->outArrayType;
    fused->obIn        = producer->obIn;
    fused->obOut       = consumer->obOut;
    fused->inStride    = producer->inStride;
    fused->iDist       = producer->iDist;
    fused->outStride   = consumer->outStride;
    fused->oDist       = consumer->oDist;
    fused->outputLength = consumer->GetOutputLength();

    fused->producerOutStride            = producer->outStride;
    fused->producerOutputLength         = producer->GetOutputLength();
    fused->producerODist                = producer->oDist;
    fused->consumerLength              = consumer->length;
    fused->consumerInStride            = consumer->inStride;
    fused->consumerOutStride           = consumer->outStride;
    fused->consumerIDist               = consumer->iDist;
    fused->consumerODist               = consumer->oDist;
    fused->consumerBatch               = consumer->batch;
    fused->consumerKernelFactors       = consumerKernel.factors;
    fused->consumerKernelKey           = consumer->GetKernelKey();
    fused->consumerWgs                 = consumerKernel.workgroup_size;
    fused->consumerBwd                 = consumerKernel.transforms_per_block;
    fused->consumerThreadsPerTransform = consumerKernel.threads_per_transform[0];
    fused->consumerAotRtc              = consumerKernel.aot_rtc;
    fused->consumerDirectToFromReg     = consumerKernel.direct_to_from_reg;
    fused->consumerUnitStride
        = consumer->inStride.front() == 1 && consumer->outStride.front() == 1;
    fused->consumerTransposeType = consumer->sbrcTranstype;

    fused->producerWgs                 = producerKernel.workgroup_size;
    fused->producerBwd                 = producerKernel.transforms_per_block;
    fused->producerThreadsPerTransform = producerKernel.threads_per_transform[0];
    fused->producerAotRtc              = producerKernel.aot_rtc;
    fused->producerUnitStride
        = producer->inStride.front() == 1 && producer->outStride.front() == 1;
    fused->producerDirectToFromReg = producerKernel.direct_to_from_reg;
    fused->producerHalfLds          = producerKernel.half_lds;
    fused->producerDir2regMode      = producer->dir2regMode;
    fused->producerIntrinsicMode   = producer->intrinsicMode;

    // TreeNode does not expose LeafNode::lds through the base pointer, so
    // derive the tile sizes from the selected kernel contracts.
    const size_t producerTileLdsElements
        = producer->length.front() * producerKernel.transforms_per_block;
    const size_t complexBytes = complex_type_size(producer->precision);
    const size_t producerScratchElements
        = (contract.producerGrid.lds_bytes + complexBytes - 1) / complexBytes;
    const size_t fusedStreamingElements
        = ((contract.fusedStreamingLdsBytes + complexBytes - 1) / complexBytes)
          * (producerKernel.half_lds ? 2 : 1);
    // Streaming places the handoff tile after the producer scratch region.
    fused->producerLdsElements = streaming ? producerScratchElements : producerTileLdsElements;
    fused->fusedLdsElements
        = streaming ? fusedStreamingElements : producerTileLdsElements;
    fused->fusedWgs             = streaming ? consumerKernel.workgroup_size
                                           : producerKernel.workgroup_size;
    fused->streamingTileHandoff = streaming;
    fused->producerTilesPerConsumerTile = contract.producerTilesRequiredPerConsumerTile;
    fused->producerTileWidth            = contract.producerTileWidth;
    fused->consumerTileWidth            = contract.consumerTileWidth;
    fused->producerTilesPerPlane        = contract.producerTilesPerPlane;
    fused->consumerTilesPerPlane        = contract.consumerTilesPerPlane;
    fused->fusedGrid                    = contract.consumerGrid;
    fused->fusedLdsBytes
        = streaming ? contract.fusedStreamingLdsBytes : contract.fusedResidentLdsBytes;

    fused->globalTileHandoff     = globalTileHandoff;
    fused->globalHandoffElements = globalHandoffElements;

    fused->kernelFactors = producerKernel.factors;
    fused->wgs           = producerKernel.workgroup_size;
    fused->bwd           = producerKernel.transforms_per_block;
    fused->lds           = fused->fusedLdsElements;
    fused->dir2regMode   = streaming ? producer->dir2regMode
                                     : DirectRegType::FORCE_OFF_OR_NOT_SUPPORT;
    fused->intrinsicMode = IntrinsicAccessType::DISABLE_BOTH;
    fused->sbrcTranstype = consumer->sbrcTranstype;
    if(producer->specified_key)
        fused->specified_key = std::make_unique<FMKey>(*producer->specified_key);

    fused->comments.push_back(
        "CCSBRCFuseShim: fused SBCC producer and SBRC consumer with an LDS tile handoff");
    if(globalTileHandoff)
    {
        fused->comments.push_back(
            "CCSBRCFuseShim: producer output and consumer input use a planner global handoff buffer");
        fused->comments.push_back("CCSBRCFuseShim: global handoff elements="
                                  + std::to_string(globalHandoffElements));
    }
    else
    {
        fused->comments.push_back(
            "CCSBRCFuseShim: producer global store and consumer global load removed");
    }
    if(streaming)
        fused->comments.push_back(
            "CCSBRCFuseShim: producer tile loop remaps block id and streams selected transpose rows into consumer LDS");

    // Keep the contract useful for planner diagnostics until the tree is
    // refreshed after the replacement.
    owner->tileLifetime->fusedKernelAvailable = true;
    owner->tileLifetime->globalHandoffRequired = globalTileHandoff;
    owner->tileLifetime->status = globalTileHandoff
                                      ? TileLifetimeStatus::GLOBAL_HANDOFF_REQUIRED
                                      : TileLifetimeStatus::LDS_HANDOFF_ELIGIBLE;
    owner->tileLifetime->reason
        = globalTileHandoff
              ? "fused SBCC -> SBRC kernel selected with planner global handoff buffer"
              : (streaming ? "streaming SBCC -> SBRC fused RTC kernel selected"
                           : "strict SBCC -> SBRC fused RTC kernel selected");

    return fused;
}

// if the in/out buffer meets the placement requirement
// firstOBuf is used in R2CTrans only
bool FuseShim::PlacementFusable(OperatingBuffer iBuf,
                                OperatingBuffer firstOBuf,
                                OperatingBuffer lastOBuf)
{
    // when allowInplace, both in-place and out-of-place are allowed.
    // otherwise, only out-of-place is allowed.
    return (allowInplace) ? true : iBuf != lastOBuf;
}

// return the check result of if these schemes can be fused
bool FuseShim::IsSchemeFusable() const
{
    return schemeFusable;
}

void FuseShim::OverwriteFusableFlag(bool fusable)
{
    schemeFusable = fusable;
}

TreeNode* FuseShim::FirstFuseNode() const
{
    if(nodes.size() <= firstFusedNode)
        throw std::runtime_error("firstFusedNode exceeds vector size");
    return nodes[firstFusedNode];
}

TreeNode* FuseShim::LastFuseNode() const
{
    if(nodes.size() <= lastFusedNode)
        throw std::runtime_error("lastFusedNode exceeds vector size");
    return nodes[lastFusedNode];
}

void FuseShim::ForEachNode(std::function<void(TreeNode*)> func)
{
    for(size_t i = firstFusedNode; i <= lastFusedNode; ++i)
    {
        func(nodes[i]);
    }
}

/*****************************************************
 * TR= transpose + FFT
 *
 * if we have a transpose followed by a stockham
 * fft that does multiple rows in one kernel, adjust input
 * strides to replace the transpose.  Multiple rows will ensure
 * that the transposed column reads are coalesced.
 *****************************************************/
bool TRFuseShim::CheckSchemeFusable()
{
    auto transpose = nodes[0];
    auto stockham  = nodes[1];

    // NB: can't get rid of a transpose that also does large twiddle multiplication
    if((transpose->scheme != CS_KERNEL_TRANSPOSE && transpose->scheme != CS_KERNEL_TRANSPOSE_Z_XY
        && transpose->scheme != CS_KERNEL_TRANSPOSE_XY_Z)
       || transpose->large1D)
        return false;
    if(stockham->scheme != CS_KERNEL_STOCKHAM)
        return false;

    if(!canOptimizeWithStride(stockham))
        return false;

    // verify that the transpose output lengths match the FFT input lengths
    auto transposeOutputLengths = transpose->length;
    if(transpose->scheme == CS_KERNEL_TRANSPOSE)
        std::swap(transposeOutputLengths[0], transposeOutputLengths[1]);
    else if(transpose->scheme == CS_KERNEL_TRANSPOSE_Z_XY)
    {
        std::swap(transposeOutputLengths[0], transposeOutputLengths[1]);
        std::swap(transposeOutputLengths[1], transposeOutputLengths[2]);
    }
    else
    {
        // must be XY_Z
        std::swap(transposeOutputLengths[1], transposeOutputLengths[2]);
        std::swap(transposeOutputLengths[0], transposeOutputLengths[1]);
    }
    if(stockham->length != transposeOutputLengths)
        return false;

    firstFusedNode = 0;
    lastFusedNode  = 1;

    return true;
}

std::unique_ptr<TreeNode> TRFuseShim::FuseKernels()
{
    auto transpose = nodes[0];
    auto stockham  = nodes[1];

    if(!PlacementFusable(transpose->obIn, transpose->obOut, stockham->obOut))
        return nullptr;

    auto fused = NodeFactory::CreateNodeFromScheme(stockham->scheme, stockham->parent);
    fused->CopyNodeData(*stockham);
    // actually no need to check kernel exists, we already have the kernel with the same length/scheme
    std::vector<FMKey> kernelkey = {stockham->GetKernelKey()};
    if(!fused->KernelCheck(kernelkey))
        return nullptr;

    fused->placement   = rocfft_placement_notinplace;
    fused->inArrayType = transpose->inArrayType;
    fused->obIn        = transpose->obIn;
    fused->iDist       = transpose->iDist;
    fused->comments.push_back("TRFuseShim: fused " + PrintScheme(transpose->scheme)
                              + " and following " + PrintScheme(stockham->scheme));

    if(transpose->scheme == CS_KERNEL_TRANSPOSE)
    {
        fused->inStride = transpose->inStride;
        std::swap(fused->inStride[0], fused->inStride[1]);
    }
    else if(transpose->scheme == CS_KERNEL_TRANSPOSE_Z_XY)
    {
        // give stockham kernel Z_XY-transposed inputs and outputs
        fused->inStride[0] = transpose->inStride[1];
        fused->inStride[1] = transpose->inStride[0];
        fused->inStride[2] = transpose->inStride[2];

        std::swap(fused->outStride[1], fused->outStride[2]);
        std::swap(fused->length[1], fused->length[2]);
    }
    else
    {
        // give stockham kernel XY_Z-transposed inputs
        fused->inStride[0] = transpose->inStride[2];
        fused->inStride[1] = transpose->inStride[0];
        fused->inStride[2] = transpose->inStride[1];
    }

    return fused;
}

/*****************************************************
 * RT= FFT + transpose
 *
 * If this is a stockham fft that does multiple rows in one
 * kernel, followed by a transpose, adjust output strides to
 * replace the transpose.  Multiple rows will ensure that the
 * transposed column writes are coalesced.
 *****************************************************/
bool RTFuseShim::CheckSchemeFusable()
{
    auto stockham  = nodes[0];
    auto transpose = nodes[1];

    if(stockham->scheme != CS_KERNEL_STOCKHAM)
        return false;

    if((transpose->scheme != CS_KERNEL_TRANSPOSE && transpose->scheme != CS_KERNEL_TRANSPOSE_Z_XY
        && transpose->scheme != CS_KERNEL_TRANSPOSE_XY_Z)
       || transpose->length != stockham->length || transpose->inStride != stockham->outStride)
        return false;

    // NB: Same as TR, can't get rid of a transpose that also does large twiddle multiplication
    if(transpose->large1D)
        return false;

    if(!canOptimizeWithStride(stockham))
        return false;

    firstFusedNode = 0;
    lastFusedNode  = 1;

    return true;
}

std::unique_ptr<TreeNode> RTFuseShim::FuseKernels()
{
    auto stockham  = nodes[0];
    auto transpose = nodes[1];

    if(!PlacementFusable(stockham->obIn, stockham->obOut, transpose->obOut))
        return nullptr;

    // should be stockham
    auto fused = NodeFactory::CreateNodeFromScheme(stockham->scheme, stockham->parent);
    fused->CopyNodeData(*stockham);
    // actually no need to check kernel exists, we already have the kernel with the same length/scheme
    std::vector<FMKey> kernelkey = {stockham->GetKernelKey()};
    if(!fused->KernelCheck(kernelkey))
        return nullptr;

    fused->placement    = rocfft_placement_notinplace;
    fused->outArrayType = transpose->outArrayType;
    fused->obOut        = transpose->obOut;
    fused->oDist        = transpose->oDist;
    fused->comments.push_back("RTFuseShim: fused " + PrintScheme(stockham->scheme)
                              + " and following " + PrintScheme(transpose->scheme));

    if(transpose->scheme == CS_KERNEL_TRANSPOSE || transpose->scheme == CS_KERNEL_TRANSPOSE_Z_XY)
    {
        fused->outStride = transpose->outStride;
    }
    else
    {
        // make stockham write XY_Z-transposed outputs
        fused->outStride[0] = transpose->outStride[1];
        fused->outStride[1] = transpose->outStride[2];
        fused->outStride[2] = transpose->outStride[0];
    }
    fused->outputLength = transpose->outputLength;

    return fused;
}

/*****************************************************
 * RT_ZXY FFT + transpose_Z_XY
 *****************************************************/
bool RT_ZXY_FuseShim::CheckSchemeFusable()
{
    auto previous = nodes[0]; // possible nullptr
    auto stockham = nodes[1];
    auto transZXY = nodes[2];

    if(stockham->scheme != CS_KERNEL_STOCKHAM)
        return false;
    if(transZXY->scheme != CS_KERNEL_TRANSPOSE_Z_XY)
        return false;

    if(previous && previous->scheme == CS_KERNEL_TRANSPOSE_XY_Z)
        return false;

    if(!transZXY->fuse_CS_KERNEL_TRANSPOSE_Z_XY())
        return false;

    firstFusedNode = 1; // not nodes[0] (not nodes.front())
    lastFusedNode  = 2;

    return true;
}

std::unique_ptr<TreeNode> RT_ZXY_FuseShim::FuseKernels()
{
    auto stockham  = nodes[1];
    auto transpose = nodes[2];

    if(!PlacementFusable(stockham->obIn, stockham->obOut, transpose->obOut))
        return nullptr;

    auto fused
        = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_TRANSPOSE_Z_XY, stockham->parent);
    fused->CopyNodeData(*stockham);
    // check if kernel exists, since the fused kernel uses different scheme other than stockham
    if(!fused->KernelCheck())
        return nullptr;

    fused->placement    = rocfft_placement_notinplace;
    fused->outArrayType = transpose->outArrayType;
    fused->obOut        = transpose->obOut;
    fused->oDist        = transpose->oDist;
    fused->outStride    = transpose->outStride;
    std::swap(fused->outStride[0], fused->outStride[1]);
    std::swap(fused->outStride[1], fused->outStride[2]);
    fused->comments.push_back("RT_ZXY_FuseShim: fused " + PrintScheme(CS_KERNEL_STOCKHAM)
                              + " and following " + PrintScheme(CS_KERNEL_TRANSPOSE_Z_XY));
    fused->outputLength = transpose->outputLength;

    return fused;
}

/*****************************************************
 * RT_XYZ FFT + transpose_XY_Z
 *
 * combine one CS_KERNEL_STOCKHAM and following CS_KERNEL_TRANSPOSE_XY_Z in 3D complex to real
 *
 * NB: this should be replaced by combining
 * CS_KERNEL_TRANSPOSE_XY_Z and the following CS_KERNEL_STOCKHAM eventually,
 * in which we might fuse 2 pairs of TR.
 *****************************************************/
bool RT_XYZ_FuseShim::CheckSchemeFusable()
{
    auto stockham = nodes[0];
    auto transXYZ = nodes[1];
    auto last     = nodes[2]; // fusable only if a stockham, but this won't be fused

    // fusable when [stockham -> Trans_XY_Z] (fusion) -> stockham
    if(stockham->scheme != CS_KERNEL_STOCKHAM)
        return false;
    if(transXYZ->scheme != CS_KERNEL_TRANSPOSE_XY_Z)
        return false;
    if(!last || last->scheme != CS_KERNEL_STOCKHAM)
        return false;

    if(!transXYZ->fuse_CS_KERNEL_TRANSPOSE_XY_Z())
        return false;

    firstFusedNode = 0;
    lastFusedNode  = 1; // not nodes[2] (not nodes.back())

    return true;
}

std::unique_ptr<TreeNode> RT_XYZ_FuseShim::FuseKernels()
{
    auto stockham = nodes[0];
    auto transXYZ = nodes[1];

    if(!PlacementFusable(stockham->obIn, stockham->obOut, transXYZ->obOut))
        return nullptr;

    auto fused
        = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z, stockham->parent);
    fused->CopyNodeData(*stockham);
    // check if kernel exists, since the fused kernel uses different scheme other than stockham
    if(!fused->KernelCheck())
        return nullptr;

    fused->placement    = rocfft_placement_notinplace;
    fused->outArrayType = transXYZ->outArrayType;
    fused->obOut        = transXYZ->obOut;
    fused->oDist        = transXYZ->oDist;
    fused->outStride    = transXYZ->outStride;
    fused->comments.push_back("RT_XYZ_FuseShim: fused " + PrintScheme(CS_KERNEL_STOCKHAM)
                              + " and following " + PrintScheme(CS_KERNEL_TRANSPOSE_XY_Z));
    return fused;
}

/*****************************************************
 * R2C_Trans = REAL_2_CMPLX + TRANSPOSE*
 *****************************************************/
bool R2CTrans_FuseShim::CheckSchemeFusable()
{
    auto realEven  = nodes[0];
    auto transpose = nodes[1];
    auto following = nodes[2];

    // check if the second is transpose
    if(transpose->scheme != CS_KERNEL_TRANSPOSE && transpose->scheme != CS_KERNEL_TRANSPOSE_Z_XY)
        return false;

    // fusable when first is realEven, and the last child of it is r2c
    if(realEven->scheme != CS_REAL_TRANSFORM_EVEN)
        return false;
    if(realEven->childNodes.back()->scheme != CS_KERNEL_R_TO_CMPLX)
        return false;

    // update the node to the final effective node
    nodes[0] = realEven->childNodes.back().get(); // the last child of real-trans-even
    nodes[2] = following->GetFirstLeaf();

    firstFusedNode = 0;
    lastFusedNode  = 1;

    // if the nextLeafNode is stockham or SBCC,
    //   we allow the EffectivePlacement of (r2c-in, trans-out) to be inplace,
    //   then we force it to be OP, but change the nextLeafNode's input..
    // So if the nextLeafNode isn't one of these (ex, a transpose for TRTRT)
    //   then we couldn't change tranpose's input buffer
    ComputeScheme nextFFTScheme = nodes[2]->scheme;
    if(nextFFTScheme == CS_KERNEL_STOCKHAM || nextFFTScheme == CS_KERNEL_STOCKHAM_BLOCK_CC)
        allowInplace = true;
    else
        allowInplace = false;

    return true;
}

bool R2CTrans_FuseShim::PlacementFusable(OperatingBuffer iBuf,
                                         OperatingBuffer firstOBuf,
                                         OperatingBuffer lastOBuf)
{
    // allow inplace (out-of-place is allowed as well)
    if(allowInplace)
    {
        // if inBuf and outBuf is already op, then it is safe.
        return true;
    }
    // only allow out-of-place
    else
    {
        return iBuf != lastOBuf;
    }
}

std::unique_ptr<TreeNode> R2CTrans_FuseShim::FuseKernels()
{
    auto r2c       = nodes[0];
    auto transpose = nodes[1];
    auto nextLeaf  = nodes[2];

    if(!PlacementFusable(r2c->obIn, r2c->obOut, transpose->obOut))
        return nullptr;

    auto fused = NodeFactory::CreateNodeFromScheme(CS_KERNEL_R_TO_CMPLX_TRANSPOSE, r2c->parent);
    fused->CopyNodeData(*r2c);
    // no need to check kernel exists, this scheme uses a built-in kernel
    fused->placement    = rocfft_placement_notinplace;
    fused->outArrayType = transpose->outArrayType;
    // fused->obOut            = transpose->obOut;
    fused->oDist     = transpose->oDist;
    fused->outStride = transpose->outStride;
    if(transpose->scheme == CS_KERNEL_TRANSPOSE)
        std::swap(fused->outStride[0], fused->outStride[1]);
    else if(transpose->scheme == CS_KERNEL_TRANSPOSE_Z_XY)
    {
        std::swap(fused->outStride[0], fused->outStride[1]);
        std::swap(fused->outStride[1], fused->outStride[2]);
    }
    fused->comments.push_back("R2CTrans_FuseShim: fused " + PrintScheme(CS_KERNEL_R_TO_CMPLX)
                              + " and following " + PrintScheme(transpose->scheme));

    // if the effective placement is:
    //   1. out-of-place, then we simply combine them to fused kernel, result in OP
    //   2. inplace, we keep the fused-out as trans-out, also result in OP
    //      in this case, we need to change the nextLeaf's input from c2r-out to trans-out
    if(r2c->obIn != transpose->obOut)
    {
        fused->obOut = transpose->obOut;
    }
    else
    {
        fused->obOut   = r2c->obOut; // already done in CopyNodeData, but just leave it tidy
        nextLeaf->obIn = fused->obOut; // so we still don't break buffer flow of [r2c-trans]-next
        nextLeaf->placement = (nextLeaf->obIn == nextLeaf->obOut) ? rocfft_placement_inplace
                                                                  : rocfft_placement_notinplace;
    }
    fused->outputLength = transpose->outputLength;

    // This fusion is crossing sub-trees of the plan, so adjust the
    // parent CS_REAL_TRANSFORM_EVEN to output what this fused kernel
    // says it outputs.  Otherwise the plan won't make sense when
    // other things look at it.
    r2c->parent->outputLength = fused->outputLength;
    r2c->parent->outStride    = fused->outStride;
    r2c->parent->oDist        = fused->oDist;

    return fused;
}

/*****************************************************
 * Trans_C2R = TRANSPOSE + CMPLX_2_REAL
 *****************************************************/
bool TransC2R_FuseShim::CheckSchemeFusable()
{
    auto transpose = nodes[0];
    auto realEven  = nodes[1];

    // check if the first is transpose
    if(transpose->scheme != CS_KERNEL_TRANSPOSE && transpose->scheme != CS_KERNEL_TRANSPOSE_XY_Z)
        return false;

    // fusable when second is realEven, and the first child of it is c2r
    if(realEven->scheme != CS_REAL_TRANSFORM_EVEN)
        return false;
    if(realEven->childNodes.front()->scheme != CS_KERNEL_CMPLX_TO_R)
        return false;

    // update the node to the final effective node: the first child of real-trans-even
    // and node[2] keeps the next leaf node after C2R kernel,
    // since it's possible we'll change its input buffer
    nodes.resize(3);
    nodes[1] = realEven->childNodes.front().get();
    nodes[2] = std::find_if(realEven->childNodes.begin() + 1,
                            realEven->childNodes.end(),
                            [](const auto& n) { return !n->IsBluesteinChirpSetup(); })
                   ->get();

    firstFusedNode = 0;
    lastFusedNode  = 1;

    // if the nextLeafNode is stockham, SBCC or PAD-MUL
    //   we allow the EffectivePlacement of (trans-in, c2r-out) to be inplace,
    //   then we force it to be OP, but change the nextLeafNode's input..
    // So if the nextLeafNode isn't one of these (ex, a transpose for TRTRT)
    //   then we couldn't change tranpose's input buffer
    ComputeScheme nextFFTScheme = nodes[2]->scheme;
    if(nextFFTScheme == CS_KERNEL_STOCKHAM || nextFFTScheme == CS_KERNEL_STOCKHAM_BLOCK_CC
       || nextFFTScheme == CS_KERNEL_PAD_MUL)
        allowInplace = true;
    else
        allowInplace = false;

    return true;
}

std::unique_ptr<TreeNode> TransC2R_FuseShim::FuseKernels()
{
    auto transpose = nodes[0];
    auto c2r       = nodes[1];
    auto nextLeaf  = nodes[2];

    if(!PlacementFusable(transpose->obIn, transpose->obOut, c2r->obOut))
        return nullptr;

    auto fused
        = NodeFactory::CreateNodeFromScheme(CS_KERNEL_TRANSPOSE_CMPLX_TO_R, transpose->parent);
    fused->CopyNodeData(*transpose);
    if(transpose->scheme == CS_KERNEL_TRANSPOSE_XY_Z)
    {
        std::swap(fused->inStride[1], fused->inStride[2]);
        std::swap(fused->length[1], fused->length[2]);
    }
    // no need to check kernel exists, this scheme uses a built-in kernel
    fused->placement    = rocfft_placement_notinplace;
    fused->outArrayType = c2r->outArrayType;
    // fused->obOut            = c2r->obOut; // move to later with comment
    fused->oDist     = c2r->oDist;
    fused->outStride = c2r->outStride;
    fused->comments.push_back("TransC2R_FuseShim: fused " + PrintScheme(transpose->scheme)
                              + " and following " + PrintScheme(CS_KERNEL_CMPLX_TO_R));

    // if the effective placement is:
    //   1. out-of-place, then we simply combine them to fused kernel, result in OP
    //   2. inplace, we keep the fused-out as trans-out, also result in OP
    //      in this case, we need to change the nextLeaf's input from c2r-out to trans-out
    if(transpose->obIn != c2r->obOut)
    {
        fused->obOut = c2r->obOut;
    }
    else
    {
        fused->obOut   = transpose->obOut; // already done in CopyNodeData, but just leave it tidy
        nextLeaf->obIn = fused->obOut; // so we still don't break buffer flow of [trans-c2r]-next
        nextLeaf->placement = (nextLeaf->obIn == nextLeaf->obOut) ? rocfft_placement_inplace
                                                                  : rocfft_placement_notinplace;
    }
    fused->outputLength = c2r->outputLength;

    // This fusion is crossing sub-trees of the plan, so adjust the
    // parent CS_REAL_TRANSFORM_EVEN to expect what this fused kernel
    // says it outputs.  Otherwise the plan won't make sense when
    // other things look at it.
    c2r->parent->length   = fused->outputLength;
    c2r->parent->inStride = fused->outStride;
    c2r->parent->iDist    = fused->oDist;

    return fused;
}

/*****************************************************
 * STK_R2C_Trans = STOCKHAM + REAL_2_CMPLX + TRANSPOSE*
 *****************************************************/
bool STK_R2CTrans_FuseShim::CheckSchemeFusable()
{
    auto realEven  = nodes[0];
    auto transpose = nodes[1];

    // check if the second node is transpose
    if(transpose->scheme != CS_KERNEL_TRANSPOSE && transpose->scheme != CS_KERNEL_TRANSPOSE_Z_XY)
        return false;

    // fusable when first node is realEven r2c, we will fuse the 2nd(STK) and the 3rd(r2c) children
    if(realEven->scheme != CS_REAL_TRANSFORM_EVEN || realEven->childNodes.size() != 3)
        return false;
    // we will fuse the 2nd(STK) and the 3rd(r2c) children, and with the following transpose
    if(realEven->childNodes[1]->scheme != CS_KERNEL_STOCKHAM
       || realEven->childNodes[2]->scheme != CS_KERNEL_R_TO_CMPLX)
        return false;

    // find if have sbrc and length fit requirement
    if(!realEven->childNodes[1]->fuse_CS_KERNEL_STK_R2C_TRANSPOSE())
        return false;

    // NB:
    //    for inplace cases: this fusion can't get correct results, so disable them now
    //    such as 128x128, 100x100, 256x256...etc (-t 2), Need more investigation
    if(realEven->GetPlanRoot()->placement == rocfft_placement_inplace)
        return false;

    // update the node to the final effective nodes:
    nodes.resize(3);
    nodes[0] = realEven->childNodes[1].get(); // stockham the cfft child of real-trans-even
    nodes[1] = realEven->childNodes[2].get(); // r2c
    nodes[2] = transpose; // transpose

    firstFusedNode = 0;
    lastFusedNode  = 2;

    return true;
}

std::unique_ptr<TreeNode> STK_R2CTrans_FuseShim::FuseKernels()
{
    auto stockham  = nodes[0];
    auto r2c       = nodes[1];
    auto transpose = nodes[2];
    // auto& r2c       = nodes[1];

    if(!PlacementFusable(stockham->obIn, stockham->obOut, transpose->obOut))
        return nullptr;

    auto fused = NodeFactory::CreateNodeFromScheme(CS_KERNEL_STOCKHAM_R_TO_CMPLX_TRANSPOSE_Z_XY,
                                                   stockham->parent);
    fused->CopyNodeData(*stockham);
    // check if kernel exists, since the fused kernel uses different scheme other than stockham
    if(!fused->KernelCheck())
        return nullptr;

    fused->placement    = rocfft_placement_notinplace;
    fused->outArrayType = transpose->outArrayType;
    fused->obOut        = transpose->obOut;
    fused->oDist        = transpose->oDist;
    fused->outStride    = transpose->outStride;
    std::swap(fused->outStride[0], fused->outStride[1]);
    // it's possible that we're using a 3D SBRC kernel in here.  only
    // adjust for the third dimension if we're inside a 3D plan.
    if(transpose->parent->length.size() > 2)
        std::swap(fused->outStride[1], fused->outStride[2]);
    fused->comments.push_back("STK_R2CTrans_FuseShim: fused " + PrintScheme(CS_KERNEL_STOCKHAM)
                              + ", " + PrintScheme(CS_KERNEL_R_TO_CMPLX) + " and following "
                              + PrintScheme(transpose->scheme));

    fused->outputLength = transpose->outputLength;

    // This fusion is crossing sub-trees of the plan, so adjust the
    // parent CS_REAL_TRANSFORM_EVEN to expect what this fused kernel
    // says it outputs.  Otherwise the plan won't make sense when
    // other things look at it.
    r2c->parent->outputLength = fused->outputLength;
    r2c->parent->outStride    = fused->outStride;
    r2c->parent->oDist        = fused->oDist;
    // Adjust strides in case we're using a 3D kernel for a 2D case
    r2c->parent->outStride.resize(r2c->parent->length.size());
    r2c->parent->outputLength.resize(r2c->parent->length.size());

    return fused;
}
