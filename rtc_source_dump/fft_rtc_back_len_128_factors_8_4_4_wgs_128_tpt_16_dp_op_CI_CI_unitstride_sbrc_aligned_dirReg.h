
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

// Copyright (C) 2016 - 2023 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef COMMON_H
#define COMMON_H

#if defined(__HIPCC_RTC__) || defined(__CUDACC_RTC__)
typedef signed int   int32_t;
typedef unsigned int uint32_t;
#endif

#ifdef WIN32
#define ROCFFT_DEVICE_EXPORT __declspec(dllexport)
#else
#define ROCFFT_DEVICE_EXPORT
#endif

// NB:
//   All kernels were compiled based on the assumption that the default max
//   work group size is 256. This default value in compiler might change in
//   future. Each kernel has to explicitly set proper sizes through
//   __launch_bounds__ or __attribute__.
//   Further performance tuning might be done later.
static const unsigned int LAUNCH_BOUNDS_R2C_C2R_KERNEL = 256;

#ifdef __HIP_PLATFORM_NVIDIA__

__device__ inline rocfft_complex<float> operator-(const rocfft_complex<float>& a,
                                                  const rocfft_complex<float>& b)
{
    return rocfft_complex<float>(a.x - b.x, a.y - b.y);
}
__device__ inline rocfft_complex<float> operator+(const rocfft_complex<float>& a,
                                                  const rocfft_complex<float>& b)
{
    return rocfft_complex<float>(a.x + b.x, a.y + b.y);
}
__device__ inline rocfft_complex<float> operator*(const float& a, const rocfft_complex<float>& b)
{
    return rocfft_complex<float>(a * b.x, a * b.y);
}
__device__ inline rocfft_complex<float> operator*=(rocfft_complex<float>&       a,
                                                   const rocfft_complex<float>& b)
{
    a = cuCmulf(a, b);
    return a;
}
__device__ inline rocfft_complex<float> operator*=(rocfft_complex<float>& a, const float& b)
{
    a = cuCmulf(a, rocfft_complex<float>(b, b));
    return a;
}
__device__ inline rocfft_complex<float> operator-(const rocfft_complex<float>& a)
{
    return cuCmulf(a, rocfft_complex<float>(-1.0, -1.0));
}

__device__ inline rocfft_complex<double> operator-(const rocfft_complex<double>& a,
                                                   const rocfft_complex<double>& b)
{
    return rocfft_complex<double>(a.x - b.x, a.y - b.y);
}
__device__ inline rocfft_complex<double> operator+(const rocfft_complex<double>& a,
                                                   const rocfft_complex<double>& b)
{
    return rocfft_complex<double>(a.x + b.x, a.y + b.y);
}
__device__ inline rocfft_complex<double> operator*(const double& a, const rocfft_complex<double>& b)
{
    return rocfft_complex<double>(a * b.x, a * b.y);
}
__device__ inline rocfft_complex<double> operator*=(rocfft_complex<double>&       a,
                                                    const rocfft_complex<double>& b)
{
    a = cuCmul(a, b);
    return a;
}
__device__ inline rocfft_complex<double> operator*=(rocfft_complex<double>& a, const double& b)
{
    a = cuCmul(a, rocfft_complex<double>(b, b));
    return a;
}
__device__ inline rocfft_complex<double> operator-(const rocfft_complex<double>& a)
{
    return cuCmul(a, rocfft_complex<double>(-1.0, -1.0));
}

#endif

template <class T>
struct real_type;

template <>
struct real_type<rocfft_complex<float>>
{
    typedef float type;
};

template <>
struct real_type<rocfft_complex<double>>
{
    typedef double type;
};

template <>
struct real_type<rocfft_complex<rocfft_fp16>>
{
    typedef rocfft_fp16 type;
};

template <class T>
using real_type_t = typename real_type<T>::type;

template <class T>
struct complex_type;

template <>
struct complex_type<float>
{
    typedef rocfft_complex<float> type;
};

template <>
struct complex_type<double>
{
    typedef rocfft_complex<double> type;
};

template <class T>
using complex_type_t = typename complex_type<T>::type;

/// example of using complex_type_t:
// complex_type_t<float> float_complex_val;
// complex_type_t<double> double_complex_val;

template <typename T>
__device__ T TWLstep1(const T* twiddles, size_t u)
{
    size_t j      = u & 255;
    T      result = twiddles[j];
    return result;
}

template <typename T>
__device__ T TWLstep2(const T* twiddles, size_t u)
{
    size_t j      = u & 255;
    T      result = twiddles[j];
    u >>= 8;
    j      = u & 255;
    result = T((result.x * twiddles[256 + j].x - result.y * twiddles[256 + j].y),
               (result.y * twiddles[256 + j].x + result.x * twiddles[256 + j].y));
    return result;
}

template <typename T>
__device__ T TWLstep3(const T* twiddles, size_t u)
{
    size_t j      = u & 255;
    T      result = twiddles[j];
    u >>= 8;
    j      = u & 255;
    result = T((result.x * twiddles[256 + j].x - result.y * twiddles[256 + j].y),
               (result.y * twiddles[256 + j].x + result.x * twiddles[256 + j].y));
    u >>= 8;
    j      = u & 255;
    result = T((result.x * twiddles[512 + j].x - result.y * twiddles[512 + j].y),
               (result.y * twiddles[512 + j].x + result.x * twiddles[512 + j].y));
    return result;
}

template <typename T>
__device__ T TWLstep4(const T* twiddles, size_t u)
{
    size_t j      = u & 255;
    T      result = twiddles[j];
    u >>= 8;
    j      = u & 255;
    result = T((result.x * twiddles[256 + j].x - result.y * twiddles[256 + j].y),
               (result.y * twiddles[256 + j].x + result.x * twiddles[256 + j].y));
    u >>= 8;
    j      = u & 255;
    result = T((result.x * twiddles[512 + j].x - result.y * twiddles[512 + j].y),
               (result.y * twiddles[512 + j].x + result.x * twiddles[512 + j].y));
    u >>= 8;
    j      = u & 255;
    result = T((result.x * twiddles[768 + j].x - result.y * twiddles[768 + j].y),
               (result.y * twiddles[768 + j].x + result.x * twiddles[768 + j].y));
    return result;
}

#define TWIDDLE_STEP_MUL_FWD(TWFUNC, TWIDDLES, INDEX, REG) \
    {                                                      \
        T              W = TWFUNC(TWIDDLES, INDEX);        \
        real_type_t<T> TR, TI;                             \
        TR    = (W.x * REG.x) - (W.y * REG.y);             \
        TI    = (W.y * REG.x) + (W.x * REG.y);             \
        REG.x = TR;                                        \
        REG.y = TI;                                        \
    }

#define TWIDDLE_STEP_MUL_INV(TWFUNC, TWIDDLES, INDEX, REG) \
    {                                                      \
        T              W = TWFUNC(TWIDDLES, INDEX);        \
        real_type_t<T> TR, TI;                             \
        TR    = (W.x * REG.x) + (W.y * REG.y);             \
        TI    = -(W.y * REG.x) + (W.x * REG.y);            \
        REG.x = TR;                                        \
        REG.y = TI;                                        \
    }

#endif // COMMON_H

// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
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

#ifndef DEVICE_ENUM_H
#define DEVICE_ENUM_H

enum StrideBin
{
    SB_UNIT,
    SB_NONUNIT,
};

enum class EmbeddedType : int
{
    NONE        = 0, // Works as the regular complex to complex FFT kernel
    Real2C_POST = 1, // Works with even-length real2complex post-processing
    C2Real_PRE  = 2, // Works with even-length complex2real pre-processing
};

// TODO: rework this
//
//
// NB:
// SBRC kernels can be used in various scenarios. Instead of tmeplate all
// combinations, we define/enable the cases in using only. In this way,
// the logic in POWX_LARGE_SBRC_GENERATOR() would be simple. People could
// add more later or find a way to simply POWX_LARGE_SBRC_GENERATOR().
enum SBRC_TYPE
{
    SBRC_2D = 2, // for one step in 1D middle size decomposition

    SBRC_3D_FFT_TRANS_XY_Z = 3, // for 3D C2C middle size fused kernel
    SBRC_3D_FFT_TRANS_Z_XY = 4, // for 3D R2C middle size fused kernel
    SBRC_3D_TRANS_XY_Z_FFT = 5, // for 3D C2R middle size fused kernel

    // for 3D R2C middle size, to fuse FFT, Even-length real2complex, and Transpose_Z_XY
    SBRC_3D_FFT_ERC_TRANS_Z_XY = 6,

    // for 3D C2R middle size, to fuse Transpose_XY_Z, Even-length complex2real, and FFT
    SBRC_3D_TRANS_XY_Z_ECR_FFT = 7,
};

enum SBRC_TRANSPOSE_TYPE
{
    NONE, // indicating this is a non-sbrc type, an SBRC kernel shouldn't have this
    DIAGONAL, // best, but requires cube sizes
    TILE_ALIGNED, // OK, doesn't require handling unaligned corner case
    TILE_UNALIGNED,
};

enum DirectRegType
{
    // the direct-to-from-reg codes are not even generated from generator
    // or is generated but we don't want to use it in some arch
    FORCE_OFF_OR_NOT_SUPPORT,
    TRY_ENABLE_IF_SUPPORT, // Use the direct-to-from-reg function
};

enum IntrinsicAccessType
{
    DISABLE_BOTH, // turn-off intrinsic buffer load/store
    ENABLE_LOAD_ONLY, // turn-on intrinsic buffer load only
    ENABLE_BOTH, // turn-on both intrinsic buffer load/store
};

enum BluesteinType
{
    BT_NONE,
    BT_SINGLE_KERNEL, // implementation for small lengths (that fit in LDS)
    BT_MULTI_KERNEL, // large lengths
    BT_MULTI_KERNEL_FUSED, // large lengths with fused intermediate Bluestein operations
};

enum BluesteinFuseType
{ // Fused operation types for multi-kernel Bluestein
    BFT_NONE,
    BFT_FWD_CHIRP, // fused chirp + padding + forward fft
    BFT_FWD_CHIRP_MUL, // fused chirp / input Hadamard product + padding + forward fft
    BFT_INV_CHIRP_MUL, // fused convolution Hadamard product + inverse fft + chirp Hadamard product
};

enum PartialPassType
{
    PPT_NONE,
    PPT_SBCC,
    PPT_SBRR,
};

#endif

/******************************************************************************
 * Copyright 2021 Advanced Micro Devices, Inc. All rights reserved.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *****************************************************************************/
/*! \file
    \brief Architecture-specific operators on memory added for GFX9
*/
// reference:
//   https://github.com/llvm/llvm-project/blob/main/llvm/test/CodeGen/AMDGPU/llvm.amdgcn.raw.buffer.load.ll

#ifndef INTRINSIC_MEM_ACCESS_H
#define INTRINSIC_MEM_ACCESS_H

#if defined(__clang__) && defined(__HIP__)

#if(defined(__NVCC__) || defined(__HIPCC__)) \
    || (defined(__clang__) && (defined(__CUDA__)) || defined(__HIP__))
#define ROCFFT_DEVICE __forceinline__ __device__
#elif defined(__CUDACC_RTC__)
#define ROCFFT_DEVICE __forceinline__ __device__
#else
#define ROCFFT_DEVICE inline
#endif

#if defined(__gfx803__) || defined(__gfx900__) || defined(__gfx906__) || defined(__gfx908__) \
    || defined(__gfx90a__) || defined(__gfx940__) || defined(__gfx941__)                     \
    || defined(__gfx942__) // test device
#define USE_GFX_BUFFER_INTRINSIC
#define BUFFER_RESOURCE_3RD_DWORD 0x00020000
#elif defined(__gfx1030__) // special device
#define USE_GFX_BUFFER_INTRINSIC
#define BUFFER_RESOURCE_3RD_DWORD 0x31014000
#else // not support
#define BUFFER_RESOURCE_3RD_DWORD -1
#endif

