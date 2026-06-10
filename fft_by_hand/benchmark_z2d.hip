#include <hip/hip_runtime.h>
#include <hipfft.h>
#include <iostream>
#include <vector>
#include <cmath>
#include <iomanip>

#define int long long
using namespace std;

const double pi = acos(-1.0);

// ==========================================
// 1. 底层 Z2Z FFT Kernel
// ==========================================
__global__ void radix2_kernel(double2 *in, double2 *out, int lim, int q) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if(tid >= lim / 2) return;
    int j = tid * 2; int now = tid;
    double2 x = in[now]; double2 y = in[now + q];
    out[j].x = x.x + y.x; out[j].y = x.y + y.y;
    out[j + 1].x = x.x - y.x; out[j + 1].y = x.y - y.y;
}

__global__ void radix4_kernel(double2 *in, double2 *out, int lim, int q, int tp) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if(tid >= lim / 4) return;
    int j = tid * 4; int now = tid; 
    double2 A = in[now], B = in[now + q], C = in[now + 2 * q], D = in[now + 3 * q];
    double2 E = {A.x + C.x, A.y + C.y}, F = {A.x - C.x, A.y - C.y};
    double2 G = {B.x + D.x, B.y + D.y}, H = {B.x - D.x, B.y - D.y};
    double2 iH = {-tp * H.y, tp * H.x};
    out[j].x = E.x + G.x; out[j].y = E.y + G.y;
    out[j + 1].x = F.x + iH.x; out[j + 1].y = F.y + iH.y;
    out[j + 2].x = E.x - G.x; out[j + 2].y = E.y - G.y;
    out[j + 3].x = F.x - iH.x; out[j + 3].y = F.y - iH.y;
}

__global__ void radix8_kernel(double2 *in, double2 *out, int lim, int q, int mid, int tp) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if(tid >= lim / 8) return;
    int j = (tid / mid) * 8 * mid; int k = tid % mid; int now = tid;
    double angle = 2.0 * 3.14159265358979323846 * k / (mid * 8);
    double2 w1 = {cos(angle), tp * sin(angle)};
    double2 w2 = {cos(2*angle), tp * sin(2*angle)};
    double2 w3 = {cos(3*angle), tp * sin(3*angle)};
    double2 w4 = {cos(4*angle), tp * sin(4*angle)};
    double2 w5 = {cos(5*angle), tp * sin(5*angle)};
    double2 w6 = {cos(6*angle), tp * sin(6*angle)};
    double2 w7 = {cos(7*angle), tp * sin(7*angle)};

    double2 I0 = in[now];
    double2 t1 = in[now + q];   double2 I1 = {w1.x*t1.x - w1.y*t1.y, w1.x*t1.y + w1.y*t1.x};
    double2 t2 = in[now + 2*q]; double2 I2 = {w2.x*t2.x - w2.y*t2.y, w2.x*t2.y + w2.y*t2.x};
    double2 t3 = in[now + 3*q]; double2 I3 = {w3.x*t3.x - w3.y*t3.y, w3.x*t3.y + w3.y*t3.x};
    double2 t4 = in[now + 4*q]; double2 I4 = {w4.x*t4.x - w4.y*t4.y, w4.x*t4.y + w4.y*t4.x};
    double2 t5 = in[now + 5*q]; double2 I5 = {w5.x*t5.x - w5.y*t5.y, w5.x*t5.y + w5.y*t5.x};
    double2 t6 = in[now + 6*q]; double2 I6 = {w6.x*t6.x - w6.y*t6.y, w6.x*t6.y + w6.y*t6.x};
    double2 t7 = in[now + 7*q]; double2 I7 = {w7.x*t7.x - w7.y*t7.y, w7.x*t7.y + w7.y*t7.x};

    double2 EE0 = {I0.x + I4.x, I0.y + I4.y}; double2 EE1 = {I0.x - I4.x, I0.y - I4.y};
    double2 EO0 = {I2.x + I6.x, I2.y + I6.y}; double2 EO1 = {I2.x - I6.x, I2.y - I6.y};
    double2 OE0 = {I1.x + I5.x, I1.y + I5.y}; double2 OE1 = {I1.x - I5.x, I1.y - I5.y};
    double2 OO0 = {I3.x + I7.x, I3.y + I7.y}; double2 OO1 = {I3.x - I7.x, I3.y - I7.y};

    double2 iEO1 = {-tp * EO1.y, tp * EO1.x};
    double2 iOO1 = {-tp * OO1.y, tp * OO1.x};

    double2 E0 = {EE0.x + EO0.x, EE0.y + EO0.y}; double2 E1 = {EE1.x + iEO1.x, EE1.y + iEO1.y};
    double2 E2 = {EE0.x - EO0.x, EE0.y - EO0.y}; double2 E3 = {EE1.x - iEO1.x, EE1.y - iEO1.y};
    double2 O0 = {OE0.x + OO0.x, OE0.y + OO0.y}; double2 O1 = {OE1.x + iOO1.x, OE1.y + iOO1.y};
    double2 O2 = {OE0.x - OO0.x, OE0.y - OO0.y}; double2 O3 = {OE1.x - iOO1.x, OE1.y - iOO1.y};

    double SQRT2_2 = 0.70710678118654752440;
    double2 W8_1 = {SQRT2_2, tp * SQRT2_2}; double2 W8_3 = {-SQRT2_2, tp * SQRT2_2};

    double2 O0_w = O0;
    double2 O1_w = {O1.x*W8_1.x - O1.y*W8_1.y, O1.x*W8_1.y + O1.y*W8_1.x};
    double2 O2_w = {-tp * O2.y, tp * O2.x};
    double2 O3_w = {O3.x*W8_3.x - O3.y*W8_3.y, O3.x*W8_3.y + O3.y*W8_3.x};

    out[j + k].x           = E0.x + O0_w.x; out[j + k].y           = E0.y + O0_w.y;
    out[j + k + mid].x     = E1.x + O1_w.x; out[j + k + mid].y     = E1.y + O1_w.y;
    out[j + k + 2*mid].x   = E2.x + O2_w.x; out[j + k + 2*mid].y   = E2.y + O2_w.y;
    out[j + k + 3*mid].x   = E3.x + O3_w.x; out[j + k + 3*mid].y   = E3.y + O3_w.y;
    out[j + k + 4*mid].x   = E0.x - O0_w.x; out[j + k + 4*mid].y   = E0.y - O0_w.y;
    out[j + k + 5*mid].x   = E1.x - O1_w.x; out[j + k + 5*mid].y   = E1.y - O1_w.y;
    out[j + k + 6*mid].x   = E2.x - O2_w.x; out[j + k + 6*mid].y   = E2.y - O2_w.y;
    out[j + k + 7*mid].x   = E3.x - O3_w.x; out[j + k + 7*mid].y   = E3.y - O3_w.y;
}

