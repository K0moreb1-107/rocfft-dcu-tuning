from pathlib import Path
import subprocess,json,hashlib
ROOT=Path('/public/home/zhangkewei/zr')
OUT=ROOT/'experiments/EXP-129/artifacts/code-equivalence-review-20261029/prefix'
SRC='rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/'
old=lambda f:subprocess.check_output(['git','show','1d22a78f:'+SRC+f],cwd=ROOT,text=True)
new=lambda f:(ROOT/SRC/f).read_text()
def function(text,signature):
 a=text.index(signature);start=text.index('{',a);n=1;i=start+1
 while n:
  if text[i]=='{':n+=1
  if text[i]=='}':n-=1
  i+=1
 return text[a:i]
def prefix(text,signature,stop,selection):
 f=function(text,signature);f=f[:f.index(stop)]
 return f+'selected='+str(selection)+'; return true;\n}\n'
def route(text):
 f=function(text,'void RealTransEvenNode::BuildTree_internal(')
 a=f.index('    // Fastest moving dimension must be even:');b=f.index('    // check schemes from solution map',a)
 early=f[a:b]
 marker='    if(noSolution && TryBuildCCLocalTree' if '    if(noSolution && TryBuildCCLocalTree' in f else '    if(try_cc_real)'
 a=f.index(marker,f.index('cfftPlan->RecursiveBuildTree'));b=f.index('    if(noSolution)\n',a)
 late=f[a:b].replace('        childNodes.emplace_back(std::move(cfftPlan));','').replace('            childNodes.emplace_back(std::move(cfftPlan));','')
 return 'void RealTransEvenNode::Route(const TreeNode& cfft, size_t n, bool noSolution) {\nconst std::vector<size_t> real_lengths{n};const auto* realLength=&real_lengths; const TreeNode* cfftPlan=&cfft; selected=0; built=false;\n'+early+'built=true;\n'+late+'}\n'
def planner(text):
 f=function(text,'NodeFactory::Decide1DScheme(')
 a=f.index('    constexpr size_t legacy_block_compute_map_threshold');b=f.index('    else // if not Pow2',a)
 return 'std::tuple<int,bool,size_t> NodeFactory::Planner(const function_pool& pool, NodeMetaData nodeData) { int scheme=CS_NONE;\n'+f[a:b]+'return {scheme,failed,divLength1};}\n'
