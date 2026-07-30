#include <hip/hip_runtime.h>
#include <rocfft/rocfft.h>

#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <vector>

struct complex_double
{
    double x;
    double y;
};

static void check_hip(hipError_t status, const char* operation)
{
    if(status != hipSuccess)
    {
        std::cerr << operation << ": " << hipGetErrorString(status) << '\n';
        std::exit(1);
    }
}

static void check_rocfft(rocfft_status status, const char* operation)
{
    if(status != rocfft_status_success)
    {
        std::cerr << operation << " failed with rocFFT status " << status << '\n';
        std::exit(1);
    }
}

int main(int argc, char** argv)
{
    constexpr size_t length = 524288;
    if(argc != 3)
    {
        std::cerr << "usage: validate_rocfft_512k INPUT OUTPUT\n";
        return 2;
    }

    std::vector<complex_double> input(length);
    std::ifstream input_file(argv[1], std::ios::binary);
    input_file.read(reinterpret_cast<char*>(input.data()), input.size() * sizeof(input[0]));
    if(!input_file || input_file.peek() != std::ifstream::traits_type::eof())
    {
        std::cerr << "invalid input file\n";
        return 2;
    }

    complex_double* device_input  = nullptr;
    complex_double* device_output = nullptr;
    const size_t    bytes         = input.size() * sizeof(input[0]);
    check_hip(hipMalloc(&device_input, bytes), "hipMalloc input");
    check_hip(hipMalloc(&device_output, bytes), "hipMalloc output");
    check_hip(hipMemcpy(device_input, input.data(), bytes, hipMemcpyHostToDevice),
              "hipMemcpy input");

    check_rocfft(rocfft_setup(), "rocfft_setup");
    rocfft_plan plan = nullptr;
    check_rocfft(rocfft_plan_create(&plan,
                                    rocfft_placement_notinplace,
                                    rocfft_transform_type_complex_forward,
                                    rocfft_precision_double,
                                    1,
                                    &length,
                                    1,
                                    nullptr),
                 "rocfft_plan_create");

    rocfft_execution_info info = nullptr;
    check_rocfft(rocfft_execution_info_create(&info), "rocfft_execution_info_create");
    void* input_buffers[]  = {device_input};
    void* output_buffers[] = {device_output};
    check_rocfft(rocfft_execute(plan, input_buffers, output_buffers, info), "rocfft_execute");
    check_hip(hipDeviceSynchronize(), "hipDeviceSynchronize");

    std::vector<complex_double> output(length);
    check_hip(hipMemcpy(output.data(), device_output, bytes, hipMemcpyDeviceToHost),
              "hipMemcpy output");
    std::ofstream output_file(argv[2], std::ios::binary);
    output_file.write(reinterpret_cast<const char*>(output.data()), bytes);
    if(!output_file)
    {
        std::cerr << "failed to write output file\n";
        return 2;
    }

    rocfft_execution_info_destroy(info);
    rocfft_plan_destroy(plan);
    rocfft_cleanup();
    hipFree(device_output);
    hipFree(device_input);
    return 0;
}
