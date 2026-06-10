// standalone test harness for kernel fft_rtc_back_len_4096_factors_16_16_16_wgs_256_tpt_256_halfLds_dim_1_dp_ip_CI_unitstride_sbrr_dirReg.
// edit init_kernel to set args + grid.

#include <hip/hip_runtime_api.h>
#include <hip/hiprtc.h>
#include <fstream>
#include <functional>
#include <future>
#include <memory>
#include <random>
#include <string>
#include <vector>
#define ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS

// Copyright (C) 2023 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef __ROCFFT_HIP_H__
#define __ROCFFT_HIP_H__


class rocfft_scoped_device
{
public:
    rocfft_scoped_device(int device)
    {
        if(hipGetDevice(&orig_device) != hipSuccess)
            throw std::runtime_error("hipGetDevice failure");

        if(hipSetDevice(device) != hipSuccess)
            throw std::runtime_error("hipSetDevice failure");
    }
    ~rocfft_scoped_device()
    {
        (void)hipSetDevice(orig_device);
    }

    // not copyable or movable
    rocfft_scoped_device(const rocfft_scoped_device&) = delete;
    rocfft_scoped_device(rocfft_scoped_device&&)      = delete;
    rocfft_scoped_device& operator=(const rocfft_scoped_device&) = delete;

private:
    int orig_device;
};

#endif // __ROCFFT_HIP_H__

// Copyright (C) 2021 - 2023 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef ROCFFT_COMPLEX_H
#define ROCFFT_COMPLEX_H

#if !defined(__HIPCC_RTC__)
#endif

#ifdef __HIP_PLATFORM_NVIDIA__
typedef __half rocfft_fp16;
#else
typedef _Float16 rocfft_fp16;
#endif

template <typename Treal>
struct rocfft_complex
{

    Treal x; // Real part
    Treal y; // Imaginary part

    // Constructors
    // Do not initialize the members x or y by default, to ensure that it can
    // be used in __shared__ and that it is a trivial class compatible with C.
    __device__ __host__ rocfft_complex()                      = default;
    __device__ __host__ rocfft_complex(const rocfft_complex&) = default;
    __device__ __host__ rocfft_complex(rocfft_complex&&)      = default;
    __device__ __host__ rocfft_complex& operator=(const rocfft_complex& rhs) & = default;
    __device__ __host__ rocfft_complex& operator=(rocfft_complex&& rhs) & = default;
    __device__                          __host__ ~rocfft_complex()        = default;

    // Constructor from real and imaginary parts
    __device__ __host__ constexpr rocfft_complex(Treal real, Treal imag)
        : x{real}
        , y{imag}
    {
    }

    // Conversion from different precision
    template <typename U>
    __device__ __host__ explicit constexpr rocfft_complex(const rocfft_complex<U>& z)
        : x(z.x)
        , y(z.y)
    {
    }

    // Accessors
    __device__ __host__ constexpr Treal real() const
    {
        return x;
    }

    __device__ __host__ constexpr Treal imag() const
    {
        return y;
    }

    // Mutators
    __device__ __host__ void real(const Treal new_x)
    {
        x = new_x;
    }

    __device__ __host__ void imag(const Treal new_y)
    {
        y = new_y;
    }

    // Unary operations
    __forceinline__ __device__ __host__ rocfft_complex operator-() const
    {
        return {-x, -y};
    }

    __forceinline__ __device__ __host__ rocfft_complex operator+() const
    {
        return *this;
    }

    __device__ __host__ Treal asum(const rocfft_complex& z)
    {
        return abs(z.x) + abs(z.y);
    }

    // Internal real functions
    static __forceinline__ __device__ __host__ Treal abs(Treal x)
    {
        return x < 0 ? -x : x;
    }

    static __forceinline__ __device__ __host__ float sqrt(float x)
    {
        return ::sqrtf(x);
    }

    static __forceinline__ __device__ __host__ double sqrt(double x)
    {
        return ::sqrt(x);
    }

    // Addition operators
    __device__ __host__ auto& operator+=(const rocfft_complex& rhs)
    {
        return *this = {x + rhs.x, y + rhs.y};
    }

    __device__ __host__ auto operator+(const rocfft_complex& rhs) const
    {
        auto lhs = *this;
        return lhs += rhs;
    }

    // Subtraction operators
    __device__ __host__ auto& operator-=(const rocfft_complex& rhs)
    {
        return *this = {x - rhs.x, y - rhs.y};
    }

    __device__ __host__ auto operator-(const rocfft_complex& rhs) const
    {
        auto lhs = *this;
        return lhs -= rhs;
    }

    // Multiplication operators
    __device__ __host__ auto& operator*=(const rocfft_complex& rhs)
    {
        return *this = {x * rhs.x - y * rhs.y, y * rhs.x + x * rhs.y};
    }