common=r"""
#include <vector>
#include <array>
#include <string>
#include <memory>
#include <optional>
#include <map>
#include <tuple>
#include <iostream>
#include <cstdlib>
#include <stdexcept>
#include <random>
#include <algorithm>
using rocfft_precision=int;
constexpr int rocfft_precision_half=0,rocfft_precision_single=1,rocfft_precision_double=2;
constexpr int rocfft_placement_notinplace=0,rocfft_placement_inplace=1;
constexpr int rocfft_array_type_real=0,rocfft_array_type_hermitian_interleaved=1,rocfft_array_type_complex_interleaved=2,rocfft_array_type_hermitian_planar=3;
constexpr int CS_NONE=0,CS_L1D_CC=1,CS_KERNEL_STOCKHAM_BLOCK_CC=2,CS_KERNEL_STOCKHAM_BLOCK_RC=3,CS_L1D_CRT=4,CS_L1D_TRTRT=5;
constexpr int BFT_NONE=0,TILE_ALIGNED=1,TILE_UNALIGNED=2;
namespace EmbeddedType{constexpr int NONE=0;}
struct Device{std::string arch="gfx936";int warpSize=64;size_t sharedMemPerBlock=65536;};
bool is_device_gcn_arch(const Device& d,const char* arch){return d.arch==arch;}
bool IsPo2(size_t n){return n && !(n&(n-1));}
struct FMKey{size_t length;int precision,scheme,tile;FMKey(size_t l,int p,int s,int t=0):length(l),precision(p),scheme(s),tile(t){}};
struct FFTKernel{size_t transforms_per_block=8;bool direct_to_from_reg=true,half_lds=true;std::array<int,2> threads_per_transform{32,0};int workgroup_size=256;std::vector<size_t> factors{4,4,4,4};};
struct function_pool{
 FFTKernel cc;bool ccPresent=true,alignedPresent=true,unalignedPresent=true;size_t largest=4096;int rowVariant=0;
 bool has_function(FMKey k)const{return k.scheme==CS_KERNEL_STOCKHAM_BLOCK_CC?ccPresent:(k.tile==TILE_UNALIGNED?unalignedPresent:alignedPresent);}
 FFTKernel get_kernel(FMKey k)const{if(k.scheme==CS_KERNEL_STOCKHAM_BLOCK_CC)return cc;FFTKernel x;x.half_lds=false;if(k.length==512){x.transforms_per_block=4;x.threads_per_transform[0]=128;x.workgroup_size=512;x.factors={8,8,8};}if(rowVariant==1)x.workgroup_size+=1;if(rowVariant==2)x.factors={2,2};if(rowVariant==3)x.transforms_per_block=3;if(rowVariant==4)x.threads_per_transform[0]+=1;return x;}
 bool has_SBCC_kernel(size_t,int)const{return ccPresent;}
 bool has_SBRC_kernel(size_t,int)const{return alignedPresent;}
 size_t get_largest_pow2_length(int)const{return largest;}
};
enum class RealBlockRole{None,PairedPostRows};enum class RealBlockLoad{Registers,LDS};
struct RealBlockIO{RealBlockRole role=RealBlockRole::None;RealBlockLoad load=RealBlockLoad::Registers;size_t n,columns,rows,pitch;
 static std::optional<RealBlockIO> ForLength(size_t n){size_t c=0,q=0;switch(n){case 65536:c=128;q=256;break;case 131072:c=256;q=256;break;case 262144:c=256;q=512;break;case 524288:c=512;q=512;break;case 1048576:c=1024;q=512;break;default:return std::nullopt;}return RealBlockIO{RealBlockRole::None,RealBlockLoad::Registers,n,c,q,q+8};}
};
struct TreeNode{int scheme=CS_L1D_CC,fuseBlue=BFT_NONE,ebtype=EmbeddedType::NONE;std::vector<size_t> length{128,256};size_t large1D=32768;std::vector<std::shared_ptr<TreeNode>> childNodes;};
struct NodeMetaData{std::vector<size_t> length;int precision=rocfft_precision_double;Device deviceProp;};
using Map1DLength=std::map<size_t,size_t>;
"""
declaration=r"""
int ROCFFT_CC_REAL_FUSION=1,ROCFFT_CC_LOCAL_REAL_FUSION=1;
struct RealTransEvenNode:TreeNode{
 int dimension=1,direction=1,precision=rocfft_precision_double,placement=rocfft_placement_notinplace,inArrayType=rocfft_array_type_hermitian_interleaved,outArrayType=rocfft_array_type_real;
 size_t batch=1,iOffset=0,oOffset=0;std::vector<size_t> inStride{1},outStride{1};Device deviceProp;function_pool pool;int selected=0;bool built=false;
 bool CanFuseCCReal()const;bool CCRealKernelsAvailable(size_t,size_t)const;
 bool TryBuildCCLocalTree(const TreeNode&,size_t);bool TryBuildLocalRealTree(size_t);bool TryFusePairedPost(TreeNode&,size_t);
 void Route(TreeNode&,size_t,bool);
};
struct NodeFactory{static Map1DLength map1DLengthSingle,map1DLengthDouble;static bool Get1DBlockComputeDivisor(const function_pool&,int,size_t,size_t&,bool&);static std::tuple<int,bool,size_t> Planner(const function_pool&,NodeMetaData);};
Map1DLength NodeFactory::map1DLengthSingle,NodeFactory::map1DLengthDouble;
"""
# Route must pass a mutable tree to the paired prefix, matching production.
def build_version(name,read,isnew):
 real=read('tree_node_real.cpp');factory=read('node_factory.cpp')
 pieces=[declaration]
 if isnew:
  for sig in ['bool RealTransEvenNode::CanFuseCCReal()','bool RealTransEvenNode::CCRealKernelsAvailable(','static RealBlockLoad real_block_load(']:pieces.append(function(real,sig))
 pieces += [prefix(real,'bool RealTransEvenNode::TryBuildCCLocalTree(', '    RealBlockIO io',1),prefix(real,'bool RealTransEvenNode::TryBuildLocalRealTree(', '    auto first = NodeFactory',2),prefix(real,'bool RealTransEvenNode::TryFusePairedPost(', '    first.allowInplace',3)]
 pieces.append(route(real).replace('const TreeNode& cfft','TreeNode& cfft').replace('const TreeNode* cfftPlan','TreeNode* cfftPlan'))
 if not isnew:pieces.append(function(factory,'bool NodeFactory::Get1DBlockComputeDivisor('))
 pieces.append(planner(factory))
 result='namespace '+name+' {\n'+'\n'.join(pieces)+'\n}\n'
 (OUT/(name+'-source-fragments.inc')).write_text(result)
 return result
