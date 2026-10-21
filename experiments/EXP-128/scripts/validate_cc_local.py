"""EXP128: public defaults, full native two-stage matrix, and actual dispatch."""
import argparse
import datetime
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from cc_fusion_ab_references import references, PATTERNS
from cc_dispatch import inspect_dispatch
import cufft261012_contract as contract


def run(command,env,folder,label,timeout=900,cwd=None):
    folder.mkdir(parents=True,exist_ok=True)
    command=list(map(str,command))
    with (folder/(label+'.out')).open('wb') as out,(folder/(label+'.err')).open('wb') as err:
        result=subprocess.run(command,env=env,cwd=cwd or folder,stdout=out,stderr=err,timeout=timeout)
    mgr.dumps(folder/(label+'-command.json'),dict(command=command,returncode=result.returncode))
    mgr.require(result.returncode==0,label+' failed: '+str(folder))


def representative_sizes(public):
    remaining={('C',x['C']) for x in public}|{('Q',x['Q']) for x in public}
    selected=[]
    while remaining:
        x=max(public,key=lambda x:(len({('C',x['C']),('Q',x['Q'])}&remaining),x['N']))
        remaining-={('C',x['C']),('Q',x['Q'])};selected.append(x['N'])
    return set(selected)


def trace_case(binary,case,func,env,folder,fused):
    n,c,q=case['N'],case['C'],case['Q']
    data=folder/'metadata';data.mkdir(parents=True)
    selected=dict(env,FFT_TEST_OUT=str(data),ROCFFT_LAYER='40',
        ROCFFT_LOG_PLAN_PATH=str(data/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(data/'rtc.txt'))
    run([binary,n,1,func],selected,data,'metadata')
    plan=(data/'plan.txt').read_text()
    sources=dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
                           (data/'rtc.txt').read_text(),re.M|re.S))
    profile=folder/'profile';(profile/'harness').mkdir(parents=True);(profile/'data').mkdir()
    run([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
         '-o',profile/'trace','-d',profile/'data',binary,n,1,func],
        dict(env,FFT_TEST_OUT=str(profile/'harness')),profile,'trace')
    row=contract.read_rows(profile/'harness/fft_test_1d.csv')[0]
    contract.validate_process(row,contract.read_samples(profile/'harness/fft_test_1d.samples.csv'),
        contract.read_check(profile/'harness/fft_test_1d.check.csv'),n,func,30)
    launches,checked=inspect_dispatch(plan,json.loads((profile/'trace.json').read_text())['traceEvents'],func)
    names=[x['name'] for x in launches]
    if fused:
        roles=(4,5) if func=='z2d_1d' else (6,7)
        mgr.require(len(names)==2 and all('_cc_local_v1_role%d_C%d_Q%d_'%(r,c,q) in name
                     for r,name in zip(roles,names)),'default did not execute both EXP128 adapters')
        mgr.require(all(name in sources for name in names),'actual generated source missing')
    else:
        mgr.require(len(names)>=3 and not any('_cc_local_v1_role' in x for x in names),
                    'unfused control still executes real fusion')
    return dict(N=n,func=func,C=c,Q=q,actual_names=names,dispatch=checked,
                source_sha256={name:__import__('hashlib').sha256(sources[name].encode()).hexdigest()
                               for name in names if name in sources})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','build-record','run','build','cache'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();cfg=mgr.load(a.config);built=json.loads(a.build_record.read_text())
    mgr.require(built['complete'],'build incomplete')
    coverage=json.loads(mgr.inside(cfg['validation']['coverage']).read_text())
    fused=cfg['validation']['fused'];source=mgr.inside(cfg['build']['source_dir'])
    install=mgr.inside(built['arm']['install']);lib=install/'lib/librocfft.so.0.1'
    folder=mgr.inside(a.run)/'cc-local-validation';folder.mkdir()
    cache=mgr.inside(a.cache);env=mgr.environment(cache);env['FFT_TEST_ITERS']='30'
    selected=dict(env,LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    here=Path(__file__).resolve().parent;build=mgr.inside(a.build)
    identity=build/'exp128-device';guard=build/'exp128-public';binary=build/'exp128-timing'
    helpers=[(identity,ROOT/'tools/fft_measurement/device_identity.cpp',[]),
        (guard,here/'cc_fusion_ab_guard.cpp',['-I'+str(source/'shared'),'-I'+str(install/'include'),
            '-L'+str(install/'lib'),'-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-lstdc++fs']),
        (binary,ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,['-I'+str(install/'include'),
            '-L'+str(install/'lib'),'-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-lstdc++fs'])]
    for output,src,flags in helpers:
        run([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936','-mcumode',
             src,*flags,'-o',output],env,folder,'compile-'+output.name)
    gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936'
        and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16),'single gfx936 device required')
    linked=subprocess.check_output(['ldd',str(guard)],env=selected,text=True)
    loaded=[mgr.inside(line.split('=>')[-1].strip().split()[0]) for line in linked.splitlines() if 'librocfft.so' in line]
    mgr.require('not found' not in linked and loaded==[lib.resolve()],'wrong actual library')
    (folder/'ldd.txt').write_text(linked)
    text=(build/'CMakeCache.txt').read_text()
    mgr.require(('ROCFFT_CC_REAL_FUSION:BOOL='+('ON' if fused else 'OFF')) in text
        and 'ROCFFT_CC_LOCAL_REAL_FUSION:BOOL=ON' in text,'wrong fusion switches')
    record=dict(complete=False,formal=False,source_commit=built['arm']['source_commit'],
        library_sha256=built['arm']['library_sha256'],gpu=gpu,fused=fused,
        public=[],internal=[],dispatch=[],controls=[],
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())
    def save():(a.run/'cc-local-validation.json').write_text(json.dumps(record,indent=2)+'\n')
    def public_case(case,func,comprehensive=False,control=False):
        n=case['N'];d=func.split('_')[0];key=str(n)+'-'+d
        for cb in ((False,True,'load','store') if comprehensive else (False,)):
            scratch=cache/'references'/key/str(cb);scratch.mkdir(parents=True)
            log=folder/'public'/key/str(cb);log.mkdir(parents=True)
            try:
                manifest,meta=references(n,d,cb,scratch,
                    PATTERNS if comprehensive else ('random',),(1.,.375) if comprehensive else (1.,))
                genv=dict(selected,ROCFFT_LAYER='40',ROCFFT_LOG_PLAN_PATH=str(log/'plan.txt'),
                          ROCFFT_LOG_RTC_PATH=str(log/'rtc.txt'))
                run([guard,n,d,manifest,('callbacks' if cb is True else cb if cb else 'plain')],genv,log,'guard')
                out=(log/'guard.out').read_text()
                mgr.require(out.count('EVEN_CC_GUARD_PASS ')==len(meta),'incomplete public guard')
                generated=(log/'rtc.txt').read_text()
                if not control:
                    roles=(4,5) if d=='z2d' else (6,7)
                    for role in roles:
                        token='_cc_local_v1_role%d_C%d_Q%d_'%(role,case['C'],case['Q'])
                        mgr.require((token in generated)==fused,'unexpected public adapter/default decomposition')
                result=dict(case,func=func,callbacks=cb,references=meta)
                record['controls' if control else 'public'].append(result)
            finally:shutil.rmtree(scratch)
    try:
        representatives=representative_sizes(coverage['public'])
        record['representative_N']=sorted(representatives)
        for case in coverage['public']:
            for func in ('z2d_1d','d2z_1d'):
                public_case(case,func,case['N'] in representatives)
                if case['N'] in representatives:
                    record['dispatch'].append(trace_case(binary,case,func,selected,
                        folder/'dispatch'/(str(case['N'])+'-'+func),fused))
            save();print('PUBLIC_PASS',case['N'],flush=True)
        for case in coverage['controls']:public_case(case,case['func'],True,True)
        if fused:
            internal=build/'exp128-pipeline'
            record['internal_fixture']=compile_internal_fixture(build,source,here/'cc_local_pipeline_guard.cpp',
                internal,env,folder/'internal-build')
            for case in coverage['geometries']:
                key='%d-%d'%(case['C'],case['Q']);scratch=cache/'internal-references'/key
                scratch.mkdir(parents=True);rows=[];metadata=[]
                try:
                    for pre,d in ((True,'z2d'),(False,'d2z')):
                        sub=scratch/d;sub.mkdir()
                        _,meta=references(case['N'],d,True,sub,('random',),(.375,));r=meta[0]
                        rows.append('%d %d %d %d .375 1 %s %s'%(case['N'],pre,case['C'],case['Q'],r['input'],r['expected']))
                        metadata.append(dict(r,pre=pre))
                    manifest=scratch/'manifest.txt';manifest.write_text('\n'.join(rows)+'\n')
                    log=folder/'internal'/key;run([internal,manifest],env,log,'guard',timeout=1800)
                    out=(log/'guard.out').read_text()
                    mgr.require(out.count('CC_LOCAL_PIPELINE_PASS ')==2 and 'CC_LOCAL_PIPELINE_ALL_PASS 2' in out,
                                'incomplete internal pipeline')
                    record['internal'].append(dict(case,references=metadata,execution=out.strip().splitlines()))
                finally:shutil.rmtree(scratch)
                save();print('INTERNAL_PASS',key,flush=True)
        mgr.require(len(record['public'])==2*(len(coverage['public'])+3*len(representatives)),
                    'public matrix incomplete')
        mgr.require(len(record['internal'])==(len(coverage['geometries']) if fused else 0),'native matrix incomplete')
        finish(record,built,gpu,env,lib,identity)
    except Exception as error:
        record['failure']=dict(type=type(error).__name__,message=str(error));raise
    finally:save()
    print(json.dumps(dict(complete=True,fused=fused,public=len(record['public']),internal=len(record['internal']))))


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

if __name__=='__main__':main()