/// Controls AMD gfx arch cache operations
struct CacheOperation
{
    enum Kind
    {
        /// Cache at all levels - accessed again
        Always,
        /// Cache at global level; glc = 1
        Global,
        /// Streaming - likely to be accessed once; slc = 1
        Streaming,
        /// Indicates the line will not be used again, glc = 1; slc = 1
        LastUse
    };
};

using float16_t = rocfft_fp16;
using float32_t = float;

template <typename T, int N>
struct NativeVector
{
    using type = T __attribute__((ext_vector_type(N)));
};

// template <int N>
// struct NativeVector<cutlass::half_t, N>
// {
//   using type = typename NativeVector<float16_t, N>::type;
// };

// template <int N>
// struct NativeVector<cutlass::bfloat16_t, N>
// {
//   using type = typename NativeVector<float16_t, N>::type;
// };

using float32x2_t = NativeVector<float, 2>::type;
using float32x4_t = NativeVector<float, 4>::type;

using int32x4_t = NativeVector<int, 4>::type;

////////////////////////////////////////////////////////////////////////////////////////////////////

struct alignas(16) BufferResource
{
    union Desc
    {
        int32x4_t d128;
        void*     d64[2];
        uint32_t  d32[4];
    };

    ROCFFT_DEVICE
    BufferResource(void const* base_addr, uint32_t num_records = (0xFFFFFFFF - 1))
    {
        // Reference:
        //   For CDNA: see section 9.1.8 in the AMD resources
        //   https://developer.amd.com/wp-content/resources/CDNA1_Shader_ISA_14December2020.pdf
        //   For RDNA: see section 8.1.8 in the AMD resources
        //   https://developer.amd.com/wp-content/resources/RDNA2_Shader_ISA_November2020.pdf
        //   The d32[3] field represents the 0x[127] ~ [96]

        // 64-bit base address
        desc_.d64[0] = const_cast<void*>(base_addr);
        // 32-bit number of records in bytes which is used to guard against out-of-range access
        desc_.d32[2] = num_records;
        // 32-bit buffer resource descriptor
        desc_.d32[3] = BUFFER_RESOURCE_3RD_DWORD;
    }

    ROCFFT_DEVICE
    operator int32x4_t()
    {
        // return desc_.d128; // NOTE HIP: Crashes compiler; see below

        /// This hack is to enforce scalarization of the variable "base_addr", where in some
        /// circumstances it becomes vectorized and then in turn causes illegal lowering to GCN ISA
        /// since compiler effectively tries to stuff VGPRs in slots where it only accepts SGPRs
        Desc ret;
        ret.d32[0] = __builtin_amdgcn_readfirstlane(desc_.d32[0]);
        ret.d32[1] = __builtin_amdgcn_readfirstlane(desc_.d32[1]);
        ret.d64[1] = desc_.d64[1];
        return ret.d128;
        ///
    }

    Desc desc_;
};

////////////////////////////////////////////////////////////////////////////////////////////////////

///
/// Load
///

// 1 byte
__device__ char
    llvm_amdgcn_raw_buffer_load_i8(int32x4_t buffer_resource,
                                   uint32_t  voffset,
                                   uint32_t  soffset,
                                   int32_t   cache_op) __asm("llvm.amdgcn.raw.buffer.load.i8");

// 2 bytes
__device__ float16_t
    llvm_amdgcn_raw_buffer_load_f16(int32x4_t buffer_resource,
                                    uint32_t  voffset,
                                    uint32_t  soffset,
                                    int32_t   cache_op) __asm("llvm.amdgcn.raw.buffer.load.f16");

// 4 bytes
__device__ float32_t
    llvm_amdgcn_raw_buffer_load_f32(int32x4_t buffer_resource,
                                    uint32_t  voffset,
                                    uint32_t  soffset,
                                    int32_t   cache_op) __asm("llvm.amdgcn.raw.buffer.load.f32");

// 8 bytes
__device__ float32x2_t
    llvm_amdgcn_raw_buffer_load_f32x2(int32x4_t buffer_resource,
                                      uint32_t  voffset,
                                      uint32_t  soffset,
                                      int32_t cache_op) __asm("llvm.amdgcn.raw.buffer.load.v2f32");

// 16 bytes
__device__ float32x4_t
    llvm_amdgcn_raw_buffer_load_f32x4(int32x4_t buffer_resource,
                                      uint32_t  voffset,
                                      uint32_t  soffset,
                                      int32_t cache_op) __asm("llvm.amdgcn.raw.buffer.load.v4f32");

///
/// Store
///

// 1 byte
__device__ void
    llvm_amdgcn_raw_buffer_store_i8(char      data,
                                    int32x4_t buffer_resource,
                                    uint32_t  voffset,
                                    uint32_t  soffset,
                                    int32_t   cache_op) __asm("llvm.amdgcn.raw.buffer.store.i8");

// 2 bytes
__device__ void
    llvm_amdgcn_raw_buffer_store_f16(float16_t data,
                                     int32x4_t buffer_resource,
                                     uint32_t  voffset,
                                     uint32_t  soffset,
                                     int32_t   cache_op) __asm("llvm.amdgcn.raw.buffer.store.f16");

// 4 bytes
__device__ void
    llvm_amdgcn_raw_buffer_store_f32(float32_t data,
                                     int32x4_t buffer_resource,
                                     uint32_t  voffset,
                                     uint32_t  soffset,
                                     int32_t   cache_op) __asm("llvm.amdgcn.raw.buffer.store.f32");

// 8 bytes
__device__ void llvm_amdgcn_raw_buffer_store_f32x2(
    float32x2_t data,
    int32x4_t   buffer_resource,
    uint32_t    voffset,
    uint32_t    soffset,
    int32_t     cache_op) __asm("llvm.amdgcn.raw.buffer.store.v2f32");

// 16 bytes
__device__ void llvm_amdgcn_raw_buffer_store_f32x4(
    float32x4_t data,
    int32x4_t   buffer_resource,
    uint32_t    voffset,
    uint32_t    soffset,
    int32_t     cache_op) __asm("llvm.amdgcn.raw.buffer.store.v4f32");

////////////////////////////////////////////////////////////////////////////////////////////////////

template <
    /// Fragment type to store loaded data
    typename AccessType,
    /// The bytes of loading
    int LoadBytes,
    /// Cache operation
    CacheOperation::Kind cache_op = CacheOperation::Always>
