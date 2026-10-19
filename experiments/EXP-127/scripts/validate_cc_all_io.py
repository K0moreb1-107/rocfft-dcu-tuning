"""Validate generic CC I/O policies across the complete registered catalogue."""
import argparse
from collections import Counter
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def normalized_source(text):
    return re.sub(r'^#define ROCFFT_CALLBACKS_ENABLED\s*','',text.strip()).strip()


def run(command,env,folder,label,expected=0,timeout=300,cwd=None):
    folder.mkdir(parents=True,exist_ok=True)
    command=list(map(str,command))
    with (folder/(label+'.out')).open('xb') as out,(folder/(label+'.err')).open('xb') as err:
        process=subprocess.run(command,env=env,cwd=cwd or folder,stdout=out,stderr=err,timeout=timeout)
    mgr.dumps(folder/(label+'-command.json'),dict(command=command,returncode=process.returncode))
    mgr.require(process.returncode==expected,label+' failed: '+str(folder))


def trace_plan(binary,n,func,env,folder,old,contract,expected=None):
    meta=folder/'metadata';data=meta/'harness';data.mkdir(parents=True)
    selected=dict(env,FFT_TEST_OUT=str(data),ROCFFT_LAYER='40',
        ROCFFT_LOG_PLAN_PATH=str(meta/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(meta/'rtc.txt'))
    run([binary,n,1,func],selected,meta,'plan')
    rows=contract.read_rows(data/'fft_test_1d.csv')
    mgr.require(len(rows)==1,'wrong metadata row count')
    contract.validate_process(rows[0],contract.read_samples(data/'fft_test_1d.samples.csv'),
        contract.read_check(data/'fft_test_1d.check.csv'),n,func,30)
    plan=(meta/'plan.txt').read_text()
    generated=old.rtc_sources((meta/'rtc.txt').read_text())
    details=old.inspect_plan(plan,n,expected['C'],expected['Q'],func,True) if expected else None
    if details:
        details['grid']=[line.strip() for line in details['grid']]
    profile=folder/'profile';(profile/'data').mkdir(parents=True);(profile/'harness').mkdir()
    run([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
        '-o',profile/'trace','-d',profile/'data',binary,n,1,func],
        dict(env,FFT_TEST_OUT=str(profile/'harness')),profile,'trace')
    prows=contract.read_rows(profile/'harness/fft_test_1d.csv')
    mgr.require(len(prows)==1,'wrong profiled row count')
    contract.validate_process(prows[0],contract.read_samples(profile/'harness/fft_test_1d.samples.csv'),
        contract.read_check(profile/'harness/fft_test_1d.check.csv'),n,func,30)
    events=json.loads((profile/'trace.json').read_text())['traceEvents']
    device_events=[e for e in events if e.get('cat')=='HIPOPS']
    counts=Counter(e.get('name','') for e in device_events)
    if expected:
        transforms=[e for e in device_events if re.match(r'(fft_|c2r_even_pre|r2c_even_post|transpose_)',e.get('name',''))]
        leaves=details['leaf_count']
    else:
        # Controls may use convolution and transpose boundaries. Include their
        # repeated dispatches as well as the FFTs; setup tables are generated once.
        transforms=[e for e in device_events if counts[e.get('name','')]%41==0]
        grids=re.findall(r'GridParams\n(.*?)End GridParams',plan,re.S)
        mgr.require(len(grids)==41 and len(set(grids))==1,'control plan geometry changed')
        leaves=len(grids[0].strip().splitlines())
    transforms.sort(key=lambda e:int(e['args']['index']))
    mgr.require(leaves>0 and len(transforms)==41*leaves,'incomplete actual dispatch')
    names=[e['name'] for e in transforms[:leaves]]
    mgr.require(all([e['name'] for e in transforms[i*leaves:(i+1)*leaves]]==names for i in range(41)),
                'execution sequence changed')
    sources={name:hashlib.sha256(normalized_source(generated[name]).encode()).hexdigest()
             for name in names if name in generated}
    if expected:
        mgr.require(names==[x['name'] for x in expected['leaves']], 'actual default kernel identity differs from host proof')
        mgr.require(len(sources)==2,'missing actual default kernel sources')
        for leaf,name in zip(expected['leaves'],names):
            mgr.require(sources[name]==leaf['source_sha256'],'actual default generated source differs')
        mgr.require(details['grid']==expected['grid'],'actual launch allocation differs from host proof')
    normalize_args=lambda text:re.sub(r'f=0x[0-9a-f]+','f=KERNEL',text)
    result=dict(N=n,func=func,actual_names=names,source_sha256=sources,
        launch_arguments=[normalize_args(e['args']['args']) for e in transforms[:leaves]],
        plan_sha256=hashlib.sha256(plan.encode()).hexdigest())
    if details:result.update(details)
    return result


def compile_internal_fixture(build,source,fixture,output,env,folder):
    # The internal objects use relocatable device code. Its link step also
    # needs the bundled LLVM archive tool, which hipcc does not locate itself.
    env=dict(env,PATH=mgr.DTK+'/llvm/bin:'+env['PATH'])
    mgr.require((Path(mgr.DTK)/'llvm/bin/llvm-ar').is_file(),'bundled LLVM archive tool missing')
    commands=json.loads((build/'compile_commands.json').read_text())
    rec=next(x for x in commands if Path(x['file']).name=='plan.cpp')
    cwd=Path(rec['directory'])
    args=shlex.split(rec['command'])
    args[args.index('-o')+1]=str(output.with_suffix('.o'))
    args[args.index(rec['file'])]=str(fixture)
    args.insert(1,'-iquote'+str(source/'library/src'))
    args.insert(1,'-I'+str(source/'shared'))
    args.insert(1,'--offload-arch=gfx936')
    run(args,env,folder,'compile-internal',timeout=600,cwd=cwd)
    link_path=cwd/'CMakeFiles/rocfft.dir/link.txt'
    def expand(items):
        result=[]
        for item in items:
            result.extend(expand(shlex.split((cwd/item[1:]).read_text())) if item.startswith('@') else [item])
        return result
    link=expand(shlex.split(link_path.read_text()))
    index=link.index('-o');del link[index:index+2]
    link=[x for x in link if x!='-shared' and not x.startswith(('-Wl,-soname,','-Wl,--version-script='))]
    objects={(cwd/x).resolve():mgr.common.sha((cwd/x).resolve()) for x in link if x.endswith('.o')}
    run(link+[str(output.with_suffix('.o')),'-o',output],env,folder,'link-internal',timeout=600,cwd=cwd)
    mgr.require(output.is_file(),'internal fixture executable missing after link')
    for name in ('compile-internal.err','link-internal.err'):
        mgr.require('command not found' not in (folder/name).read_text(),'incomplete internal device link')
    return dict(binary_sha256=mgr.common.sha(output),link_recipe_sha256=mgr.common.sha(link_path),
                objects={str(p):h for p,h in objects.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','build-record','run','build','cache'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args()
    cfg=mgr.load(a.config);v=cfg['validation'];mode=v['policy_index']
    built=json.loads(mgr.inside(a.build_record).read_text())
    mgr.require(built['complete'] and mgr.source_identity(cfg)==built['plan']['source_identity'],'source/build changed')
    mgr.validation_hook(cfg)
    frozen=json.loads(mgr.inside(v['runtime_inputs']).read_text())
    for name,digest in frozen['files'].items():
        path=mgr.inside(name)
        mgr.require(mgr.common.sha(path)==digest,'validation input changed: '+name)
        blob=subprocess.check_output(['git','-C',str(ROOT),'show',cfg['build']['source_commit']+':'+str(path.relative_to(ROOT))])
        mgr.require(hashlib.sha256(blob).hexdigest()==digest,'validation input not committed: '+name)
    cache=mgr.inside(a.cache);env=mgr.environment(cache);env['FFT_TEST_ITERS']='30'
    lib=mgr.inside(built['arm']['install'])/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(lib)==built['arm']['library_sha256'],'library changed')
    cache_text=(mgr.inside(a.build)/'CMakeCache.txt').read_text()
    mgr.require('ROCFFT_CC_REAL_FUSION:BOOL=ON' in cache_text
        and 'ROCFFT_REAL_PAIR_SCALAR_CAPACITY:BOOL=OFF' in cache_text
        and 'ROCFFT_REAL_PAIR_IO_POLICY:STRING='+v['policy'] in cache_text,'build policy mismatch')
    identity=mgr.inside(v['identity_binary']);binary=mgr.inside(v['timing_binary'])
    mgr.require(mgr.common.sha(identity)==v['identity_binary_sha256']
                and mgr.common.sha(binary)==v['timing_binary_sha256'],'helper changed')
    gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(gpu['count']==1 and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16)>0
                and all(gpu[k]==v['gpu'][k] for k in ('arch','runtime_version','driver_version')),
                'GPU/runtime differs')
    folder=mgr.inside(a.run)/'cc-all-io-validation';folder.mkdir()
    selected=dict(env,LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(lib.parent)+':'+env['LD_LIBRARY_PATH'])
    linked=subprocess.check_output(['ldd',str(binary)],env=selected,text=True)
    loaded=[mgr.inside(line.split('=>')[-1].strip().split()[0]) for line in linked.splitlines() if 'librocfft.so' in line]
    mgr.require('not found' not in linked and loaded==[lib],'wrong actual rocFFT library')
    (folder/'ldd.txt').write_text(linked)
    old=module('cc_all_previous_validator',mgr.inside(v['previous_validator']))
    refs=module('cc_all_public_references',mgr.inside(v['public_references']))
    boundary_refs=module('cc_all_boundary_references',mgr.inside(v['boundary_references']))
    contract=old.contract
    coverage=json.loads(mgr.inside(v['coverage']).read_text())
    model=json.loads(mgr.inside(v['coordinate_proof']).read_text())
    expected=json.loads(mgr.inside(v['host_expected']).read_text())[str(mode)]
    guard=mgr.inside(a.build)/'cc-all-public-guard'
    install=mgr.inside(built['arm']['install']);source=mgr.inside(cfg['build']['source_dir'])
    run([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',v['public_guard'],
        '-I'+str(install/'include'),'-I'+str(source/'shared'),'-L'+str(install/'lib'),
        '-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-lstdc++fs','-o',guard],selected,folder,'compile-public',timeout=600)
    record=dict(complete=False,formal=False,policy=v['policy'],source_commit=built['arm']['source_commit'],
        library_sha256=built['arm']['library_sha256'],gpu=gpu,start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        default_cases=[],boundary_cases=[],controls=[],folded_regressions=[],failures=[])

    def guard_case(n,func,gfolder,genv,geometry,expected_return=0):
        ref_folder=cache/'cc-all-references'/gfolder.relative_to(folder)
        ref_folder.mkdir(parents=True)
        manifest,metadata=refs.references(n,func.removesuffix('_1d'),True,ref_folder)
        mgr.require(len(metadata)==14,'public reference matrix changed')
        logged=dict(genv,ROCFFT_LAYER='40',ROCFFT_LOG_PLAN_PATH=str(gfolder/'plan.txt'),
                    ROCFFT_LOG_RTC_PATH=str(gfolder/'rtc.txt'))
        run([guard,n,func.removesuffix('_1d'),manifest,'callbacks'],logged,gfolder,'guard',expected_return)
        if expected_return==0:
            text=(gfolder/'guard.out').read_text()
            mgr.require(text.count('EVEN_CC_GUARD_PASS')==14 and 'EVEN_CC_ALL_PASS cases=14' in text,'public checks incomplete')
            plan=(gfolder/'plan.txt').read_text()
            # Every scale/callback variant must keep the same registered backend.
            chosen=geometry['leaves'][0 if func=='z2d_1d' else 1]
            if chosen['generic']:
                pattern=r'EXP126 pair geometry C=(\d+) Q=(\d+) T=(\d+) W=(\d+) LDS=(\d+)'
                actual=set(tuple(map(int,m)) for m in re.findall(pattern,plan))
                mgr.require(actual=={(geometry['C'],geometry['Q'],chosen['T'],chosen['W'],chosen['LDS'])},'guard allocation changed')
                generated=old.rtc_sources((gfolder/'rtc.txt').read_text())
                marker='paired_pre_columns_v2_' if func=='z2d_1d' else 'generic_paired_post_v2_'
                names=[name for name in generated if marker in name]
                mgr.require(names and any('_CB' in name for name in names),'missing callback boundary source')
                for name in names:
                    mgr.require('_'+chosen['exchange']+'_packed1_phase_' in name
                        and '_wgs_'+str(chosen['W'])+'_tpt_'+str(chosen['P'])+'_' in name,
                        'guard compiled a different boundary backend')
        return dict(references=metadata,expected_returncode=expected_return)

    try:
        for case in coverage['cases']:
            key=str(case['N'])+'_'+str(int(case['func']=='z2d_1d'))
            actual=trace_plan(binary,case['N'],case['func'],selected,folder/'default'/key,old,contract,expected[key])
            actual['guard']=guard_case(case['N'],case['func'],folder/'default'/key/'guard-callbacks',selected,expected[key])
            record['default_cases'].append(actual)
        # All 54 boundary configurations, including those with no eligible
        # default opposite kernel, are checked independently against full FFT identities.
        internal=mgr.inside(a.build)/'cc-all-boundary-guard'
        record['internal_fixture']=compile_internal_fixture(mgr.inside(a.build),source,
            mgr.inside(v['boundary_guard']),internal,env,folder/'internal-build')
        manifest,metadata=boundary_refs.references(model,cache/'cc-all-boundary-references')
        benv=dict(env,ROCFFT_LAYER='32',ROCFFT_LOG_RTC_PATH=str(folder/'boundary-rtc.txt'))
        # This executable links the candidate's actual internal objects. Do not
        # preload a second copy of rocFFT into it.
        benv.pop('LD_PRELOAD',None)
        run([internal,manifest,mode],benv,folder,'all-boundaries',timeout=4*3600)
        output=(folder/'all-boundaries.out').read_text()
        lines=re.findall(r'^CC_BOUNDARY_PASS (.+)$',output,re.M)
        mgr.require(len(lines)==len(metadata) and 'CC_BOUNDARY_ALL_PASS '+str(len(metadata)) in output,'boundary coverage incomplete')
        for line,meta in zip(lines,metadata):
            fields=line.split();case=model['results'][meta['case_index']]
            mgr.require(fields[0]==meta['id'] and list(map(int,fields[1:7]))==
                [meta['N'],int(meta['pre']),meta['C'],meta['Q'],case['P'],case['T']], 'boundary geometry mismatch')
            exchange=fields[10]
            mgr.require(mode==0 or exchange==('direct_complex' if mode==1 else 'direct_scalar'),'boundary policy missing')
            wanted=case['scalar_LDS_bytes'] if exchange=='direct_scalar' else case['complex_LDS_bytes']
            mgr.require(int(fields[7])==case['blocks'] and int(fields[8])==case['W']
                and int(fields[9])==wanted and int(fields[12])==int(meta['callbacks'])
                and float(fields[13])==meta['scale'] and float(fields[14])<1e-9
                and '_factors_'+'_'.join(map(str,case['factors']))+'_wgs_' in fields[15],
                'boundary launch/numerical mismatch')
            record['boundary_cases'].append(dict(meta,exchange=exchange,LDS_bytes=wanted,
                phase=int(fields[11]),max_error=float(fields[14]),kernel=fields[15]))
        for case in coverage['controls']:
            record['controls'].append(trace_plan(binary,case['N'],case['func'],selected,
                folder/'controls'/(str(case['N'])+'_'+case['func']),old,contract))
        # Preserve the distinct folded algorithm and both correctness-only
        # load overrides. Formal performance still uses only registered defaults.
        for case in coverage['folded']:
            key=str(case['N'])+'_1';geometry=expected[key]
            for load in ('registers','lds'):
                genv=dict(selected,ROCFFT_EXP125_LOCAL_REAL_LOAD=load)
                gfolder=folder/'folded'/str(case['N'])/load
                checked=guard_case(case['N'],'z2d_1d',gfolder,genv,geometry)
                block=(gfolder/'plan.txt').read_text().split('scheme: CS_KERNEL_STOCKHAM_BLOCK_CC',1)[1].split('scheme:',1)[0]
                mode_name='FORCE_OFF_OR_NOT_SUPPORT' if load=='lds' else 'TRY_ENABLE_IF_SUPPORT'
                mgr.require('Direct_to_from_Reg: '+mode_name in block,'folded load override ignored')
                record['folded_regressions'].append(dict(case,load=load,**checked))
        negative=v['negative_arm'];negative_lib=mgr.inside(negative['install'])/'lib/librocfft.so.0.1'
        mgr.require(mgr.common.sha(negative_lib)==negative['library_sha256'],'negative control changed')
        negative_env=dict(selected,LD_PRELOAD=str(negative_lib),LD_LIBRARY_PATH=str(negative_lib.parent)+':'+env['LD_LIBRARY_PATH'])
        neg_folder=folder/'negative-control'
        record['negative_control']=guard_case(131072,'z2d_1d',neg_folder,negative_env,expected['131072_1'],1)
        mgr.require('observed=2 expected=1' in (neg_folder/'guard.err').read_text(),'callback counter negative control ineffective')
        if mode>0:
            prior=mgr.inside(v['retained_build_record'])
            other_build=json.loads(prior.read_text());other=json.loads((prior.parent/'cc-all-io-validation.json').read_text())
            checked=json.loads((prior.parent/'post-build-validation.json').read_text())
            mgr.require(other_build['complete'] and checked['complete'] and other['complete']
                and other['policy']=='retained' and other_build['arm']['source_commit']==built['arm']['source_commit'],
                'same-source retained control not validated')
            left=dict(other_build['plan']['profile']);right=dict(built['plan']['profile'])
            mgr.require(left.pop('ROCFFT_REAL_PAIR_IO_POLICY')=='retained'
                and right.pop('ROCFFT_REAL_PAIR_IO_POLICY')==v['policy'] and left==right
                and other_build['compiler_version']==built['compiler_version'],'build profiles differ beyond backend policy')
            for current,previous in zip(record['default_cases'],other['default_cases']):
                mgr.require((current['N'],current['func'],current['C'],current['Q'])==
                    (previous['N'],previous['func'],previous['C'],previous['Q']),'default decomposition changed')
                for index,(name,old_name) in enumerate(zip(current['actual_names'],previous['actual_names'])):
                    boundary=(index==(0 if current['func']=='z2d_1d' else 1))
                    if not boundary or not expected[str(current['N'])+'_'+str(int(current['func']=='z2d_1d'))]['leaves'][index]['generic']:
                        mgr.require(name==old_name and current['source_sha256'][name]==previous['source_sha256'][old_name]
                            and current['launch_arguments'][index]==previous['launch_arguments'][index],'unrelated FFT stage changed')
            mgr.require(len(record['controls'])==len(other['controls']),'control coverage changed')
            for current,previous in zip(record['controls'],other['controls']):
                mgr.require(all(current[key]==previous[key] for key in
                    ('N','func','actual_names','source_sha256','launch_arguments')),
                    'out-of-scope control kernel/source/launch changed')
            record['retained_validation_sha256']=mgr.common.sha(prior.parent/'cc-all-io-validation.json')
        mgr.require(len(record['default_cases'])==len(coverage['cases']) and
            len(record['boundary_cases'])==model['cases']+model['configurations'],'coverage incomplete')
        mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity']
            and mgr.common.sha(lib)==built['arm']['library_sha256'],'source/library changed during validation')
        mgr.require(json.loads(subprocess.check_output([str(identity)],env=env,text=True))==gpu,
                    'allocated validation device changed')
        record['complete']=True
        print(json.dumps(dict(complete=True,policy=v['policy'],default_cases=len(record['default_cases']),
            configurations=model['configurations'],boundary_cases=len(record['boundary_cases']))),flush=True)
    except Exception as error:
        record['failures'].append(dict(type=type(error).__name__,message=str(error)))
        raise
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        record['files']={p.relative_to(folder).as_posix():mgr.common.sha(p) for p in folder.rglob('*') if p.is_file()}
        mgr.dumps(mgr.inside(a.run)/'cc-all-io-validation.json',record)


if __name__=='__main__':main()
