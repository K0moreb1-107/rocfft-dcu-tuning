// Copyright (C) 2020 - 2025 Advanced Micro Devices, Inc. All rights reserved.
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

#include "tree_node.h"
#include "../../shared/precision_type.h"

#include <limits>

bool LeafNode::MakeRealBoundaryRowsKey(FMKey& key) const
{
    if(scheme != CS_KERNEL_STOCKHAM || dimension != 1 || length.size() != 2
       || length[0] == 0 || length[1] == 0 || batch != 1
       || precision != rocfft_precision_double || ebtype != EmbeddedType::NONE
       || large1D != 0 || fuseBlue != BFT_NONE || isPartialPassEnabled())
        return false;
    FMKey candidate(length[0], precision, scheme);
    if(!pool.has_function(candidate))
        return false;
    const auto kernel = pool.get_kernel(candidate);
    const auto p = kernel.threads_per_transform[0];
    const size_t slots = kernel.transforms_per_block & ~size_t(1);
    // Ordinary row kernels may leave tail threads idle.  Only the new paired
    // workgroup needs an exact TPT*slots thread count.
    if(p <= 0 || slots < 4 || kernel.factors.empty()
       || product(kernel.factors.begin(), kernel.factors.end()) != length[0]
       || kernel.workgroup_size <= 0
       || static_cast<size_t>(kernel.workgroup_size) / p < kernel.transforms_per_block
       || slots > static_cast<size_t>(deviceProp.maxThreadsPerBlock) / p
       || static_cast<size_t>(p) * slots > static_cast<size_t>(deviceProp.maxThreadsDim[0]))
        return false;
    const size_t complex_bytes = complex_type_size(precision);
    if(length[0] == std::numeric_limits<size_t>::max()
       || length[0] + 1 > static_cast<size_t>(deviceProp.sharedMemPerBlock)
                              / complex_bytes / slots)
        return false;
    // Count row pairs without overflowing axis+1 or adding the rounding term.
    const size_t pairs = length[1] / 2 + length[1] % 2;
    const size_t blocks = (pairs - 1) / (slots / 2) + 1;
    if(blocks > static_cast<size_t>(deviceProp.maxGridSize[0])
       || blocks > std::numeric_limits<unsigned int>::max())
        return false;
    auto config = kernel.get_kernel_config();
    config.transforms_per_block = slots;
    config.workgroup_size = static_cast<size_t>(p) * slots;
    config.direct_to_from_reg = true;
    config.intrinsic_buffer_inst = false;
    candidate.kernel_config = config;
    key = candidate;
    return true;
}
