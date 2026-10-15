#pragma once
// Layout and independent correctness checks retained from v2; no event timing here.
// Nonfinite errors are rejected; the small even-N Nyquist term is counted once.
static double checked_abs(double value)
{
    if(!std::isfinite(value)) throw std::runtime_error("nonfinite correctness output");
    return std::fabs(value);
}

struct RocFFTSession
{
    RocFFTSession() { CHECK_FFT(rocfft_setup()); }
    ~RocFFTSession() { rocfft_cleanup(); }
};

struct DeviceBuffer
{
    void* data = nullptr;
    explicit DeviceBuffer(size_t bytes) { CHECK_HIP(hipMalloc(&data, bytes)); }
    ~DeviceBuffer() { if(data) hipFree(data); }
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
};

constexpr double CHECK_TOL     = 1e-9;
constexpr double TWO_PI        = 6.283185307179586476925286766559;

static inline hipDoubleComplex cmplx(double re, double im = 0.0)
{
    hipDoubleComplex v;
    v.x = re;
    v.y = im;
    return v;
}

static inline double rnd(unsigned long long& s)
{
    s ^= s << 13;
    s ^= s >> 7;
    s ^= s << 17;
    return static_cast<double>((s >> 11) & ((1ull << 52) - 1))
               / static_cast<double>(1ull << 52)
           - 0.5;
}

static inline unsigned long long seed_of(int t)
{
    return 0x9E3779B97F4A7C15ull
           ^ (static_cast<unsigned long long>(t + 1) * 0xBF58476D1CE4E5B9ull);
}

struct Check
{
    bool   ran   = false;
    bool   pass  = true;
    double err_a = -1.0;
    double err_b = -1.0;
};

enum class TransformKind
{
    z2z_forward,
    z2z_inverse,
    d2z,
    z2d,
};

struct RocPlan
{
    rocfft_plan             plan        = nullptr;
    rocfft_plan_description description = nullptr;
    rocfft_execution_info   info        = nullptr;
    void*                   work_buffer = nullptr;
    size_t                  work_bytes  = 0;

    RocPlan() = default;
    RocPlan(const RocPlan&)            = delete;
    RocPlan& operator=(const RocPlan&) = delete;

    ~RocPlan()
    {
        if(work_buffer)
            (void)hipFree(work_buffer);
        if(info)
            rocfft_execution_info_destroy(info);
        if(plan)
            rocfft_plan_destroy(plan);
        if(description)
            rocfft_plan_description_destroy(description);
    }
};

static RocPlan* create_plan(size_t N, size_t batch, TransformKind kind)
{
    auto p = new RocPlan;

    const size_t Nc      = N / 2 + 1;
    const size_t stride  = 1;
    size_t       idist   = N;
    size_t       odist   = N;
    auto         itype   = rocfft_array_type_complex_interleaved;
    auto         otype   = rocfft_array_type_complex_interleaved;
    auto         ffttype = rocfft_transform_type_complex_forward;

    if(kind == TransformKind::z2z_inverse)
        ffttype = rocfft_transform_type_complex_inverse;
    else if(kind == TransformKind::d2z)
    {
        ffttype = rocfft_transform_type_real_forward;
        itype   = rocfft_array_type_real;
        otype   = rocfft_array_type_hermitian_interleaved;
        odist   = Nc;
    }
    else if(kind == TransformKind::z2d)
    {
        ffttype = rocfft_transform_type_real_inverse;
        itype   = rocfft_array_type_hermitian_interleaved;
        otype   = rocfft_array_type_real;
        idist   = Nc;
    }

    CHECK_FFT(rocfft_plan_description_create(&p->description));
    CHECK_FFT(rocfft_plan_description_set_data_layout(p->description,
                                                       itype,
                                                       otype,
                                                       nullptr,
                                                       nullptr,
                                                       1,
                                                       &stride,
                                                       idist,
                                                       1,
                                                       &stride,
                                                       odist));
    CHECK_FFT(rocfft_plan_create(&p->plan,
                                 rocfft_placement_notinplace,
                                 ffttype,
                                 rocfft_precision_double,
                                 1,
                                 &N,
                                 batch,
                                 p->description));
    CHECK_FFT(rocfft_execution_info_create(&p->info));
    CHECK_FFT(rocfft_execution_info_set_stream(p->info, nullptr));
    CHECK_FFT(rocfft_plan_get_work_buffer_size(p->plan, &p->work_bytes));

    if(p->work_bytes)
    {
        CHECK_HIP(hipMalloc(&p->work_buffer, p->work_bytes));
        CHECK_FFT(rocfft_execution_info_set_work_buffer(p->info,
                                                        p->work_buffer,
                                                        p->work_bytes));
    }
    return p;
}

static void execute(RocPlan& p, void* input, void* output)
{
    void* inputs[]  = {input};
    void* outputs[] = {output};
    CHECK_FFT(rocfft_execute(p.plan, inputs, outputs, p.info));
}

static double check_tone_z2z(int N,
                             int batch,
                             RocPlan& plan,
                             hipDoubleComplex* x,
                             hipDoubleComplex* y,
                             std::vector<hipDoubleComplex>& hx,
                             std::vector<hipDoubleComplex>& hout)
{
    const int k0 = N > 1 ? 1 : 0;
    std::fill(hx.begin(), hx.end(), cmplx(0.0));
    for(int t = 0; t < batch; ++t)
        hx[static_cast<size_t>(t) * N + k0] = cmplx(static_cast<double>(t + 1));

    CHECK_HIP(hipMemcpy(x, hx.data(), sizeof(*x) * static_cast<size_t>(N) * batch,
                        hipMemcpyHostToDevice));
    execute(plan, x, y);
    CHECK_HIP(hipDeviceSynchronize());

    double worst = 0.0;
    const int probes[2] = {0, batch - 1};
    for(int p = 0; p < 2; ++p)
    {
        const int t = probes[p];
        if(t < 0 || (p == 1 && batch == 1))
            continue;
        CHECK_HIP(hipMemcpy(hout.data(), y + static_cast<size_t>(t) * N,
                            sizeof(*y) * static_cast<size_t>(N), hipMemcpyDeviceToHost));
        const double want = static_cast<double>(t + 1);
        for(int j = 0; j < N; ++j)
            worst = std::max(worst,
                             checked_abs(std::hypot(hout[j].x, hout[j].y) - want) / want);
    }
    return worst;
}