struct buffer_load;

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_load<AccessType, 1, cache_op>
{
    ROCFFT_DEVICE
    buffer_load() {}

    ROCFFT_DEVICE
    buffer_load(
        AccessType& D, void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset  = pred_guard ? voffset : -1;
        char ret = llvm_amdgcn_raw_buffer_load_i8(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        D = *reinterpret_cast<AccessType*>(&ret);
    }

    ROCFFT_DEVICE
    AccessType load(void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset  = pred_guard ? voffset : -1;
        char ret = llvm_amdgcn_raw_buffer_load_i8(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        return *reinterpret_cast<AccessType*>(&ret);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_load<AccessType, 2, cache_op>
{
    ROCFFT_DEVICE
    buffer_load() {}

    ROCFFT_DEVICE
    buffer_load(
        AccessType& D, void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset       = pred_guard ? voffset : -1;
        float16_t ret = llvm_amdgcn_raw_buffer_load_f16(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        D = *reinterpret_cast<AccessType*>(&ret);
    }

    ROCFFT_DEVICE
    AccessType load(void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset       = pred_guard ? voffset : -1;
        float16_t ret = llvm_amdgcn_raw_buffer_load_f16(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        return *reinterpret_cast<AccessType*>(&ret);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_load<AccessType, 4, cache_op>
{
    ROCFFT_DEVICE
    buffer_load() {}

    ROCFFT_DEVICE
    buffer_load(
        AccessType& D, void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset       = pred_guard ? voffset : -1;
        float32_t ret = llvm_amdgcn_raw_buffer_load_f32(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        D = *reinterpret_cast<AccessType*>(&ret);
    }

    ROCFFT_DEVICE
    AccessType load(void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset       = pred_guard ? voffset : -1;
        float32_t ret = llvm_amdgcn_raw_buffer_load_f32(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        return *reinterpret_cast<AccessType*>(&ret);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_load<AccessType, 8, cache_op>
{
    ROCFFT_DEVICE
    buffer_load() {}

    ROCFFT_DEVICE
    buffer_load(
        AccessType& D, void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset         = pred_guard ? voffset : -1;
        float32x2_t ret = llvm_amdgcn_raw_buffer_load_f32x2(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        D = *reinterpret_cast<AccessType*>(&ret);
    }

    ROCFFT_DEVICE
    AccessType load(void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset         = pred_guard ? voffset : -1;
        float32x2_t ret = llvm_amdgcn_raw_buffer_load_f32x2(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        return *reinterpret_cast<AccessType*>(&ret);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_load<AccessType, 16, cache_op>
{
    ROCFFT_DEVICE
    buffer_load() {}

    ROCFFT_DEVICE
    buffer_load(
        AccessType& D, void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset         = pred_guard ? voffset : -1;
        float32x4_t ret = llvm_amdgcn_raw_buffer_load_f32x4(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        D = *reinterpret_cast<AccessType*>(&ret);
    }

    ROCFFT_DEVICE
    AccessType load(void const* base_ptr, uint32_t voffset, uint32_t soffset, bool pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset         = pred_guard ? voffset : -1;
        float32x4_t ret = llvm_amdgcn_raw_buffer_load_f32x4(
            buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
        return *reinterpret_cast<AccessType*>(&ret);
    }
};

////////////////////////////////////////////////////////////////////////////////////////////////////

template <
    /// Fragment type to store loaded data
    typename AccessType,
    /// The width of loading
    int NumElements,
    /// Cache operation
    CacheOperation::Kind cache_op = CacheOperation::Always>
struct buffer_store;

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_store<AccessType, 1, cache_op>
{
    ROCFFT_DEVICE
    buffer_store(const AccessType& D,
                 void const*       base_ptr,
                 uint32_t          voffset,
                 uint32_t          soffset,
                 bool              pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset   = pred_guard ? voffset : -1;
        char data = *reinterpret_cast<char const*>(&D);
        llvm_amdgcn_raw_buffer_store_i8(
            data, buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_store<AccessType, 2, cache_op>
{
    ROCFFT_DEVICE
    buffer_store(const AccessType& D,
                 void const*       base_ptr,
                 uint32_t          voffset,
                 uint32_t          soffset,
                 bool              pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset        = pred_guard ? voffset : -1;
        float16_t data = *reinterpret_cast<float16_t const*>(&D);
        llvm_amdgcn_raw_buffer_store_f16(
            data, buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_store<AccessType, 4, cache_op>
{
    ROCFFT_DEVICE
    buffer_store(const AccessType& D,
                 void const*       base_ptr,
                 uint32_t          voffset,
                 uint32_t          soffset,
                 bool              pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset        = pred_guard ? voffset : -1;
        float32_t data = *reinterpret_cast<float32_t const*>(&D);
        llvm_amdgcn_raw_buffer_store_f32(
            data, buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_store<AccessType, 8, cache_op>
{
    ROCFFT_DEVICE
    buffer_store(const AccessType& D,
                 void const*       base_ptr,
                 uint32_t          voffset,
                 uint32_t          soffset,
                 bool              pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset          = pred_guard ? voffset : -1;
        float32x2_t data = *reinterpret_cast<float32x2_t const*>(&D);
        llvm_amdgcn_raw_buffer_store_f32x2(
            data, buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
    }
};

template <typename AccessType, CacheOperation::Kind cache_op>
struct buffer_store<AccessType, 16, cache_op>
{
    ROCFFT_DEVICE
    buffer_store(const AccessType& D,
                 void const*       base_ptr,
                 uint32_t          voffset,
                 uint32_t          soffset,
                 bool              pred_guard)
    {
        BufferResource buffer_rsc(base_ptr);
        voffset          = pred_guard ? voffset : -1;
        float32x4_t data = *reinterpret_cast<float32x4_t const*>(&D);
        llvm_amdgcn_raw_buffer_store_f32x4(
            data, buffer_rsc, voffset, __builtin_amdgcn_readfirstlane(soffset), cache_op);
    }
};

////////////////////////////////////////////////////////////////////////////////////////////////////

#endif // defined(__clang__) && defined(__HIP__)

#endif // INTRINSIC_MEM_ACCESS_H

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

#ifndef ROCFFT_DEVICE_CALLBACK_H
#define ROCFFT_DEVICE_CALLBACK_H



// user-provided data saying what callbacks to run
struct UserCallbacks
{
    void*  load_cb_fn        = nullptr;
    void*  load_cb_data      = nullptr;
    size_t load_cb_lds_bytes = 0;

    void*  store_cb_fn        = nullptr;
    void*  store_cb_data      = nullptr;
    size_t store_cb_lds_bytes = 0;
};

// default callback implementations that just do simple load/store
template <typename T>
__device__ T load_cb_default(T* data, size_t offset, void* cbdata, void* sharedMem)
{
    return data[offset];
}

template <typename T>
__device__ void store_cb_default(T* data, size_t offset, T element, void* cbdata, void* sharedMem)
{
    data[offset] = element;
}

// callback function types
template <typename T>
struct callback_type;

template <>
struct callback_type<rocfft_complex<rocfft_fp16>>
{
    typedef rocfft_complex<rocfft_fp16> (*load)(rocfft_complex<rocfft_fp16>* data,
                                                size_t                       offset,
                                                void*                        cbdata,
                                                void*                        sharedMem);
    typedef void (*store)(rocfft_complex<rocfft_fp16>* data,
                          size_t                       offset,
                          rocfft_complex<rocfft_fp16>  element,
                          void*                        cbdata,
                          void*                        sharedMem);
};

static __device__ auto load_cb_default_complex_half = load_cb_default<rocfft_complex<rocfft_fp16>>;
static __device__ auto store_cb_default_complex_half
    = store_cb_default<rocfft_complex<rocfft_fp16>>;

template <>
struct callback_type<rocfft_complex<float>>
{
    typedef rocfft_complex<float> (*load)(rocfft_complex<float>* data,
                                          size_t                 offset,
                                          void*                  cbdata,
                                          void*                  sharedMem);
    typedef void (*store)(rocfft_complex<float>* data,
                          size_t                 offset,
                          rocfft_complex<float>  element,
                          void*                  cbdata,
                          void*                  sharedMem);
};

static __device__ auto load_cb_default_complex_float  = load_cb_default<rocfft_complex<float>>;
static __device__ auto store_cb_default_complex_float = store_cb_default<rocfft_complex<float>>;

template <>
struct callback_type<rocfft_complex<double>>
{
    typedef rocfft_complex<double> (*load)(rocfft_complex<double>* data,
                                           size_t                  offset,
                                           void*                   cbdata,
                                           void*                   sharedMem);
    typedef void (*store)(rocfft_complex<double>* data,
                          size_t                  offset,
                          rocfft_complex<double>  element,
                          void*                   cbdata,
                          void*                   sharedMem);
};

static __device__ auto load_cb_default_complex_double  = load_cb_default<rocfft_complex<double>>;
static __device__ auto store_cb_default_complex_double = store_cb_default<rocfft_complex<double>>;

template <>
struct callback_type<rocfft_fp16>
{
    typedef rocfft_fp16 (*load)(rocfft_fp16* data, size_t offset, void* cbdata, void* sharedMem);
    typedef void (*store)(
        rocfft_fp16* data, size_t offset, rocfft_fp16 element, void* cbdata, void* sharedMem);
};

static __device__ auto load_cb_default_half  = load_cb_default<rocfft_fp16>;
static __device__ auto store_cb_default_half = store_cb_default<rocfft_fp16>;

template <>
struct callback_type<float>
{
    typedef float (*load)(float* data, size_t offset, void* cbdata, void* sharedMem);
    typedef void (*store)(float* data, size_t offset, float element, void* cbdata, void* sharedMem);
};

static __device__ auto load_cb_default_float  = load_cb_default<float>;
static __device__ auto store_cb_default_float = store_cb_default<float>;

template <>
struct callback_type<double>
{
    typedef double (*load)(double* data, size_t offset, void* cbdata, void* sharedMem);
    typedef void (*store)(
        double* data, size_t offset, double element, void* cbdata, void* sharedMem);
};

static __device__ auto load_cb_default_double  = load_cb_default<double>;
static __device__ auto store_cb_default_double = store_cb_default<double>;

// planar helpers
template <typename Tfloat>
__device__ rocfft_complex<Tfloat>
           load_planar(const Tfloat* dataRe, const Tfloat* dataIm, size_t offset)
{
    return rocfft_complex<Tfloat>{dataRe[offset], dataIm[offset]};
}

template <typename Tfloat>
__device__ void
    store_planar(Tfloat* dataRe, Tfloat* dataIm, size_t offset, rocfft_complex<Tfloat> element)
{
    dataRe[offset] = element.x;
    dataIm[offset] = element.y;
}

// intrinsic
template <typename T>
__device__ void intrinsic_load_to_dest(
    T& target, const T* data, unsigned int voffset, unsigned int soffset, bool rw)
{
#ifdef USE_GFX_BUFFER_INTRINSIC
    buffer_load<T, sizeof(T)>(target,
                              reinterpret_cast<void*>(const_cast<T*>(data)),
                              (uint32_t)(voffset * sizeof(T)),
                              (uint32_t)(soffset * sizeof(T)),
                              rw);
#else
    target = rw ? data[soffset + voffset] : target;
#endif
}

template <typename T>
__device__ T intrinsic_load(const T* data, unsigned int voffset, unsigned int soffset, bool rw)
{
#ifdef USE_GFX_BUFFER_INTRINSIC
    return buffer_load<T, sizeof(T)>().load(reinterpret_cast<void*>(const_cast<T*>(data)),
                                            (uint32_t)(voffset * sizeof(T)),
                                            (uint32_t)(soffset * sizeof(T)),
                                            rw);
#else
    return rw ? data[soffset + voffset] : T();
#endif
}

template <typename Tfloat>
__device__ rocfft_complex<Tfloat> intrinsic_load_planar(
    const Tfloat* dataRe, const Tfloat* dataIm, unsigned int voffset, unsigned int soffset, bool rw)
{
#ifdef USE_GFX_BUFFER_INTRINSIC
    return rocfft_complex<Tfloat>{buffer_load<Tfloat, sizeof(Tfloat)>().load(
                                      reinterpret_cast<void*>(const_cast<Tfloat*>(dataRe)),
                                      (uint32_t)(voffset * sizeof(Tfloat)),
                                      (uint32_t)(soffset * sizeof(Tfloat)),
                                      rw),
                                  buffer_load<Tfloat, sizeof(Tfloat)>().load(
                                      reinterpret_cast<void*>(const_cast<Tfloat*>(dataIm)),
                                      (uint32_t)(voffset * sizeof(Tfloat)),
                                      (uint32_t)(soffset * sizeof(Tfloat)),
                                      rw)};
#else
    return rw ? rocfft_complex<Tfloat>{dataRe[soffset + voffset], dataIm[soffset + voffset]}
              : rocfft_complex<Tfloat>();
#endif
}

template <typename T>
__device__ void
    store_intrinsic(T* data, unsigned int voffset, unsigned int soffset, T element, bool rw)
{
#ifdef USE_GFX_BUFFER_INTRINSIC
    buffer_store<T, sizeof(T)>(element,
                               reinterpret_cast<void*>(const_cast<T*>(data)),
                               (uint32_t)(voffset * sizeof(T)),
                               (uint32_t)(soffset * sizeof(T)),
                               rw);
#else
    if(rw)
        data[soffset + voffset] = element;
#endif
}

template <typename Tfloat>
__device__ void store_intrinsic_planar(Tfloat*                dataRe,
                                       Tfloat*                dataIm,
                                       unsigned int           voffset,
                                       unsigned int           soffset,
                                       rocfft_complex<Tfloat> element,
                                       bool                   rw)
{
#ifdef USE_GFX_BUFFER_INTRINSIC
    buffer_store<Tfloat, sizeof(Tfloat)>(element.x,
                                         reinterpret_cast<void*>(const_cast<Tfloat*>(dataRe)),
                                         (uint32_t)(voffset * sizeof(Tfloat)),
                                         (uint32_t)(soffset * sizeof(Tfloat)),
                                         rw);
    buffer_store<Tfloat, sizeof(Tfloat)>(element.y,
                                         reinterpret_cast<void*>(const_cast<Tfloat*>(dataIm)),
                                         (uint32_t)(voffset * sizeof(Tfloat)),
                                         (uint32_t)(soffset * sizeof(Tfloat)),
                                         rw);
#else
    if(rw)
    {
        dataRe[soffset + voffset] = element.x;
        dataIm[soffset + voffset] = element.y;
    }
#endif
}

enum struct CallbackType
{
    // don't run user callbacks
    NONE,
    // run user load/store callbacks
    USER_LOAD_STORE,
    // run user load/store callbacks, but user code loads
    // reals and the kernel wants complex
    USER_LOAD_STORE_R2C,
    // run user load/store callbacks, but user code stores
    // reals and the kernel wants complex
    USER_LOAD_STORE_C2R,
};

// helpers to cast void* to the correct function pointer type
template <typename T, CallbackType cbtype>
static __device__ typename callback_type<T>::load get_load_cb(void* ptr)
{
#ifdef ROCFFT_CALLBACKS_ENABLED
    if(cbtype != CallbackType::NONE)
        return reinterpret_cast<typename callback_type<T>::load>(ptr);
#endif
    return load_cb_default<T>;
}

template <typename T, CallbackType cbtype>
static __device__ typename callback_type<T>::store get_store_cb(void* ptr)
{
#ifdef ROCFFT_CALLBACKS_ENABLED
    if(cbtype != CallbackType::NONE)
        return reinterpret_cast<typename callback_type<T>::store>(ptr);
#endif
    return store_cb_default<T>;
}

#endif

/*******************************************************************************
 * Copyright (C) 2016-2022 Advanced Micro Devices, Inc. All rights reserved.
 ******************************************************************************/

#ifndef BUTTERFLY_CONSTANT_H
#define BUTTERFLY_CONSTANT_H

// butterfly radix-3 constants
#define C3QA static_cast<real_type_t<T>>(0.50000000000000000000000000000000)
#define C3QB static_cast<real_type_t<T>>(0.86602540378443864676372317075294)

// butterfly radix-5 constants
#define C5QA static_cast<real_type_t<T>>(0.30901699437494742410229341718282)
#define C5QB static_cast<real_type_t<T>>(0.95105651629515357211643933337938)
#define C5QC static_cast<real_type_t<T>>(0.50000000000000000000000000000000)
#define C5QD static_cast<real_type_t<T>>(0.58778525229247312916870595463907)
#define C5QE static_cast<real_type_t<T>>(0.80901699437494742410229341718282)

// butterfly radix-7 constants
#define C7Q1 static_cast<real_type_t<T>>(-1.16666666666666651863693004997913)
#define C7Q2 static_cast<real_type_t<T>>(0.79015646852540022404554065360571)
#define C7Q3 static_cast<real_type_t<T>>(0.05585426728964774240049351305970)
#define C7Q4 static_cast<real_type_t<T>>(0.73430220123575240531721419756650)
#define C7Q5 static_cast<real_type_t<T>>(0.44095855184409837868031445395900)
#define C7Q6 static_cast<real_type_t<T>>(0.34087293062393136944265847887436)
#define C7Q7 static_cast<real_type_t<T>>(-0.53396936033772524066165487965918)
#define C7Q8 static_cast<real_type_t<T>>(0.87484229096165666561546458979137)

// butterfly radix-8 constants
#define C8Q static_cast<real_type_t<T>>(0.70710678118654752440084436210485)

// butterfly radix-9 constants
#define C9QA static_cast<real_type_t<T>>(0.766044443118978)
#define C9QB static_cast<real_type_t<T>>(0.6427876096865393)
#define C9QC static_cast<real_type_t<T>>(0.1736481776669304)
#define C9QD static_cast<real_type_t<T>>(0.984807753012208)
#define C9QE static_cast<real_type_t<T>>(0.5000000000000000)
#define C9QF static_cast<real_type_t<T>>(0.8660254037844387)
#define C9QG static_cast<real_type_t<T>>(0.9396926207859083)
#define C9QH static_cast<real_type_t<T>>(0.3420201433256689)

//
// For radix-11 and radix-13 the butterfly constants correspond to
// the roots of unity for the radix; and are named according to:
//
//   "Q" + radix + "i" + i + "j" + j + "R"/"I"
//
// where i and j are the row/col indicies of the DFT matrix A
// corresponding to the radix and R/I is the real/imaginary part.
// More specifically:
//
//  A[i,j] = exp(-2 pi I i j / radix)
//
// and hence, for example
//
//  Q11i2j5R = Re( exp(-2 pi I 2 * 5 / 11) )
//

// butterfly radix-11 constants
#define Q11i1j1R static_cast<real_type_t<T>>((0.8412535328311811688618))
#define Q11i1j1I static_cast<real_type_t<T>>((-0.5406408174555975821076))
#define Q11i1j2R static_cast<real_type_t<T>>((0.4154150130018864255293))
#define Q11i1j2I static_cast<real_type_t<T>>((-0.9096319953545183714117))
#define Q11i1j3R static_cast<real_type_t<T>>((-0.1423148382732851404438))
#define Q11i1j3I static_cast<real_type_t<T>>((-0.9898214418809327323761))
#define Q11i1j4R static_cast<real_type_t<T>>((-0.6548607339452850640569))
#define Q11i1j4I static_cast<real_type_t<T>>((-0.7557495743542582837740))
#define Q11i1j5R static_cast<real_type_t<T>>((-0.9594929736144973898904))
#define Q11i1j5I static_cast<real_type_t<T>>((-0.2817325568414296977114))
#define Q11i2j1R static_cast<real_type_t<T>>((0.4154150130018864255293))
#define Q11i2j1I static_cast<real_type_t<T>>((-0.9096319953545183714117))
#define Q11i2j2R static_cast<real_type_t<T>>((-0.6548607339452850640569))
#define Q11i2j2I static_cast<real_type_t<T>>((-0.7557495743542582837740))
#define Q11i2j3R static_cast<real_type_t<T>>((-0.9594929736144973898904))
#define Q11i2j3I static_cast<real_type_t<T>>((0.2817325568414296977114))
#define Q11i2j4R static_cast<real_type_t<T>>((-0.1423148382732851404438))
#define Q11i2j4I static_cast<real_type_t<T>>((0.9898214418809327323761))
#define Q11i2j5R static_cast<real_type_t<T>>((0.8412535328311811688618))
#define Q11i2j5I static_cast<real_type_t<T>>((0.5406408174555975821076))
#define Q11i3j1R static_cast<real_type_t<T>>((-0.1423148382732851404438))
#define Q11i3j1I static_cast<real_type_t<T>>((-0.9898214418809327323761))
#define Q11i3j2R static_cast<real_type_t<T>>((-0.9594929736144973898904))
#define Q11i3j2I static_cast<real_type_t<T>>((0.2817325568414296977114))
#define Q11i3j3R static_cast<real_type_t<T>>((0.4154150130018864255293))
#define Q11i3j3I static_cast<real_type_t<T>>((0.9096319953545183714117))
#define Q11i3j4R static_cast<real_type_t<T>>((0.8412535328311811688618))
#define Q11i3j4I static_cast<real_type_t<T>>((-0.5406408174555975821076))
#define Q11i3j5R static_cast<real_type_t<T>>((-0.6548607339452850640569))
#define Q11i3j5I static_cast<real_type_t<T>>((-0.7557495743542582837740))
#define Q11i4j1R static_cast<real_type_t<T>>((-0.6548607339452850640569))
#define Q11i4j1I static_cast<real_type_t<T>>((-0.7557495743542582837740))
#define Q11i4j2R static_cast<real_type_t<T>>((-0.1423148382732851404438))
#define Q11i4j2I static_cast<real_type_t<T>>((0.9898214418809327323761))
#define Q11i4j3R static_cast<real_type_t<T>>((0.8412535328311811688618))
#define Q11i4j3I static_cast<real_type_t<T>>((-0.5406408174555975821076))
#define Q11i4j4R static_cast<real_type_t<T>>((-0.9594929736144973898904))
#define Q11i4j4I static_cast<real_type_t<T>>((-0.2817325568414296977114))
#define Q11i4j5R static_cast<real_type_t<T>>((0.4154150130018864255293))
#define Q11i4j5I static_cast<real_type_t<T>>((0.9096319953545183714117))
#define Q11i5j1R static_cast<real_type_t<T>>((-0.9594929736144973898904))
#define Q11i5j1I static_cast<real_type_t<T>>((-0.2817325568414296977114))
#define Q11i5j2R static_cast<real_type_t<T>>((0.8412535328311811688618))
#define Q11i5j2I static_cast<real_type_t<T>>((0.5406408174555975821076))
#define Q11i5j3R static_cast<real_type_t<T>>((-0.6548607339452850640569))
#define Q11i5j3I static_cast<real_type_t<T>>((-0.7557495743542582837740))
#define Q11i5j4R static_cast<real_type_t<T>>((0.4154150130018864255293))
#define Q11i5j4I static_cast<real_type_t<T>>((0.9096319953545183714117))
#define Q11i5j5R static_cast<real_type_t<T>>((-0.1423148382732851404438))
#define Q11i5j5I static_cast<real_type_t<T>>((-0.9898214418809327323761))

// butterfly radix-13 constants
#define Q13i1j1R static_cast<real_type_t<T>>((0.8854560256532098959004))
#define Q13i1j1I static_cast<real_type_t<T>>((-0.4647231720437685456560))
#define Q13i1j2R static_cast<real_type_t<T>>((0.5680647467311558025118))
#define Q13i1j2I static_cast<real_type_t<T>>((-0.8229838658936563945796))
#define Q13i1j3R static_cast<real_type_t<T>>((0.1205366802553230533491))
#define Q13i1j3I static_cast<real_type_t<T>>((-0.9927088740980539928007))
#define Q13i1j4R static_cast<real_type_t<T>>((-0.3546048870425356259696))
#define Q13i1j4I static_cast<real_type_t<T>>((-0.9350162426854148234398))
#define Q13i1j5R static_cast<real_type_t<T>>((-0.7485107481711010986346))
#define Q13i1j5I static_cast<real_type_t<T>>((-0.6631226582407952023768))
#define Q13i1j6R static_cast<real_type_t<T>>((-0.9709418174260520271570))
#define Q13i1j6I static_cast<real_type_t<T>>((-0.2393156642875577671488))
#define Q13i2j1R static_cast<real_type_t<T>>((0.5680647467311558025118))
#define Q13i2j1I static_cast<real_type_t<T>>((-0.8229838658936563945796))
#define Q13i2j2R static_cast<real_type_t<T>>((-0.3546048870425356259696))
#define Q13i2j2I static_cast<real_type_t<T>>((-0.9350162426854148234398))
#define Q13i2j3R static_cast<real_type_t<T>>((-0.9709418174260520271570))
#define Q13i2j3I static_cast<real_type_t<T>>((-0.2393156642875577671488))
#define Q13i2j4R static_cast<real_type_t<T>>((-0.7485107481711010986346))
#define Q13i2j4I static_cast<real_type_t<T>>((0.6631226582407952023768))
#define Q13i2j5R static_cast<real_type_t<T>>((0.1205366802553230533491))
#define Q13i2j5I static_cast<real_type_t<T>>((0.9927088740980539928007))
#define Q13i2j6R static_cast<real_type_t<T>>((0.8854560256532098959004))
#define Q13i2j6I static_cast<real_type_t<T>>((0.4647231720437685456560))
#define Q13i3j1R static_cast<real_type_t<T>>((0.1205366802553230533491))
#define Q13i3j1I static_cast<real_type_t<T>>((-0.9927088740980539928007))
#define Q13i3j2R static_cast<real_type_t<T>>((-0.9709418174260520271570))
#define Q13i3j2I static_cast<real_type_t<T>>((-0.2393156642875577671488))
#define Q13i3j3R static_cast<real_type_t<T>>((-0.3546048870425356259696))
#define Q13i3j3I static_cast<real_type_t<T>>((0.9350162426854148234398))
#define Q13i3j4R static_cast<real_type_t<T>>((0.8854560256532098959004))
#define Q13i3j4I static_cast<real_type_t<T>>((0.4647231720437685456560))
#define Q13i3j5R static_cast<real_type_t<T>>((0.5680647467311558025118))
#define Q13i3j5I static_cast<real_type_t<T>>((-0.8229838658936563945796))
#define Q13i3j6R static_cast<real_type_t<T>>((-0.7485107481711010986346))
#define Q13i3j6I static_cast<real_type_t<T>>((-0.6631226582407952023768))
#define Q13i4j1R static_cast<real_type_t<T>>((-0.3546048870425356259696))
#define Q13i4j1I static_cast<real_type_t<T>>((-0.9350162426854148234398))
#define Q13i4j2R static_cast<real_type_t<T>>((-0.7485107481711010986346))
#define Q13i4j2I static_cast<real_type_t<T>>((0.6631226582407952023768))
#define Q13i4j3R static_cast<real_type_t<T>>((0.8854560256532098959004))
#define Q13i4j3I static_cast<real_type_t<T>>((0.4647231720437685456560))
#define Q13i4j4R static_cast<real_type_t<T>>((0.1205366802553230533491))
#define Q13i4j4I static_cast<real_type_t<T>>((-0.9927088740980539928007))
#define Q13i4j5R static_cast<real_type_t<T>>((-0.9709418174260520271570))
#define Q13i4j5I static_cast<real_type_t<T>>((0.2393156642875577671488))
#define Q13i4j6R static_cast<real_type_t<T>>((0.5680647467311558025118))
#define Q13i4j6I static_cast<real_type_t<T>>((0.8229838658936563945796))
#define Q13i5j1R static_cast<real_type_t<T>>((-0.7485107481711010986346))
#define Q13i5j1I static_cast<real_type_t<T>>((-0.6631226582407952023768))
#define Q13i5j2R static_cast<real_type_t<T>>((0.1205366802553230533491))
#define Q13i5j2I static_cast<real_type_t<T>>((0.9927088740980539928007))
#define Q13i5j3R static_cast<real_type_t<T>>((0.5680647467311558025118))
#define Q13i5j3I static_cast<real_type_t<T>>((-0.8229838658936563945796))
#define Q13i5j4R static_cast<real_type_t<T>>((-0.9709418174260520271570))
#define Q13i5j4I static_cast<real_type_t<T>>((0.2393156642875577671488))
#define Q13i5j5R static_cast<real_type_t<T>>((0.8854560256532098959004))
#define Q13i5j5I static_cast<real_type_t<T>>((0.4647231720437685456560))
#define Q13i5j6R static_cast<real_type_t<T>>((-0.3546048870425356259696))
#define Q13i5j6I static_cast<real_type_t<T>>((-0.9350162426854148234398))
#define Q13i6j1R static_cast<real_type_t<T>>((-0.9709418174260520271570))
#define Q13i6j1I static_cast<real_type_t<T>>((-0.2393156642875577671488))
#define Q13i6j2R static_cast<real_type_t<T>>((0.8854560256532098959004))
#define Q13i6j2I static_cast<real_type_t<T>>((0.4647231720437685456560))
#define Q13i6j3R static_cast<real_type_t<T>>((-0.7485107481711010986346))
#define Q13i6j3I static_cast<real_type_t<T>>((-0.6631226582407952023768))
#define Q13i6j4R static_cast<real_type_t<T>>((0.5680647467311558025118))
#define Q13i6j4I static_cast<real_type_t<T>>((0.8229838658936563945796))
#define Q13i6j5R static_cast<real_type_t<T>>((-0.3546048870425356259696))
#define Q13i6j5I static_cast<real_type_t<T>>((-0.9350162426854148234398))
#define Q13i6j6R static_cast<real_type_t<T>>((0.1205366802553230533491))
#define Q13i6j6I static_cast<real_type_t<T>>((0.9927088740980539928007))

#define Q17i1j1R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i1j1I static_cast<real_type_t<T>>((-0.3612416661871529487447))
#define Q17i1j2R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i1j2I static_cast<real_type_t<T>>((-0.6736956436465572117127))
#define Q17i1j3R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i1j3I static_cast<real_type_t<T>>((-0.8951632913550623220670))
#define Q17i1j4R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i1j4I static_cast<real_type_t<T>>((-0.9957341762950345218712))
#define Q17i1j5R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i1j5I static_cast<real_type_t<T>>((-0.9618256431728190704088))
#define Q17i1j6R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i1j6I static_cast<real_type_t<T>>((-0.7980172272802395033328))
#define Q17i1j7R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i1j7I static_cast<real_type_t<T>>((-0.5264321628773558002446))
#define Q17i1j8R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i1j8I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i2j1R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i2j1I static_cast<real_type_t<T>>((-0.6736956436465572117127))
#define Q17i2j2R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i2j2I static_cast<real_type_t<T>>((-0.9957341762950345218712))
#define Q17i2j3R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i2j3I static_cast<real_type_t<T>>((-0.7980172272802395033328))
#define Q17i2j4R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i2j4I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i2j5R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i2j5I static_cast<real_type_t<T>>((0.5264321628773558002446))
#define Q17i2j6R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i2j6I static_cast<real_type_t<T>>((0.9618256431728190704088))
#define Q17i2j7R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i2j7I static_cast<real_type_t<T>>((0.8951632913550623220670))
#define Q17i2j8R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i2j8I static_cast<real_type_t<T>>((0.3612416661871529487447))
#define Q17i3j1R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i3j1I static_cast<real_type_t<T>>((-0.8951632913550623220670))
#define Q17i3j2R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i3j2I static_cast<real_type_t<T>>((-0.7980172272802395033328))
#define Q17i3j3R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i3j3I static_cast<real_type_t<T>>((0.1837495178165703315744))
#define Q17i3j4R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i3j4I static_cast<real_type_t<T>>((0.9618256431728190704088))
#define Q17i3j5R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i3j5I static_cast<real_type_t<T>>((0.6736956436465572117127))
#define Q17i3j6R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i3j6I static_cast<real_type_t<T>>((-0.3612416661871529487447))
#define Q17i3j7R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i3j7I static_cast<real_type_t<T>>((-0.9957341762950345218712))
#define Q17i3j8R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i3j8I static_cast<real_type_t<T>>((-0.5264321628773558002446))
#define Q17i4j1R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i4j1I static_cast<real_type_t<T>>((-0.9957341762950345218712))
#define Q17i4j2R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i4j2I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i4j3R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i4j3I static_cast<real_type_t<T>>((0.9618256431728190704088))
#define Q17i4j4R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i4j4I static_cast<real_type_t<T>>((0.3612416661871529487447))
#define Q17i4j5R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i4j5I static_cast<real_type_t<T>>((-0.8951632913550623220670))
#define Q17i4j6R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i4j6I static_cast<real_type_t<T>>((-0.5264321628773558002446))
#define Q17i4j7R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i4j7I static_cast<real_type_t<T>>((0.7980172272802395033328))
#define Q17i4j8R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i4j8I static_cast<real_type_t<T>>((0.6736956436465572117127))
#define Q17i5j1R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i5j1I static_cast<real_type_t<T>>((-0.9618256431728190704088))
#define Q17i5j2R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i5j2I static_cast<real_type_t<T>>((0.5264321628773558002446))
#define Q17i5j3R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i5j3I static_cast<real_type_t<T>>((0.6736956436465572117127))
#define Q17i5j4R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i5j4I static_cast<real_type_t<T>>((-0.8951632913550623220670))
#define Q17i5j5R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i5j5I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i5j6R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i5j6I static_cast<real_type_t<T>>((0.9957341762950345218712))
#define Q17i5j7R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i5j7I static_cast<real_type_t<T>>((-0.3612416661871529487447))
#define Q17i5j8R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i5j8I static_cast<real_type_t<T>>((-0.7980172272802395033328))
#define Q17i6j1R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i6j1I static_cast<real_type_t<T>>((-0.7980172272802395033328))
#define Q17i6j2R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i6j2I static_cast<real_type_t<T>>((0.9618256431728190704088))
#define Q17i6j3R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i6j3I static_cast<real_type_t<T>>((-0.3612416661871529487447))
#define Q17i6j4R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i6j4I static_cast<real_type_t<T>>((-0.5264321628773558002446))
#define Q17i6j5R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i6j5I static_cast<real_type_t<T>>((0.9957341762950345218712))
#define Q17i6j6R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i6j6I static_cast<real_type_t<T>>((-0.6736956436465572117127))
#define Q17i6j7R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i6j7I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i6j8R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i6j8I static_cast<real_type_t<T>>((0.8951632913550623220670))
#define Q17i7j1R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i7j1I static_cast<real_type_t<T>>((-0.5264321628773558002446))
#define Q17i7j2R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i7j2I static_cast<real_type_t<T>>((0.8951632913550623220670))
#define Q17i7j3R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i7j3I static_cast<real_type_t<T>>((-0.9957341762950345218712))
#define Q17i7j4R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i7j4I static_cast<real_type_t<T>>((0.7980172272802395033328))
#define Q17i7j5R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i7j5I static_cast<real_type_t<T>>((-0.3612416661871529487447))
#define Q17i7j6R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i7j6I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i7j7R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i7j7I static_cast<real_type_t<T>>((0.6736956436465572117127))
#define Q17i7j8R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i7j8I static_cast<real_type_t<T>>((-0.9618256431728190704088))
#define Q17i8j1R static_cast<real_type_t<T>>((-0.9829730996839017782819))
#define Q17i8j1I static_cast<real_type_t<T>>((-0.1837495178165703315744))
#define Q17i8j2R static_cast<real_type_t<T>>((0.9324722294043558045731))
#define Q17i8j2I static_cast<real_type_t<T>>((0.3612416661871529487447))
#define Q17i8j3R static_cast<real_type_t<T>>((-0.8502171357296141521341))
#define Q17i8j3I static_cast<real_type_t<T>>((-0.5264321628773558002446))
#define Q17i8j4R static_cast<real_type_t<T>>((0.7390089172206591159245))
#define Q17i8j4I static_cast<real_type_t<T>>((0.6736956436465572117127))
#define Q17i8j5R static_cast<real_type_t<T>>((-0.6026346363792563891786))
#define Q17i8j5I static_cast<real_type_t<T>>((-0.7980172272802395033328))
#define Q17i8j6R static_cast<real_type_t<T>>((0.4457383557765382673965))
#define Q17i8j6I static_cast<real_type_t<T>>((0.8951632913550623220670))
#define Q17i8j7R static_cast<real_type_t<T>>((-0.2736629900720828635391))
#define Q17i8j7I static_cast<real_type_t<T>>((-0.9618256431728190704088))
#define Q17i8j8R static_cast<real_type_t<T>>((0.09226835946330199523965))
#define Q17i8j8I static_cast<real_type_t<T>>((0.9957341762950345218712))

// butterfly radix-11 constants
#define b11_0 static_cast<real_type_t<T>>(0.9898214418809327)
#define b11_1 static_cast<real_type_t<T>>(0.9594929736144973)
#define b11_2 static_cast<real_type_t<T>>(0.9189859472289947)
#define b11_3 static_cast<real_type_t<T>>(0.8767688310025893)
#define b11_4 static_cast<real_type_t<T>>(0.8308300260037728)
#define b11_5 static_cast<real_type_t<T>>(0.7784344533346518)
#define b11_6 static_cast<real_type_t<T>>(0.7153703234534297)
#define b11_7 static_cast<real_type_t<T>>(0.6343562706824244)
#define b11_8 static_cast<real_type_t<T>>(0.3425847256816375)
#define b11_9 static_cast<real_type_t<T>>(0.5211085581132027)

// butterfly radix-13 constants
#define b13_0 static_cast<real_type_t<T>>(0.9682872443619840)
#define b13_1 static_cast<real_type_t<T>>(0.9578059925946651)
#define b13_2 static_cast<real_type_t<T>>(0.8755023024091479)
#define b13_3 static_cast<real_type_t<T>>(0.8660254037844386)
#define b13_4 static_cast<real_type_t<T>>(0.8595425350987748)
#define b13_5 static_cast<real_type_t<T>>(0.8534800018598239)
#define b13_6 static_cast<real_type_t<T>>(0.7693388175729806)
#define b13_7 static_cast<real_type_t<T>>(0.6865583707817543)
#define b13_8 static_cast<real_type_t<T>>(0.6122646503767565)
#define b13_9 static_cast<real_type_t<T>>(0.6004772719326652)
#define b13_10 static_cast<real_type_t<T>>(0.5817047785105157)
#define b13_11 static_cast<real_type_t<T>>(0.5751407294740031)
#define b13_12 static_cast<real_type_t<T>>(0.5220263851612750)
#define b13_13 static_cast<real_type_t<T>>(0.5200285718888646)
#define b13_14 static_cast<real_type_t<T>>(0.5165207806234897)
#define b13_15 static_cast<real_type_t<T>>(0.5149187780863157)
#define b13_16 static_cast<real_type_t<T>>(0.5035370328637666)
#define b13_17 static_cast<real_type_t<T>>(0.5000000000000000)
#define b13_18 static_cast<real_type_t<T>>(0.3027756377319946)
#define b13_19 static_cast<real_type_t<T>>(0.3014792600477098)
#define b13_20 static_cast<real_type_t<T>>(0.3004626062886657)
#define b13_21 static_cast<real_type_t<T>>(0.2517685164318833)
#define b13_22 static_cast<real_type_t<T>>(0.2261094450357824)
#define b13_23 static_cast<real_type_t<T>>(0.0833333333333333)
#define b13_24 static_cast<real_type_t<T>>(0.0386329546443481)

// butterfly radix-16 constants
#define C16A static_cast<real_type_t<T>>(0.923879532511286738)
#define C16B static_cast<real_type_t<T>>(0.382683432365089837)

#endif //  BUTTERFLY_CONSTANT_H

/*******************************************************************************
 * Copyright (C) 2016-2023 Advanced Micro Devices, Inc. All rights reserved.
 ******************************************************************************/

template <typename T>
__device__ void FwdRad4B1(T* R0, T* R2, T* R1, T* R3)
{

    T res;

    (*R1) = (*R0) - (*R1);
    (*R0) = 2.0 * (*R0) - (*R1);
    (*R3) = (*R2) - (*R3);
    (*R2) = 2.0 * (*R2) - (*R3);

    (*R2) = (*R0) - (*R2);
    (*R0) = 2.0 * (*R0) - (*R2);

    (*R3) = (*R1) + T(-(*R3).y, (*R3).x);
    (*R1) = 2.0 * (*R1) - (*R3);

    res   = (*R1);
    (*R1) = (*R2);
    (*R2) = res;
}

template <typename T>
__device__ void InvRad4B1(T* R0, T* R2, T* R1, T* R3)
{

    T res;

    (*R1) = (*R0) - (*R1);
    (*R0) = 2.0 * (*R0) - (*R1);
    (*R3) = (*R2) - (*R3);
    (*R2) = 2.0 * (*R2) - (*R3);

    (*R2) = (*R0) - (*R2);
    (*R0) = 2.0 * (*R0) - (*R2);
    (*R3) = (*R1) + T((*R3).y, -(*R3).x);
    (*R1) = 2.0 * (*R1) - (*R3);

    res   = (*R1);
    (*R1) = (*R2);
    (*R2) = res;
}

/*******************************************************************************
 * Copyright (C) 2016-2023 Advanced Micro Devices, Inc. All rights reserved.
 ******************************************************************************/

template <typename T>
__device__ void FwdRad8B1(T* R0, T* R4, T* R2, T* R6, T* R1, T* R5, T* R3, T* R7)
{

    T res;

    (*R1) = (*R0) - (*R1);
    (*R0) = 2.0 * (*R0) - (*R1);
    (*R3) = (*R2) - (*R3);
    (*R2) = 2.0 * (*R2) - (*R3);
    (*R5) = (*R4) - (*R5);
    (*R4) = 2.0 * (*R4) - (*R5);
    (*R7) = (*R6) - (*R7);
    (*R6) = 2.0 * (*R6) - (*R7);

    (*R2) = (*R0) - (*R2);
    (*R0) = 2.0 * (*R0) - (*R2);
    (*R3) = (*R1) + T(-(*R3).y, (*R3).x);
    (*R1) = 2.0 * (*R1) - (*R3);
    (*R6) = (*R4) - (*R6);
    (*R4) = 2.0 * (*R4) - (*R6);
    (*R7) = (*R5) + T(-(*R7).y, (*R7).x);

    (*R5) = 2.0 * (*R5) - (*R7);

    (*R4) = (*R0) - (*R4);
    (*R0) = 2.0 * (*R0) - (*R4);
    (*R5) = ((*R1) - C8Q * (*R5)) - C8Q * T((*R5).y, -(*R5).x);
    (*R1) = 2.0 * (*R1) - (*R5);
    (*R6) = (*R2) + T(-(*R6).y, (*R6).x);
    (*R2) = 2.0 * (*R2) - (*R6);
    (*R7) = ((*R3) + C8Q * (*R7)) - C8Q * T((*R7).y, -(*R7).x);
    (*R3) = 2.0 * (*R3) - (*R7);

    res   = (*R1);
    (*R1) = (*R4);
    (*R4) = res;
    res   = (*R3);
    (*R3) = (*R6);
    (*R6) = res;
}

template <typename T>
__device__ void InvRad8B1(T* R0, T* R4, T* R2, T* R6, T* R1, T* R5, T* R3, T* R7)
{

    T res;

    (*R1) = (*R0) - (*R1);
    (*R0) = 2.0 * (*R0) - (*R1);
    (*R3) = (*R2) - (*R3);
    (*R2) = 2.0 * (*R2) - (*R3);
    (*R5) = (*R4) - (*R5);
    (*R4) = 2.0 * (*R4) - (*R5);
    (*R7) = (*R6) - (*R7);
    (*R6) = 2.0 * (*R6) - (*R7);

    (*R2) = (*R0) - (*R2);
    (*R0) = 2.0 * (*R0) - (*R2);
    (*R3) = (*R1) + T((*R3).y, -(*R3).x);
    (*R1) = 2.0 * (*R1) - (*R3);
    (*R6) = (*R4) - (*R6);
    (*R4) = 2.0 * (*R4) - (*R6);
    (*R7) = (*R5) + T((*R7).y, -(*R7).x);
    (*R5) = 2.0 * (*R5) - (*R7);

    (*R4) = (*R0) - (*R4);
    (*R0) = 2.0 * (*R0) - (*R4);
    (*R5) = ((*R1) - C8Q * (*R5)) + C8Q * T((*R5).y, -(*R5).x);
    (*R1) = 2.0 * (*R1) - (*R5);
    (*R6) = (*R2) + T((*R6).y, -(*R6).x);
    (*R2) = 2.0 * (*R2) - (*R6);
    (*R7) = ((*R3) + C8Q * (*R7)) + C8Q * T((*R7).y, -(*R7).x);
    (*R3) = 2.0 * (*R3) - (*R7);

    res   = (*R1);
    (*R1) = (*R4);
    (*R4) = res;
    res   = (*R3);
    (*R3) = (*R6);
    (*R6) = res;
}

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

#ifndef REAL_TO_COMPLEX_DEVICE_H
#define REAL_TO_COMPLEX_DEVICE_H

// The even-length real to complex post process device kernel
template <typename Tcomplex, bool Ndiv4, CallbackType cbtype, bool SCALE = false>
__device__ inline void post_process_interleaved(const size_t    idx_p,
                                                const size_t    idx_q,
                                                const size_t    half_N,
                                                const size_t    quarter_N,
                                                const Tcomplex* input,
                                                Tcomplex*       output,
                                                size_t          output_base,
                                                const Tcomplex* twiddles,
                                                void* __restrict__ load_cb_fn,
                                                void* __restrict__ load_cb_data,
                                                uint32_t load_cb_lds_bytes,
                                                void* __restrict__ store_cb_fn,
                                                void* __restrict__ store_cb_data,
                                                const real_type_t<Tcomplex> scale_factor = 0.0)
{
    // post process can't be the first kernel, so don't bother
    // going through the load cb to read global memory
    auto store_cb = get_store_cb<Tcomplex, cbtype>(store_cb_fn);

    Tcomplex outval;

    if(idx_p == 0)
    {
        outval.x = input[0].x - input[0].y;
        outval.y = 0;
        store_cb(output,
                 output_base + half_N,
                 SCALE ? (outval * scale_factor) : outval,
                 store_cb_data,
                 nullptr);

        outval.x = input[0].x + input[0].y;
        outval.y = 0;
        store_cb(output,
                 output_base + 0,
                 SCALE ? (outval * scale_factor) : outval,
                 store_cb_data,
                 nullptr);

        if(Ndiv4)
        {
            outval.x = input[quarter_N].x;
            outval.y = -input[quarter_N].y;

            store_cb(output,
                     output_base + quarter_N,
                     SCALE ? (outval * scale_factor) : outval,
                     store_cb_data,
                     nullptr);
        }
    }
    else
    {
        const Tcomplex p = input[idx_p];
        const Tcomplex q = input[idx_q];
        const Tcomplex u = 0.5 * (p + q);
        const Tcomplex v = 0.5 * (p - q);

        const Tcomplex twd_p = twiddles[idx_p];
        // NB: twd_q = -conj(twd_p) = (-twd_p.x, twd_p.y);

        outval.x = u.x + v.x * twd_p.y + u.y * twd_p.x;
        outval.y = v.y + u.y * twd_p.y - v.x * twd_p.x;
        store_cb(output,
                 output_base + idx_p,
                 SCALE ? (outval * scale_factor) : outval,
                 store_cb_data,
                 nullptr);

        outval.x = u.x - v.x * twd_p.y - u.y * twd_p.x;
        outval.y = -v.y + u.y * twd_p.y - v.x * twd_p.x;
        store_cb(output,
                 output_base + idx_q,
                 SCALE ? (outval * scale_factor) : outval,
                 store_cb_data,
                 nullptr);
    }
}

// TODO: rework pre/post processing
template <typename T, bool Ndiv4, CallbackType cbtype>
__device__ inline void post_process_interleaved_inplace(const size_t idx_p,
                                                        const size_t idx_q,
                                                        const size_t half_N,
                                                        const size_t quarter_N,
                                                        T*           inout,
                                                        size_t       offset_base,
                                                        const T*     twiddles,
                                                        void* __restrict__ load_cb_fn,
                                                        void* __restrict__ load_cb_data,
                                                        uint32_t load_cb_lds_bytes,
                                                        void* __restrict__ store_cb_fn,
                                                        void* __restrict__ store_cb_data)
{
    // post process can't be the first kernel, so don't bother
    // going through the load cb to read global memory
    auto store_cb = get_store_cb<T, cbtype>(store_cb_fn);

    T p, q, outval;
    if(idx_p < quarter_N)
    {
        p = inout[offset_base + idx_p];
        q = inout[offset_base + idx_q];
    }

    __syncthreads();

    if(idx_p == 0)
    {
        outval.x = p.x + p.y;
        outval.y = 0;
        store_cb(inout, offset_base + idx_p, outval, store_cb_data, nullptr);

        outval.x = p.x - p.y;
        outval.y = 0;
        store_cb(inout, offset_base + idx_q, outval, store_cb_data, nullptr);

        if(Ndiv4)
        {
            outval   = inout[offset_base + quarter_N];
            outval.y = -outval.y;
            store_cb(inout, offset_base + quarter_N, outval, store_cb_data, nullptr);
        }
    }
    else if(idx_p < quarter_N)
    {
        const T u = 0.5 * (p + q);
        const T v = 0.5 * (p - q);

        const T twd_p = twiddles[idx_p];
        // NB: twd_q = -conj(twd_p) = (-twd_p.x, twd_p.y);

        outval.x = u.x + v.x * twd_p.y + u.y * twd_p.x;
        outval.y = v.y + u.y * twd_p.y - v.x * twd_p.x;
        store_cb(inout, offset_base + idx_p, outval, store_cb_data, nullptr);

        outval.x = u.x - v.x * twd_p.y - u.y * twd_p.x;
        outval.y = -v.y + u.y * twd_p.y - v.x * twd_p.x;
        store_cb(inout, offset_base + idx_q, outval, store_cb_data, nullptr);
    }
}

// The below 2 functions are only for inplace in lds. So no callback.
template <typename Tcomplex, bool Ndiv4>
__device__ inline void real_post_process_kernel_inplace(const size_t    idx_p,
                                                        const size_t    idx_q,
                                                        const size_t    quarter_N,
                                                        Tcomplex*       inout,
                                                        size_t          offset_base,
                                                        const Tcomplex* twiddles)
{
    if(idx_p < quarter_N)
    {
        Tcomplex p = inout[offset_base + idx_p];
        Tcomplex q = inout[offset_base + idx_q];

        if(idx_p == 0)
        {
            inout[offset_base + idx_p].x = p.x + p.y;
            inout[offset_base + idx_p].y = 0;

            inout[offset_base + idx_q].x = p.x - p.y;
            inout[offset_base + idx_q].y = 0;

            if(Ndiv4)
            {
                inout[offset_base + quarter_N].y = -inout[offset_base + quarter_N].y;
            }
        }
        else
        {
            const Tcomplex u = 0.5 * (p + q);
            const Tcomplex v = 0.5 * (p - q);

            const Tcomplex twd_p = twiddles[idx_p];
            // NB: twd_q = -conj(twd_p) = (-twd_p.x, twd_p.y);

            inout[offset_base + idx_p].x = u.x + v.x * twd_p.y + u.y * twd_p.x;
            inout[offset_base + idx_p].y = v.y + u.y * twd_p.y - v.x * twd_p.x;

            inout[offset_base + idx_q].x = u.x - v.x * twd_p.y - u.y * twd_p.x;
            inout[offset_base + idx_q].y = -v.y + u.y * twd_p.y - v.x * twd_p.x;
        }
    }
}

template <typename Tcomplex, bool Ndiv4>
__device__ inline void real_pre_process_kernel_inplace(const size_t    idx_p,
                                                       const size_t    idx_q,
                                                       const size_t    quarter_N,
                                                       Tcomplex*       inout,
                                                       size_t          offset_base,
                                                       const Tcomplex* twiddles)
{
    if(idx_p < quarter_N)
    {
        Tcomplex p = inout[offset_base + idx_p];
        Tcomplex q = inout[offset_base + idx_q];

        if(idx_p == 0)
        {
            // NB: multi-dimensional transforms may have non-zero
            // imaginary part at index 0 or at the Nyquist frequency.
            inout[offset_base + idx_p].x = p.x + q.x;
            inout[offset_base + idx_p].y = p.x - q.x;

            if(Ndiv4)
            {
                auto quarter_elem                = inout[offset_base + quarter_N];
                inout[offset_base + quarter_N].x = 2.0 * quarter_elem.x;
                inout[offset_base + quarter_N].y = -2.0 * quarter_elem.y;
            }
        }
        else
        {
            const Tcomplex u = p + q;
            const Tcomplex v = p - q;

            const Tcomplex twd_p = twiddles[idx_p];
            // NB: twd_q = -conj(twd_p);

            inout[offset_base + idx_p].x = u.x + v.x * twd_p.y - u.y * twd_p.x;
            inout[offset_base + idx_p].y = v.y + u.y * twd_p.y + v.x * twd_p.x;

            inout[offset_base + idx_q].x = u.x - v.x * twd_p.y + u.y * twd_p.x;
            inout[offset_base + idx_q].y = -v.y + u.y * twd_p.y + v.x * twd_p.x;
        }
    }
}

#endif
template<typename scalar_type,StrideBin sb,bool lds_reg_sync = true>__device__ void lds_to_reg_input_length128_device(scalar_type* R,scalar_type* __restrict__ lds_complex,unsigned int stride_lds,unsigned int offset_lds,unsigned int thread,bool write) {
const unsigned int lstride = (sb == SB_UNIT) ? (1) : (stride_lds);
unsigned int l_offset;
if(lds_reg_sync) {
__syncthreads();

}

l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 16) * lstride;
R[1] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[2] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 48) * lstride;
R[3] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[4] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 80) * lstride;
R[5] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[6] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 112) * lstride;
R[7] = lds_complex[l_offset];
}
template<typename scalar_type,StrideBin sb,bool lds_reg_sync = true>__device__ void lds_from_reg_output_length128_device(scalar_type* R,scalar_type* __restrict__ lds_complex,unsigned int stride_lds,unsigned int offset_lds,unsigned int thread,bool write) {
const unsigned int lstride = (sb == SB_UNIT) ? (1) : (stride_lds);
unsigned int l_offset;
if(lds_reg_sync) {
__syncthreads();

}

l_offset = offset_lds + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 0) * lstride;
lds_complex[l_offset] = R[0];
l_offset = offset_lds + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 32) * lstride;
lds_complex[l_offset] = R[1];
l_offset = offset_lds + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 64) * lstride;
lds_complex[l_offset] = R[2];
l_offset = offset_lds + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 96) * lstride;
lds_complex[l_offset] = R[3];
l_offset = offset_lds + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 0) * lstride;
lds_complex[l_offset] = R[4];
l_offset = offset_lds + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 32) * lstride;
lds_complex[l_offset] = R[5];
l_offset = offset_lds + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 64) * lstride;
lds_complex[l_offset] = R[6];
l_offset = offset_lds + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 96) * lstride;
lds_complex[l_offset] = R[7];
}
template<typename scalar_type,const bool lds_is_real,SBRC_TYPE sbrc_type,SBRC_TRANSPOSE_TYPE transpose_type,StrideBin sb,const bool lds_linear,const bool direct_load_to_reg>__device__ void inverse_length128_SBRC_device(scalar_type* R,real_type_t<scalar_type>* __restrict__ lds_real,scalar_type* __restrict__ lds_complex,const scalar_type* __restrict__ twiddles,unsigned int stride_lds,unsigned int offset_lds,unsigned int thread,bool write) {
scalar_type W;
scalar_type t;
const unsigned int lstride = (sb == SB_UNIT) ? (1) : (stride_lds);
unsigned int l_offset;



// pass 0, width 8
// using 16 threads we need to do 16 radix-8 butterflies
// therefore each thread will do 1.000000 butterflies
InvRad8B1(R + 0,R + 1,R + 2,R + 3,R + 4,R + 5,R + 6,R + 7);
if( !lds_is_real) {
if( !direct_load_to_reg) {
__syncthreads();

}

l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 0) * lstride;
lds_complex[l_offset] = R[0];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 1) * lstride;
lds_complex[l_offset] = R[1];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 2) * lstride;
lds_complex[l_offset] = R[2];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 3) * lstride;
lds_complex[l_offset] = R[3];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 4) * lstride;
lds_complex[l_offset] = R[4];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 5) * lstride;
lds_complex[l_offset] = R[5];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 6) * lstride;
lds_complex[l_offset] = R[6];
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 7) * lstride;
lds_complex[l_offset] = R[7];

}

else {
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 0) * lstride;
lds_real[l_offset] = R[0].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 1) * lstride;
lds_real[l_offset] = R[1].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 2) * lstride;
lds_real[l_offset] = R[2].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 3) * lstride;
lds_real[l_offset] = R[3].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 4) * lstride;
lds_real[l_offset] = R[4].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 5) * lstride;
lds_real[l_offset] = R[5].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 6) * lstride;
lds_real[l_offset] = R[6].x;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 7) * lstride;
lds_real[l_offset] = R[7].x;
__syncthreads();
l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[1].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[2].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[3].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 0) * lstride;
R[4].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 32) * lstride;
R[5].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 64) * lstride;
R[6].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 96) * lstride;
R[7].x = lds_real[l_offset];
__syncthreads();
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 0) * lstride;
lds_real[l_offset] = R[0].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 1) * lstride;
lds_real[l_offset] = R[1].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 2) * lstride;
lds_real[l_offset] = R[2].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 3) * lstride;
lds_real[l_offset] = R[3].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 4) * lstride;
lds_real[l_offset] = R[4].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 5) * lstride;
lds_real[l_offset] = R[5].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 6) * lstride;
lds_real[l_offset] = R[6].y;
l_offset = offset_lds + (((thread + 0 + 0) / 1) * 8 + (thread + 0 + 0) % 1 + 7) * lstride;
lds_real[l_offset] = R[7].y;
__syncthreads();
l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[1].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[2].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[3].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 0) * lstride;
R[4].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 32) * lstride;
R[5].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 64) * lstride;
R[6].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 96) * lstride;
R[7].y = lds_real[l_offset];

}




