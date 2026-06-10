#include<stockham_fft.h>
#include<algorithm>
#include<cmath>

#ifdef _OPENMP
#include<omp.h>
#endif

namespace stockham {
    FFTPlan::FFTPlan(int length, Direction dir) 
        : lim(length), tp(static_cast<int>(dir)), pi(std::acos(-1.0)) {
        tmp_buffer.resize(lim);
    }

    void FFTPlan::FFT(std::complex<double>* data) {
        auto in = data;
        auto out = tmp_buffer.data();
        int mid = 1;

        int L = __builtin_ctz(lim);

        if(L % 3 == 1) {
            int q = lim / 2;
            #pragma omp parallel for
            for(int j = 0; j < lim; j += 2) {
                int now = j / 2;
                std::complex<double> x = in[now];
                std::complex<double> y = in[now + q];
                out[j] = x + y;
                out[j + 1] = x - y;
            }
            mid *= 2;
            std::swap(in, out);
        }

        else if(L % 3 == 2) {
            int q = lim / 4;
            #pragma omp parallel for
            for(int j = 0; j < lim; j += 4) {
                int now = j / 4;
                std::complex<double> A = in[now];
                std::complex<double> B = in[now + q];
                std::complex<double> C = in[now + 2 * q];
                std::complex<double> D = in[now + 3 * q];
                
                std::complex<double> E = A + C;
                std::complex<double> F = A - C;
                std::complex<double> G = B + D;
                std::complex<double> H = B - D;
                std::complex<double> iH(-tp * H.imag(), tp * H.real());
                
                out[j]     = E + G;
                out[j + 1] = F + iH;
                out[j + 2] = E - G;
                out[j + 3] = F - iH;
            }
            mid *= 4;
            std::swap(in, out);
        }
        
        int q = lim / 8;
        const double SQRT2_2 = sqrtl(2) / 2;
        for(; mid < lim; mid <<= 3) {
            int len = mid * 8;
            std::complex<double> wn = {std::cos(2 * pi / len), tp * std::sin(2 * pi / len)};
            int step = 8 * mid; 
            
            #pragma omp parallel for
            for(int j = 0; j < lim; j += step) {
                std::complex<double> w1(1.0, 0.0), w2(1.0, 0.0), w3(1.0, 0.0);
                std::complex<double> w4(1.0, 0.0), w5(1.0, 0.0), w6(1.0, 0.0), w7(1.0, 0.0);
                for(int k = 0; k < mid; k++) {
                    int now = j / 8 + k;

                    std::complex<double> I0 = in[now];
                    std::complex<double> I1 = w1 * in[now + q];
                    std::complex<double> I2 = w2 * in[now + 2 * q];
                    std::complex<double> I3 = w3 * in[now + 3 * q];
                    std::complex<double> I4 = w4 * in[now + 4 * q];
                    std::complex<double> I5 = w5 * in[now + 5 * q];
                    std::complex<double> I6 = w6 * in[now + 6 * q];
                    std::complex<double> I7 = w7 * in[now + 7 * q];

                    std::complex<double> EE0 = I0 + I4, EE1 = I0 - I4;
                    std::complex<double> EO0 = I2 + I6, EO1 = I2 - I6;
                    std::complex<double> OE0 = I1 + I5, OE1 = I1 - I5;
                    std::complex<double> OO0 = I3 + I7, OO1 = I3 - I7;

                    std::complex<double> iEO1(-tp * EO1.imag(), tp * EO1.real());
                    std::complex<double> iOO1(-tp * OO1.imag(), tp * OO1.real());
                    std::complex<double> E0 = EE0 + EO0;
                    std::complex<double> E1 = EE1 + iEO1; 
                    std::complex<double> E2 = EE0 - EO0;
                    std::complex<double> E3 = EE1 - iEO1;
                    std::complex<double> O0 = OE0 + OO0;
                    std::complex<double> O1 = OE1 + iOO1;
                    std::complex<double> O2 = OE0 - OO0;
                    std::complex<double> O3 = OE1 - iOO1;

                    std::complex<double> W8_1(SQRT2_2, tp * SQRT2_2);
                    std::complex<double> W8_3(-SQRT2_2, tp * SQRT2_2);
                    std::complex<double> O0_w = O0;
                    std::complex<double> O1_w = O1 * W8_1;

                    std::complex<double> O2_w(-tp * O2.imag(), tp * O2.real()); 
                    std::complex<double> O3_w = O3 * W8_3;

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
            std::swap(in, out);
        } 
        
        if(in != data) {
            #pragma omp parallel for
            for(int i = 0; i < lim; i++) data[i] = in[i];
        }
    }
}

template<typename T>
std::vector<long long> fftexec(const std::vector<T>& a,const std::vector<T>& b) {
    int n = a.size() - 1;
    int m = b.size() - 1;
    
}