    __device__ __host__ auto operator*(const rocfft_complex& rhs) const
    {
        auto lhs = *this;
        return lhs *= rhs;
    }

    // Division operators
    __device__ __host__ auto& operator/=(const rocfft_complex& rhs)
    {
        // Form of Robert L. Smith's Algorithm 116
        if(abs(rhs.x) > abs(rhs.y))
        {
            Treal ratio = rhs.y / rhs.x;
            Treal scale = 1 / (rhs.x + rhs.y * ratio);
            *this       = {(x + y * ratio) * scale, (y - x * ratio) * scale};
        }
        else
        {
            Treal ratio = rhs.x / rhs.y;
            Treal scale = 1 / (rhs.x * ratio + rhs.y);
            *this       = {(y + x * ratio) * scale, (y * ratio - x) * scale};
        }
        return *this;
    }

    __device__ __host__ auto operator/(const rocfft_complex& rhs) const
    {
        auto lhs = *this;
        return lhs /= rhs;
    }

    // Comparison operators
    __device__ __host__ constexpr bool operator==(const rocfft_complex& rhs) const
    {
        return x == rhs.x && y == rhs.y;
    }

    __device__ __host__ constexpr bool operator!=(const rocfft_complex& rhs) const
    {
        return !(*this == rhs);
    }

    // Operators for complex-real computations
    template <typename U>
    __device__ __host__ auto& operator+=(const U& rhs)
    {
        return (x += Treal(rhs)), *this;
    }

    template <typename U>
    __device__ __host__ auto& operator-=(const U& rhs)
    {
        return (x -= Treal(rhs)), *this;
    }

    __device__ __host__ auto operator+(const Treal& rhs)
    {
        auto lhs = *this;
        return lhs += rhs;
    }

    __device__ __host__ auto operator-(const Treal& rhs)
    {
        auto lhs = *this;
        return lhs -= rhs;
    }

    template <typename U>
    __device__ __host__ auto& operator*=(const U& rhs)
    {
        return (x *= Treal(rhs)), (y *= Treal(rhs)), *this;
    }

    template <typename U>
    __device__ __host__ auto operator*(const U& rhs) const
    {
        auto lhs = *this;
        return lhs *= Treal(rhs);
    }

    template <typename U>
    __device__ __host__ auto& operator/=(const U& rhs)
    {
        return (x /= Treal(rhs)), (y /= Treal(rhs)), *this;
    }

    template <typename U>
    __device__ __host__ auto operator/(const U& rhs) const
    {
        auto lhs = *this;
        return lhs /= Treal(rhs);
    }

    template <typename U>
    __device__ __host__ constexpr bool operator==(const U& rhs) const
    {
        return x == Treal(rhs) && y == 0;
    }

    template <typename U>
    __device__ __host__ constexpr bool operator!=(const U& rhs) const
    {
        return !(*this == rhs);
    }
};

// Stream operators
#if !defined(__HIPCC_RTC__)
static std::ostream& operator<<(std::ostream& stream, const rocfft_fp16& f)
{
    return stream << static_cast<double>(f);
}

template <typename Treal>
std::ostream& operator<<(std::ostream& out, const rocfft_complex<Treal>& z)
{
    return out << '(' << static_cast<double>(z.x) << ',' << static_cast<double>(z.y) << ')';
}
#endif

// Operators for real-complex computations
template <typename U, typename Treal>
__device__ __host__ rocfft_complex<Treal> operator+(const U& lhs, const rocfft_complex<Treal>& rhs)
{
    return {Treal(lhs) + rhs.x, rhs.y};
}

template <typename U, typename Treal>
__device__ __host__ rocfft_complex<Treal> operator-(const U& lhs, const rocfft_complex<Treal>& rhs)
{
    return {Treal(lhs) - rhs.x, -rhs.y};
}

template <typename U, typename Treal>
__device__ __host__ rocfft_complex<Treal> operator*(const U& lhs, const rocfft_complex<Treal>& rhs)
{
    return {Treal(lhs) * rhs.x, Treal(lhs) * rhs.y};
}

template <typename U, typename Treal>
__device__ __host__ rocfft_complex<Treal> operator/(const U& lhs, const rocfft_complex<Treal>& rhs)
{
    // Form of Robert L. Smith's Algorithm 116
    if(rocfft_complex<Treal>::abs(rhs.x) > rocfft_complex<Treal>::abs(rhs.y))
    {
        Treal ratio = rhs.y / rhs.x;
        Treal scale = Treal(lhs) / (rhs.x + rhs.y * ratio);
        return {scale, -scale * ratio};
    }
    else
    {
        Treal ratio = rhs.x / rhs.y;
        Treal scale = Treal(lhs) / (rhs.x * ratio + rhs.y);
        return {ratio * scale, -scale};
    }
}

template <typename U, typename Treal>
__device__ __host__ constexpr bool operator==(const U& lhs, const rocfft_complex<Treal>& rhs)
{
    return Treal(lhs) == rhs.x && 0 == rhs.y;
}