static double check_roundtrip_z2z(int N,
                                  int batch,
                                  RocPlan& forward,
                                  RocPlan& inverse,
                                  hipDoubleComplex* x,
                                  hipDoubleComplex* y,
                                  std::vector<hipDoubleComplex>& hx,
                                  std::vector<hipDoubleComplex>& hout)
{
    double peak = 0.0;
    for(int t = 0; t < batch; ++t)
    {
        auto s = seed_of(t);
        for(int k = 0; k < N; ++k)
        {
            const double re = rnd(s);
            const double im = rnd(s);
            hx[static_cast<size_t>(t) * N + k] = cmplx(re, im);
            peak = std::max(peak, std::hypot(re, im));
        }
    }
    peak = peak > 0.0 ? peak : 1.0;
    CHECK_HIP(hipMemcpy(x, hx.data(), sizeof(*x) * static_cast<size_t>(N) * batch,
                        hipMemcpyHostToDevice));
    execute(forward, x, y);
    execute(inverse, y, x);
    CHECK_HIP(hipDeviceSynchronize());

    double worst = 0.0;
    const int probes[2] = {0, batch - 1};
    for(int p = 0; p < 2; ++p)
    {
        const int t = probes[p];
        if(t < 0 || (p == 1 && batch == 1))
            continue;
        CHECK_HIP(hipMemcpy(hout.data(), x + static_cast<size_t>(t) * N,
                            sizeof(*x) * static_cast<size_t>(N), hipMemcpyDeviceToHost));
        for(int k = 0; k < N; ++k)
        {
            const double re = hout[k].x / N - hx[static_cast<size_t>(t) * N + k].x;
            const double im = hout[k].y / N - hx[static_cast<size_t>(t) * N + k].y;
            worst = std::max(worst, checked_abs(std::hypot(re, im)) / peak);
        }
    }
    return worst;
}

static double check_tone_d2z(int N,
                             int batch,
                             RocPlan& plan,
                             double* x,
                             hipDoubleComplex* y,
                             std::vector<double>& hx,
                             std::vector<hipDoubleComplex>& hout)
{
    const int k0 = N > 1 ? 1 : 0;
    std::fill(hx.begin(), hx.end(), 0.0);
    for(int t = 0; t < batch; ++t)
        hx[static_cast<size_t>(t) * N + k0] = static_cast<double>(t + 1);
    CHECK_HIP(hipMemcpy(x, hx.data(), sizeof(double) * static_cast<size_t>(N) * batch,
                        hipMemcpyHostToDevice));
    execute(plan, x, y);
    CHECK_HIP(hipDeviceSynchronize());

    const size_t Nc = static_cast<size_t>(N) / 2 + 1;
    double worst = 0.0;
    const int probes[2] = {0, batch - 1};
    for(int p = 0; p < 2; ++p)
    {
        const int t = probes[p];
        if(t < 0 || (p == 1 && batch == 1))
            continue;
        CHECK_HIP(hipMemcpy(hout.data(), y + static_cast<size_t>(t) * Nc,
                            sizeof(*y) * Nc, hipMemcpyDeviceToHost));
        const double want = static_cast<double>(t + 1);
        for(size_t j = 0; j < Nc; ++j)
            worst = std::max(worst,
                             checked_abs(std::hypot(hout[j].x, hout[j].y) - want) / want);
    }
    return worst;
}

static double check_z2d(int N,
                        int batch,
                        RocPlan& plan,
                        hipDoubleComplex* x,
                        double* y,
                        std::vector<hipDoubleComplex>& hx,
                        std::vector<double>& hout)
{
    const size_t Nc    = static_cast<size_t>(N) / 2 + 1;
    const int nbins    = Nc >= 3 ? 3 : 1;
    std::fill(hx.begin(), hx.end(), cmplx(0.0));
    for(int t = 0; t < batch; ++t)
        for(int j = 0; j < nbins; ++j)
            hx[static_cast<size_t>(t) * Nc + j] = cmplx(static_cast<double>(t + 1));
    CHECK_HIP(hipMemcpy(x, hx.data(), sizeof(*x) * Nc * batch, hipMemcpyHostToDevice));
    execute(plan, x, y);
    CHECK_HIP(hipDeviceSynchronize());

    double worst = 0.0;
    const int probes[2] = {0, batch - 1};
    for(int p = 0; p < 2; ++p)
    {
        const int t = probes[p];
        if(t < 0 || (p == 1 && batch == 1))
            continue;
        CHECK_HIP(hipMemcpy(hout.data(), y + static_cast<size_t>(t) * N,
                            sizeof(double) * static_cast<size_t>(N), hipMemcpyDeviceToHost));
        const double amp   = static_cast<double>(t + 1);
        const double scale = amp * nbins;
        for(int n = 0; n < N; ++n)
        {
            double want = amp;
            for(int j = 1; j < nbins; ++j)
                want += ((N % 2 == 0 && j == N / 2) ? 1.0 : 2.0) * amp * std::cos(TWO_PI * j * n / N);
            worst = std::max(worst, checked_abs(hout[n] - want) / scale);
        }
    }
    return worst;
}
