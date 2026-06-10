
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
typedef rocfft_complex<double> scalar_type;
static const CallbackType cbtype = CallbackType::NONE;
typedef scalar_type T;
extern "C" __global__ __launch_bounds__(1024) void transpose_rtc_tile32x32_dim2_dp_CI_CI_twd4step_back_diag_aligned(scalar_type* __restrict__ input,scalar_type* __restrict__ output,const scalar_type* __restrict__ twiddles_large,unsigned int dim,unsigned int length0,unsigned int length1,unsigned int length2,const size_t* __restrict__ lengths,unsigned int stride_in0,unsigned int stride_in1,unsigned int stride_in2,const size_t* __restrict__ stride_in,unsigned int idist,unsigned int stride_out0,unsigned int stride_out1,unsigned int stride_out2,const size_t* __restrict__ stride_out,unsigned int odist,const unsigned int gridX,const unsigned int gridY,const unsigned int gridZ,void* __restrict__ load_cb_fn,void* __restrict__ load_cb_data,unsigned int load_cb_lds_bytes,void* __restrict__ store_cb_fn,void* __restrict__ store_cb_data) {
__shared__ scalar_type lds[32][32];
// since gridDim is passed as {gridX, 1, 1}, use the
// following variables to recover block indices in a 3-D fashion:
unsigned int tileBlockIdx_y = blockIdx.y;
unsigned int tileBlockIdx_x = blockIdx.x;



auto bid = blockIdx.x + gridDim.x * blockIdx.y;
tileBlockIdx_y = bid % gridDim.y;
tileBlockIdx_x = (bid / gridDim.y + tileBlockIdx_y) % gridDim.x;
// only using 2 dimensions, pretend length2 is 1 so the
// compiler can optimize out comparisons against it
length2 = 1;
unsigned int tile_x_index = threadIdx.x;
unsigned int tile_y_index = threadIdx.y;
// work out offset for dimensions after the first 3
unsigned int remaining = blockIdx.z;
unsigned int offset_in = 0;
unsigned int offset_out = 0;
// remaining is now the batch
offset_in += remaining * idist;
offset_out += remaining * odist;
auto load_cb = get_load_cb<scalar_type, cbtype>(load_cb_fn);
auto store_cb = get_store_cb<scalar_type, cbtype>(store_cb_fn);
#pragma unroll
for(unsigned int i = 0; i < 1; ++i) {
 auto logical_row = 32 * tileBlockIdx_y + tile_y_index + i * 32;
auto idx0 = 32 * tileBlockIdx_x + tile_x_index;
auto idx1 = logical_row;
auto idx2 = 0;
auto global_read_idx = idx0 * stride_in0 + idx1 * stride_in1 + idx2 * stride_in2 + offset_in;
scalar_type elem;
elem = load_cb(input,global_read_idx, load_cb_data, nullptr);
auto twl_idx = idx0 * idx1;
TWIDDLE_STEP_MUL_INV(TWLstep4,twiddles_large,twl_idx,elem);
lds[tile_x_index][i * 32 + tile_y_index] = elem;

}
__syncthreads();
scalar_type val[1];
// reallocate threads to write along fastest dim (length1) and
// read transposed from LDS
tile_x_index = threadIdx.y;
tile_y_index = threadIdx.x;
#pragma unroll
for(unsigned int i = 0; i < 1; ++i) {
 val[i] = lds[tile_x_index + i * 32][tile_y_index];

}
#pragma unroll
for(unsigned int i = 0; i < 1; ++i) {
 auto logical_col = 32 * tileBlockIdx_x + tile_x_index + i * 32;
auto logical_row = 32 * tileBlockIdx_y + tile_y_index;
auto idx0 = logical_col;
auto idx1 = logical_row;
auto idx2 = 0;
auto global_write_idx = idx0 * stride_out0 + idx1 * stride_out1 + idx2 * stride_out2 + offset_out;
store_cb(output,global_write_idx,val[i], store_cb_data, nullptr);

}
}