template <typename U, typename Treal>
__device__ __host__ constexpr bool operator!=(const U& lhs, const rocfft_complex<Treal>& rhs)
{
    return !(lhs == rhs);
}

// Extending std namespace to handle rocfft_complex datatype
namespace std
{
    template <typename Treal>
    __device__ __host__ constexpr Treal real(const rocfft_complex<Treal>& z)
    {
        return z.x;
    }

    template <typename Treal>
    __device__ __host__ constexpr Treal imag(const rocfft_complex<Treal>& z)
    {
        return z.y;
    }

    template <typename Treal>
    __device__ __host__ constexpr rocfft_complex<Treal> conj(const rocfft_complex<Treal>& z)
    {
        return {z.x, -z.y};
    }

    template <typename Treal>
    __device__ __host__ inline Treal norm(const rocfft_complex<Treal>& z)
    {
        return (z.x * z.x) + (z.y * z.y);
    }

    template <typename Treal>
    __device__ __host__ inline Treal abs(const rocfft_complex<Treal>& z)
    {
        Treal tr = rocfft_complex<Treal>::abs(z.x), ti = rocfft_complex<Treal>::abs(z.y);
        return tr > ti ? (ti /= tr, tr * rocfft_complex<Treal>::sqrt(ti * ti + 1))
               : ti    ? (tr /= ti, ti * rocfft_complex<Treal>::sqrt(tr * tr + 1))
                       : 0;
    }
}

#endif // ROCFFT_COMPLEX_H

// Copyright (C) 2021 - 2023 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef ROCFFT_GPUBUF_H
#define ROCFFT_GPUBUF_H


// Simple RAII class for GPU buffers.  T is the type of pointer that
// data() returns
template <class T = void>
class gpubuf_t
{
public:
    gpubuf_t() {}
    // buffers are movable but not copyable
    gpubuf_t(gpubuf_t&& other)
    {
        std::swap(buf, other.buf);
        std::swap(owned, other.owned);
        std::swap(bsize, other.bsize);
        std::swap(device, other.device);
        std::swap(is_managed_memory, other.is_managed_memory);
    }
    gpubuf_t& operator=(gpubuf_t&& other)
    {
        std::swap(buf, other.buf);
        std::swap(owned, other.owned);
        std::swap(bsize, other.bsize);
        std::swap(device, other.device);
        std::swap(is_managed_memory, other.is_managed_memory);
        return *this;
    }
    gpubuf_t(const gpubuf_t&) = delete;
    gpubuf_t& operator=(const gpubuf_t&) = delete;

    static gpubuf_t make_nonowned(T* p, size_t size_bytes = 0)
    {
        gpubuf_t ret;
        ret.owned             = false;
        ret.buf               = p;
        ret.bsize             = size_bytes;
        ret.is_managed_memory = false; // irrelevant if not owned
        return ret;
    }

    ~gpubuf_t()
    {
        free();
    }

    static bool use_alloc_managed()
    {
        return std::getenv("ROCFFT_MALLOC_MANAGED");
    }

    hipError_t alloc(const size_t size, bool make_it_shared = false)
    {
        // remember the device that was current as of alloc, so we can
        // free on the correct device
        auto ret = hipGetDevice(&device);
        if(ret != hipSuccess)
            return ret;

        bsize             = size;
        is_managed_memory = use_alloc_managed() || make_it_shared;
        free();
        ret = is_managed_memory ? hipMallocManaged(&buf, bsize) : hipMalloc(&buf, bsize);
        if(ret != hipSuccess)
        {
            buf   = nullptr;
            bsize = 0;
        }
        return ret;
    }

    size_t size() const
    {
        return bsize;
    }

    void free()
    {
        if(buf != nullptr)
        {
            if(owned)
            {
                // free on the device we allocated on
                rocfft_scoped_device dev(device);
                (void)hipFree(buf);
            }
            buf   = nullptr;
            bsize = 0;
        }
        owned = true;
    }

    // return a pointer to the allocated memory, offset by the
    // specified number of bytes
    T* data_offset(size_t offset_bytes = 0) const
    {
        void* ptr = static_cast<char*>(buf) + offset_bytes;
        return static_cast<T*>(ptr);
    }

    T* data() const
    {
        return static_cast<T*>(buf);
    }

    // equality/bool tests
    bool operator==(std::nullptr_t n) const
    {
        return buf == n;
    }
    bool operator!=(std::nullptr_t n) const
    {
        return buf != n;
    }
    operator bool() const
    {
        return buf;
    }

private:
    // The GPU buffer
    void* buf = nullptr;
    // whether this object owns the 'buf' pointer (and hence needs to
    // free it)
    bool   owned             = true;
    bool   is_managed_memory = false;
    size_t bsize             = 0;
    int    device            = 0;
};

