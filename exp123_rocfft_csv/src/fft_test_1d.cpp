// 1D rocFFT timing/correctness harness compatible with the CUDA/cuFFT CSV schema.
// Usage: fft_test_1d N is_warmup {z2z_1d|d2z_1d|z2d_1d} [batch] [nocheck]

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <vector>

#include <hip/hip_complex.h>
#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>

#define CHECK_HIP(x)                                                                            \
    do                                                                                          \
    {                                                                                           \
        hipError_t err_ = (x);                                                                  \
        if(err_ != hipSuccess)                                                                  \
        {                                                                                       \
            std::cerr << "HIP error: " << hipGetErrorString(err_) << "\n";                    \
            std::exit(1);                                                                       \
        }                                                                                       \
    } while(0)

#define CHECK_FFT(x)                                                                            \
    do                                                                                          \
    {                                                                                           \
        rocfft_status err_ = (x);                                                               \
        if(err_ != rocfft_status_success)                                                       \
        {                                                                                       \
            std::cerr << "rocFFT error: " << static_cast<int>(err_) << "\n";                  \
            std::exit(1);                                                                       \
        }                                                                                       \
    } while(0)

constexpr bool   ENABLE_TIMING = true;
constexpr bool   ENABLE_CSV    = true;
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

struct Timing
{
    double plan_ms  = 0.0;
    double first_ms = 0.0;
    double min_ms   = 0.0;
    double mean_ms  = 0.0;
    double max_ms   = 0.0;
};

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

template <typename F>
static Timing time_loop(F&& exec, int warmup, int iters)
{
    hipEvent_t start, stop;
    CHECK_HIP(hipEventCreate(&start));
    CHECK_HIP(hipEventCreate(&stop));

    for(int i = 0; i < warmup; ++i)
        exec();
    CHECK_HIP(hipDeviceSynchronize());

    Timing T;
    T.min_ms       = 1e30;
    double total   = 0.0;
    for(int i = 0; i < iters; ++i)
    {
        CHECK_HIP(hipEventRecord(start, nullptr));
        exec();
        CHECK_HIP(hipEventRecord(stop, nullptr));
        CHECK_HIP(hipEventSynchronize(stop));
        float ms = 0.0f;
        CHECK_HIP(hipEventElapsedTime(&ms, start, stop));
        total    += ms;
        T.min_ms  = std::min(T.min_ms, static_cast<double>(ms));
        T.max_ms  = std::max(T.max_ms, static_cast<double>(ms));
    }
    T.mean_ms = total / iters;
    CHECK_HIP(hipEventDestroy(start));
    CHECK_HIP(hipEventDestroy(stop));
    return T;
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
                             std::fabs(std::hypot(hout[j].x, hout[j].y) - want) / want);
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
            worst = std::max(worst, std::hypot(re, im) / peak);
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
                             std::fabs(std::hypot(hout[j].x, hout[j].y) - want) / want);
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
                want += 2.0 * amp * std::cos(TWO_PI * j * n / N);
            worst = std::max(worst, std::fabs(hout[n] - want) / scale);
        }
    }
    return worst;
}