// pass 1, width 4
// using 16 threads we need to do 32 radix-4 butterflies
// therefore each thread will do 2.000000 butterflies
if( !lds_is_real) {
__syncthreads();
l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[1] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[2] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[3] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 0) * lstride;
R[4] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 32) * lstride;
R[5] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 64) * lstride;
R[6] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 96) * lstride;
R[7] = lds_complex[l_offset];

}

W = twiddles[0 + 3 * ((thread + 0 + 0) % 8)];
t = {R[1].x * W.x + R[1].y * W.y,R[1].y * W.x - R[1].x * W.y};
R[1] = t;
W = twiddles[1 + 3 * ((thread + 0 + 0) % 8)];
t = {R[2].x * W.x + R[2].y * W.y,R[2].y * W.x - R[2].x * W.y};
R[2] = t;
W = twiddles[2 + 3 * ((thread + 0 + 0) % 8)];
t = {R[3].x * W.x + R[3].y * W.y,R[3].y * W.x - R[3].x * W.y};
R[3] = t;
W = twiddles[0 + 3 * ((thread + 0 + 16) % 8)];
t = {R[5].x * W.x + R[5].y * W.y,R[5].y * W.x - R[5].x * W.y};
R[5] = t;
W = twiddles[1 + 3 * ((thread + 0 + 16) % 8)];
t = {R[6].x * W.x + R[6].y * W.y,R[6].y * W.x - R[6].x * W.y};
R[6] = t;
W = twiddles[2 + 3 * ((thread + 0 + 16) % 8)];
t = {R[7].x * W.x + R[7].y * W.y,R[7].y * W.x - R[7].x * W.y};
R[7] = t;
InvRad4B1(R + 0,R + 1,R + 2,R + 3);
InvRad4B1(R + 4,R + 5,R + 6,R + 7);
if( !lds_is_real) {
__syncthreads();
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 0) * lstride;
lds_complex[l_offset] = R[0];
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 8) * lstride;
lds_complex[l_offset] = R[1];
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 16) * lstride;
lds_complex[l_offset] = R[2];
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 24) * lstride;
lds_complex[l_offset] = R[3];
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 0) * lstride;
lds_complex[l_offset] = R[4];
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 8) * lstride;
lds_complex[l_offset] = R[5];
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 16) * lstride;
lds_complex[l_offset] = R[6];
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 24) * lstride;
lds_complex[l_offset] = R[7];

}