// default gpubuf that gives out void* pointers
typedef gpubuf_t<> gpubuf;
#endif

// Copyright (C) 2023 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef ROCFFT_DEVICE_PROPS_H
#define ROCFFT_DEVICE_PROPS_H


// get device properties
static hipDeviceProp_t get_curr_device_prop()
{
    hipDeviceProp_t prop;
    int             deviceId = 0;
    if(hipGetDevice(&deviceId) != hipSuccess)
        throw std::runtime_error("hipGetDevice failed.");

    if(hipGetDeviceProperties(&prop, deviceId) != hipSuccess)
        throw std::runtime_error("hipGetDeviceProperties failed for deviceId "
                                 + std::to_string(deviceId));

    return prop;
}

// check that the given grid/block dims will fit into the limits in
// the device properties.  throws std::runtime_error if the limits
// are exceeded.
static void launch_limits_check(const std::string&     kernel_name,
                                const dim3             gridDim,
                                const dim3             blockDim,
                                const hipDeviceProp_t& deviceProp)
{
    // Need lots of casting here because dim3 is unsigned but device
    // props are signed.  Cast direct comparisons to fix signedness
    // issues.  Promote types to 64-bit when multiplying to try to
    // avoid overflow.

    // Block limits along each dimension
    if(blockDim.x > static_cast<uint32_t>(deviceProp.maxThreadsDim[0])
       || blockDim.y > static_cast<uint32_t>(deviceProp.maxThreadsDim[1])
       || blockDim.z > static_cast<uint32_t>(deviceProp.maxThreadsDim[2]))
        throw std::runtime_error("max threads per dim exceeded: " + kernel_name);

    // Total threads for the whole block
    if(static_cast<uint64_t>(blockDim.x) * blockDim.y * blockDim.z
       > static_cast<uint64_t>(deviceProp.maxThreadsPerBlock))
        throw std::runtime_error("max threads per block exceeded: " + kernel_name);

    // Grid dimension limits
    if(gridDim.x > static_cast<uint32_t>(deviceProp.maxGridSize[0])
       || gridDim.y > static_cast<uint32_t>(deviceProp.maxGridSize[1])
       || gridDim.z > static_cast<uint32_t>(deviceProp.maxGridSize[2]))
        throw std::runtime_error("max grid size exceeded: " + kernel_name);
}

#endif

// Copyright (C) 2021 - 2023 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef ROCFFT_RTC_H
#define ROCFFT_RTC_H




struct DeviceCallIn;
class TreeNode;
class LeafNode;
struct GridParam;

// Helper class that handles alignment of kernel arguments
class RTCKernelArgs
{
public:
    RTCKernelArgs() = default;
    void append_ptr(const void* ptr)
    {
        append(&ptr, sizeof(void*));
    }
    void append_size_t(size_t s)
    {
        append(&s, sizeof(size_t));
    }
    void append_unsigned_int(unsigned int i)
    {
        append(&i, sizeof(unsigned int));
    }
    void append_int(int i)
    {
        append(&i, sizeof(int));
    }
    void append_double(double d)
    {
        append(&d, sizeof(double));
    }
    void append_float(float f)
    {
        append(&f, sizeof(float));
    }
    void append_half(rocfft_fp16 f)
    {
        append(&f, sizeof(rocfft_fp16));
    }
    template <typename T>
    void append_struct(const T& data)
    {
        append(&data, sizeof(T), 8);
    }

    size_t size_bytes() const
    {
        return buf.size();
    }
    void* data()
    {
        return buf.data();
    }

private:
    void append(const void* src, size_t nbytes, size_t align = 0)
    {
        // values need to be aligned to their width (i.e. 8-byte values
        // need 8-byte alignment, 4-byte needs 4-byte alignment)
        if(align == 0)
            align = nbytes;

        size_t oldsize = buf.size();
        size_t padding = oldsize % align ? align - (oldsize % align) : 0;
        buf.resize(oldsize + padding + nbytes);
        std::copy_n(static_cast<const char*>(src), nbytes, buf.begin() + oldsize + padding);
    }

    std::vector<char> buf;
};

// Base class for a runtime compiled kernel.  Subclassed for
// different kernel types that each have their own details about how
// to be launched.
struct RTCKernel
{
    // try to compile kernel for node, and attach compiled kernel to
    // node if successful.  returns nullptr if there is no matching
    // supported scheme + problem size.  throws runtime_error on
    // error.
    static std::shared_future<std::unique_ptr<RTCKernel>>
        runtime_compile(const LeafNode&    node,
                        const std::string& gpu_arch,
                        std::string&       kernel_name,
                        bool               enable_callbacks = false);

    // take already-compiled code object and prepare to launch the
    // named kernel
    RTCKernel(const std::string&       kernel_name,
              const std::vector<char>& code,
              dim3                     gridDim  = {},
              dim3                     blockDim = {});

