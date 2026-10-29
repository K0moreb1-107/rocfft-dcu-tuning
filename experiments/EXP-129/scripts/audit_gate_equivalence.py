"""Recheck EXP129 code equivalence, including complete fusion helper mutations."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/public/home/zhangkewei/zr')
SRC = Path('rocm-libraries-rocm-7.2.2/projects/rocfft/library/src')
BEFORE = '1d22a78fad885db364b3ad631eaddb2baf0fcf1f'
AFTER = 'c4de21bc379612ce420949575d8acc2cc9336177'
ART = ROOT/'experiments/EXP-129/artifacts/code-equivalence-review-20261029'
REC = ROOT/'experiments/EXP-129/records/code-equivalence-review-20261029'
OLD = ROOT/'experiments/EXP-129/records/implementation-20261029'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, name):
    result = subprocess.run(list(map(str, argv)), cwd=ROOT, text=True, capture_output=True, timeout=240)
    (ART/(name+'.out')).write_text(result.stdout)
    (ART/(name+'.err')).write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(name+': '+result.stderr[-6000:])
    return result.stdout


def read_old(name):
    return subprocess.check_output(['git', 'show', BEFORE+':'+str(SRC/name)], cwd=ROOT, text=True)


def main():
    ART.mkdir(parents=True)
    REC.mkdir(parents=True)
    started = time.monotonic()
    implementation = json.loads((OLD/'implementation.json').read_text())
    for path, digest in implementation['production_sha256'].items():
        assert sha(ROOT/path) == digest, 'reviewed production file differs: '+path
    trees = {ref: subprocess.check_output(['git','rev-parse',ref+':'+str(SRC.parents[1])], cwd=ROOT, text=True).strip()
             for ref in ('babe7b5379aa37892f56cd190de21190d1838f68', BEFORE, AFTER, 'HEAD')}
    assert trees['babe7b5379aa37892f56cd190de21190d1838f68'] == trees[BEFORE]
    assert trees[AFTER] == trees['HEAD']
    saved = OLD/'host-proofs/planner-gates/run_compare.py'
    syntax = ast.parse(saved.read_text())
    namespace = {}
    definitions = [node for node in syntax.body if isinstance(node, ast.FunctionDef) and node.name in ('function','prefix','route','planner')]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(saved), 'exec'), namespace)
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in syntax.body
                 if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in ('common','declaration','main')}
    function, route, planner = (namespace[name] for name in ('function','route','planner'))
    # Repeat the existing fresh-source gate/planner comparison in a new directory.
    old_runner = saved.read_text().replace("OUT=ROOT/'experiments/EXP-129/artifacts/planner-gates'", "OUT=ROOT/'experiments/EXP-129/artifacts/code-equivalence-review-20261029/prefix'")
    (ART/'prefix').mkdir()
    (ART/'prefix/run_compare.py').write_text(old_runner)
    prefix = json.loads(run(['python3', ART/'prefix/run_compare.py'], 'prefix'))
    print('PREFIX_PASS', prefix['route_cases'], prefix['planner_cases'], flush=True)
    # Extend the former mock with the fields mutated by all complete fusion helpers.
    common = constants['common']
    start = common.index('enum class RealBlockRole')
    stop = common.index('struct NodeMetaData', start)
    common = common[:start]+'''\n#include <sstream>
#include <iomanip>
#include "/public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/include/real_block_io.h"
constexpr int OB_TEMP=1,OB_USER_OUT=2;
struct TreeNode {
 int scheme=CS_L1D_CC,fuseBlue=BFT_NONE,ebtype=EmbeddedType::NONE,dimension=1;
 std::vector<size_t> length{128,256},outputLength,inStride,outStride;
 size_t large1D=0,iDist=65536,oDist=65536;
 bool largeTwdBatchIsTransformCount=true,allowInplace=true;
 int allowedOutBuf=0,assignCalls=0;
 std::vector<int> allowedOutArrayTypes;
 std::vector<std::string> comments;
 RealBlockIO real_io;
 TreeNode* parent=nullptr;
 std::vector<std::shared_ptr<TreeNode>> childNodes;
 void AssignParams(){++assignCalls;}
};
template<class T> void sequence(std::ostream& out,const std::vector<T>& values){
 out<<'[';for(const auto& x:values)out<<x<<',';out<<']';
}
std::string signature(const TreeNode& n){
 std::ostringstream out;
 out<<n.scheme<<'|'<<n.fuseBlue<<'|'<<n.ebtype<<'|'<<n.dimension<<'|';
 sequence(out,n.length);sequence(out,n.outputLength);sequence(out,n.inStride);sequence(out,n.outStride);
 out<<'|'<<n.large1D<<'|'<<n.iDist<<'|'<<n.oDist<<'|'<<n.largeTwdBatchIsTransformCount<<'|'<<n.allowInplace<<'|'<<n.allowedOutBuf<<'|'<<n.assignCalls;
 sequence(out,n.allowedOutArrayTypes);for(const auto& text:n.comments)out<<std::quoted(text);
 const auto& io=n.real_io;
 out<<'|'<<int(io.role)<<'|'<<int(io.load)<<'|'<<io.n<<'|'<<io.columns<<'|'<<io.rows<<'|'<<io.pitch;
 for(const auto& child:n.childNodes)out<<"{parent="<<(child->parent==&n)<<':'<<signature(*child)<<'}';
 return out.str();
}
''' + common[stop:]
    declaration = constants['declaration'].replace('int selected=0;bool built=false;',
        'int selected=0;bool built=false;bool local_real_pipeline=false,cc_local_pipeline=false;')
    declaration = declaration.replace(' void Route(TreeNode&,size_t,bool);',
        ' void AssignCCLocalParams();void AssignLocalRealParams();void Route(TreeNode&,size_t,bool);')
    declaration = declaration.replace('struct NodeFactory{', '''struct NodeFactory{
 static std::unique_ptr<TreeNode> CreateNodeFromScheme(int s,TreeNode* parent){
  auto node=std::make_unique<TreeNode>();node->scheme=s;node->parent=parent;node->length.clear();return node;
 }
''')
    versions = []
    for name, read, is_new in [('before', read_old, False), ('after', lambda name:(ROOT/SRC/name).read_text(), True)]:
        real, factory = read('tree_node_real.cpp'), read('node_factory.cpp')
        pieces = [declaration]
        if is_new:
            pieces += [function(real, sig) for sig in ('bool RealTransEvenNode::CanFuseCCReal()',
                'bool RealTransEvenNode::CCRealKernelsAvailable(', 'static RealBlockLoad real_block_load(')]
        pieces += [function(real,sig) for sig in ('bool RealTransEvenNode::TryBuildCCLocalTree(',
            'bool RealTransEvenNode::TryBuildLocalRealTree(', 'bool RealTransEvenNode::TryFusePairedPost(',
            'void RealTransEvenNode::AssignCCLocalParams()', 'void RealTransEvenNode::AssignLocalRealParams()')]
        pieces.append(route(real).replace('const TreeNode& cfft','TreeNode& cfft').replace('const TreeNode* cfftPlan','TreeNode* cfftPlan'))
        if not is_new:
            pieces.append(function(factory,'bool NodeFactory::Get1DBlockComputeDivisor('))
        pieces.append(planner(factory))
        value='namespace '+name+' {\n'+'\n'.join(pieces)+'\n}\n'
        (ART/(name+'-full-fragments.inc')).write_text(value)
        versions.append(value)
    driver = constants['main']
    driver = driver.replace('node.Route(t,in.n,!solution);',
        'node.Route(t,in.n,!solution);if(node.cc_local_pipeline)node.AssignCCLocalParams();if(node.local_real_pipeline)node.AssignLocalRealParams();')
    driver = driver.replace('return std::make_tuple(node.selected,node.built,error);',
        'return std::make_tuple(node.selected,node.built,error,signature(node),signature(t),node.local_real_pipeline,node.cc_local_pipeline);')
    # Existing failure diagnostics can still print tuple fields 0..2 unchanged.
    (ART/'full-helpers.cpp').write_text(common+'\n'.join(versions)+driver)
    run(['g++','-std=c++17','-O2',ART/'full-helpers.cpp','-o',ART/'full-helpers'], 'full-compile')
    full = json.loads(run([ART/'full-helpers'], 'full-run'))
    print('FULL_HELPERS_PASS', full['route_cases'], flush=True)
    reruns = {}
    for key, folder, source in [('rtc', 'rtc-gates', 'policy-equivalence.cpp'),
                                 ('generator', 'generator-simplification', 'predicate-comparison.cpp')]:
        source_path=OLD/'host-proofs'/folder/source
        (ART/source).write_bytes(source_path.read_bytes())
        binary=ART/source.removesuffix('.cpp')
        run(['g++','-std=c++17','-O2',ART/source,'-o',binary], key+'-compile')
        reruns[key]=json.loads(run([binary],key+'-run'))
        print(key.upper()+'_PASS',json.dumps(reruns[key]),flush=True)
    # Re-audit all retained exact-source comparisons instead of regenerating unchanged sources.
    old_report=json.loads((OLD/'host-equivalence.json').read_text())
    generated=ROOT/'experiments/EXP-129/artifacts/host-equivalence-20261029'
    for entry in old_report['sources']:
        mode,name=entry['mode'],entry['file']
        old,new=(generated/('v6-'+mode)/name),(generated/('candidate-'+mode)/name)
        assert old.read_bytes()==new.read_bytes() and sha(new)==entry['sha256'], name
    result=dict(complete=True,device_execution=False,before=BEFORE,after=AFTER,source_trees=trees,
        reviewed_production_files=implementation['production_sha256'],prefix_rerun=prefix,
        full_helper_mutation_cases=full['route_cases'],planner_cases=full['planner_cases'],
        rtc_rerun=reruns['rtc'],generator_rerun=reruns['generator'],
        retained_byte_identical_generated_sources=len(old_report['sources']),
        expanded_comparison='Complete old/new helper bodies and stride/distance assignment, returned state and exceptions; same mock registry and reachable CC input invariants.',
        limits='CPU-only differential checks, constructed CC preconditions and retained generation matrix; not an exhaustive public API or GPU validation.',
        elapsed_seconds=time.monotonic()-started,
        evidence_sha256={str(p.relative_to(ROOT)):sha(p) for p in ART.rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.inc','.out','.err')})
    (REC/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('AUDIT_COMPLETE',str(REC/'audit.json'),flush=True)


if __name__ == '__main__':
    main()
