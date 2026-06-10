#include<bits/stdc++.h>
#include <omp.h>
#define int long long

using namespace std;

const int N = 4e6 + 10;
const int inf = 1e18;
const double pi = acos(-1.0);
complex<double> a[N],b[N],c[N],tmp[N];
int n,m;

void fft_radix_mixed(complex<double> *a,int lim,int tp) {
    auto in = a;
    auto out = tmp;
    int mid = 1;

    int L = __builtin_ctz(lim);

    if(L % 3 == 1) {
        int q = lim / 2;
        #pragma omp parallel for
        for(int j = 0;j < lim;j += 2) {
            int now = j / 2;

            complex<double> x = in[now];
            complex<double> y = in[now + q];

            out[j] = x + y;
            out[j + 1] = x - y;
        }
        mid *= 2;
        swap(in,out);
    }
    
    else if(L % 3 == 2) {
        int q = lim / 4;
        #pragma omp parallel for
        for(int j = 0; j < lim; j += 4) {
            int now = j / 4;
            complex<double> A = in[now];
            complex<double> B = in[now + q];
            complex<double> C = in[now + 2 * q];
            complex<double> D = in[now + 3 * q];
            
            complex<double> E = A + C;
            complex<double> F = A - C;
            complex<double> G = B + D;
            complex<double> H = B - D;
            complex<double> iH(-tp * H.imag(), tp * H.real());
            
            out[j]     = E + G;
            out[j + 1] = F + iH;
            out[j + 2] = E - G;
            out[j + 3] = F - iH;
        }
        mid *= 4;
        swap(in, out);
    }
    
    int q = lim / 8;
    const double SQRT2_2 = sqrtl(2) / 2;
    for(;mid < lim;mid <<= 3) {
        int len = mid * 8;
        complex<double> wn = {cos(2 * pi / len),tp * sin(2 * pi / len)};
        
        int step = 8 * mid; 
        
        #pragma omp parallel for
        for(int j = 0;j < lim;j += step) {
            complex<double> w1(1.0,0.0);
            complex<double> w2(1.0,0.0);
            complex<double> w3(1.0,0.0);
            complex<double> w4(1.0,0.0);
            complex<double> w5(1.0,0.0);
            complex<double> w6(1.0,0.0);
            complex<double> w7(1.0,0.0);
            for(int k = 0;k < mid;k++) {
                int now = j / 8 + k;

                complex<double> I0 = in[now];
                complex<double> I1 = w1 * in[now + q];
                complex<double> I2 = w2 * in[now + 2 * q];
                complex<double> I3 = w3 * in[now + 3 * q];
                complex<double> I4 = w4 * in[now + 4 * q];
                complex<double> I5 = w5 * in[now + 5 * q];
                complex<double> I6 = w6 * in[now + 6 * q];
                complex<double> I7 = w7 * in[now + 7 * q];

                complex<double> EE0 = I0 + I4, EE1 = I0 - I4;
                complex<double> EO0 = I2 + I6, EO1 = I2 - I6;
                complex<double> OE0 = I1 + I5, OE1 = I1 - I5;
                complex<double> OO0 = I3 + I7, OO1 = I3 - I7;

                complex<double> iEO1(-tp * EO1.imag(), tp * EO1.real());
                complex<double> iOO1(-tp * OO1.imag(), tp * OO1.real());
                complex<double> E0 = EE0 + EO0;
                complex<double> E1 = EE1 + iEO1; 
                complex<double> E2 = EE0 - EO0;
                complex<double> E3 = EE1 - iEO1;
                complex<double> O0 = OE0 + OO0;
                complex<double> O1 = OE1 + iOO1;
                complex<double> O2 = OE0 - OO0;
                complex<double> O3 = OE1 - iOO1;

                complex<double> W8_1(SQRT2_2, tp * SQRT2_2);
                complex<double> W8_3(-SQRT2_2, tp * SQRT2_2);
                complex<double> O0_w = O0;
                complex<double> O1_w = O1 * W8_1;

                complex<double> O2_w(-tp * O2.imag(), tp * O2.real()); 
                complex<double> O3_w = O3 * W8_3;

                out[j + k]             = E0 + O0_w;
                out[j + k + mid]       = E1 + O1_w;
                out[j + k + 2 * mid]   = E2 + O2_w;
                out[j + k + 3 * mid]   = E3 + O3_w;
                out[j + k + 4 * mid]   = E0 - O0_w;
                out[j + k + 5 * mid]   = E1 - O1_w;
                out[j + k + 6 * mid]   = E2 - O2_w;
                out[j + k + 7 * mid]   = E3 - O3_w;

                w1 = w1 * wn;
                w2 = w1 * w1;
                w3 = w2 * w1;
                w4 = w2 * w2;
                w5 = w4 * w1;
                w6 = w4 * w2;
                w7 = w6 * w1;
            }
        }
        swap(in,out);
    } 
    
    if(in != a) {
        #pragma omp parallel for
        for(int i = 0;i < lim;i++) a[i] = in[i];
    }
}

signed main() {
    ios::sync_with_stdio(0);
    cin.tie(0);cout.tie(0);

    cin >> n >> m;
    for(int i = 0;i <= n;i++) {
        double u;
        cin >> u;
        a[i] = {u,0.0};
    }
    for(int i = 0;i <= m;i++) {
        double u;
        cin >> u;
        b[i] = {u,0.0};
    }
    
    int l = 32 - __builtin_clz(n + m);
    int lim = 1ll << l;
    
    fft_radix_mixed(a,lim,1);
    fft_radix_mixed(b,lim,1);
    
    #pragma omp parallel for
    for(int i = 0;i < lim;i++) c[i] = a[i] * b[i];
    
    fft_radix_mixed(c,lim,-1);
    
    for(int i = 0;i <= n + m;i++) cout << (int)(c[i].real() / lim + 0.5) << ' ';
    
    return 0;
}