else {
__syncthreads();
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 0) * lstride;
lds_real[l_offset] = R[0].x;
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 8) * lstride;
lds_real[l_offset] = R[1].x;
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 16) * lstride;
lds_real[l_offset] = R[2].x;
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 24) * lstride;
lds_real[l_offset] = R[3].x;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 0) * lstride;
lds_real[l_offset] = R[4].x;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 8) * lstride;
lds_real[l_offset] = R[5].x;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 16) * lstride;
lds_real[l_offset] = R[6].x;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 24) * lstride;
lds_real[l_offset] = R[7].x;
__syncthreads();
l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[1].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[2].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[3].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 0) * lstride;
R[4].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 32) * lstride;
R[5].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 64) * lstride;
R[6].x = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 96) * lstride;
R[7].x = lds_real[l_offset];
__syncthreads();
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 0) * lstride;
lds_real[l_offset] = R[0].y;
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 8) * lstride;
lds_real[l_offset] = R[1].y;
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 16) * lstride;
lds_real[l_offset] = R[2].y;
l_offset = offset_lds + (((thread + 0 + 0) / 8) * 32 + (thread + 0 + 0) % 8 + 24) * lstride;
lds_real[l_offset] = R[3].y;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 0) * lstride;
lds_real[l_offset] = R[4].y;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 8) * lstride;
lds_real[l_offset] = R[5].y;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 16) * lstride;
lds_real[l_offset] = R[6].y;
l_offset = offset_lds + (((thread + 0 + 16) / 8) * 32 + (thread + 0 + 16) % 8 + 24) * lstride;
lds_real[l_offset] = R[7].y;
__syncthreads();
l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[1].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[2].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[3].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 0) * lstride;
R[4].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 32) * lstride;
R[5].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 64) * lstride;
R[6].y = lds_real[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 96) * lstride;
R[7].y = lds_real[l_offset];

}




