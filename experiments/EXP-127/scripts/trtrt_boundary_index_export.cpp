// Host-only exporter. It renders the actual first_pass_io/last_pass_io AST,
// including add_work thread predicates, into executable CPU index checks.
#include <functional>
using namespace std::placeholders;

#include "device/generator/generator.h"
#include "device/generator/stockham_gen_rr.h"
#include "device/generator/real_pair_layout.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

void write_standalone_test_harness(const Function&, const std::string&) {}

static const char* host_tests = R"test(
struct C { double x,y; };
static void ensure(bool p,const char* message) { if(!p) throw std::runtime_error(message); }
static std::complex<double> z(C p) { return {p.x,p.y}; }
static C c(std::complex<double> p) { return {p.real(),p.imag()}; }
static size_t tests=0, addresses=0;

static void index_case(size_t n,unsigned int threads,void (*mapping)(unsigned int,std::vector<unsigned int>&))
{
    std::vector<unsigned int> counts(n,0);
    for(unsigned int thread=0;thread<threads;++thread) mapping(thread,counts);
    ensure(std::all_of(counts.begin(),counts.end(),[](auto count){return count==1;}),"core index ownership");
    ++tests;addresses+=n;
}

static std::pair<size_t,size_t> mirror(size_t axis,size_t span,size_t row,size_t j)
{
    return {row==0 ? 0 : axis-row,row==0 ? (j==0 ? 0 : span-j) : span-1-j};
}

// Both tile arrays use the owner's local coordinates. The reader swaps local
// axes, recomputes the same ownership mask, and recomputes physical mirror
// coordinates per element. No mirror rectangle or extra global column exists.
static void transpose_case(size_t axis,size_t span,size_t pad)
{
    const size_t m=axis*span, pitch=span+pad;
    std::vector<unsigned char> logical(m,0),physical(axis*pitch,0);
    for(size_t sr=0;sr<axis;sr+=32)
        for(size_t sj=0;sj<span/2+1;sj+=32)
        {
            std::array<size_t,32*33> own{},peer{};
            std::array<unsigned char,32*33> live{};
            for(size_t lr=0;lr<32;++lr)
                for(size_t lj=0;lj<32;++lj)
                {
                    const auto row=sr+lr,j=sj+lj;
                    if(row>=axis || j>=span) continue;
                    const auto k=row+axis*j;
                    if(2*k>m) continue;
                    const auto cell=lr*33+lj;
                    own[cell]=k;peer[cell]=k==0 ? 0 : m-k;live[cell]=1;
                }
            for(size_t lj=0;lj<32;++lj)
                for(size_t lr=0;lr<32;++lr)
                {
                    const auto row=sr+lr,j=sj+lj;
                    if(row>=axis || j>=span) continue;
                    const auto k=row+axis*j;
                    if(2*k>m) continue;
                    const auto cell=lr*33+lj;
                    ensure(live[cell] && own[cell]==k,"read uninitialized owner tile");
                    auto visit=[&](size_t r,size_t q,size_t expected) {
                        ensure(r<axis && q<span && r+axis*q==expected,"wrong mirror coordinate");
                        ensure(++logical[expected]==1 && ++physical[r*pitch+q]==1,"duplicate transpose output");
                    };
                    visit(row,j,k);
                    if(k!=0 && 2*k!=m)
                    {
                        const auto mirrored=mirror(axis,span,row,j);
                        ensure(peer[cell]==m-k,"read uninitialized mirror tile");
                        visit(mirrored.first,mirrored.second,m-k);
                    }
                }
        }
    ensure(std::all_of(logical.begin(),logical.end(),[](auto count){return count==1;}),"missing transpose output");
    for(size_t r=0;r<axis;++r)
        for(size_t j=0;j<pitch;++j)
            ensure(physical[r*pitch+j]==(j<span),"transpose padding modified");
    ++tests;addresses+=m;
}

