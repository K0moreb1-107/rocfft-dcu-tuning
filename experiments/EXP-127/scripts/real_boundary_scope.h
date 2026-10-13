#pragma once

// Scope references are exact: an impulse transforms to all ones, and an
// all-one real/complex spectrum transforms to a single DC impulse.
static int validate_scope(const std::string& mode, const std::string& direction,
                          size_t requested_n = 0)
{
    const bool real_forward = direction == "d2z", real_inverse = direction == "z2d";
    const bool complex_forward = direction == "cforward", complex_inverse = direction == "cinverse";
    if(!real_forward && !real_inverse && !complex_forward && !complex_inverse)
        throw std::runtime_error("bad scope direction");
    const std::vector<std::string> modes = {"batch", "stride", "offset", "inplace", "planar",
        "multidim", "small", "odd", "single", "offset_input", "offset_output", "offset_even",
        "offset_planar", "offset_inplace", "offset_inplace_planar", "offset_callbacks",
        "offset_overflow", "offset_inplace_mismatch"};
    if(std::find(modes.begin(),modes.end(),mode)==modes.end())
        throw std::runtime_error("bad scope mode");
    const size_t n = requested_n ? requested_n : mode == "small" ? 65534 : mode == "odd" ? 65539 : 65540;
    const size_t higher = mode == "multidim" ? 2 : 1, batch = mode == "batch" ? 2 : 1;
    const size_t stride = mode == "stride" ? 3 : 1;
    const bool inplace = mode == "inplace" || mode.find("offset_inplace") == 0;
    const bool planar = mode == "planar" || mode == "offset_planar" || mode == "offset_inplace_planar";
    const bool callbacks = mode == "offset_callbacks";
    const auto precision = mode == "single" ? rocfft_precision_single : rocfft_precision_double;
    const size_t real_row = n + (inplace && (real_forward || real_inverse) ? 2 : 0);
    const size_t half_row = n / 2 + 1;
    const size_t in_row = real_forward ? real_row : real_inverse ? half_row : n;
    const size_t out_row = real_forward ? half_row : real_inverse ? real_row : n;
    const size_t input_count = real_forward ? n : in_row, output_count = real_inverse ? n : out_row;
    const size_t in_unit = real_forward || planar ? 1 : 2, out_unit = real_inverse || planar ? 1 : 2;
    const size_t istrides[2] = {stride, stride * in_row}, ostrides[2] = {stride, stride * out_row};
    const size_t idist = stride * in_row * higher, odist = stride * out_row * higher;
    const size_t lengths[2] = {n, higher}, dimension = higher == 1 ? 1 : 2;
    size_t ioffsets[2] = {0,0}, ooffsets[2] = {0,0};
    if(mode.find("offset") == 0)
    {
        ioffsets[0] = ioffsets[1] = mode == "offset_output" ? 0 : 3;
        ooffsets[0] = ooffsets[1] = mode == "offset_input" ? 0 : 5;
        if(mode == "offset_even") {ioffsets[0]=ioffsets[1]=4; ooffsets[0]=ooffsets[1]=6;}
        if(planar) {ioffsets[1]=7; ooffsets[1]=9;}
        if(inplace)
        {
            const size_t bytes_in_doubles = 8;
            ioffsets[0]=ioffsets[1]=bytes_in_doubles/in_unit;
            ooffsets[0]=ooffsets[1]=bytes_in_doubles/out_unit;
            if(mode == "offset_inplace_planar") {ioffsets[1]=12; ooffsets[1]=12;}
        }
        if(mode == "offset_overflow") ioffsets[0]=std::numeric_limits<size_t>::max();
        if(mode == "offset_inplace_mismatch") ++ooffsets[0];
    }
    const auto complex_type = planar ? rocfft_array_type_complex_planar : rocfft_array_type_complex_interleaved;
    const auto hermitian = planar ? rocfft_array_type_hermitian_planar : rocfft_array_type_hermitian_interleaved;
    const auto in_type = real_forward ? rocfft_array_type_real : real_inverse ? hermitian : complex_type;
    const auto out_type = real_forward ? hermitian : real_inverse ? rocfft_array_type_real : complex_type;
    const auto transform = real_forward ? rocfft_transform_type_real_forward
                         : real_inverse ? rocfft_transform_type_real_inverse
                         : complex_forward ? rocfft_transform_type_complex_forward : rocfft_transform_type_complex_inverse;
    rocfft_plan_description description = nullptr;
    fft_check(rocfft_setup());fft_check(rocfft_plan_description_create(&description));
    fft_check(rocfft_plan_description_set_data_layout(description,in_type,out_type,
        ioffsets,ooffsets,dimension,istrides,idist,dimension,ostrides,odist));
    constexpr double scale = 0.375;
    fft_check(rocfft_plan_description_set_scale_factor(description,scale));
    rocfft_plan plan = nullptr;
    const auto status = rocfft_plan_create(&plan,inplace ? rocfft_placement_inplace : rocfft_placement_notinplace,
        transform,precision,dimension,lengths,batch,description);
    fft_check(rocfft_plan_description_destroy(description));
    if(mode == "offset_overflow" || mode == "offset_inplace_mismatch")
    {
        if(plan) fft_check(rocfft_plan_destroy(plan));
        fft_check(rocfft_cleanup());
        if(status != rocfft_status_invalid_offset) throw std::runtime_error("invalid offset not rejected");
        std::cout << "REAL_BOUNDARY_SCOPE_PASS mode=" << mode << " direction=" << direction
                  << " N=" << n << " plan_only=1 expected_rejection=invalid_offset\n";
        return 0;
    }
    fft_check(status);fft_check(rocfft_plan_get_print(plan));
    if(mode == "single")
    {
        fft_check(rocfft_plan_destroy(plan));fft_check(rocfft_cleanup());
        std::cout << "REAL_BOUNDARY_SCOPE_PASS mode=single plan_only=1\n";return 0;
    }
    const bool in_planar = planar && !real_forward, out_planar = planar && !real_inverse;
    const size_t in_doubles = (ioffsets[0]+idist*batch)*in_unit;
    const size_t out_doubles = (ooffsets[0]+odist*batch)*out_unit;
    const size_t in_imag_doubles = in_planar ? ioffsets[1]+idist*batch : 0;
    const size_t out_imag_doubles = out_planar ? ooffsets[1]+odist*batch : 0;
    GuardedBuffer input((inplace ? std::max(in_doubles,out_doubles) : in_doubles)*sizeof(double));
    GuardedBuffer input_imag((inplace ? std::max(in_imag_doubles,out_imag_doubles) : in_imag_doubles)*sizeof(double));
    GuardedBuffer output(inplace ? 0 : out_doubles*sizeof(double));
    GuardedBuffer output_imag(inplace ? 0 : out_imag_doubles*sizeof(double));
    if(!inplace)
    {
        const auto fill_output=[](GuardedBuffer& buffer,size_t prefix_doubles) {
            const size_t count=buffer.bytes/sizeof(double)-prefix_doubles;
            std::vector<double> values(count,std::numeric_limits<double>::quiet_NaN());
            if(count) hip_check(hipMemcpy(static_cast<unsigned char*>(buffer.data())+prefix_doubles*sizeof(double),
                values.data(),count*sizeof(double),hipMemcpyHostToDevice));
        };
        fill_output(output,ooffsets[0]*out_unit);
        if(out_planar) fill_output(output_imag,ooffsets[1]);
    }
    std::vector<double> original(input.bytes/sizeof(double),0);
    for(size_t b=0;b<batch;++b)
    {
        if(real_forward || complex_forward) original[(ioffsets[0]+b*idist)*in_unit]=1;
        else
            for(size_t j=0;j<higher;++j)
                for(size_t k=0;k<input_count;++k)
                    original[(ioffsets[0]+b*idist+j*istrides[1]+k*stride)*in_unit]=1;
    }
    hip_check(hipMemcpy(input.data(),original.data(),input.bytes,hipMemcpyHostToDevice));
    if(in_planar) hip_check(hipMemset(input_imag.data(),0,input_imag.bytes));
    size_t work_bytes=0;fft_check(rocfft_plan_get_work_buffer_size(plan,&work_bytes));
    GuardedBuffer work(work_bytes);
    rocfft_execution_info info=nullptr;fft_check(rocfft_execution_info_create(&info));
    if(work_bytes) fft_check(rocfft_execution_info_set_work_buffer(info,work.data(),work_bytes));
    GuardedBuffer load_counts(callbacks ? (input_count+1)*sizeof(unsigned int) : 0);
    GuardedBuffer store_counts(callbacks ? (output_count+1)*sizeof(unsigned int) : 0);
    GuardedBuffer load_data(callbacks ? sizeof(CallbackData) : 0), store_data(callbacks ? sizeof(CallbackData) : 0);
    // The execution API retains these host arrays until execution finishes.
    void* load_fn=nullptr;void* store_fn=nullptr;
    void* load_user=load_data.data();void* store_user=store_data.data();
    if(callbacks)
    {
        hip_check(hipMemset(load_counts.data(),0,load_counts.bytes));
        hip_check(hipMemset(store_counts.data(),0,store_counts.bytes));
        CallbackData load{static_cast<unsigned int*>(load_counts.data()),input_count};
        CallbackData store{static_cast<unsigned int*>(store_counts.data()),output_count};
        hip_check(hipMemcpy(load_data.data(),&load,sizeof(load),hipMemcpyHostToDevice));
        hip_check(hipMemcpy(store_data.data(),&store,sizeof(store),hipMemcpyHostToDevice));
        if(real_forward) hip_check(hipMemcpyFromSymbol(&load_fn,HIP_SYMBOL(scope_load_real_pointer),sizeof(load_fn)));
        else hip_check(hipMemcpyFromSymbol(&load_fn,HIP_SYMBOL(scope_load_complex_pointer),sizeof(load_fn)));
        if(real_inverse) hip_check(hipMemcpyFromSymbol(&store_fn,HIP_SYMBOL(scope_store_real_pointer),sizeof(store_fn)));
        else hip_check(hipMemcpyFromSymbol(&store_fn,HIP_SYMBOL(scope_store_complex_pointer),sizeof(store_fn)));
        fft_check(rocfft_execution_info_set_load_callback(info,&load_fn,&load_user,0));
        fft_check(rocfft_execution_info_set_store_callback(info,&store_fn,&store_user,0));
    }
    void* ins[2]={input.data(),input_imag.data()};
    void* outs[2]={inplace ? input.data() : output.data(),inplace ? input_imag.data() : output_imag.data()};
    fft_check(rocfft_execute(plan,ins,inplace ? nullptr : outs,info));hip_check(hipDeviceSynchronize());
    std::vector<double> actual(out_doubles),imag(out_planar ? out_imag_doubles : 0);
    hip_check(hipMemcpy(actual.data(),outs[0],out_doubles*sizeof(double),hipMemcpyDeviceToHost));
    if(out_planar) hip_check(hipMemcpy(imag.data(),outs[1],imag.size()*sizeof(double),hipMemcpyDeviceToHost));
    const double gain = callbacks ? 0.75*1.125 : 1.0;
    double error=0;size_t worst=0;
    for(size_t b=0;b<batch;++b)
        for(size_t j=0;j<higher;++j)
            for(size_t k=0;k<output_count;++k)
            {
                const size_t offset=ooffsets[0]+b*odist+j*ostrides[1]+k*stride;
                const double expected=(real_forward || complex_forward) ? scale*gain
                                     : (j==0 && k==0 ? n*higher*scale*gain : 0);
                const double real=actual[offset*out_unit];
                const double imaginary=real_inverse ? 0 : out_planar
                    ? imag[ooffsets[1]+b*odist+j*ostrides[1]+k*stride] : actual[offset*2+1];
                if(!std::isfinite(real) || !std::isfinite(imaginary)) throw std::runtime_error("scope nonfinite output");
                const auto delta=std::max(std::abs(real-expected),std::abs(imaginary));
                if(delta>error) {error=delta;worst=offset;}
            }
    error /= (real_forward || complex_forward) ? 1.0 : std::max(1.0,n*higher*scale*gain);
    if(error>=1e-9)
        throw std::runtime_error("scope reference mismatch N="+std::to_string(n)+" index="
            +std::to_string(worst)+" error="+std::to_string(error));
    // Existing real inverse plans may reuse user input as temporary storage.
    // Target fused paths still enforce input immutability in validate_case().
    if(!inplace && !real_inverse)
    {
        std::vector<double> unchanged(original.size());
        hip_check(hipMemcpy(unchanged.data(),input.data(),input.bytes,hipMemcpyDeviceToHost));
        if(unchanged!=original) throw std::runtime_error("scope input modified");
        if(in_planar)
        {
            std::vector<double> imaginary(in_imag_doubles);
            hip_check(hipMemcpy(imaginary.data(),input_imag.data(),input_imag.bytes,hipMemcpyDeviceToHost));
            if(std::any_of(imaginary.begin(),imaginary.end(),[](double v){return v!=0;}))
                throw std::runtime_error("scope imaginary input modified");
        }
    }
    const auto prefix_unchanged=[](const void* device,size_t bytes,unsigned char expected) {
        std::vector<unsigned char> host(bytes);
        if(bytes) hip_check(hipMemcpy(host.data(),device,bytes,hipMemcpyDeviceToHost));
        return std::all_of(host.begin(),host.end(),[expected](unsigned char b){return b==expected;});
    };
    if(!prefix_unchanged(input.data(),ioffsets[0]*in_unit*sizeof(double),0)
       || (in_planar && !prefix_unchanged(input_imag.data(),ioffsets[1]*sizeof(double),0))
       || !prefix_unchanged(outs[0],ooffsets[0]*out_unit*sizeof(double),inplace ? 0 : GuardedBuffer::canary)
       || (out_planar && !prefix_unchanged(outs[1],ooffsets[1]*sizeof(double),inplace ? 0 : GuardedBuffer::canary)))
        throw std::runtime_error("scope offset prefix modified");
    if(callbacks)
    {
        for(const auto& item : {std::make_pair(&load_counts,input_count),std::make_pair(&store_counts,output_count)})
        {
            std::vector<unsigned int> counts(item.second+1);
            hip_check(hipMemcpy(counts.data(),item.first->data(),item.first->bytes,hipMemcpyDeviceToHost));
            // Existing fallback kernels may visit a self-paired frequency
            // more than once. Require complete, bounded callback coverage;
            // the target fused guards separately require exactly one visit.
            if(counts.back()!=0 || !std::all_of(counts.begin(),counts.end()-1,[](unsigned int c){return c>=1;}))
                throw std::runtime_error("scope callback coverage or bounds mismatch");
            std::cout << "SCOPE_CALLBACK_VISITS min=" << *std::min_element(counts.begin(),counts.end()-1)
                      << " max=" << *std::max_element(counts.begin(),counts.end()-1) << '\n';
        }
    }
    for(const auto* buffer : {&input,&input_imag,&output,&output_imag,&work,&load_counts,&store_counts,&load_data,&store_data})
        if(!buffer->check()) throw std::runtime_error("scope guard modified");
    fft_check(rocfft_execution_info_destroy(info));fft_check(rocfft_plan_destroy(plan));fft_check(rocfft_cleanup());
    std::cout << "REAL_BOUNDARY_SCOPE_PASS mode=" << mode << " direction=" << direction
              << " N=" << n << " plan_only=0 input_preserved_required=" << (!inplace && !real_inverse)
              << " error=" << std::setprecision(17) << error << '\n';
    return 0;
}
