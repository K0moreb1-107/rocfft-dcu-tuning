"""Controlled RTC-only ablations of the accepted library, with original v3 checks."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
import cufft261012_contract as contract
from validate_cc_local_unified import read_numerical_outputs
from prototype_cc_957127 import mirrored_pre,output_hoist,scope_end
from io_hoist_cc_957127 import input_hoist,spectrum_hoist,merge_column_boundaries

RECORD=ROOT/'experiments/EXP-128/records/regression-955252-20261022/ablation-957127'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/ablation-957127'
ORIGINAL=ROOT/'experiments/EXP-128/runs/EXP-128-cc-regression-955252-diagnostic-20261022'
RUN_ID='EXP-128-cc-regression-ablation-20261022'


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def transform(source,name,variant,previous_sources):
    if variant=='identity': return source
    role=int(re.search(r'_role(\d+)_',name)[1])
    c,q=map(int,re.search(r'_C(\d+)_Q(\d+)_',name).groups())
    wgs,p=map(int,re.search(r'_wgs_(\d+)_tpt_(\d+)_',name).groups())
    assert wgs%p==0
    t=wgs//p
    if (role==4 and variant=='column_restore') or (role==7 and variant=='input_restore'):
        previous_name=name.replace('_cc_local_v2_','_cc_local_v1_')
        if variant=='input_restore': previous_name=re.sub(r'_reg$','_lds',previous_name)
        other=previous_sources[previous_name]
        def arguments(text,entry):
            start=text.index(entry+'(')+len(entry)+1
            return text[start:text.index(') {',start)]
        assert arguments(source,name)==arguments(other,previous_name),'restored body ABI differs'
        current_global=source[source.index('extern "C" __global__'):]
        previous_global=other[other.index('extern "C" __global__'):]
        assert re.search(r'scalar_type R\[\d+\]',current_global)[0] == re.search(
            r'scalar_type R\[\d+\]',previous_global)[0],'restored register map size differs'
        if variant=='input_restore':
            begin='// load global into registers\n';end='// calc the thread_in_device'
            a,b=source.index(begin),source.index(end,source.index(begin))
            x,y=other.index(begin),other.index(end,other.index(begin))
            return source[:a]+other[x:y]+source[b:]
        starts=[m.start() for m in re.finditer(r'const unsigned int cc_store_lane =',source)]
        old_starts=[m.start() for m in re.finditer(r'const unsigned int cc_store_lane =',other)]
        assert len(starts)==len(old_starts)==2
        for a,b in reversed(list(zip(starts,old_starts))):
            source=source[:a]+other[b:scope_end(other,b)]+source[scope_end(source,a):]
        return source
    if role==4 and variant in ('column_merge','combined'):
        source=merge_column_boundaries(source,q)
    if role==5:
        if variant in ('pre_mirror','combined') and name.endswith('_lds'):
            source=mirrored_pre(source,c,q,p,t)
        if variant in ('row_hoist','combined'):
            source=output_hoist(source,c,q,p,t)
    if role==7 and variant in ('row_hoist','combined'):
        source=spectrum_hoist(input_hoist(source,c,q,p,t),c,q,p,t)
    return source


def compile_host(source,output):
    command=['g++','-O2','-std=c++17','-shared','-fPIC','-D__HIP_PLATFORM_AMD__',
             '-I'+mgr.DTK+'/hip/include',str(source),'-ldl','-o',str(output)]
    proc=subprocess.run(command,env=mgr.environment(ART),capture_output=True,text=True,timeout=120)
    output.with_suffix('.compile.out').write_text(proc.stdout)
    output.with_suffix('.compile.err').write_text(proc.stderr)
    mgr.require(proc.returncode==0,'host diagnostic compiler failed: '+proc.stderr[-1500:])
    return dict(command=command,binary=str(output),sha256=sha(output))


def host_interposition_test(shim):
    folder=ART/'host-test'
    folder.mkdir(exist_ok=True)
    original,replacement=folder/'original.cpp',folder/'replacement.cpp'
    original.write_text('__global__ void probe() {}\n')
    replacement.write_text('__global__ void probe() {}\n// diagnostic replacement\n')
    rules=folder/'rules.tsv'
    rules.write_text('probe\t'+str(original)+'\t'+str(replacement)+'\n')
    stub=folder/'stub.cpp'
    stub.write_text('''#include <hip/hiprtc.h>
#include <fstream>
#include <cstdlib>
extern "C" hiprtcResult hiprtcCreateProgram(hiprtcProgram*,const char* s,const char*,int,const char**,const char**) {
std::ofstream(std::getenv("CC_RTC_STUB_OUT")) << s; return HIPRTC_SUCCESS;
}
''')
    stub_so=folder/'stub.so'
    compile_host(stub,stub_so)
    code='''import ctypes,os
from pathlib import Path
f=ctypes.CDLL(None).hiprtcCreateProgram
f.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p]
f.restype=ctypes.c_int
p=ctypes.c_void_p()
call=lambda s:f(ctypes.byref(p),s.encode(),b"test.hip",0,None,None)
assert call("__global__ void probe() {}\\n")==0
assert Path(os.environ["CC_RTC_STUB_OUT"]).read_text().endswith("// diagnostic replacement\\n")
assert call("unrelated source")==0
assert Path(os.environ["CC_RTC_STUB_OUT"]).read_text()=="unrelated source"
assert call("__global__ void probe() {int x;}\\n")!=0
print("replacement, delegation and mismatch rejection passed")
'''
    env=mgr.environment(ART)
    env.update(LD_PRELOAD=str(shim)+':'+str(stub_so),CC_RTC_DIAG_RULES=str(rules),
               CC_RTC_DIAG_LOG=str(folder/'audit.tsv'),CC_RTC_STUB_OUT=str(folder/'received.txt'))
    proc=subprocess.run([mgr.PYTHON,'-B','-c',code],env=env,capture_output=True,text=True,timeout=60)
    result=dict(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr)
    save(RECORD/'host-interposition-test.json',result)
    mgr.require(proc.returncode==0,'host diagnostic interposition test failed: '+proc.stderr)


def prepare():
    ART.mkdir(exist_ok=True)
    RECORD.mkdir(exist_ok=True)
    accepted=read(ORIGINAL/'diagnostic-result.json')
    mgr.require(accepted['complete'] and not accepted['failures'],'original diagnostic incomplete')
    by_key={(x['N'],x['func']):x for x in accepted['traces'] if x['arm']=='candidate'}
    previous={(x['N'],x['func']):x for x in accepted['traces'] if x['arm']=='previous'}
    cases=[(167042,'z2d_1d'),(65536,'d2z_1d')]
    cases += [(n,'z2d_1d') for n in (69938,72250,92480,120224,142688,65536,131072,497664,591872,1048576)]
    cases += [(n,'d2z_1d') for n in (131072,69938,73008,81120,82134,142688,167042,346112)]
    seeds,trials={},[]
    for case_index,(n,func) in enumerate(cases):
        item=by_key[n,func]
        rtc=Path(item['folder'])/'metadata/rtc.txt'
        sources=dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',rtc.read_text(),re.M|re.S))
        # rtc_cache.cpp inserts exactly one newline before the RTC_END delimiter.
        sources={name:text[:-1] for name,text in sources.items() if '_cc_local_v2_role' in name}
        previous_rtc=Path(previous[n,func]['folder'])/'metadata/rtc.txt'
        previous_sources={name:text[:-1] for name,text in re.findall(
            r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',previous_rtc.read_text(),re.M|re.S)}
        mgr.require(all(name in sources for name in item['trace']['kernel_names']),'actual source missing')
        seeds[str(n)+'-'+func]=dict(path=str(rtc),sha256=sha(rtc),
            previous_path=str(previous_rtc),previous_sha256=sha(previous_rtc),
            kernel_names=item['trace']['kernel_names'],source_names=sorted(sources))
        variants=['original','row_hoist'] if func=='d2z_1d' else ['original','column_merge','row_hoist','combined']
        if func=='z2d_1d' and '_C1024_' in item['trace']['kernel_names'][0]:
            variants.insert(2,'column_restore')
        if func=='d2z_1d' and '_len_169_' in item['trace']['kernel_names'][1]:
            variants.append('input_restore')
        if func=='z2d_1d' and item['trace']['kernel_names'][1].endswith('_lds'):
            variants.insert(-1,'pre_mirror')
        if case_index%2: variants.reverse()
        if (n,func) in ((167042,'z2d_1d'),(65536,'d2z_1d')):
            variants.insert(variants.index('original')+1,'identity')
        for variant in variants:
            folder=ART/'sources'/(str(n)+'-'+func)/variant
            folder.mkdir(parents=True,exist_ok=True)
            rule_lines,rules,required=[],[],[]
            for source_index,(name,text) in enumerate(sources.items()):
                if variant=='original': break
                replacement=transform(text,name,variant,previous_sources)
                original=folder/(str(source_index)+'-original.cpp')
                changed=folder/(str(source_index)+'-variant.cpp')
                original.write_text(text);changed.write_text(replacement)
                rule_lines.append(name+'\t'+str(original)+'\t'+str(changed))
                status='identity' if text==replacement else 'override'
                rules.append(dict(name=name,original=str(original),original_sha256=sha(original),
                    replacement=str(changed),replacement_sha256=sha(changed),status=status))
                if status=='override' or variant=='identity': required.append(name)
            manifest=folder/'rules.tsv'
            manifest.write_text('\n'.join(rule_lines)+'\n')
            if variant!='original': mgr.require(required,'ablation does not change this case')
            trials.append(dict(index=len(trials),N=n,func=func,variant=variant,
                metadata=False,smoke=case_index<2,
                rules_manifest=str(manifest),rules_manifest_sha256=sha(manifest),rules=rules,
                required_source_names=required))
    measured_processes=len(trials)
    metadata_cases={(167042,'z2d_1d'),(167042,'d2z_1d'),(82134,'d2z_1d'),(497664,'z2d_1d')}
    for item in list(trials):
        if (item['N'],item['func']) in metadata_cases and item['variant']!='identity':
            trials.append(dict(item,index=len(trials),metadata=True,smoke=False))
    shim=ART/'rtc_source_diagnostic.so'
    build=compile_host(ROOT/'experiments/EXP-128/scripts/rtc_source_diagnostic.cpp',shim)
    host_interposition_test(shim)
    save(RECORD/'selection.json',dict(cases=[dict(N=n,func=func) for n,func in cases],
        source_diagnostic='957127',seeds=seeds,trials=trials,shim=build,
        protocol='Same accepted library and v3 ramp input/check/10 warmups/30 event samples; RTC-only controlled ablations.',
        measured_processes=measured_processes,metadata_processes=len(trials)-measured_processes,
        formal=False,scope='Shared class changes; three C1024 cases and three Q169 cases plus power-of-two and odd endpoints.'))
    print(json.dumps(dict(complete=True,cases=len(cases),processes=len(trials),
        shim=build,host_interposition_test='passed',selection=str(RECORD/'selection.json')),indent=2))


def run(a):
    cfg=read(a.config)
    allocation=mgr.common.single_gpu_allocation(os.environ)
    selected=cfg['rtc_ablation']
    program=cfg['diagnostic_program']
    env=mgr.environment(a.cache);env['FFT_TEST_ITERS']='30'
    gpu=json.loads(subprocess.check_output([program['identity']],env=env,text=True))
    mgr.require(gpu==program['gpu'],'diagnostic GPU/runtime differs')
    for key,digest in [('binary',program['binary_sha256']),('identity',program['identity_sha256'])]:
        mgr.require(sha(mgr.inside(program[key]))==digest,'diagnostic program identity differs')
    arm=cfg['arms']['candidate']
    library=mgr.inside(arm['install'])/'lib/librocfft.so.0.1'
    mgr.require(sha(library)==arm['library_sha256'],'diagnostic library differs')
    mgr.require(sha(Path(selected['shim']['binary']))==selected['shim']['sha256'],'diagnostic shim differs')
    result=dict(complete=False,formal=False,job_id=os.environ['SLURM_JOB_ID'],gpu=gpu,
        start=datetime.datetime.now(datetime.timezone.utc).isoformat(),trials=[],failures=[])
    try:
        for item in selected['trials']:
            folder=a.run/'cases'/('%03d-%d-%s-%s-%s'%(item['index'],item['N'],item['func'],item['variant'],
                                                  'metadata' if item['metadata'] else 'timing'))
            output=folder/'harness';output.mkdir(parents=True)
            entry=dict(item,valid=False,folder=str(folder))
            try:
                seed=selected['seeds'][str(item['N'])+'-'+item['func']]
                mgr.require(sha(Path(seed['path']))==seed['sha256'],'diagnostic source evidence differs')
                mgr.require(sha(Path(seed['previous_path']))==seed['previous_sha256'],'previous source evidence differs')
                trial_env=dict(env,LD_PRELOAD=str(library),LD_LIBRARY_PATH=str(library.parent)+':'+env['LD_LIBRARY_PATH'],
                               FFT_TEST_OUT=str(output))
                if item['metadata']:
                    trial_env.update(ROCFFT_LAYER='8',ROCFFT_LOG_PLAN_PATH=str(folder/'plan.txt'))
                if item['variant']!='original':
                    mgr.require(sha(Path(item['rules_manifest']))==item['rules_manifest_sha256'],'diagnostic rules differ')
                    for rule in item['rules']:
                        for key in ('original','replacement'):
                            mgr.require(sha(Path(rule[key]))==rule[key+'_sha256'],'diagnostic source rule differs')
                    trial_env.update(LD_PRELOAD=selected['shim']['binary']+':'+str(library),
                        CC_RTC_DIAG_RULES=item['rules_manifest'],CC_RTC_DIAG_LOG=str(folder/'source-audit.tsv'))
                linked=subprocess.check_output(['ldd',program['binary']],env=trial_env,text=True)
                (folder/'ldd.txt').write_text(linked)
                loaded=[Path(line.strip().split('=>')[-1].strip().split()[0]).resolve()
                        for line in linked.splitlines() if 'librocfft.so' in line]
                mgr.require('not found' not in linked and set(loaded)=={library.resolve()},'wrong diagnostic library loaded')
                with (folder/'process.out').open('xb') as out,(folder/'process.err').open('xb') as err:
                    process=subprocess.run([program['binary'],str(item['N']),'1',item['func']],env=trial_env,
                        cwd=folder,stdout=out,stderr=err,timeout=180)
                check=read_numerical_outputs(output,item['N'],item['func'],process.returncode)
                mgr.require(process.returncode==0,'timing/check program failed')
                audit=[]
                if item['variant']!='original':
                    audit=[line.split('\t') for line in (folder/'source-audit.tsv').read_text().splitlines()]
                    mgr.require(all(status in ('override','identity') for status,name in audit),'diagnostic source mismatch')
                    hits={name for status,name in audit}
                    mgr.require(set(item['required_source_names'])<=hits,'a required timing/correctness source was not replaced')
                row=contract.read_rows(output/'fft_test_1d.csv')[0]
                samples=contract.read_samples(output/'fft_test_1d.samples.csv')
                values=contract.validate_process(row,samples,check,item['N'],item['func'],30)
                entry.update(valid=True,check=check,samples_ms=values,source_audit=audit,
                             statistics_ms=contract.statistics_for(values))
                if item['metadata']:
                    occupancies=list(map(int,re.findall(r'Kernel occupancy:\s*(\d+)',(folder/'plan.txt').read_text())))
                    mgr.require(len(occupancies)>=80 and occupancies[-80:]==occupancies[-2:]*40,
                                'metadata execution/occupancy sequence incomplete')
                    entry['maximum_active_workgroups']=occupancies[-2:]
            except Exception as error:
                entry['error']=dict(kind=type(error).__name__,message=str(error))
                result['failures'].append(dict(N=item['N'],func=item['func'],variant=item['variant'],error=entry['error']))
            result['trials'].append(entry)
            result['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            save(a.run/'ablation-result.json',result)
            print(item['N'],item['func'],item['variant'],entry['valid'],entry.get('error',''),flush=True)
            # The first case exercises shared mirrored input, both boundaries and the callback check.
            if item['smoke'] and not entry['valid']:
                break
        result['complete']=not result['failures'] and len(result['trials'])==len(selected['trials'])
    finally:
        save(a.run/'ablation-result.json',result)
    mgr.require(result['complete'],'ablation errors retained in ablation-result.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    for name in ('config','run','build','cache'): parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    if args.prepare: prepare()
    else:
        mgr.require(all(getattr(args,name) is not None for name in ('config','run','build','cache')),'diagnostic arguments missing')
        run(args)