// pass 2, width 4
// using 16 threads we need to do 32 radix-4 butterflies
// therefore each thread will do 2.000000 butterflies
if( !lds_is_real) {
__syncthreads();
l_offset = offset_lds + ((thread + 0 + 0) + 0) * lstride;
R[0] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 32) * lstride;
R[1] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 64) * lstride;
R[2] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 0) + 96) * lstride;
R[3] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 0) * lstride;
R[4] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 32) * lstride;
R[5] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 64) * lstride;
R[6] = lds_complex[l_offset];
l_offset = offset_lds + ((thread + 0 + 16) + 96) * lstride;
R[7] = lds_complex[l_offset];

}

W = twiddles[24 + 3 * ((thread + 0 + 0) % 32)];
t = {R[1].x * W.x + R[1].y * W.y,R[1].y * W.x - R[1].x * W.y};
R[1] = t;
W = twiddles[25 + 3 * ((thread + 0 + 0) % 32)];
t = {R[2].x * W.x + R[2].y * W.y,R[2].y * W.x - R[2].x * W.y};
R[2] = t;
W = twiddles[26 + 3 * ((thread + 0 + 0) % 32)];
t = {R[3].x * W.x + R[3].y * W.y,R[3].y * W.x - R[3].x * W.y};
R[3] = t;
W = twiddles[24 + 3 * ((thread + 0 + 16) % 32)];
t = {R[5].x * W.x + R[5].y * W.y,R[5].y * W.x - R[5].x * W.y};
R[5] = t;
W = twiddles[25 + 3 * ((thread + 0 + 16) % 32)];
t = {R[6].x * W.x + R[6].y * W.y,R[6].y * W.x - R[6].x * W.y};
R[6] = t;
W = twiddles[26 + 3 * ((thread + 0 + 16) % 32)];
t = {R[7].x * W.x + R[7].y * W.y,R[7].y * W.x - R[7].x * W.y};
R[7] = t;
InvRad4B1(R + 0,R + 1,R + 2,R + 3);
InvRad4B1(R + 4,R + 5,R + 6,R + 7);
}
typedef rocfft_complex<double> scalar_type;
static const StrideBin sb = SB_UNIT;
static const SBRC_TYPE sbrc_type = SBRC_2D;
static const SBRC_TRANSPOSE_TYPE transpose_type = TILE_ALIGNED;
static const CallbackType cbtype = CallbackType::NONE;
static const DirectRegType drtype = DirectRegType::TRY_ENABLE_IF_SUPPORT;
static const bool apply_large_twiddle = false;
static const IntrinsicAccessType intrinsic_mode = IntrinsicAccessType::DISABLE_BOTH;
static const size_t large_twiddle_base = 8;
static const size_t large_twiddle_steps = 0;
extern "C" __global__ __launch_bounds__(128) void fft_rtc_back_len_128_factors_8_4_4_wgs_128_tpt_16_dp_op_CI_CI_unitstride_sbrc_aligned_dirReg(const scalar_type* __restrict__ twiddles,const size_t dim,const size_t* __restrict__ lengths,const size_t* __restrict__ stride_in,const size_t* __restrict__ stride_out,const size_t nbatch,void* __restrict__ load_cb_fn,void* __restrict__ load_cb_data,unsigned int load_cb_lds_bytes,void* __restrict__ store_cb_fn,void* __restrict__ store_cb_data,scalar_type* __restrict__ buf_in,scalar_type* __restrict__ buf_out) {
// this kernel:
//   uses 16 threads per transform
//   does 8 transforms per thread block
// therefore it should be called with 128 threads per thread block
scalar_type R[8];
extern __shared__ unsigned char __attribute__((aligned(sizeof(scalar_type)))) lds_uchar[];
real_type_t<scalar_type>* __restrict__ lds_real = reinterpret_cast<real_type_t<scalar_type>*>(lds_uchar);
scalar_type* __restrict__ lds_complex = reinterpret_cast<scalar_type*>(lds_uchar);
size_t offset_in = 0;
size_t offset_out = 0;
unsigned int offset_lds;
unsigned int stride_lds;
size_t batch;
size_t transform;
const bool direct_load_to_reg = false;
const bool direct_store_from_reg = drtype == DirectRegType::TRY_ENABLE_IF_SUPPORT && sbrc_type != SBRC_3D_FFT_ERC_TRANS_Z_XY;
const bool lds_linear =  !direct_store_from_reg;
const bool lds_is_real = false;
auto load_cb = get_load_cb<scalar_type, cbtype>(load_cb_fn);
auto store_cb = get_store_cb<scalar_type, cbtype>(store_cb_fn);



// large twiddles
// - no large twiddles



// offsets
const size_t stride0_in = (sb == SB_UNIT) ? (1) : (stride_in[0]);
const size_t stride0_out = (sb == SB_UNIT) ? (1) : (stride_out[0]);
const unsigned int len_along_block = (sbrc_type == SBRC_3D_FFT_TRANS_XY_Z) ? lengths[2] : lengths[1];
const unsigned int stride_load_in = (sbrc_type == SBRC_3D_FFT_TRANS_XY_Z) ? stride_in[2] : stride_in[1];
const unsigned int stride_store_out = (sbrc_type == SBRC_3D_FFT_TRANS_XY_Z || sbrc_type == SBRC_2D) ? stride_out[1] : stride_out[2];



unsigned int num_of_tiles_in_batch;
unsigned int tile_index_in_plane;



unsigned int num_of_tiles_in_plane = (len_along_block - 1) / 8 + 1;
unsigned int plane_id;
unsigned int tile_serial_in_batch;
if(sbrc_type == SBRC_2D) {
num_of_tiles_in_batch = num_of_tiles_in_plane;
tile_index_in_plane = blockIdx.x % num_of_tiles_in_plane;
unsigned int remaining = blockIdx.x / num_of_tiles_in_plane;
unsigned int index_along_d;
offset_in = tile_index_in_plane * 8 * stride_load_in;
offset_out = tile_index_in_plane * 8 * stride0_out;
for(unsigned int d = 2; d < dim; ++d) {
 num_of_tiles_in_batch = num_of_tiles_in_batch * lengths[d];
index_along_d = remaining % lengths[d];
remaining = remaining / lengths[d];
offset_in = offset_in + index_along_d * stride_in[d];
offset_out = offset_out + index_along_d * stride_out[d];

}

}

else {
const unsigned int len_along_plane = (sbrc_type == SBRC_3D_FFT_TRANS_XY_Z) ? lengths[1] : lengths[2];
const unsigned int stride_plane_in = (sbrc_type == SBRC_3D_FFT_TRANS_XY_Z) ? stride_in[1] : stride_in[2];
const unsigned int stride_plane_out = (sbrc_type == SBRC_3D_FFT_TRANS_XY_Z) ? stride_out[2] : stride_out[1];
num_of_tiles_in_batch = num_of_tiles_in_plane * len_along_plane;
tile_serial_in_batch = blockIdx.x % num_of_tiles_in_batch;
if(sbrc_type == SBRC_3D_FFT_TRANS_XY_Z) {
if(transpose_type == DIAGONAL) {
tile_index_in_plane = tile_serial_in_batch % 16;
plane_id = (tile_serial_in_batch / 16 + tile_index_in_plane) % 128;

}

else {
tile_index_in_plane = tile_serial_in_batch / lengths[1];
plane_id = blockIdx.x % lengths[1];

}


}

else {
if(transpose_type == DIAGONAL) {
tile_index_in_plane = tile_serial_in_batch % 16;
plane_id = (tile_serial_in_batch / 16 + tile_index_in_plane) % 128;

}

else {
plane_id = tile_serial_in_batch / num_of_tiles_in_plane;
tile_index_in_plane = blockIdx.x % num_of_tiles_in_plane;

}


}

offset_in = plane_id * stride_plane_in + tile_index_in_plane * 8 * stride_load_in;
offset_out = plane_id * stride_plane_out + tile_index_in_plane * 8 * stride0_out;

}




batch = blockIdx.x / num_of_tiles_in_batch;
offset_in = offset_in + batch * stride_in[dim];
offset_out = offset_out + batch * stride_out[dim];
transform = lds_linear ? tile_index_in_plane * 8 + threadIdx.x / 16 : tile_index_in_plane * 8 + threadIdx.x % 8;
stride_lds = lds_linear ? 128 + (sbrc_type != SBRC_3D_FFT_ERC_TRANS_Z_XY ? 0 : 1) : 8 + (sbrc_type != SBRC_3D_FFT_ERC_TRANS_Z_XY ? 0 : 1);
offset_lds = lds_linear ? stride_lds * (transform % 8) : threadIdx.x % 8;
bool edge = false;
unsigned int thread;
unsigned int tid_hor;
if(transpose_type == TILE_UNALIGNED) {
edge = ((tile_index_in_plane + 1) * 8 > len_along_block) ? true : false;

}




if(direct_load_to_reg) {
// load global into registers
// For row-input we don't load to reg

}

else {
// load global into lds
thread = threadIdx.x / 128;
tid_hor = threadIdx.x % 128;
if(transpose_type != TILE_UNALIGNED ||  !edge) {
lds_complex[lds_linear ? tid_hor * 1 + (thread + 0) * stride_lds : tid_hor * stride_lds + (thread + 0) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 0) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 1) * stride_lds : tid_hor * stride_lds + (thread + 1) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 1) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 2) * stride_lds : tid_hor * stride_lds + (thread + 2) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 2) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 3) * stride_lds : tid_hor * stride_lds + (thread + 3) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 3) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 4) * stride_lds : tid_hor * stride_lds + (thread + 4) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 4) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 5) * stride_lds : tid_hor * stride_lds + (thread + 5) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 5) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 6) * stride_lds : tid_hor * stride_lds + (thread + 6) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 6) * stride_load_in), load_cb_data, nullptr);
lds_complex[lds_linear ? tid_hor * 1 + (thread + 7) * stride_lds : tid_hor * stride_lds + (thread + 7) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + 7) * stride_load_in), load_cb_data, nullptr);

}

