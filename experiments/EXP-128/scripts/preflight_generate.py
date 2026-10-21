from pathlib import Path
import concurrent.futures,json,subprocess,sys,shlex
ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
s=ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
b=ROOT/'experiments/EXP-128/artifacts/preflight/host-20261021';build=b/'rocfft_build'
out=b/'generated';out.mkdir(exist_ok=True)
env=mgr.environment(b)
def run(argv,label,cwd=ROOT):
    with (b/(label+'.log')).open('wb') as log:r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
    print(label,r.returncode,flush=True)
    if r.returncode:print((b/(label+'.log')).read_text()[-16000:],flush=True);sys.exit(r.returncode)
if '--syntax-only' not in sys.argv:
    run(['cmake','--build',build,'--target','rocfft-rtc-gen','rocfft-rtc-common','generator','-j16'],'generator-common')
    incs=[s/'library/src/include',s/'library/include',build/'include',build/'include/rocfft',Path(mgr.DTK)/'hip/include']
    objects=list((build/'library/src/CMakeFiles/rocfft-rtc-gen.dir').rglob('*.o'))+list((build/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
    run([mgr.DTK+'/bin/hipcc','--offload-host-only','-std=c++17','-D__HIP_PLATFORM_AMD__','-DROCFFT_STATIC_LIB',*['-I'+str(p) for p in incs],'-c',ROOT/'experiments/EXP-128/scripts/cc_local_generate.cpp','-o',b/'generate.o'],'compile-driver')
    objects.extend((build/'library/src/device/generator/CMakeFiles/generator.dir').rglob('*.o'))
    run([mgr.DTK+'/bin/hipcc',b/'generate.o',*objects,'-L'+mgr.DTK+'/lib','-lamdhip64','-lpthread','-ldl','-lstdc++fs','-o',b/'generate'],'link-driver')
    env['LD_LIBRARY_PATH']=mgr.DTK+'/lib:'+env['LD_LIBRARY_PATH']
    run([b/'generate',ROOT/'experiments/EXP-128/records/implementation-20261021/generation-matrix.txt',out],'generation-matrix')
commands=json.loads((build/'compile_commands.json').read_text());checks=[]
for name in ['assignment_policy.cpp','node_factory.cpp','cc_local_pipeline_guard.cpp']:
    rec=next(x for x in commands if Path(x['file']).name==('plan.cpp' if name.startswith('cc_') else name))
    argv=shlex.split(rec['command']);i=argv.index('-o');del argv[i:i+2];argv.remove('-c')
    if name.startswith('cc_'):
        argv[argv.index(rec['file'])]=str(ROOT/'experiments/EXP-128/scripts'/name)
        argv.extend(['-iquote'+str(s/'library/src'),'-I'+str(s/'shared')])
    run(argv+['-fsyntax-only','--offload-host-only','-ferror-limit=5'],name+'-syntax',Path(rec['directory']))
def syntax(path):
    log=path.with_suffix('.log')
    argv=[mgr.DTK+'/bin/hipcc','--offload-arch=gfx936','-mcumode','-std=c++17','-include','hip/hip_runtime.h','-fsyntax-only','-ferror-limit=4','-DROCFFT_CALLBACKS_ENABLED',path]
    with log.open('wb') as f:r=subprocess.run(list(map(str,argv)),env=env,stdout=f,stderr=subprocess.STDOUT)
    errors=[x for x in log.read_text().splitlines() if 'error:' in x]
    return {'file':str(path),'returncode':r.returncode,'errors':errors}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:checks=list(pool.map(syntax,sorted(out.glob('*.cpp'))))
(b/'generated-syntax.json').write_text(json.dumps(checks,indent=2))
print(json.dumps({'generated_matrix':279*8,'syntax_cases':len(checks),'failure_count':sum(bool(x['returncode']) for x in checks),'first_failures':[x for x in checks if x['returncode']][:4]}),flush=True)
assert len(checks)==96 and all(x['returncode']==0 for x in checks)