int main(int argc, char* argv[])
{
    if(argc < 4)
    {
        std::cerr << "Usage: " << argv[0]
                  << " N is_warmup func [batch] [nocheck]\n";
        return 1;
    }

    const int N = std::atoi(argv[1]);
    if(N < 1)
    {
        std::cerr << "N must be positive\n";
        return 1;
    }
    const bool is_warmup = std::atoi(argv[2]) != 0;
    const std::string func = argv[3];
    int batch = argc > 4 ? std::atoi(argv[4]) : 1;
    batch = std::max(batch, 1);
    bool do_check = true;
    for(int i = 5; i < argc; ++i)
        if(std::string(argv[i]) == "nocheck")
            do_check = false;

    int iters = 50;
    if(const char* e = std::getenv("FFT_TEST_ITERS"))
        if(std::atoi(e) > 0)
            iters = std::atoi(e);

    if(func != "z2z_1d" && func != "d2z_1d" && func != "z2d_1d")
    {
        std::cerr << "Unknown func\n";
        return 1;
    }

    const bool is_z2z = func == "z2z_1d";
    const bool is_d2z = func == "d2z_1d";
    const size_t Nc = static_cast<size_t>(N) / 2 + 1;
    const size_t n_in  = is_z2z ? static_cast<size_t>(N) : (is_d2z ? static_cast<size_t>(N) : Nc);
    const size_t n_out = is_z2z ? static_cast<size_t>(N) : (is_d2z ? Nc : static_cast<size_t>(N));
    const size_t total_in  = n_in * static_cast<size_t>(batch);
    const size_t total_out = n_out * static_cast<size_t>(batch);

    CHECK_FFT(rocfft_setup());
    void* x = nullptr;
    void* y = nullptr;
    const size_t alloc_elems = std::max(total_in, total_out);
    CHECK_HIP(hipMalloc(&x, sizeof(hipDoubleComplex) * alloc_elems));
    CHECK_HIP(hipMalloc(&y, sizeof(hipDoubleComplex) * alloc_elems));

    // Move rocFFT's process-wide initialization outside the target plan window.
    {
        RocPlan* warm = create_plan(1, 1, TransformKind::z2z_forward);
        delete warm;
    }

    const TransformKind kind = is_z2z ? TransformKind::z2z_forward
                               : is_d2z ? TransformKind::d2z
                                        : TransformKind::z2d;
    const auto t0 = std::chrono::steady_clock::now();
    RocPlan* plan = create_plan(static_cast<size_t>(N), static_cast<size_t>(batch), kind);
    const auto t1 = std::chrono::steady_clock::now();
    const double plan_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    double first_ms = 0.0;
    {
        hipEvent_t s, e;
        CHECK_HIP(hipEventCreate(&s));
        CHECK_HIP(hipEventCreate(&e));
        CHECK_HIP(hipEventRecord(s, nullptr));
        execute(*plan, x, y);
        CHECK_HIP(hipEventRecord(e, nullptr));
        CHECK_HIP(hipEventSynchronize(e));
        float ms = 0.0f;
        CHECK_HIP(hipEventElapsedTime(&ms, s, e));
        first_ms = ms;
        CHECK_HIP(hipEventDestroy(s));
        CHECK_HIP(hipEventDestroy(e));
    }

    Check chk;
    if(do_check)
    {
        chk.ran = true;
        if(is_z2z)
        {
            std::vector<hipDoubleComplex> hx(total_in), hout(static_cast<size_t>(N));
            chk.err_a = check_tone_z2z(N, batch, *plan,
                                       static_cast<hipDoubleComplex*>(x),
                                       static_cast<hipDoubleComplex*>(y), hx, hout);
            RocPlan* inverse = create_plan(static_cast<size_t>(N), static_cast<size_t>(batch),
                                           TransformKind::z2z_inverse);
            chk.err_b = check_roundtrip_z2z(N, batch, *plan, *inverse,
                                            static_cast<hipDoubleComplex*>(x),
                                            static_cast<hipDoubleComplex*>(y), hx, hout);
            delete inverse;
        }
        else if(is_d2z)
        {
            std::vector<double> hx(total_in);
            std::vector<hipDoubleComplex> hout(Nc);
            chk.err_a = check_tone_d2z(N, batch, *plan, static_cast<double*>(x),
                                       static_cast<hipDoubleComplex*>(y), hx, hout);
        }
        else
        {
            std::vector<hipDoubleComplex> hx(total_in);
            std::vector<double> hout(static_cast<size_t>(N));
            chk.err_a = check_z2d(N, batch, *plan, static_cast<hipDoubleComplex*>(x),
                                  static_cast<double*>(y), hx, hout);
        }
        chk.pass = chk.err_a >= 0.0 && chk.err_a < CHECK_TOL
                   && (chk.err_b < 0.0 || chk.err_b < CHECK_TOL);
    }

    // Preserve the CUDA harness's byte pattern, including real-transform cases.
    {
        std::vector<hipDoubleComplex> hx(total_in);
        for(size_t i = 0; i < total_in; ++i)
            hx[i] = cmplx(static_cast<double>(i % 1024), static_cast<double>(i % 97));
        CHECK_HIP(hipMemcpy(x, hx.data(), sizeof(hipDoubleComplex) * total_in,
                            hipMemcpyHostToDevice));
    }

    Timing T;
    if(ENABLE_TIMING)
        T = time_loop([&] { execute(*plan, x, y); }, 3, iters);
    T.plan_ms  = plan_ms;
    T.first_ms = first_ms;
    const double per_tf = T.min_ms / batch;

    delete plan;
    CHECK_HIP(hipFree(x));
    CHECK_HIP(hipFree(y));
    CHECK_FFT(rocfft_cleanup());

    const char* ck = !chk.ran ? "NA" : (chk.pass ? "PASS" : "FAIL");
    char errstr[64];
    std::snprintf(errstr, sizeof(errstr), chk.ran ? "%.3e" : "-1", chk.err_a);

    if(ENABLE_CSV)
    {
        std::string output_path = "../data/results_rocfft/";
        if(const char* e = std::getenv("FFT_TEST_OUT"))
            output_path = e;
        if(!output_path.empty() && output_path.back() != '/')
            output_path += '/';
        mkdir(output_path.c_str(), 0755);
        const std::string file_path = output_path + "fft_test_1d.csv";
        bool write_header = false;
        {
            std::ifstream fin(file_path, std::ios::binary);
            if(!fin.good())
                write_header = true;
            else
            {
                fin.seekg(0, std::ios::end);
                write_header = fin.tellg() == 0;
            }
        }
        std::ofstream fout(file_path, std::ios::app);
        if(!fout)
        {
            std::cerr << "Cannot open CSV: " << file_path << "\n";
            return 1;
        }
        if(write_header)
            fout << "func,N,batch,is_warmup,iters,plan_ms,first_ms,min_ms,mean_ms,max_ms,"
                    "per_tf_ms,check,err_a,err_b\n";
        fout << func << ',' << N << ',' << batch << ',' << (is_warmup ? 1 : 0) << ','
             << iters << ',' << plan_ms << ',' << first_ms << ',' << T.min_ms << ','
             << T.mean_ms << ',' << T.max_ms << ',' << per_tf << ',' << ck << ','
             << (chk.ran ? chk.err_a : -1.0) << ',' << (chk.err_b >= 0.0 ? chk.err_b : -1.0)
             << '\n';
    }

    if(ENABLE_TIMING)
        std::cout << func << " N=" << N << " batch=" << batch << " iters=" << iters
                  << " plan_ms=" << plan_ms << " first_ms=" << first_ms
                  << " min_ms=" << T.min_ms << " mean_ms=" << T.mean_ms
                  << " max_ms=" << T.max_ms << " per_tf_ms=" << per_tf
                  << " spread=" << (T.min_ms > 0.0 ? (T.max_ms - T.min_ms) / T.min_ms : 0.0)
                  << " check=" << ck << " err_a=" << errstr
                  << " err_b=" << (chk.err_b >= 0.0 ? chk.err_b : -1.0) << '\n';
    return chk.ran && !chk.pass ? 2 : 0;
}
