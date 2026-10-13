#pragma once

// Scope regressions execute an impulse (forward) or all-one half spectrum
// (inverse), for which the independent full-transform result is known exactly.
static int validate_scope(const std::string& mode, const std::string& direction)
{
    const bool post = direction == "d2z";
    if(!post && direction != "z2d") throw std::runtime_error("bad scope direction");
    const size_t n = mode == "small" ? 65534 : mode == "odd" ? 65539 : 65540;
    const size_t m = n / 2;
    const size_t higher = mode == "multidim" ? 2 : 1;
    const size_t batch = mode == "batch" ? 2 : 1;
    const size_t stride = mode == "stride" ? 3 : 1;
    const bool inplace = mode == "inplace", planar = mode == "planar";
    const size_t input_offset = mode == "offset" ? 3 : 0;
    const size_t output_offset = mode == "offset" ? 5 : 0;
    const auto precision = mode == "single" ? rocfft_precision_single : rocfft_precision_double;
    const size_t real_row = n + (inplace ? 2 : 0), half_row = m + 1;
    const size_t in_row = post ? real_row : half_row, out_row = post ? half_row : real_row;
    const size_t istrides[2] = {stride, stride * in_row};
    const size_t ostrides[2] = {stride, stride * out_row};
    const size_t idist = stride * in_row * higher, odist = stride * out_row * higher;
    const size_t lengths[2] = {n, higher};
    const size_t dimension = higher == 1 ? 1 : 2;
    const size_t ioffsets[2] = {input_offset, input_offset};
    const size_t ooffsets[2] = {output_offset, output_offset};
    const auto hermitian = planar ? rocfft_array_type_hermitian_planar
                                  : rocfft_array_type_hermitian_interleaved;
    rocfft_plan_description description = nullptr;
    fft_check(rocfft_setup());
    fft_check(rocfft_plan_description_create(&description));
    fft_check(rocfft_plan_description_set_data_layout(description,
        post ? rocfft_array_type_real : hermitian, post ? hermitian : rocfft_array_type_real,
        ioffsets, ooffsets, dimension, istrides, idist, dimension, ostrides, odist));
    constexpr double scale = 0.375;
    fft_check(rocfft_plan_description_set_scale_factor(description, scale));
    rocfft_plan plan = nullptr;
    fft_check(rocfft_plan_create(&plan, inplace ? rocfft_placement_inplace : rocfft_placement_notinplace,
        post ? rocfft_transform_type_real_forward : rocfft_transform_type_real_inverse,
        precision, dimension, lengths, batch, description));
    fft_check(rocfft_plan_description_destroy(description));
    fft_check(rocfft_plan_get_print(plan));
    if(mode == "single")
    {
        // Only gate/creation is checked outside the requested double precision.
        fft_check(rocfft_plan_destroy(plan));fft_check(rocfft_cleanup());
        std::cout << "REAL_BOUNDARY_SCOPE_PASS mode=single plan_only=1\n";
        return 0;
    }
    const size_t in_unit = !post && !planar ? 2 : 1;
    const size_t out_unit = post && !planar ? 2 : 1;
    const size_t in_doubles = (input_offset + idist * batch) * in_unit;
    const size_t out_doubles = (output_offset + odist * batch) * out_unit;
    GuardedBuffer input((inplace ? std::max(in_doubles,out_doubles) : in_doubles) * sizeof(double));
    GuardedBuffer input_imag(planar && !post ? in_doubles * sizeof(double) : 0);
    GuardedBuffer output(inplace ? 0 : out_doubles * sizeof(double));
    GuardedBuffer output_imag(planar && post ? out_doubles * sizeof(double) : 0);
    std::vector<double> original(input.bytes / sizeof(double), 0);
    for(size_t b = 0; b < batch; ++b)
    {
        if(post) original[input_offset + b * idist] = 1;
        else
            for(size_t j = 0; j < higher; ++j)
                for(size_t k = 0; k < half_row; ++k)
                    original[(input_offset+b*idist+j*istrides[1]+k*stride)*in_unit] = 1;
    }
    hip_check(hipMemcpy(input.data(), original.data(), input.bytes, hipMemcpyHostToDevice));
    if(planar && !post) hip_check(hipMemset(input_imag.data(),0,input_imag.bytes));
    size_t work_bytes = 0;fft_check(rocfft_plan_get_work_buffer_size(plan,&work_bytes));
    GuardedBuffer work(work_bytes);
    rocfft_execution_info info = nullptr;fft_check(rocfft_execution_info_create(&info));
    if(work_bytes) fft_check(rocfft_execution_info_set_work_buffer(info,work.data(),work_bytes));
    void* ins[2] = {input.data(),input_imag.data()};
    void* outs[2] = {inplace ? input.data() : output.data(),output_imag.data()};
    fft_check(rocfft_execute(plan,ins,inplace ? nullptr : outs,info));
    hip_check(hipDeviceSynchronize());
    std::vector<double> actual(out_doubles), imag(planar && post ? out_doubles : 0);
    hip_check(hipMemcpy(actual.data(),outs[0],out_doubles*sizeof(double),hipMemcpyDeviceToHost));
    if(!imag.empty()) hip_check(hipMemcpy(imag.data(),outs[1],imag.size()*sizeof(double),hipMemcpyDeviceToHost));
    double error = 0;
    for(size_t b = 0; b < batch; ++b)
        for(size_t j = 0; j < higher; ++j)
            for(size_t k = 0; k < (post ? half_row : n); ++k)
            {
                const size_t offset = output_offset+b*odist+j*ostrides[1]+k*stride;
                const double expected = post ? scale : (j==0 && k==0 ? n*higher*scale : 0);
                const double real = actual[offset*out_unit];
                const double imaginary = post ? (planar ? imag[offset] : actual[offset*2+1]) : 0;
                if(!std::isfinite(real) || !std::isfinite(imaginary))
                    throw std::runtime_error("scope nonfinite output");
                error = std::max(error,std::max(std::abs(real-expected),std::abs(imaginary)));
            }
    error /= post ? 1.0 : std::max(1.0,n*higher*scale);
    if(error >= 1e-9) throw std::runtime_error("scope reference mismatch");
    if(!inplace)
    {
        std::vector<double> unchanged(original.size());
        hip_check(hipMemcpy(unchanged.data(),input.data(),input.bytes,hipMemcpyDeviceToHost));
        if(unchanged != original) throw std::runtime_error("scope input modified");
    }
    for(const auto* buffer : {&input,&input_imag,&output,&output_imag,&work})
        if(!buffer->check()) throw std::runtime_error("scope guard modified");
    fft_check(rocfft_execution_info_destroy(info));
    fft_check(rocfft_plan_destroy(plan));fft_check(rocfft_cleanup());
    std::cout << "REAL_BOUNDARY_SCOPE_PASS mode=" << mode << " direction=" << direction
              << " plan_only=0 error=" << std::setprecision(17) << error << '\n';
    return 0;
}