static void rows_case(size_t axis,size_t span,unsigned int slots)
{
    ensure(slots>=2 && slots%2==0,"invalid paired slots");
    const size_t m=axis*span, blocks=((axis+1)/2+slots/2-1)/(slots/2);
    std::vector<unsigned char> counts(m,0),rows(axis,0);
    for(size_t block=0;block<blocks;++block)
    {
        std::vector<size_t> labels(slots,axis);
        for(unsigned int s=0;s<slots;++s)
        {
            labels[s]=real_pair_row(axis,slots,s,block);
            if(labels[s]<axis) ensure(++rows[labels[s]]==1,"row label duplicated");
        }
        std::vector<size_t> shared(slots*(span+1),m);
        for(unsigned int s=0;s<slots;++s)
        {
            const auto row=labels[s];
            if(row>=axis) continue;
            for(size_t j=0;j<span;++j)
            {
                const auto k=row+axis*j;
                if(2*k>m) continue;
                auto store=[&](unsigned int slot,size_t element,size_t value) {
                    ensure(slot<slots && labels[slot]<axis && element<span,"invalid exchange write");
                    auto& cell=shared[slot*(span+1)+element];
                    ensure(cell==m,"exchange write duplicated");cell=value;
                    ensure(++counts[value]==1,"row-pair logical output duplicated");
                };
                store(s,j,k);
                if(k!=0 && 2*k!=m)
                {
                    const auto q=mirror(axis,span,row,j);
                    const auto ps=real_pair_peer(axis,slots,s,row);
                    ensure(labels[ps]==q.first,"mirror row in another block");
                    store(ps,q.second,m-k);
                }
            }
        }
        for(unsigned int s=0;s<slots;++s)
            for(size_t j=0;j<span+1;++j)
                if(labels[s]<axis && j<span)
                    ensure(shared[s*(span+1)+j]==labels[s]+axis*j,"row exchange read mismatch");
                else ensure(shared[s*(span+1)+j]==m,"inactive slot or padding modified");
    }
    ensure(std::all_of(rows.begin(),rows.end(),[](auto count){return count==1;}),"missing paired row");
    ensure(std::all_of(counts.begin(),counts.end(),[](auto count){return count==1;}),"missing paired element");
    ++tests;addresses+=m;
}

static std::vector<std::complex<double>> dft(const std::vector<std::complex<double>>& x,int sign)
{
    const auto n=x.size();const double pi=std::acos(-1.0);
    std::vector<std::complex<double>> result(n);
    for(size_t k=0;k<n;++k)
        for(size_t j=0;j<n;++j)
            result[k]+=x[j]*std::polar(1.0,sign*2*pi*double(j*k)/n);
    return result;
}

static void matrix_fft_case(size_t axis,size_t span)
{
    const size_t m=axis*span;const double pi=std::acos(-1.0);
    std::vector<std::complex<double>> input(m);
    for(size_t k=0;k<m;++k) input[k]={0.1*double(k%13),0.07*double(k%11)};
    for(int sign:{-1,1})
    {
        std::vector<std::complex<double>> first(m),actual(m);
        for(size_t row=0;row<axis;++row)
        {
            std::vector<std::complex<double>> values(span);
            for(size_t j=0;j<span;++j) values[j]=input[row+axis*j];
            values=dft(values,sign);
            for(size_t v=0;v<span;++v)
                first[row+axis*v]=values[v]*std::polar(1.0,sign*2*pi*double(row*v)/m);
        }
        for(size_t v=0;v<span;++v)
        {
            std::vector<std::complex<double>> values(axis);
            for(size_t row=0;row<axis;++row) values[row]=first[row+axis*v];
            values=dft(values,sign);
            for(size_t r=0;r<axis;++r) actual[v+span*r]=values[r];
        }
        const auto reference=dft(input,sign);
        for(size_t k=0;k<m;++k) ensure(std::abs(actual[k]-reference[k])<1e-9,"TRTRT phase or natural order mismatch");
        ++tests;
    }
}

static void arithmetic_case(size_t m)
{
    const double pi=std::acos(-1.0);const size_t n=2*m;
    std::vector<std::complex<double>> real(n),packed(m);
    for(size_t j=0;j<n;++j) real[j]=0.2*std::sin(0.31*j)+0.3*std::cos(0.17*j)+double(j%7)*0.01;
    for(size_t j=0;j<m;++j) packed[j]={real[2*j].real(),real[2*j+1].real()};
    const auto reference=dft(real,-1), transformed=dft(packed,-1);
    std::vector<std::complex<double>> half(m+1),pre(m);
    half[0]={transformed[0].real()+transformed[0].imag(),0};
    half[m]={transformed[0].real()-transformed[0].imag(),0};
    pre[0]={half[0].real()+half[m].real(),half[0].real()-half[m].real()};
    for(size_t k=1;2*k<m;++k)
    {
        C own{},peer{};const auto w=c(std::polar(1.0,-pi*double(k)/m));
        real_pair_post(c(transformed[k]),c(transformed[m-k]),w,own,peer);
        half[k]=z(own);half[m-k]=z(peer);
        real_pair_pre(c(half[k]),c(half[m-k]),w,own,peer);
        pre[k]=z(own);pre[m-k]=z(peer);
    }
    if(m%2==0) {half[m/2]=std::conj(transformed[m/2]);pre[m/2]=2.0*std::conj(half[m/2]);}
    for(size_t k=0;k<m+1;++k) ensure(std::abs(half[k]-reference[k])<1e-9,"post formula/endpoint mismatch");
    const auto inverse=dft(pre,1);
    for(size_t j=0;j<m;++j)
        ensure(std::abs(inverse[j]-double(n)*packed[j])<1e-9,"pre factor/endpoint mismatch");
    ++tests;
}
)test";