void hip_fft_radix_mixed(double2 *d_data, double2 *d_tmp, int lim, int tp) {
    double2 *d_in = d_data;
    double2 *d_out = d_tmp;
    int mid = 1; int L = __builtin_ctz(lim); int threads = 256;
    if(L % 3 == 1) {
        int q = lim / 2; int blocks = (lim/2 + threads - 1) / threads;
        radix2_kernel<<<blocks, threads>>>(d_in, d_out, lim, q);
        mid *= 2; swap(d_in, d_out);
    } else if(L % 3 == 2) {
        int q = lim / 4; int blocks = (lim/4 + threads - 1) / threads;
        radix4_kernel<<<blocks, threads>>>(d_in, d_out, lim, q, tp);
        mid *= 4; swap(d_in, d_out);
    }
    int q = lim / 8;
    for(; mid < lim; mid <<= 3) {
        int blocks = (lim/8 + threads - 1) / threads;
        radix8_kernel<<<blocks, threads>>>(d_in, d_out, lim, q, mid, tp);
        swap(d_in, d_out);
    } 
    if(d_in != d_data) {
        hipMemcpy(d_data, d_in, lim * sizeof(double2), hipMemcpyDeviceToDevice);
    }
}

// ==========================================
// D2Z 后处理解包 Kernel 
// ==========================================
__global__ void d2z_postprocess_kernel(double2 *F, double2 *X, int N) {
    int k = blockIdx.x * blockDim.x + threadIdx.x;
    int half_N = N / 2;
    if (k > half_N) return;
    if (k == 0) {
        X[0].x = F[0].x + F[0].y;
        X[0].y = 0.0;
    } else if (k == half_N) {
        X[half_N].x = F[0].x - F[0].y;
        X[half_N].y = 0.0;
    } else {
        double2 fk = F[k]; double2 fnk = F[half_N - k];
        double A_x = 0.5 * (fk.x + fnk.x); double A_y = 0.5 * (fk.y - fnk.y);
        double B_x = 0.5 * (fk.y + fnk.y); double B_y = -0.5 * (fk.x - fnk.x);
        double angle = -2.0 * 3.14159265358979323846 * k / N;
        double W_x = cos(angle), W_y = sin(angle);
        X[k].x = A_x + (B_x * W_x - B_y * W_y);
        X[k].y = A_y + (B_x * W_y + B_y * W_x);
    }
}

