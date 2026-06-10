#pragma once

#include<vector>
#include<complex>

namespace stockham {
    enum class Direction {
        FORWARD = 1,
        BACKWARD = -1
    }

    class FFTPlan {
    private:
        int lim,tp;
        std::vector<std::complex<double> > tmp_buffer;
        const double pi;
    
    public:
        FFTPlan(int length,Direction dir);

        ~FFTPlan() = default;

        void FFT(std::complex<double> *data);

        void MUL(std::complex<double> *a,std::complex<double> *b);
    };
}

template<typename T>
std::vector<long long> fftexec(const std::vector<T>& a,const std::vector<T>& b);