before=build_version('before',old,False);after=build_version('after',new,True)
main=r"""
struct Input{int dimension=1,direction=1,precision=2,placement=0,it=1,ot=0;size_t batch=1,io=0,oo=0;std::vector<size_t> len{65536},is{1},os{1};Device device;function_pool pool;size_t n=65536,c=128,q=256;int scheme=CS_L1D_CC,blue=0;};
template<class N> void init(N& n,const Input& in){n.dimension=in.dimension;n.direction=in.direction;n.precision=in.precision;n.placement=in.placement;n.inArrayType=in.it;n.outArrayType=in.ot;n.batch=in.batch;n.iOffset=in.io;n.oOffset=in.oo;n.length=in.len;n.inStride=in.is;n.outStride=in.os;n.deviceProp=in.device;n.pool=in.pool;}
TreeNode tree(const Input& in){TreeNode t;t.scheme=in.scheme;t.fuseBlue=in.blue;auto c=std::make_shared<TreeNode>();auto q=std::make_shared<TreeNode>();c->scheme=CS_KERNEL_STOCKHAM_BLOCK_CC;q->scheme=CS_KERNEL_STOCKHAM_BLOCK_RC;c->fuseBlue=q->fuseBlue=in.blue;c->length={in.c,in.q};q->length={in.q,in.c};c->large1D=in.n/2;t.childNodes={c,q};return t;}
template<class N> auto run(N& node,const Input& in,bool solution){init(node,in);auto t=tree(in);std::string error;try{node.Route(t,in.n,!solution);}catch(const std::exception& e){error=e.what();}return std::make_tuple(node.selected,node.built,error);}
size_t cases=0;
void compare(const Input& in){for(int f=0;f<2;f++)for(int l=0;l<2;l++)for(int s=0;s<2;s++){
 before::ROCFFT_CC_REAL_FUSION=after::ROCFFT_CC_REAL_FUSION=f;before::ROCFFT_CC_LOCAL_REAL_FUSION=after::ROCFFT_CC_LOCAL_REAL_FUSION=l;
 before::RealTransEvenNode a;after::RealTransEvenNode b;auto x=run(a,in,s),y=run(b,in,s);++cases;if(x!=y){std::cerr<<"route mismatch case "<<cases<<" N "<<in.n<<" c "<<in.c<<" q "<<in.q<<" f/l/s "<<f<<l<<s<<" old "<<std::get<0>(x)<<"/"<<std::get<1>(x)<<"/"<<std::get<2>(x)<<" new "<<std::get<0>(y)<<"/"<<std::get<1>(y)<<"/"<<std::get<2>(y)<<"\n";std::exit(1);}
 }}
int main(){
 Input base;compare(base);
 for(int direction:{-1,1})for(int it=0;it<4;it++)for(int ot=0;ot<4;ot++){auto x=base;x.direction=direction;x.it=it;x.ot=ot;compare(x);}
 for(auto st:std::vector<std::vector<size_t>>{{},{0},{1},{2},{1,1},{1,2}}){auto x=base;x.is=st;compare(x);x=base;x.os=st;compare(x);x=base;x.len=st;compare(x);}
 for(auto n:{size_t(65534),size_t(65535),size_t(65536),size_t(131072),size_t(262144),size_t(524288),size_t(1048576),size_t(1)<<24,(size_t(1)<<24)+2})for(int shape=0;shape<2;shape++){auto x=base;x.n=n;x.c=shape?256:128;x.q=(n/2)/x.c;if(n%2||n/2%x.c){x.c=1;x.q=n/2;}x.len={n};compare(x);x.direction=-1;x.it=0;x.ot=1;compare(x);}
 for(size_t sh:std::vector<size_t>{0,8191,8192,32767,32768,65535,65536,size_t(1)<<30}){auto x=base;x.device.sharedMemPerBlock=sh;compare(x);}
 for(auto cq:std::vector<std::pair<size_t,size_t>>{{128,256},{1024,512},{121,343}})for(size_t tpb:std::vector<size_t>{1,2,4,8})for(bool half:{false,true}){auto x=base;x.c=cq.first;x.q=cq.second;x.n=2*x.c*x.q;x.len={x.n};x.pool.cc.transforms_per_block=tpb;x.pool.cc.half_lds=half;size_t bytes=std::max(x.c*tpb*16/(half?2:1),x.q*(x.q==512?4:8)*16);for(auto sh:std::vector<size_t>{bytes-1,bytes,bytes+1}){x.device.sharedMemPerBlock=sh;compare(x);}}
 for(size_t n:std::vector<size_t>{65534,65536,size_t(1)<<24,(size_t(1)<<24)+2}){auto x=base;x.n=n;x.c=1;x.q=n/2;x.len={n};x.device.sharedMemPerBlock=size_t(1)<<30;compare(x);}
 for(int m=0;m<9;m++){auto x=base;if(m==0)x.pool.ccPresent=false;if(m==1)x.pool.alignedPresent=false;if(m==2)x.pool.unalignedPresent=false;if(m==3)x.pool.cc.direct_to_from_reg=false;if(m==4)x.pool.cc.transforms_per_block=1;if(m==5)x.pool.cc.half_lds=false;if(m==6)x.pool.cc.transforms_per_block=257;if(m==7)x.device.arch="gfx906";if(m==8)x.device.warpSize=32;compare(x);}
 std::mt19937 rng(129);std::vector<std::pair<size_t,size_t>> shapes{{128,256},{256,128},{256,256},{256,512},{512,512},{1024,512},{121,343},{343,121},{50,1331},{128,625}};
 for(int i=0;i<5000;i++){auto x=base;auto cq=shapes[rng()%shapes.size()];x.c=cq.first;x.q=cq.second;x.n=2*x.c*x.q;x.len={x.n};x.direction=(rng()%2)?1:-1;x.it=x.direction==1?1:0;x.ot=x.direction==1?0:1;
 switch(rng()%20){case 0:x.dimension=2;break;case 1:x.batch=2;break;case 2:x.precision=1;break;case 3:x.placement=1;break;case 4:x.is={};break;case 5:x.os={1,1};break;case 6:x.io=1;break;case 7:x.oo=1;break;case 8:x.device.arch="gfx90a";break;case 9:x.device.warpSize=32;break;case 10:x.scheme=CS_NONE;break;case 11:x.blue=1;break;case 12:x.pool.ccPresent=false;break;case 13:x.pool.alignedPresent=false;break;case 14:x.pool.unalignedPresent=false;break;case 15:x.device.sharedMemPerBlock=(rng()%4)*8192;break;case 16:x.pool.rowVariant=1+rng()%4;break;case 17:x.pool.cc.half_lds=rng()%2;x.pool.cc.transforms_per_block=1+rng()%20;break;case 18:x.it=3;break;default:break;}compare(x);}
 for(const char* mode:{"registers","lds","bad",""}){setenv("ROCFFT_EXP125_LOCAL_REAL_LOAD",mode,1);setenv("ROCFFT_EXP125_REAL_POST_LOAD",mode,1);compare(base);auto x=base;x.direction=-1;x.it=0;x.ot=1;compare(x);x.it=3;compare(x);}unsetenv("ROCFFT_EXP125_LOCAL_REAL_LOAD");unsetenv("ROCFFT_EXP125_REAL_POST_LOAD");
 size_t planners=0;for(int precision:{0,1,2,3})for(size_t n:{1024,262144,524288,1048576})for(int shape=0;shape<4;shape++)for(int ck=0;ck<2;ck++)for(int rk=0;rk<2;rk++)for(int arch=0;arch<2;arch++)for(size_t largest:{size_t(1),size_t(4096)}){
 before::NodeFactory::map1DLengthSingle.clear();before::NodeFactory::map1DLengthDouble.clear();after::NodeFactory::map1DLengthSingle.clear();after::NodeFactory::map1DLengthDouble.clear();
 if(shape){size_t d=shape==1?256:shape==2?0:3;before::NodeFactory::map1DLengthSingle[n]=before::NodeFactory::map1DLengthDouble[n]=after::NodeFactory::map1DLengthSingle[n]=after::NodeFactory::map1DLengthDouble[n]=d;}
 NodeMetaData nd;nd.precision=precision;nd.length={n};nd.deviceProp.arch=arch?"gfx906":"gfx936";function_pool p;p.ccPresent=ck;p.alignedPresent=rk;p.largest=largest;auto x=before::NodeFactory::Planner(p,nd),y=after::NodeFactory::Planner(p,nd);++planners;if(x!=y){std::cerr<<"planner mismatch\n";return 2;}}
 std::cout<<"{\"complete\":true,\"route_cases\":"<<cases<<",\"planner_cases\":"<<planners<<",\"source\":\"extracted actual old/new function prefixes and call-order branches\",\"gpu_execution\":false}"<<std::endl;
}
"""
source=common+before+after+main
(OUT/'compare.cpp').write_text(source)
cmd=['g++','-std=c++17','-O2',str(OUT/'compare.cpp'),'-o',str(OUT/'compare')]
p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
(OUT/'compile.out').write_text(p.stdout);(OUT/'compile.err').write_text(p.stderr)
if p.returncode:raise RuntimeError(p.stderr[-10000:])
p=subprocess.run([str(OUT/'compare')],cwd=ROOT,capture_output=True,text=True)
(OUT/'run.out').write_text(p.stdout);(OUT/'run.err').write_text(p.stderr)
if p.returncode:raise RuntimeError(p.stderr)
result=json.loads(p.stdout);result.update(source_hashes={n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in ['before-source-fragments.inc','after-source-fragments.inc','compare.cpp']},boundary='Gate acceptance, dispatch order, exceptions and mapped-kernel planner branch only; node-construction bodies, public plan integration, GPU code and numerical/device behavior are not covered.',artifacts=str(OUT))
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