// ==========================================
// Z2D 预处理打包 Kernel
// ==========================================
__global__ void z2d_preprocess_kernel(double2 *X, double2 *F, int N) {
    int k = blockIdx.x * blockDim.x + threadIdx.x;
    int half_N = N / 2;
    if (k >= half_N) return;
    if (k == 0) {
        F[0].x = 0.5 * (X[0].x + X[half_N].x); 
        F[0].y = 0.5 * (X[0].x - X[half_N].x);
    } else {
        double2 xk = X[k]; double2 xnk = X[half_N - k];
        double A_x = 0.5 * (xk.x + xnk.x); double A_y = 0.5 * (xk.y - xnk.y);
        double B_x = -0.5 * (xk.y + xnk.y); double B_y = 0.5 * (xk.x - xnk.x);
        double angle = 2.0 * 3.14159265358979323846 * k / N;
        double W_x = cos(angle), W_y = sin(angle);
        F[k].x = A_x + (B_x * W_x - B_y * W_y);
        F[k].y = A_y + (B_x * W_y + B_y * W_x);
    }
}

// ==========================================
// 点乘 Kernel (通用)
// ==========================================
__global__ void pointwise_mul_kernel(hipfftDoubleComplex *a, hipfftDoubleComplex *b, hipfftDoubleComplex *c, int len) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= len) return; 
    hipfftDoubleComplex A = a[tid], B = b[tid];
    c[tid].x = A.x * B.x - A.y * B.y;
    c[tid].y = A.x * B.y + A.y * B.x;
}