int main(int argc,char** argv)
{
    if(argc!=4) return 2;
    std::ifstream configs(argv[1]),matrices(argv[2]);
    std::ofstream out(argv[3]);
    if(!configs || !matrices || !out) throw std::runtime_error("native exporter path unavailable");
    out << "#include <algorithm>\n#include <array>\n#include <cmath>\n#include <complex>\n#include <iostream>\n#include <stdexcept>\n#include <utility>\n#include <vector>\n";
    out << "#define __device__\n#define __forceinline__ inline\n" << real_pair_layout_device_helpers() << host_tests;
    std::vector<std::pair<unsigned int,unsigned int>> launches;
    unsigned int n,tpt,tpb,half,count;
    while(configs>>n>>tpt>>tpb>>half>>count)
    {
        std::vector<unsigned int> factors(count);
        for(auto& f:factors) if(!(configs>>f)) throw std::runtime_error("truncated factor configuration");
        StockhamGeneratorSpecs specs(factors,{}, {rocfft_precision_double},tpt*tpb,"CS_KERNEL_STOCKHAM");
        specs.threads_per_transform=tpt;specs.wgs_is_derived=true;specs.half_lds=half;
        StockhamKernelRR kernel(specs);
        if(kernel.length!=n) throw std::runtime_error("factor product mismatch");
        const auto index=launches.size();launches.push_back({n,tpt});
        for(bool first:{true,false})
        {
            const auto collect=[](Expression value,Variable) {
                return StatementList{Call{"record", {Expression{value}}}};
            };
            const auto statements=first ? kernel.first_pass_io(collect) : kernel.last_pass_io(collect);
            out << "static void map_" << index << (first ? "_first" : "_last")
                << "(unsigned int thread,std::vector<unsigned int>& counts) {"
                << "auto record=[&](size_t index){ensure(index<counts.size(),\"core index overflow\");ensure(++counts[index]==1,\"core index duplicate\");};"
                << statements.render() << "}\n";
        }
    }
    if(!configs.eof() || launches.empty()) throw std::runtime_error("invalid or empty core configuration input");
    out << "int main(){try {\n";
    for(size_t i=0;i<launches.size();++i)
        for(const auto* pass:{"first","last"})
            out << "index_case(" << launches[i].first << ',' << launches[i].second << ",map_" << i << '_' << pass << ");\n";
    size_t axis,span;unsigned int pre_slots,post_slots;
    while(matrices>>axis>>span>>pre_slots>>post_slots)
    {
        for(unsigned int pad:{0,1,7})
            out << "transpose_case(" << axis << ',' << span << ',' << pad << ");transpose_case(" << span << ',' << axis << ',' << pad << ");\n";
        if(pre_slots) out << "rows_case(" << axis << ',' << span << ',' << pre_slots << ");\n";
        if(post_slots) out << "rows_case(" << span << ',' << axis << ',' << post_slots << ");\n";
    }
    if(!matrices.eof()) throw std::runtime_error("invalid matrix input");
    out << "for(size_t axis:{1,2,3,4,5,6,17,31,32,33,63,64,65}) for(size_t span:{1,2,3,4,5,6,17,31,32,33,63,64,65}) {"
        << "transpose_case(axis,span,3);for(unsigned int slots:{2,4,6,14,18}) rows_case(axis,span,slots);}\n"
        << "const std::pair<size_t,size_t> shapes[]={{2,7},{7,2},{3,5},{6,9},{17,3},{3,17},{32,3},{3,32},{31,2}};for(auto shape:shapes) matrix_fft_case(shape.first,shape.second);\n"
        << "for(size_t m:{1,2,3,4,5,6,7,16,17,31,32,33,64,65,127}) arithmetic_case(m);\n"
        << "std::cout<<\"TRTRT_NATIVE_INDEX_PASS tests=\"<<tests<<\" addresses=\"<<addresses<<\" core_configs=" << launches.size()
        << " gpu_execution=0 actual_add_work_predicates=1\\n\";return 0;"
        << "}catch(const std::exception& e){std::cerr<<e.what()<<'\\n';return 1;}}\n";
    if(!out) throw std::runtime_error("native source write failed");
    std::cout << "TRTRT_NATIVE_EXPORT_PASS core_configs=" << launches.size() << " gpu_execution=0\n";
}