    virtual ~RTCKernel()
    {
        kernel = nullptr;
        (void)hipModuleUnload(module);
        module = nullptr;
    }

    // disallow copies, since we expect this to be managed by smart ptr
    RTCKernel(const RTCKernel&) = delete;
    RTCKernel(RTCKernel&&)      = delete;

    void operator=(const RTCKernel&) = delete;

    // normal launch from within rocFFT execution plan
    void launch(DeviceCallIn& data, const hipDeviceProp_t& deviceProp);
    // direct launch with kernel args
    void launch(RTCKernelArgs&         kargs,
                dim3                   gridDim,
                dim3                   blockDim,
                unsigned int           lds_bytes,
                const hipDeviceProp_t& deviceProp,
                hipStream_t            stream = nullptr);

    // normal launch from within rocFFT execution plan
    bool get_occupancy(dim3 blockDim, unsigned int lds_bytes, int& occupancy);

#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS
    // Subclasses implement this - each kernel type has different
    // parameters
    virtual RTCKernelArgs get_launch_args(DeviceCallIn& data) = 0;
#endif

    // function to construct the correct RTCKernel object, given a kernel name and its compiled code
    using rtckernel_construct_t = std::function<std::unique_ptr<RTCKernel>(
        const std::string&, const std::vector<char>&, dim3, dim3)>;

    // grid parameters for this kernel.  may be set by runtime
    // compilation, if compilation of this kernel type knows how to.
    // Otherwise, TreeNode::SetupGridParam_internal will do it
    // later.
    dim3 gridDim;
    dim3 blockDim;

    std::string kernel_name;

protected:
#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS
    struct RTCGenerator
    {
        kernel_name_gen_t     generate_name;
        kernel_src_gen_t      generate_src;
        rtckernel_construct_t construct_rtckernel;

        virtual bool valid() const
        {
            return generate_name && generate_src && construct_rtckernel;
        }
        // generator is the correct type, but kernel is already compiled
        virtual bool is_pre_compiled() const
        {
            return false;
        }

        // if known at compile time, the grid parameters of the kernel
        // to launch with
        dim3 gridDim;
        dim3 blockDim;
    };
#endif

    hipModule_t   module = nullptr;
    hipFunction_t kernel = nullptr;
};

#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS

// helper functions to construct pieces of RTC kernel names
static const char* rtc_array_type_name(rocfft_array_type type)
{
    // hermitian is the same as complex in terms of generated code,
    // so give them the same names in kernels
    switch(type)
    {
    case rocfft_array_type_complex_interleaved:
    case rocfft_array_type_hermitian_interleaved:
        return "_CI";
    case rocfft_array_type_complex_planar:
    case rocfft_array_type_hermitian_planar:
        return "_CP";
    case rocfft_array_type_real:
        return "_R";
    default:
        return "_UN";
    }
}

static const char* rtc_precision_name(rocfft_precision precision)
{
    switch(precision)
    {
    case rocfft_precision_single:
        return "_sp";
    case rocfft_precision_double:
        return "_dp";
    case rocfft_precision_half:
        return "_half";
    }
}

static const char* rtc_precision_type_decl(rocfft_precision precision, bool is_complex = true)
{
    switch(precision)
    {
    case rocfft_precision_single:
        return is_complex ? "typedef rocfft_complex<float> scalar_type;\n"
                          : "typedef float scalar_type;\n";
    case rocfft_precision_double:
        return is_complex ? "typedef rocfft_complex<double> scalar_type;\n"
                          : "typedef double scalar_type;\n";
    case rocfft_precision_half:
        return is_complex ? "typedef rocfft_complex<rocfft_fp16> scalar_type;\n"
                          : "typedef rocfft_fp16 scalar_type;\n";
    }
}

static const char* rtc_cbtype_name(CallbackType cbtype)
{
    switch(cbtype)
    {
    case CallbackType::NONE:
        return "";
    case CallbackType::USER_LOAD_STORE:
        return "_CB";
    case CallbackType::USER_LOAD_STORE_R2C:
        return "_CBr2c";
    case CallbackType::USER_LOAD_STORE_C2R:
        return "_CBc2r";
    }
}

// realDataAsComplex is true if we're treating real data as complex
// (in an even-length real-complex FFT)
static const std::string rtc_const_cbtype_decl(CallbackType cbtype)
{
    switch(cbtype)
    {
    case CallbackType::NONE:
        return "static const CallbackType cbtype = CallbackType::NONE;\n";
    case CallbackType::USER_LOAD_STORE:
        return "static const CallbackType cbtype = CallbackType::USER_LOAD_STORE;\n";
    case CallbackType::USER_LOAD_STORE_R2C:
        return "static const CallbackType cbtype = CallbackType::USER_LOAD_STORE_R2C;\n";
    case CallbackType::USER_LOAD_STORE_C2R:
        return "static const CallbackType cbtype = CallbackType::USER_LOAD_STORE_C2R;\n";
    }
}
#endif

