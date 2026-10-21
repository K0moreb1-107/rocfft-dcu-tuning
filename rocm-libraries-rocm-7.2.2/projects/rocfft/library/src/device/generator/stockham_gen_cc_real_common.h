// EXP128: typed boundary access and value-only real-pair operations.
#pragma once
#include "stockham_gen_base.h"

struct CCRealTypedIOVisitor : BaseVisitor
{
    explicit CCRealTypedIOVisitor(const RealBlockIO& io)
        : io(io)
    {
    }
    RealBlockIO io;
    StatementList visit_CallbackLoadDeclaration(const CallbackLoadDeclaration& x) override
    {
        auto y = x;
        y.typed_real_io = true;
        y.user_boundary = io.IsInputBoundary();
        y.real_boundary = io.role == RealBlockRole::LocalPostColumns;
        return { y };
    }
    StatementList visit_CallbackStoreDeclaration(const CallbackStoreDeclaration& x) override
    {
        auto y = x;
        y.typed_real_io = true;
        y.user_boundary = io.IsOutputBoundary();
        y.real_boundary = io.role == RealBlockRole::PackedInverseRows;
        return { y };
    }
};

inline Expression cc_real_pointer(const Expression& pointer)
{
    return CallExpr { "cc_real_pointer", { pointer } };
}

inline std::string cc_real_device_helpers()
{
    return R"src(

template <typename T> __device__ __forceinline__ real_type_t<T>* cc_real_pointer(T* p)
{
    return reinterpret_cast<real_type_t<T>*>(p);
}

template <typename T, CallbackType CB, bool User, bool Real> struct cc_boundary_load
{
    void* fn;
    __device__ __forceinline__ T operator()(T* p, size_t i, void* data, void* shared) const
    {
#ifdef ROCFFT_CALLBACKS_ENABLED
        if constexpr(User && CB != CallbackType::NONE)
        {
            if(fn)
            {
                if constexpr(Real)
                {
                    auto f = reinterpret_cast<typename callback_type<real_type_t<T>>::load>(fn);
                    auto r = cc_real_pointer(p);
                    return T { f(r, 2 * i, data, shared), f(r, 2 * i + 1, data, shared) };
                }
                else
                    return reinterpret_cast<typename callback_type<T>::load>(fn)(
                        p, i, data, shared);
            }
        }
#endif
        return p[i];
    }
    __device__ __forceinline__ real_type_t<T> operator()(
        real_type_t<T>* p, size_t i, void* data, void* shared) const
    {
#ifdef ROCFFT_CALLBACKS_ENABLED
        if constexpr(User && Real && CB != CallbackType::NONE)
            if(fn)
                return reinterpret_cast<typename callback_type<real_type_t<T>>::load>(fn)(
                    p, i, data, shared);
#endif
        return p[i];
    }
};
template <typename T, CallbackType CB, bool User, bool Real> struct cc_boundary_store
{
    void* fn;
    __device__ __forceinline__ void operator()(T* p, size_t i, T v, void* data, void* shared) const
    {
#ifdef ROCFFT_CALLBACKS_ENABLED
        if constexpr(User && CB != CallbackType::NONE)
        {
            if(fn)
            {
                if constexpr(Real)
                {
                    auto f = reinterpret_cast<typename callback_type<real_type_t<T>>::store>(fn);
                    auto r = cc_real_pointer(p);
                    f(r, 2 * i, v.x, data, shared);
                    f(r, 2 * i + 1, v.y, data, shared);
                }
                else
                    reinterpret_cast<typename callback_type<T>::store>(fn)(p, i, v, data, shared);
                return;
            }
        }
#endif
        p[i] = v;
    }
    __device__ __forceinline__ void operator()(
        real_type_t<T>* p, size_t i, real_type_t<T> v, void* data, void* shared) const
    {
#ifdef ROCFFT_CALLBACKS_ENABLED
        if constexpr(User && Real && CB != CallbackType::NONE)
        {
            if(fn)
            {
                reinterpret_cast<typename callback_type<real_type_t<T>>::store>(fn)(
                    p, i, v, data, shared);
                return;
            }
        }
#endif
        p[i] = v;
    }
};
template <typename T> __device__ __forceinline__ T cc_folded_value(T v, size_t k, size_t n)
{
    if(k == 0 || k == n / 2)
        v.y = 0;
    if(k > n / 2)
        v.y = -v.y;
    return v;
}
template <typename T> __device__ __forceinline__ void cc_post_pair(T p, T q, T w, T& own, T& other)
{
    const auto ux = (p.x + q.x) * 0.5, uy = (p.y + q.y) * 0.5;
    const auto vx = (p.x - q.x) * 0.5, vy = (p.y - q.y) * 0.5;
    const auto a = vx * w.y + uy * w.x, b = uy * w.y - vx * w.x;
    own = T { ux + a, vy + b };
    other = T { ux - a, b - vy };
}
template <typename T> __device__ __forceinline__ void cc_pre_pair(T p, T q, T w, T& own, T& other)
{
    const auto ux = p.x + q.x, uy = p.y + q.y, vx = p.x - q.x, vy = p.y - q.y;
    const auto a = vx * w.y - uy * w.x, b = uy * w.y + vx * w.x;
    own = T { ux + a, vy + b };
    other = T { ux - a, b - vy };
}
template <typename T> __device__ __forceinline__ T cc_conjugate(T p) { return T { p.x, -p.y }; }
template <typename T> __device__ __forceinline__ T cc_inverse_endpoints(T p)
{
    return T { p.x + p.y, p.x - p.y };
}
template <typename T> __device__ __forceinline__ T cc_inverse_middle(T p)
{
    return T { 2 * p.x, -2 * p.y };
}
)src";
}
