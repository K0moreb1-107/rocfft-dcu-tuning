#include<bits/stdc++.h>
#include <hip/hip_runtime.h>
#define int long long

using namespace std;

const int N = 4e6 + 10;
const int inf = 1e18;
const double pi = acos(-1.0);

__global__ void radix2_kernel(hipfftDoubleComplex *in, hipfftDoubleComplex *out, int lim, int q) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if(tid >= lim / 2) return;
    int j = tid * 2; int now = tid;
    hipfftDoubleComplex x = in[now]; hipfftDoubleComplex y = in[now + q];
    out[j].x = x.x + y.x; out[j].y = x.y + y.y;
    out[j + 1].x = x.x - y.x; out[j + 1].y = x.y - y.y;
}

__global__ void radix4_kernel(hipfftDoubleComplex *in, hipfftDoubleComplex *out, int lim, int q, int tp) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if(tid >= lim / 4) return;
    int j = tid * 4; int now = tid; 
    hipfftDoubleComplex A = in[now], B = in[now + q], C = in[now + 2 * q], D = in[now + 3 * q];
    hipfftDoubleComplex E = {A.x + C.x, A.y + C.y}, F = {A.x - C.x, A.y - C.y};
    hipfftDoubleComplex G = {B.x + D.x, B.y + D.y}, H = {B.x - D.x, B.y - D.y};
    hipfftDoubleComplex iH = {-tp * H.y, tp * H.x};
    out[j].x = E.x + G.x; out[j].y = E.y + G.y;
    out[j + 1].x = F.x + iH.x; out[j + 1].y = F.y + iH.y;
    out[j + 2].x = E.x - G.x; out[j + 2].y = E.y - G.y;
    out[j + 3].x = F.x - iH.x; out[j + 3].y = F.y - iH.y;
}

__global__ void radix8_kernel(hipfftDoubleComplex *in, hipfftDoubleComplex *out, int lim, int q, int mid, int tp) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if(tid >= lim / 8) return;
    int j = (tid / mid) * 8 * mid; int k = tid % mid; int now = tid;
    double angle = 2.0 * 3.14159265358979323846 * k / (mid * 8);
    hipfftDoubleComplex w1 = {cos(angle), tp * sin(angle)};
    hipfftDoubleComplex w2 = {cos(2*angle), tp * sin(2*angle)};
    hipfftDoubleComplex w3 = {cos(3*angle), tp * sin(3*angle)};
    hipfftDoubleComplex w4 = {cos(4*angle), tp * sin(4*angle)};
    hipfftDoubleComplex w5 = {cos(5*angle), tp * sin(5*angle)};
    hipfftDoubleComplex w6 = {cos(6*angle), tp * sin(6*angle)};
    hipfftDoubleComplex w7 = {cos(7*angle), tp * sin(7*angle)};

    hipfftDoubleComplex I0 = in[now];
    hipfftDoubleComplex t1 = in[now + q];   hipfftDoubleComplex I1 = {w1.x*t1.x - w1.y*t1.y, w1.x*t1.y + w1.y*t1.x};
    hipfftDoubleComplex t2 = in[now + 2*q]; hipfftDoubleComplex I2 = {w2.x*t2.x - w2.y*t2.y, w2.x*t2.y + w2.y*t2.x};
    hipfftDoubleComplex t3 = in[now + 3*q]; hipfftDoubleComplex I3 = {w3.x*t3.x - w3.y*t3.y, w3.x*t3.y + w3.y*t3.x};
    hipfftDoubleComplex t4 = in[now + 4*q]; hipfftDoubleComplex I4 = {w4.x*t4.x - w4.y*t4.y, w4.x*t4.y + w4.y*t4.x};
    hipfftDoubleComplex t5 = in[now + 5*q]; hipfftDoubleComplex I5 = {w5.x*t5.x - w5.y*t5.y, w5.x*t5.y + w5.y*t5.x};
    hipfftDoubleComplex t6 = in[now + 6*q]; hipfftDoubleComplex I6 = {w6.x*t6.x - w6.y*t6.y, w6.x*t6.y + w6.y*t6.x};
    hipfftDoubleComplex t7 = in[now + 7*q]; hipfftDoubleComplex I7 = {w7.x*t7.x - w7.y*t7.y, w7.x*t7.y + w7.y*t7.x};

    hipfftDoubleComplex EE0 = {I0.x + I4.x, I0.y + I4.y}; hipfftDoubleComplex EE1 = {I0.x - I4.x, I0.y - I4.y};
    hipfftDoubleComplex EO0 = {I2.x + I6.x, I2.y + I6.y}; hipfftDoubleComplex EO1 = {I2.x - I6.x, I2.y - I6.y};
    hipfftDoubleComplex OE0 = {I1.x + I5.x, I1.y + I5.y}; hipfftDoubleComplex OE1 = {I1.x - I5.x, I1.y - I5.y};
    hipfftDoubleComplex OO0 = {I3.x + I7.x, I3.y + I7.y}; hipfftDoubleComplex OO1 = {I3.x - I7.x, I3.y - I7.y};

    hipfftDoubleComplex iEO1 = {-tp * EO1.y, tp * EO1.x};
    hipfftDoubleComplex iOO1 = {-tp * OO1.y, tp * OO1.x};

    hipfftDoubleComplex E0 = {EE0.x + EO0.x, EE0.y + EO0.y}; hipfftDoubleComplex E1 = {EE1.x + iEO1.x, EE1.y + iEO1.y};
    hipfftDoubleComplex E2 = {EE0.x - EO0.x, EE0.y - EO0.y}; hipfftDoubleComplex E3 = {EE1.x - iEO1.x, EE1.y - iEO1.y};
    hipfftDoubleComplex O0 = {OE0.x + OO0.x, OE0.y + OO0.y}; hipfftDoubleComplex O1 = {OE1.x + iOO1.x, OE1.y + iOO1.y};
    hipfftDoubleComplex O2 = {OE0.x - OO0.x, OE0.y - OO0.y}; hipfftDoubleComplex O3 = {OE1.x - iOO1.x, OE1.y - iOO1.y};

    double SQRT2_2 = 0.70710678118654752440;
    hipfftDoubleComplex W8_1 = {SQRT2_2, tp * SQRT2_2}; hipfftDoubleComplex W8_3 = {-SQRT2_2, tp * SQRT2_2};

    hipfftDoubleComplex O0_w = O0;
    hipfftDoubleComplex O1_w = {O1.x*W8_1.x - O1.y*W8_1.y, O1.x*W8_1.y + O1.y*W8_1.x};
    hipfftDoubleComplex O2_w = {-tp * O2.y, tp * O2.x};
    hipfftDoubleComplex O3_w = {O3.x*W8_3.x - O3.y*W8_3.y, O3.x*W8_3.y + O3.y*W8_3.x};

    out[j + k].x           = E0.x + O0_w.x; out[j + k].y           = E0.y + O0_w.y;
    out[j + k + mid].x     = E1.x + O1_w.x; out[j + k + mid].y     = E1.y + O1_w.y;
    out[j + k + 2*mid].x   = E2.x + O2_w.x; out[j + k + 2*mid].y   = E2.y + O2_w.y;
    out[j + k + 3*mid].x   = E3.x + O3_w.x; out[j + k + 3*mid].y   = E3.y + O3_w.y;
    out[j + k + 4*mid].x   = E0.x - O0_w.x; out[j + k + 4*mid].y   = E0.y - O0_w.y;
    out[j + k + 5*mid].x   = E1.x - O1_w.x; out[j + k + 5*mid].y   = E1.y - O1_w.y;
    out[j + k + 6*mid].x   = E2.x - O2_w.x; out[j + k + 6*mid].y   = E2.y - O2_w.y;
    out[j + k + 7*mid].x   = E3.x - O3_w.x; out[j + k + 7*mid].y   = E3.y - O3_w.y;
}

