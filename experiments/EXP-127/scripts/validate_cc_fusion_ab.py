"""Validate same-source CC fusion on/off builds before any formal samples."""
import argparse
import datetime
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
import cufft261012_contract as contract


def launched(argv,env,folder,label):
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/(label+'.out')).open('xb') as out,(folder/(label+'.err')).open('xb') as err:
        result=subprocess.run(list(map(str,argv)),cwd=folder,env=env,stdout=out,stderr=err,timeout=300)
    mgr.dumps(folder/(label+'-command.json'),dict(argv=list(map(str,argv)),returncode=result.returncode))
    mgr.require(result.returncode==0,label+' failed: '+str(folder))


def nodes(plan):
    result=[];matches=list(re.finditer(r'(?m)^([ \t]*)scheme: (CS_[A-Z0-9_]+)',plan))
    for i,m in enumerate(matches):
        block=plan[m.end():matches[i+1].start() if i+1<len(matches) else len(plan)]
        length=re.search(r'(?m)^\s*length:\s*([^\n]+)',block)
        result.append(dict(scheme=m.group(2),length=list(map(int,re.findall(r'\d+',length.group(1)))) if length else []))
    return result


def rtc_sources(text):
    return dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S))


def inspect_plan(plan,n,c,q,func,fused):
    sequences=re.findall(r'GridParams\n(.*?)End GridParams',plan,re.S)
    mgr.require(len(sequences)==41 and len(set(sequences))==1,'missing/inconsistent repeated plan geometry')
    tree=nodes(plan[:plan.index('End GridParams')])
    cc=[p for p in tree if p['scheme']=='CS_KERNEL_STOCKHAM_BLOCK_CC']
    rc=[p for p in tree if p['scheme']=='CS_KERNEL_STOCKHAM_BLOCK_RC']
    mgr.require(len(cc)==len(rc)==1,'same CC+RC decomposition required')
    folded=fused and func=='z2d_1d' and n in (65536,131072,262144,524288,1048576)
    mgr.require(cc[0]['length']==[c,q+int(folded)] and rc[0]['length']==[q,c],
                'registered row/column decomposition changed')
    standalone=[p for p in tree if p['scheme'] in ('CS_KERNEL_R_TO_CMPLX','CS_KERNEL_CMPLX_TO_R')]
    mgr.require(len(standalone)==int(not fused),'standalone real boundary presence mismatch')
    mgr.require(len(sequences[0].strip().splitlines())==(2 if fused else 3),'wrong plan leaf count')
    return dict(C=c,Q=q,folded_columns=folded,leaf_count=2 if fused else 3,grid=sequences[0].strip().splitlines())



def completion_summary(record,fused):
    return json.dumps(dict(complete=True,fusion_enabled=fused,cases=len(record['cases']),
        independent_references=14*len(record['guards']),executions=28*len(record['guards'])))