signed main() {
    int N_real = 1ll << 24; // 2^21 = 2,097,152
    int half_N = N_real / 2;
    int max_complex_len = half_N + 1;
    
    cout << "================================================" << endl;
    cout << "  GPU D2Z/Z2D Benchmark: Custom vs hipFFT       " << endl;
    cout << "  Data Length (N): " << N_real << " (2^21)" << endl;
    cout << "================================================" << endl;

    vector<double> h_a(N_real);
    vector<double> h_b(N_real);
    for(int i = 0; i < N_real; i++) {
        h_a[i] = (rand() % 1000) / 10.0;
        h_b[i] = (rand() % 1000) / 10.0;
    }

    void *d_mem_a, *d_mem_b, *d_mem_c, *d_mem_tmp;
    hipMalloc(&d_mem_a, max_complex_len * sizeof(double2));
    hipMalloc(&d_mem_b, max_complex_len * sizeof(double2));
    hipMalloc(&d_mem_c, max_complex_len * sizeof(double2));
    hipMalloc(&d_mem_tmp, max_complex_len * sizeof(double2));
    
    hipEvent_t start, stop;
    hipEventCreate(&start); hipEventCreate(&stop);
    float time_custom = 0.0, time_hipfft = 0.0;
    
    // ===================================
    // 赛道一：Custom D2Z/Z2D
    // ===================================
    cout << "\n[Custom D2Z/Z2D] Warm-up..." << endl;
    
    hipMemcpy(d_mem_a, h_a.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    hipMemcpy(d_mem_b, h_b.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    
    double2 *custom_a = (double2*)d_mem_a;
    double2 *custom_b = (double2*)d_mem_b;
    double2 *custom_c = (double2*)d_mem_c;
    double2 *custom_tmp = (double2*)d_mem_tmp;
    
    int blocks_post = (half_N + 1 + 255) / 256;
    int blocks_pre = (half_N + 255) / 256;
    
    // Warm up
    hip_fft_radix_mixed(custom_a, custom_tmp, half_N, -1);
    hipMemcpy(custom_tmp, custom_a, half_N * sizeof(double2), hipMemcpyDeviceToDevice);
    d2z_postprocess_kernel<<<blocks_post, 256>>>(custom_tmp, custom_a, N_real);
    
    cout << "[Custom D2Z/Z2D] Running benchmark..." << endl;
    
    hipMemcpy(d_mem_a, h_a.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    hipMemcpy(d_mem_b, h_b.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    hipDeviceSynchronize();
    
    hipEventRecord(start);
    
    // D2Z A
    hip_fft_radix_mixed(custom_a, custom_tmp, half_N, -1);
    hipMemcpy(custom_tmp, custom_a, half_N * sizeof(double2), hipMemcpyDeviceToDevice);
    d2z_postprocess_kernel<<<blocks_post, 256>>>(custom_tmp, custom_a, N_real);
    
    // D2Z B
    hip_fft_radix_mixed(custom_b, custom_tmp, half_N, -1);
    hipMemcpy(custom_tmp, custom_b, half_N * sizeof(double2), hipMemcpyDeviceToDevice);
    d2z_postprocess_kernel<<<blocks_post, 256>>>(custom_tmp, custom_b, N_real);
    
    // Pointwise Multiply
    pointwise_mul_kernel<<<blocks_post, 256>>>((hipfftDoubleComplex*)custom_a, (hipfftDoubleComplex*)custom_b, (hipfftDoubleComplex*)custom_c, max_complex_len);
    
    // Z2D C
    z2d_preprocess_kernel<<<blocks_pre, 256>>>(custom_c, custom_a, N_real);
    hip_fft_radix_mixed(custom_a, custom_tmp, half_N, 1);
    
    hipEventRecord(stop);
    hipEventSynchronize(stop);
    hipEventElapsedTime(&time_custom, start, stop);
    
    // 内存地址是完全对齐的，直接以 double 方式把 N_real 个元素拷回
    vector<double> ans_custom(N_real);
    hipMemcpy(ans_custom.data(), custom_a, N_real * sizeof(double), hipMemcpyDeviceToHost);
    
    // ===================================
    // 赛道二：Official hipFFT D2Z/Z2D
    // ===================================
    cout << "\n[hipFFT D2Z/Z2D] Creating plan and Warm-up (RTC compiling)..." << endl;
    hipfftHandle plan_d2z, plan_z2d;
    hipfftPlan1d(&plan_d2z, N_real, HIPFFT_D2Z, 1);
    hipfftPlan1d(&plan_z2d, N_real, HIPFFT_Z2D, 1);
    
    hipfftDoubleReal *official_real_a = (hipfftDoubleReal*)d_mem_a;
    hipfftDoubleReal *official_real_b = (hipfftDoubleReal*)d_mem_b;
    hipfftDoubleReal *official_real_c = (hipfftDoubleReal*)d_mem_tmp; 
    hipfftDoubleComplex *official_comp_a = (hipfftDoubleComplex*)d_mem_a; 
    hipfftDoubleComplex *official_comp_b = (hipfftDoubleComplex*)d_mem_b; 
    hipfftDoubleComplex *official_comp_c = (hipfftDoubleComplex*)d_mem_c; 
    
    // Warm up hipFFT
    hipMemcpy(official_real_a, h_a.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    hipfftExecD2Z(plan_d2z, official_real_a, official_comp_a); 
    
    cout << "[hipFFT D2Z/Z2D] Running benchmark..." << endl;
    hipMemcpy(official_real_a, h_a.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    hipMemcpy(official_real_b, h_b.data(), N_real * sizeof(double), hipMemcpyHostToDevice);
    hipDeviceSynchronize();
    
    hipEventRecord(start);
    
    hipfftExecD2Z(plan_d2z, official_real_a, official_comp_a);
    hipfftExecD2Z(plan_d2z, official_real_b, official_comp_b);
    pointwise_mul_kernel<<<blocks_post, 256>>>(official_comp_a, official_comp_b, official_comp_c, max_complex_len);
    hipfftExecZ2D(plan_z2d, official_comp_c, official_real_c);
    
    hipEventRecord(stop);
    hipEventSynchronize(stop);
    hipEventElapsedTime(&time_hipfft, start, stop);
    
    vector<double> ans_official(N_real);
    hipMemcpy(ans_official.data(), official_real_c, N_real * sizeof(double), hipMemcpyDeviceToHost);
    
    // ===================================
    // 结果比对与输出
    // ===================================
    double max_err = 0.0;
    for(int i = 0; i < N_real; i++) {
        double v_custom = ans_custom[i] / half_N;
        double v_official = ans_official[i] / N_real;
        
        double err = abs(v_custom - v_official);
        if(err > max_err) max_err = err;
    }
    
    cout << "                z2d RESULTS                   " << endl;
    cout << "Data Length (N): " << N_real << endl;
    cout << fixed << setprecision(3);
    cout << "Custom Time : " << time_custom << " ms" << endl;
    cout << "Official hipFFT Time     : " << time_hipfft << " ms" << endl;
    cout << scientific << setprecision(3);
    cout << "Max Absolute Error       : " << max_err << endl;
    
    if(max_err < 1e-3) {
        cout << "Accuracy Check           : PASSED!" << endl;
    } else {
        cout << "Accuracy Check           : FAILED!" << endl;
    }
    cout << "================================================" << endl;

    hipfftDestroy(plan_d2z);
    hipfftDestroy(plan_z2d);
    hipEventDestroy(start);
    hipEventDestroy(stop);
    hipFree(d_mem_a); hipFree(d_mem_b); hipFree(d_mem_c); hipFree(d_mem_tmp);
    return 0;
}