#endif

// Copyright (C) 2021 - 2023 Advanced Micro Devices, Inc. All rights reserved.
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



RTCKernel::RTCKernel(const std::string&       kernel_name,
                     const std::vector<char>& code,
                     dim3                     gridDim,
                     dim3                     blockDim)
    : gridDim(gridDim)
    , blockDim(blockDim)
    , kernel_name(kernel_name)
{
#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS
    // if we're only compiling, no need to actually load the code objects
    if(rocfft_getenv("ROCFFT_INTERNAL_COMPILE_ONLY") == "1")
        return;
#endif
    if(hipModuleLoadData(&module, code.data()) != hipSuccess)
        throw std::runtime_error("failed to load module for " + kernel_name);

    if(hipModuleGetFunction(&kernel, module, kernel_name.c_str()) != hipSuccess)
        throw std::runtime_error("failed to get function " + kernel_name);
}

#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS
void RTCKernel::launch(DeviceCallIn& data, const hipDeviceProp_t& deviceProp)
{
    RTCKernelArgs kargs = get_launch_args(data);

    const auto& gp = data.gridParam;

    launch(kargs,
           {gp.b_x, gp.b_y, gp.b_z},
           {gp.wgs_x, gp.wgs_y, gp.wgs_z},
           gp.lds_bytes,
           deviceProp,
           data.rocfft_stream);
}
#endif

void RTCKernel::launch(RTCKernelArgs&         kargs,
                       dim3                   gridDim,
                       dim3                   blockDim,
                       unsigned int           lds_bytes,
                       const hipDeviceProp_t& deviceProp,
                       hipStream_t            stream)
{
    launch_limits_check(kernel_name, gridDim, blockDim, deviceProp);
    auto  size     = kargs.size_bytes();
    void* config[] = {HIP_LAUNCH_PARAM_BUFFER_POINTER,
                      kargs.data(),
                      HIP_LAUNCH_PARAM_BUFFER_SIZE,
                      &size,
                      HIP_LAUNCH_PARAM_END};

#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS
    if(LOG_PLAN_ENABLED())
    {
        int        max_blocks_per_sm;
        hipError_t ret = hipModuleOccupancyMaxActiveBlocksPerMultiprocessor(
            &max_blocks_per_sm, kernel, blockDim.x * blockDim.y * blockDim.z, lds_bytes);
        rocfft_ostream* kernelplan_stream = LogSingleton::GetInstance().GetPlanOS();
        if(ret == hipSuccess)
            *kernelplan_stream << "Kernel occupancy: " << max_blocks_per_sm << std::endl;
        else
            *kernelplan_stream << "Can not retrieve occupancy info." << std::endl;
    }
#endif

    if(hipModuleLaunchKernel(kernel,
                             gridDim.x,
                             gridDim.y,
                             gridDim.z,
                             blockDim.x,
                             blockDim.y,
                             blockDim.z,
                             lds_bytes,
                             stream,
                             nullptr,
                             config)
       != hipSuccess)
        throw std::runtime_error("hipModuleLaunchKernel failure");
}

bool RTCKernel::get_occupancy(dim3 blockDim, unsigned int lds_bytes, int& occupancy)
{
    hipError_t ret = hipModuleOccupancyMaxActiveBlocksPerMultiprocessor(
        &occupancy, kernel, blockDim.x * blockDim.y * blockDim.z, lds_bytes);

    return ret == hipSuccess;
}

