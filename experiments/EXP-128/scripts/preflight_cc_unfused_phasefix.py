"""Reproduce the actual phase-capacity exception on CPU and audit every default CC choice."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
SOURCE=ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
OLD=ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-unfused-cc-20261027'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/unfused-phasefix-20261027'
RECORD=ROOT/'experiments/EXP-128/records/unfused-phasefix-20261027'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def function(text,signature):
    start=text.index(signature);a=text.index('{',start);depth=0
    for i in range(a,len(text)):
        if text[i]=='{':depth+=1
        if text[i]=='}':
            depth-=1
            if not depth:return text[start:i+1]
    raise ValueError('function closing brace missing')
def run(cmd,label,cwd=None):
    p=subprocess.run(list(map(str,cmd)),cwd=cwd or ART,env=mgr.environment(ART),capture_output=True,text=True,timeout=180)
    (ART/(label+'.out')).write_text(p.stdout);(ART/(label+'.err')).write_text(p.stderr)
    mgr.require(p.returncode==0,label+': '+p.stderr[-2000:]);return p.stdout


def main():
    ART.mkdir(exist_ok=True);RECORD.mkdir(exist_ok=True)
    flags={};metadata=[]
    for path in (OLD/'library/src/device').glob('function_pool_init_*.cpp'):
        lines=path.read_text().splitlines()
        for i,line in enumerate(lines):
            m=re.search(r'insert_default_entry\(FMKey\((\d+), 0, rocfft_precision_double, CS_KERNEL_STOCKHAM_BLOCK_CC, NONE,',line)
            if not m:continue
            declaration=lines[i-1];flag=re.search(r'kernel = FFTKernel\((true|false),',declaration)
            mgr.require(flag is not None,'native phase flag missing');c=int(m[1]);v=flag[1]=='true'
            mgr.require(c not in flags or flags[c]==v,'duplicate conflicting kernel flags');flags[c]=v
            metadata.append(dict(C=c,use3=v,path=str(path.relative_to(ROOT)),line=i+1,
                initialization=declaration,source_sha256=sha(path)))
    public=json.loads((ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json').read_text())['public']
    mgr.require(len(public)==194 and all(x['C'] in flags for x in public),'incomplete native catalog')
    plan=SOURCE/'library/src/plan.cpp';node=SOURCE/'library/src/tree_node_1D.cpp'
    getter=function(plan.read_text(),'void get_large_twd_base_steps(')
    selection=re.search(r'largeTwd3Steps\s*=\s*kernel.use_3steps_large_twd\s*&&[^;]+;',node.read_text())[0]
    # Compile the production range-checking function, rather than reimplementing its exception.
    cpp='#include <algorithm>\n#include <cmath>\n#include <iostream>\n#include <stdexcept>\n#include "'+str(SOURCE/'shared/arithmetic.h')+'"\n'+getter+'\n'
    cpp+='''int main(){size_t n;bool requested;while(std::cin>>n>>requested){
    for(int mode=0;mode<3;++mode){size_t large1D=mode==2?2*n:n;
    struct {bool use_3steps_large_twd;}kernel{requested};bool largeTwd3Steps;
    if(mode==0)largeTwd3Steps=requested;
    else {'''+selection+'''}
    size_t base=0,steps=0;try{get_large_twd_base_steps(large1D,largeTwd3Steps,base,steps);
    std::cout<<n<<" "<<requested<<" "<<mode<<" OK "<<base<<" "<<steps<<"\\n";}
    catch(const std::exception& e){std::cout<<n<<" "<<requested<<" "<<mode<<" ERROR "<<e.what()<<"\\n";}}}}'''
    source=ART/'phase-capacity.cpp';source.write_text(cpp);exe=ART/'phase-capacity'
    run([mgr.DTK+'/llvm/bin/clang++','-O2','-std=c++14',source,'-o',exe],'compile-model')
    requests={(x['N']//2,flags[x['C']]) for x in public}
    requests|={(n,v) for n in ((1<<18)-1,1<<18,(1<<18)+1,351232,384659,456533,(1<<23)) for v in (False,True)}
    payload=''.join('%d %d\n'%(n,v) for n,v in sorted(requests))
    p=subprocess.run([str(exe)],input=payload,env=mgr.environment(ART),capture_output=True,text=True,check=True)
    (ART/'phase-capacity.out').write_text(p.stdout)
    results={}
    for line in p.stdout.splitlines():
        n,flag,mode,status,*fields=line.split();results[int(n),bool(int(flag)),int(mode)]=dict(status=status,values=fields)
    changed=[];catalog=[]
    partial=json.loads((ROOT/'experiments/EXP-128/records/boundary-v5-20261027/inspection-983952/audit.json').read_text())
    complete=json.loads((ROOT/'experiments/EXP-128/records/boundary-v5-20261027/inspection-983952/valid-four-arm-cases.json').read_text())
    completed={x['N'] for x in complete}
    for x in public:
        n=x['N'];flag=flags[x['C']];old=results[n//2,flag,0];new=results[n//2,flag,1]
        mgr.require(new['status']=='OK','new selection still rejects a registered size')
        old_fused=results[n//2,flag,2]
        # The previous folded-column role already applied this same capacity guard.
        mgr.require(old_fused['status']=='OK','fused role lacks a supported phase table')
        same=old==new
        if not same:
            mgr.require(old['status']=='ERROR' and 'must be 3-steps' in ' '.join(old['values']),
                        'unexplained selector difference')
            changed.append(dict(x,large1D=n//2,old=old,new=new))
        if n in completed:mgr.require(same,'completed measured case changes selection')
        catalog.append(dict(x,requested_three_steps=flag,old=old,new=new,
            completed_four_arm=n in completed,base=int(new['values'][0]),steps=int(new['values'][1])))
    mgr.require({x['N'] for x in changed}=={702464,769318,913066},'unexpected affected class')
    # The unfused and fused registrations retain the same FFT decomposition.
    commands=json.loads((OLD/'compile_commands.json').read_text())
    entry=next(x for x in commands if x['file'].endswith('/tree_node_1D.cpp'))
    args=shlex.split(entry['command']);args[args.index('-o')+1]=str(ART/'tree_node_1D.cpp.o')
    run(args,'compile-node',entry['directory'])
    proof=dict(complete=True,device_execution=False,geometries=len(public),catalog=catalog,affected=changed,
        original_368_cases_unchanged=True,completed_N=len(completed),native_metadata=metadata,
        original_failure=partial['failures'],exact_getter_source=getter,exact_new_selector=selection,
        production_sources_sha256={str(p.relative_to(ROOT)):sha(p) for p in (node,plan,SOURCE/'shared/arithmetic.h')},
        model_source_sha256=sha(source),model_output_sha256=sha(ART/'phase-capacity.out'),
        old_getter_351232=results[351232,True,0],new_getter_351232=results[351232,True,1],
        limits='CPU reproduction and native registration facts; device numerical and actual-path acceptance still required.')
    write(RECORD/'phase-selector-model.json',proof)
    print(json.dumps(dict(complete=True,affected=changed,completed_N_unchanged=len(completed),
        source_compile=True,device_execution=False),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