__global__ void pointwise_mul_kernel(hipfftDoubleComplex *a, hipfftDoubleComplex *b, hipfftDoubleComplex *c, int lim) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= lim) return;
    hipfftDoubleComplex A = a[tid], B = b[tid];
    c[tid].x = A.x * B.x - A.y * B.y;
    c[tid].y = A.x * B.y + A.y * B.x;
}

void hip_fft_radix_mixed(hipfftDoubleComplex *d_data, hipfftDoubleComplex *d_tmp, int lim, int tp) {
    hipfftDoubleComplex *d_in = d_data;
    hipfftDoubleComplex *d_out = d_tmp;
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
        hipMemcpy(d_data, d_in, lim * sizeof(hipfftDoubleComplex), hipMemcpyDeviceToDevice);
    }
}

signed main() {
    ios::sync_with_stdio(0);
    cin.tie(0);cout.tie(0);

    int n,m;
    cin >> n >> m;
    
    int l = 32 - __builtin_clz(n + m);
    int lim = 1ll << l;

    vector<double2> h_a(lim, {0.0, 0.0});
    vector<double2> h_b(lim, {0.0, 0.0});

    for(int i = 0; i <= n; i++) { double u; cin >> u; h_a[i].x = u; }
    for(int i = 0; i <= m; i++) { double u; cin >> u; h_b[i].x = u; }
    
    double2 *d_a, *d_b, *d_c, *d_tmp;
    hipMalloc(&d_a, lim * sizeof(double2));
    hipMalloc(&d_b, lim * sizeof(double2));
    hipMalloc(&d_c, lim * sizeof(double2));
    hipMalloc(&d_tmp, lim * sizeof(double2));
    
    hipMemcpy(d_a, h_a.data(), lim * sizeof(double2), hipMemcpyHostToDevice);
    hipMemcpy(d_b, h_b.data(), lim * sizeof(double2), hipMemcpyHostToDevice);
    
    hip_fft_radix_mixed(d_a, d_tmp, lim, -1);
    hip_fft_radix_mixed(d_b, d_tmp, lim, -1);
    
    int blocks = (lim + 255) / 256;
    hipLaunchKernelGGL(pointwise_mul_kernel, dim3(blocks), dim3(256), 0, 0, d_a, d_b, d_c, lim);
    
    hip_fft_radix_mixed(d_c, d_tmp, lim, 1);
    
    vector<double2> h_c(lim);
    hipMemcpy(h_c.data(), d_c, lim * sizeof(double2), hipMemcpyDeviceToHost);
    
    for(int i = 0; i <= n + m; i++) {
        long long ans = (long long)(h_c[i].x / lim + 0.5);
        cout << ans << " ";
    }
    cout << "\n";
    
    hipFree(d_a); hipFree(d_b); hipFree(d_c); hipFree(d_tmp);
    
    return 0;
}