std::shared_future<std::unique_ptr<RTCKernel>>
    RTCKernel::runtime_compile(const LeafNode&    node,
                               const std::string& gpu_arch,
                               std::string&       kernel_name,
                               bool               enable_callbacks)
{
#ifndef ROCFFT_DEBUG_GENERATE_KERNEL_HARNESS
    int deviceId = 0;
    if(hipGetDevice(&deviceId) != hipSuccess)
    {
        throw std::runtime_error("failed to get device");
    }

    RTCGenerator generator;
    // try each type of generator until one is valid
    generator = RTCKernelStockham::generate_from_node(node, gpu_arch, enable_callbacks);
    if(!generator.valid())
        generator = RTCKernelTranspose::generate_from_node(node, gpu_arch, enable_callbacks);
    if(!generator.valid())
        generator = RTCKernelRealComplex::generate_from_node(node, gpu_arch, enable_callbacks);
    if(!generator.valid())
        generator = RTCKernelRealComplexEven::generate_from_node(node, gpu_arch, enable_callbacks);
    if(!generator.valid())
        generator = RTCKernelRealComplexEvenTranspose::generate_from_node(
            node, gpu_arch, enable_callbacks);
    if(!generator.valid())
        generator = RTCKernelBluesteinSingle::generate_from_node(node, gpu_arch, enable_callbacks);
    if(!generator.valid())
        generator = RTCKernelBluesteinMulti::generate_from_node(node, gpu_arch, enable_callbacks);

    if(generator.valid())
    {
        kernel_name = generator.generate_name();

        auto compile = [=](std::promise<std::unique_ptr<RTCKernel>> compile_promise) {
            if(hipSetDevice(deviceId) != hipSuccess)
            {
                compile_promise.set_exception(
                    std::make_exception_ptr(std::runtime_error("failed to set device")));
            }
            try
            {
                std::vector<char> code = RTCCache::cached_compile(
                    kernel_name, gpu_arch, generator.generate_src, generator_sum());
                compile_promise.set_value(generator.construct_rtckernel(
                    kernel_name, code, generator.gridDim, generator.blockDim));
            }
            catch(std::exception& e)
            {
                if(LOG_RTC_ENABLED())
                    (*LogSingleton::GetInstance().GetRTCOS()) << e.what() << std::endl;
                compile_promise.set_exception(std::current_exception());
            }
        };

        // compile to code object
        std::promise<std::unique_ptr<RTCKernel>>       compile_promise;
        std::shared_future<std::unique_ptr<RTCKernel>> compile_future
            = compile_promise.get_future();
        std::thread compile_thread(compile, std::move(compile_promise));
        // we'll wait for the future so the thread can continue
        // without being managed by this object
        compile_thread.detach();
        return compile_future;
    }
    // a pre-compiled rtc-stockham-kernel goes here
    else if(generator.is_pre_compiled())
    {
        kernel_name = generator.generate_name();
    }
#endif
    // kernel harness being generated or no kernel found, return
    // null RTCKernel
    std::promise<std::unique_ptr<RTCKernel>> p;
    p.set_value(nullptr);
    return p.get_future();
}

// Copyright (C) 2023 Advanced Micro Devices, Inc. All rights reserved.
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

// utility code to embed into generated test harnesses, to simplify
// allocating and initializing device memory

// copy a host vector to the device
template <typename T>
gpubuf_t<T> host_vec_to_dev(const std::vector<T>& hvec)
{
    gpubuf_t<T> ret;
    if(ret.alloc(sizeof(T) * hvec.size()) != hipSuccess)
        throw std::runtime_error("failed to hipMalloc");
    if(hipMemcpy(ret.data(), hvec.data(), sizeof(T) * hvec.size(), hipMemcpyHostToDevice)
       != hipSuccess)
        throw std::runtime_error("failed to memcpy");
    return ret;
}

template <typename T1, typename T2>
T1 ceildiv(T1 a, T2 b)
{
    return (a + b - 1) / b;
}

// generate random complex input
template <typename Tcomplex>
gpubuf_t<Tcomplex> random_complex_device(unsigned int count)
{
    std::vector<Tcomplex> hostBuf(count);

    auto partitions     = std::max<size_t>(std::thread::hardware_concurrency(), 32);
    auto partition_size = ceildiv(count, partitions);

#pragma omp parallel for
    for(unsigned int partition = 0; partition < partitions; ++partition)
    {
        std::mt19937                           gen(partition);
        std::uniform_real_distribution<double> dis(0.0, 1.0);

        auto begin = partition * partition_size;
        if(begin >= count)
            continue;
        auto end = std::min(begin + partition_size, count);

        for(auto d = hostBuf.begin() + begin; d != hostBuf.begin() + end; ++d)
        {
            d->x = dis(gen);
            d->y = dis(gen);
        }
    }
    return host_vec_to_dev(hostBuf);
}

// generate random real input
template <typename Treal>
gpubuf_t<Treal> random_real_device(unsigned int count)
{
    std::vector<Treal> hostBuf(count);

    auto partitions     = std::max<size_t>(std::thread::hardware_concurrency(), 32);
    auto partition_size = ceildiv(count, partitions);

#pragma omp parallel for
    for(unsigned int partition = 0; partition < partitions; ++partition)
    {
        std::mt19937                           gen(partition);
        std::uniform_real_distribution<double> dis(0.0, 1.0);

        auto begin = partition * partition_size;
        if(begin >= count)
            continue;
        auto end = std::min(begin + partition_size, count);

        for(auto d = hostBuf.begin() + begin; d != hostBuf.begin() + end; ++d)
        {
            *d = dis(gen);
        }
    }
    return host_vec_to_dev(hostBuf);
}