else {
for(unsigned int t = 0; tile_index_in_plane * 8 + thread + t < len_along_block; ++t) {
 lds_complex[lds_linear ? tid_hor * 1 + (thread + t) * stride_lds : tid_hor * stride_lds + (thread + t) * 1] = load_cb(buf_in,offset_in + (tid_hor * stride0_in + (thread + t) * stride_load_in), load_cb_data, nullptr);

}

}





}




// calc the thread_in_device value once and for all device funcs
unsigned int thread_in_device = lds_linear ? threadIdx.x % 16 : threadIdx.x / 8;



// call a pre-load from lds to registers (if necessary)
if( !direct_load_to_reg) {
lds_to_reg_input_length128_device<scalar_type,lds_linear ? SB_UNIT : SB_NONUNIT,true>(R,lds_complex,stride_lds,offset_lds,thread_in_device,true);

}




// transform
inverse_length128_SBRC_device<scalar_type,lds_is_real,sbrc_type,transpose_type,lds_linear ? SB_UNIT : SB_NONUNIT,lds_linear,direct_load_to_reg>(R,lds_real,lds_complex,twiddles,stride_lds,offset_lds,thread_in_device,true);






// call a post-store from registers to lds (if necessary)
if( !direct_store_from_reg) {
lds_from_reg_output_length128_device<scalar_type,lds_linear ? SB_UNIT : SB_NONUNIT,true>(R,lds_complex,stride_lds,offset_lds,thread_in_device,true);

}




