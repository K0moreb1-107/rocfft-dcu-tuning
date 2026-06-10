#include<bits/stdc++.h>
#include <omp.h>
#include <chrono>
#include <stockham_fft.h>

#define int long long

using namespace std;

const int N = 3e7 + 10;
complex<double> a[N], b[N], c[N];

// 供串行测试用的包装函数
void run_pure_serial_benchmark(int lim) {
    mt19937 rng(42); 
    uniform_real_distribution<double> dist(0.0, 100.0);
    for(int i = 0; i < lim; i++) {
        a[i] = {dist(rng), 0.0};
        b[i] = {dist(rng), 0.0};
        c[i] = {0.0, 0.0};
        tmp[i] = {0.0, 0.0};
    }

    auto start_time = chrono::high_resolution_clock::now();

    fft_radix_mixed_serial(a, lim, 1);
    fft_radix_mixed_serial(b, lim, 1);
    for(int i = 0; i < lim; i++) c[i] = a[i] * b[i];
    fft_radix_mixed_serial(c, lim, -1);
    double check_sum = c[0].real() + c[lim-1].real(); 

    auto end_time = chrono::high_resolution_clock::now();
    auto duration = chrono::duration_cast<chrono::milliseconds>(end_time - start_time).count();

    cout << "纯串行 | Length: " << lim 
         << " | Time: " << setw(4) << duration << " ms" 
         << "  (check: " << check_sum << ")" << endl;
}

// 供并行测试用的包装函数
void run_parallel_benchmark(int num_threads, int lim) {
    omp_set_num_threads(num_threads);
    mt19937 rng(42); 
    uniform_real_distribution<double> dist(0.0, 100.0);
    for(int i = 0; i < lim; i++) {
        a[i] = {dist(rng), 0.0};
        b[i] = {dist(rng), 0.0};
        c[i] = {0.0, 0.0};
        tmp[i] = {0.0, 0.0};
    }

    auto start_time = chrono::high_resolution_clock::now();

    fft_radix_mixed_parallel(a, lim, 1);
    fft_radix_mixed_parallel(b, lim, 1);
    #pragma omp parallel for
    for(int i = 0; i < lim; i++) c[i] = a[i] * b[i];
    fft_radix_mixed_parallel(c, lim, -1);
    double check_sum = c[0].real() + c[lim-1].real(); 

    auto end_time = chrono::high_resolution_clock::now();
    auto duration = chrono::duration_cast<chrono::milliseconds>(end_time - start_time).count();

    cout << "OMP 并行版本 (" << setw(2) << num_threads << " 线程) | Length: " << lim 
         << " | Time: " << setw(4) << duration << " ms" 
         << "  (check: " << check_sum << ")" << endl;
}

signed main() {
    int max_lim = 1ll << 24; 
    
    int max_threads = omp_get_max_threads();
    cout << "Max System Threads: " << max_threads << "\n";
    cout << "------------------------------------------\n";

    cout << "=== 1. 串行测试 ===" << endl;
    run_pure_serial_benchmark(max_lim); // 预热
    run_pure_serial_benchmark(max_lim); // 正式测量
    
    cout << "------------------------------------------\n";

    cout << "=== 2. 并行测试 ===" << endl;
    run_parallel_benchmark(1, max_lim); 
    run_parallel_benchmark(2, max_lim);
    run_parallel_benchmark(4, max_lim);
    run_parallel_benchmark(8, max_lim);
    run_parallel_benchmark(16, max_lim);
    run_parallel_benchmark(max_threads, max_lim);

    return 0;
}