// compile a function using hipRTC
std::unique_ptr<RTCKernel> compile(const std::string& name, const std::string& src)
{
    hiprtcProgram prog;
    if(hiprtcCreateProgram(&prog, src.c_str(), "rtc.cu", 0, nullptr, nullptr) != HIPRTC_SUCCESS)
    {
        throw std::runtime_error("unable to create program");
    }
    std::vector<const char*> options;
    options.reserve(2);
    options.push_back("-O3");
    options.push_back("-mcumode");

    auto compileResult = hiprtcCompileProgram(prog, options.size(), options.data());
    if(compileResult != HIPRTC_SUCCESS)
    {
        size_t logSize = 0;
        hiprtcGetProgramLogSize(prog, &logSize);

        if(logSize)
        {
            std::vector<char> log(logSize, '\0');
            if(hiprtcGetProgramLog(prog, log.data()) == HIPRTC_SUCCESS)
                throw std::runtime_error(log.data());
        }
        throw std::runtime_error("compile failed without log");
    }

    size_t codeSize;
    if(hiprtcGetCodeSize(prog, &codeSize) != HIPRTC_SUCCESS)
        throw std::runtime_error("failed to get code size");

    std::vector<char> code(codeSize);
    if(hiprtcGetCode(prog, code.data()) != HIPRTC_SUCCESS)
        throw std::runtime_error("failed to get code");
    hiprtcDestroyProgram(&prog);

    return std::make_unique<RTCKernel>(name, code);
}
typedef rocfft_complex<double> scalar_type;
// declare globals for kernel fft_rtc_back_len_4096_factors_16_16_16_wgs_256_tpt_256_halfLds_dim_1_dp_ip_CI_unitstride_sbrr_dirReg
gpubuf_t<scalar_type> twiddles;
gpubuf_t<size_t> lengths;
gpubuf_t<size_t> stride;
size_t nbatch;
gpubuf_t<scalar_type> buf;
dim3 gridDim;
dim3 blockDim;
unsigned int lds_bytes;
 void init_kernel() {
// edit this function to set the inputs to the kernel
twiddles = random_complex_device<scalar_type>(0);
lengths = host_vec_to_dev<size_t>({});
stride = host_vec_to_dev<size_t>({});
nbatch = 0;
buf = random_complex_device<scalar_type>(0);
gridDim = {1,1,1};
blockDim = {1,1,1};
lds_bytes = 0;
}


 void launch_kernel(std::unique_ptr<RTCKernel>& rtckernel,const hipDeviceProp_t& deviceProp) {
RTCKernelArgs kargs;
kargs.append_ptr(twiddles.data());
kargs.append_ptr(lengths.data());
kargs.append_ptr(stride.data());
kargs.append_size_t(nbatch);
kargs.append_ptr(nullptr);
kargs.append_ptr(nullptr);
kargs.append_ptr(0);
kargs.append_ptr(nullptr);
kargs.append_ptr(nullptr);
kargs.append_ptr(buf.data());
rtckernel->launch(kargs,gridDim,blockDim,lds_bytes,deviceProp);
}


 int main() {
// open kernel source file and read it to a string
std::ifstream kernel_file;
std::string kernel_src;
kernel_file.open("fft_rtc_back_len_4096_factors_16_16_16_wgs_256_tpt_256_halfLds_dim_1_dp_ip_CI_unitstride_sbrr_dirReg.h");
if( !kernel_file.is_open()) {
throw std::runtime_error("fft_rtc_back_len_4096_factors_16_16_16_wgs_256_tpt_256_halfLds_dim_1_dp_ip_CI_unitstride_sbrr_dirReg.h not found in current directory");

}

std::getline(kernel_file,kernel_src,static_cast<char>(0));
// compile the kernel
std::unique_ptr<RTCKernel> rtc_kernel = compile("fft_rtc_back_len_4096_factors_16_16_16_wgs_256_tpt_256_halfLds_dim_1_dp_ip_CI_unitstride_sbrr_dirReg",kernel_src);
// initialize arguments, grid
init_kernel();
hipDeviceProp_t deviceProp = get_curr_device_prop();
unsigned int num_trials = 1;
hipEvent_t start;
hipEvent_t stop;
std::vector<float> samples;
samples.resize(num_trials);
if(hipEventCreate(&start) != hipSuccess) {
throw std::runtime_error("hipEventCreate failed");

}

if(hipEventCreate(&stop) != hipSuccess) {
throw std::runtime_error("hipEventCreate failed");

}

for(unsigned int trial = 0; trial < num_trials; ++trial) {
 if(hipEventRecord(start) != hipSuccess) {
throw std::runtime_error("hipEventRecord failed");

}

launch_kernel(rtc_kernel,deviceProp);
if(hipEventRecord(stop) != hipSuccess) {
throw std::runtime_error("hipEventRecord failed");

}

if(hipEventSynchronize(stop) != hipSuccess) {
throw std::runtime_error("hipEventRecord failed");

}

if(hipEventElapsedTime(samples.data() + trial,start,stop) != hipSuccess) {
throw std::runtime_error("hipEventElapsedTime failed");

}


}
for(unsigned int trial = 0; trial < num_trials; ++trial) {
 printf("%f ms\n",static_cast<double>(samples[trial]));

}
std::sort(samples.begin(),samples.end());
printf("median: %f ms\n",num_trials % 2 ? samples[num_trials / 2] : (samples[num_trials / 2] + samples[num_trials / 2 + 1]) / 2);
return 0;
}