if(direct_store_from_reg) {
// store registers into global
thread = threadIdx.x / 8;
tid_hor = threadIdx.x % 8;
if(transpose_type != TILE_UNALIGNED ||  !edge) {
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 0) * stride_store_out,R[0], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 32) * stride_store_out,R[1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 64) * stride_store_out,R[2], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 96) * stride_store_out,R[3], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 0) * stride_store_out,R[4], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 32) * stride_store_out,R[5], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 64) * stride_store_out,R[6], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 96) * stride_store_out,R[7], store_cb_data, nullptr);

}

else {
if(tile_index_in_plane * 8 + tid_hor < len_along_block) {
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 0) * stride_store_out,R[0], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 32) * stride_store_out,R[1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 64) * stride_store_out,R[2], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 0) / 32) * 128 + (thread + 0 + 0) % 32 + 96) * stride_store_out,R[3], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 0) * stride_store_out,R[4], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 32) * stride_store_out,R[5], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 64) * stride_store_out,R[6], store_cb_data, nullptr);
store_cb(buf_out,offset_out + tid_hor * stride0_out + (((thread + 0 + 16) / 32) * 128 + (thread + 0 + 16) % 32 + 96) * stride_store_out,R[7], store_cb_data, nullptr);

}


}


}

else {






// store global
__syncthreads();
thread = threadIdx.x / 8;
tid_hor = threadIdx.x % 8;
if(transpose_type != TILE_UNALIGNED ||  !edge) {
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 0) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 0) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 16) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 16) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 32) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 32) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 48) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 48) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 64) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 64) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 80) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 80) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 96) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 96) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 112) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 112) * 1], store_cb_data, nullptr);
if(sbrc_type == SBRC_3D_FFT_ERC_TRANS_Z_XY) {
// extra global write for SBRC_3D_FFT_ERC_TRANS_Z_XY
if(threadIdx.x < 8) {
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 128) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 128) * 1], store_cb_data, nullptr);

}


}


}

else {
if(tile_index_in_plane * 8 + tid_hor < len_along_block) {
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 0) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 0) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 16) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 16) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 32) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 32) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 48) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 48) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 64) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 64) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 80) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 80) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 96) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 96) * 1], store_cb_data, nullptr);
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 112) * stride_store_out),lds_complex[tid_hor * stride_lds + (thread + 112) * 1], store_cb_data, nullptr);
if(sbrc_type == SBRC_3D_FFT_ERC_TRANS_Z_XY) {
// extra global write for SBRC_3D_FFT_ERC_TRANS_Z_XY
if(threadIdx.x < (len_along_block % 8)) {
store_cb(buf_out,offset_out + (tid_hor * stride0_out + (thread + 128) * stride_store_out),lds_complex[tid_hor * stride_lds + 128], store_cb_data, nullptr);

}


}


}


}


}

}