def retained_sources(v,env,binary,case,folder,expected_names):
    arm=v['retained_arm'];install=mgr.inside(arm['install']);lib=install/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(lib)==arm['library_sha256'],'retained library changed')
    provenance=mgr.inside(arm['build_provenance'])
    mgr.require(mgr.common.sha(provenance)==v['retained_build_provenance_sha256'],
                'retained build provenance changed')
    built=json.loads(provenance.read_text())
    mgr.require(built['complete'] and all(built['arm'][key]==arm[key] for key in
                ('install','source_commit','library_sha256')),'retained build identity mismatch')
    selected=dict(env,LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(lib.parent)+':'+env['LD_LIBRARY_PATH'])
    linked=subprocess.check_output(['ldd',str(binary)],env=selected,text=True)
    loaded=[mgr.inside(line.split('=>')[-1].strip().split()[0])
            for line in linked.splitlines() if 'librocfft.so' in line]
    mgr.require('not found' not in linked and loaded==[lib],'retained library loading mismatch')
    folder.mkdir(parents=True);(folder/'ldd.txt').write_text(linked)
    output=folder/'harness';output.mkdir()
    selected.update(FFT_TEST_OUT=str(output),ROCFFT_LAYER='40',
        ROCFFT_LOG_PLAN_PATH=str(folder/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(folder/'rtc.txt'))
    launched([binary,case['N'],1,case['func']],selected,folder,'retained-plan')
    rows=contract.read_rows(output/'fft_test_1d.csv')
    mgr.require(len(rows)==1,'wrong retained metadata output count')
    contract.validate_process(rows[0],contract.read_samples(output/'fft_test_1d.samples.csv'),
        contract.read_check(output/'fft_test_1d.check.csv'),case['N'],case['func'],30)
    inspect_plan((folder/'plan.txt').read_text(),case['N'],case['C'],case['Q'],case['func'],True)
    # The log also contains precompiled callback variants. Select the two kernel
    # names from the candidate's actual default dispatch, rather than counting
    # every generated FFT variant as another executed kernel.
    generated=rtc_sources((folder/'rtc.txt').read_text())
    mgr.require(len(expected_names)==2 and len(set(expected_names))==2
                and all(name.startswith('fft_rtc_') and name in generated for name in expected_names),
                'missing retained source for actual CC dispatch')
    sources={name:generated[name] for name in expected_names}
    mgr.require(mgr.common.sha(lib)==arm['library_sha256'],'retained library changed during reference')
    return sources


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('config','build-record','run','build','cache'):ap.add_argument('--'+k,type=Path,required=True)
    a=ap.parse_args();cfg=mgr.load(a.config);v=cfg['validation'];fused=v['fusion_enabled']
    built=json.loads(mgr.inside(a.build_record).read_text());mgr.require(built['complete'],'build incomplete')
    mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity'],'source identity changed')
    mgr.validation_hook(cfg)
    runtime_inputs=json.loads(mgr.inside(v['runtime_inputs']).read_text())
    for name,digest in runtime_inputs['files'].items():
        path=mgr.inside(name)
        mgr.require(mgr.common.sha(path)==digest,'validation dependency changed: '+name)
        blob=subprocess.check_output(['git','-C',str(ROOT),'show',
            cfg['build']['source_commit']+':'+str(path.relative_to(ROOT))])
        mgr.require(hashlib.sha256(blob).hexdigest()==digest,'validation dependency is not committed')
    cache=mgr.inside(a.cache);env=mgr.environment(cache);env['FFT_TEST_ITERS']='30'
    install=mgr.inside(built['arm']['install']);lib=install/'lib/librocfft.so.0.1'
    mgr.require(mgr.common.sha(lib)==built['arm']['library_sha256'],'library changed')
    cache_text=(mgr.inside(a.build)/'CMakeCache.txt').read_text()
    mgr.require('ROCFFT_CC_REAL_FUSION:BOOL='+('ON' if fused else 'OFF') in cache_text,'build switch mismatch')
    coverage=json.loads(mgr.inside(v['coverage']).read_text())
    binary=mgr.inside(v['timing_binary']);identity=mgr.inside(v['identity_binary'])
    mgr.require(mgr.common.sha(binary)==v['timing_binary_sha256'] and
                mgr.common.sha(identity)==v['identity_binary_sha256'],'frozen helper binary changed')
    gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(gpu['count']==1 and all(gpu[k]==v['gpu'][k] for k in
                ('arch','runtime_version','driver_version')),'validation GPU architecture/runtime differs')
    run=mgr.inside(a.run)/'cc-fusion-validation';run.mkdir()
    env.update(LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(lib.parent)+':'+env['LD_LIBRARY_PATH'])
    linked=subprocess.check_output(['ldd',str(binary)],env=env,text=True)
    loaded=[mgr.inside(line.split('=>')[-1].strip().split()[0]) for line in linked.splitlines() if 'librocfft.so' in line]
    mgr.require('not found' not in linked and loaded==[lib],'unexpected actual library')
    (run/'ldd.txt').write_text(linked)
    helper=mgr.inside(v['reference_helper']);spec=importlib.util.spec_from_file_location('frozen_cc_ab_references',helper)
    blue=importlib.util.module_from_spec(spec);spec.loader.exec_module(blue)
    guard=mgr.inside(a.build)/'cc-fusion-ab-guard'
    launched([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',v['guard_source'],
        '-I'+str(install/'include'),'-I'+str(mgr.inside(cfg['build']['source_dir'])/'shared'),
        '-L'+str(install/'lib'),'-Wl,-rpath,'+str(install/'lib'),
        '-lrocfft','-lstdc++fs','-o',guard],env,run,'compile-guard')
    record=dict(complete=False,fusion_enabled=fused,source_commit=built['arm']['source_commit'],
        library_sha256=built['arm']['library_sha256'],gpu=gpu,formal=False,
        start=datetime.datetime.now(datetime.timezone.utc).isoformat(),cases=[],guards=[],controls=[],
        source_differences=[],failures=[])
    try:
        for case in coverage['cases']:
            n,func,c,q=case['N'],case['func'],case['C'],case['Q']
            folder=run/'cases'/('%d_%s'%(n,func));meta=folder/'metadata';meta.mkdir(parents=True)
            output=meta/'harness';output.mkdir()
            logging_env=dict(env,FFT_TEST_OUT=str(output),ROCFFT_LAYER='40',
                ROCFFT_LOG_PLAN_PATH=str(meta/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(meta/'rtc.txt'))
            launched([binary,n,1,func],logging_env,meta,'plan')
            rows=contract.read_rows(output/'fft_test_1d.csv')
            mgr.require(len(rows)==1,'wrong metadata output count')
            contract.validate_process(rows[0],contract.read_samples(output/'fft_test_1d.samples.csv'),
                contract.read_check(output/'fft_test_1d.check.csv'),n,func,30)
            details=inspect_plan((meta/'plan.txt').read_text(),n,c,q,func,fused)
            # A separate trace avoids per-launch occupancy queries and plan I/O.
            profile=folder/'profile';profile.mkdir();data=profile/'data';data.mkdir()
            pout=profile/'harness';pout.mkdir()
            launched([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
                '-o',profile/'trace','-d',data,binary,n,1,func],dict(env,FFT_TEST_OUT=str(pout)),profile,'trace')
            rows=contract.read_rows(pout/'fft_test_1d.csv')
            mgr.require(len(rows)==1,'wrong profiled output count')
            contract.validate_process(rows[0],contract.read_samples(pout/'fft_test_1d.samples.csv'),
                contract.read_check(pout/'fft_test_1d.check.csv'),n,func,30)
            trace=json.loads((profile/'trace.json').read_text())['traceEvents']
            transforms=sorted([e for e in trace if e.get('cat')=='HIPOPS' and
                re.match(r'(fft_rtc_|c2r_even_pre|r2c_even_post|transpose_rtc_)',e.get('name',''))],
                key=lambda e:int(e['args']['index']))
            leaves=details['leaf_count'];mgr.require(len(transforms)==41*leaves,'wrong actual transform dispatch count')
            names=[e['name'] for e in transforms[:leaves]]
            mgr.require(all([e['name'] for e in transforms[i*leaves:(i+1)*leaves]]==names for i in range(41)),
                        'actual execution sequence changed')
            mgr.require(sum(bool(re.search(r'(c2r_even_pre|r2c_even_post)',name)) for name in names)==int(not fused),
                        'standalone real kernel execution mismatch')
            sources=rtc_sources((meta/'rtc.txt').read_text())
            actual_core=[name for name in names if name.startswith('fft_rtc_')]
            mgr.require(len(actual_core)==2 and all(name in sources for name in actual_core),'missing actual CC source')
            retained_hashes={}
            if fused:
                old_sources=retained_sources(v,env,binary,case,folder/'retained-metadata',actual_core)
                mgr.require(set(actual_core)==set(old_sources),
                            'ON kernel selection changed from retained implementation')
                for name in actual_core:
                    mgr.require(sources[name]==old_sources[name],'ON generated kernel changed')
                    retained_hashes[name]=hashlib.sha256(old_sources[name].encode()).hexdigest()
            else:
                mgr.require(not any(re.search(r'(paired_pre|paired_post|local_real)',name) for name in names),
                            'fusion leaked into OFF')
            entry=dict(case,check='PASS',actual_names=names,**details,
                source_sha256={name:hashlib.sha256(sources[name].encode()).hexdigest() for name in actual_core},
                launch_arguments=[e['args']['args'] for e in transforms[:leaves]],folder=str(folder))
            entry['retained_source_sha256']=retained_hashes
            record['cases'].append(entry)
            for callbacks in (False,True):
                refs_dir=cache/'independent-reference'/str(n)/func/('callbacks' if callbacks else 'plain');refs_dir.mkdir(parents=True)
                refs,metadata=blue.references(n,func.removesuffix('_1d'),callbacks,refs_dir)
                mgr.require(len(metadata)==14,'independent input matrix changed')
                gfolder=folder/('guard-callbacks' if callbacks else 'guard-plain')
                genv=dict(env,ROCFFT_LAYER='40',ROCFFT_LOG_PLAN_PATH=str(gfolder/'plan.txt'),
                          ROCFFT_LOG_RTC_PATH=str(gfolder/'rtc.txt'))
                launched([guard,n,func.removesuffix('_1d'),refs,'callbacks' if callbacks else 'plain'],genv,gfolder,'guard')
                text=(gfolder/'guard.out').read_text()
                mgr.require(text.count('EVEN_CC_GUARD_PASS')==14 and 'EVEN_CC_ALL_PASS cases=14' in text,
                            'incomplete full independent reference checks')
                record['guards'].append(dict(N=n,func=func,callbacks=callbacks,references=metadata,executions=28,check='PASS'))
        for item in coverage['controls']:
            folder=run/'controls'/('%d_%s'%(item['N'],item['func']));folder.mkdir(parents=True)
            launched([binary,item['N'],1,item['func']],dict(env,FFT_TEST_OUT=str(folder)),folder,'control')
            rows=contract.read_rows(folder/'fft_test_1d.csv')
            mgr.require(len(rows)==1,'wrong control output count')
            contract.validate_process(rows[0],contract.read_samples(folder/'fft_test_1d.samples.csv'),
                contract.read_check(folder/'fft_test_1d.check.csv'),item['N'],item['func'],30)
            record['controls'].append(dict(item,check='PASS'))
        mgr.require(len(record['cases'])==len(coverage['cases'])
                    and len(record['guards'])==2*len(coverage['cases'])
                    and len(record['controls'])==len(coverage['controls']),'validation coverage incomplete')
        if fused:
            off_path=mgr.inside(v['unfused_build_record']);off=json.loads(off_path.read_text())
            checked=json.loads((off_path.parent/'post-build-validation.json').read_text())
            other=json.loads((off_path.parent/'cc-fusion-validation.json').read_text())
            mgr.require(off['complete'] and checked['complete'] and other['complete'] and not other['fusion_enabled'],
                        'unfused reference is not fully validated')
            mgr.require(off['arm']['source_commit']==built['arm']['source_commit'] and
                        mgr.common.sha(mgr.inside(off['arm']['install'])/'lib/librocfft.so.0.1')==off['arm']['library_sha256'],
                        'same-source OFF identity mismatch')
            left=dict(off['plan']['profile']);right=dict(built['plan']['profile'])
            mgr.require(left.pop('ROCFFT_CC_REAL_FUSION')=='OFF' and right.pop('ROCFFT_CC_REAL_FUSION')=='ON'
                        and left==right and off['compiler_version']==built['compiler_version'],
                        'builds differ beyond fusion switch')
            for case in record['cases']:
                previous=next(p for p in other['cases'] if (p['N'],p['func'])==(case['N'],case['func']))
                mgr.require((case['C'],case['Q'])==(previous['C'],previous['Q']),'cross-build decomposition mismatch')
                common=set(case['source_sha256'])&set(previous['source_sha256'])
                expected_common=0 if case['func']=='z2d_1d' and case['folded_columns'] else 1
                mgr.require(len(common)==expected_common,'unrelated FFT kernel choice changed')
                for name in common:
                    mgr.require(case['source_sha256'][name]==previous['source_sha256'][name],
                                'unrelated FFT generated source changed')
                    current_args=case['launch_arguments'][case['actual_names'].index(name)]
                    previous_args=previous['launch_arguments'][previous['actual_names'].index(name)]
                    normalize=lambda text: re.sub(r'f=0x[0-9a-f]+','f=KERNEL',text)
                    mgr.require(normalize(current_args)==normalize(previous_args),
                                'unrelated FFT launch geometry changed')
                record['source_differences'].append(dict(N=case['N'],func=case['func'],
                    same_CQ=True,unchanged_kernel_names=sorted(common),folded_layout=case['folded_columns']))
            record['unfused_library_sha256']=off['arm']['library_sha256']
            record['unfused_validation_sha256']=mgr.common.sha(off_path.parent/'post-build-validation.json')
        mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity'],'source changed during validation')
        mgr.require(mgr.common.sha(lib)==built['arm']['library_sha256'],'library changed during validation')
        print(completion_summary(record,fused),flush=True)
        record['complete']=True
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        record['files']={p.relative_to(run).as_posix():mgr.common.sha(p) for p in run.rglob('*') if p.is_file()}
        mgr.dumps(mgr.inside(a.run)/'cc-fusion-validation.json',record)


if __name__=='__main__':main()
