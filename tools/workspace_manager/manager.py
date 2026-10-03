"""Explicit experiment tasks; preview by default, immutable outputs per ID."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/fft_measurement'))
import common

DTK = '/public/software/compiler/dtk-26.04'
PYTHON = '/public/software/apps/anaconda3/2023.09/bin/python'
PROFILE = {'CMAKE_BUILD_TYPE':'Release', 'GPU_TARGETS':'gfx936',
           'BUILD_CLIENTS_BENCH':'ON', 'BUILD_CLIENTS_SAMPLES':'OFF',
           'BUILD_CLIENTS_TESTS':'OFF', 'ROCFFT_BUILD_OFFLINE_TUNER':'OFF',
           'ROCFFT_KERNEL_CACHE_ENABLE':'OFF', 'HAVE_STD_FILESYSTEM':'ON',
           'CMAKE_SHARED_LINKER_FLAGS':'-lstdc++fs', 'CMAKE_EXE_LINKER_FLAGS':'-lstdc++fs',
           'SQLITE_USE_SYSTEM_PACKAGE':'OFF'}

def require(value, message):
    if not value: raise ValueError(message)

def inside(path, root=None, allow_root=False):
    root = Path(root or ROOT).resolve()
    p = Path(path)
    if not p.is_absolute(): p = root / p
    p = p.resolve()
    require((allow_root and p==root) or root in p.parents, 'path outside workspace or workspace root: '+str(p))
    return p

def ident(value, label):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',value), 'invalid '+label)
    require('REPLACE' not in value, label+' is still a placeholder')
    return value

def load(path):
    cfg = json.loads(inside(path).read_text(encoding='utf-8'))
    require(cfg.get('schema_version') == 1, 'unsupported schema_version')
    require(re.fullmatch(r'EXP-\d{3,}',cfg.get('experiment','')), 'explicit EXP identifier required')
    ident(cfg.get('run_id'), 'run_id')
    return cfg

def locations(cfg, task):
    base = inside(ROOT/'experiments'/cfg['experiment'])
    run = inside(base/'runs'/ident(cfg['run_id'],'run_id'))
    build_id = ident(cfg.get('build',{}).get('build_id',cfg['run_id']), 'build_id') if task=='build' else cfg['run_id']
    return {'run':run,'logs':inside(run/'logs'),
            'build':inside(base/'artifacts/build'/build_id) if task=='build' else inside(base/'artifacts/build/measurement'/cfg['run_id']),
            'install':inside(base/'artifacts/install'/build_id),
            'cache':inside(base/'artifacts/cache'/cfg['run_id'])}

def dumps(path, value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')

def registry():
    return json.loads((ROOT/'configs/installations.json').read_text(encoding='utf-8'))

def measurement(cfg):
    m=copy.deepcopy(cfg)
    fields=('install','source_repo','source_commit','source_state','library_sha256','build_provenance')
    for arm in common.ARMS:
        a=m['arms'][arm]
        if a.get('registry_id'):
            record=registry()['installations'][a['registry_id']]
            require(record.get('role')==arm and record.get('eligible_formal_arm'), 'registry entry is not eligible for '+arm)
            record=record['arm']
        elif a.get('build_record'):
            require(arm=='candidate','build_record is only for candidate')
            record_path=inside(a['build_record'])
            built=json.loads(record_path.read_text())
            require(built.get('complete') is True and built.get('component')=='rocfft','incomplete or wrong build record')
            require(built['experiment']==cfg['experiment'], 'candidate build belongs to another experiment')
            record=built['arm']
            require(common.sha(inside(record['install'])/'lib/librocfft.so.0.1')==record['library_sha256'], 'candidate build/library mismatch')
        else: continue
        for key in fields:
            if key in a: require(a[key]==record[key], 'conflicting frozen '+arm+'.'+key)
            a[key]=record[key]
        a['install']=str(inside(a['install']))
        a['source_repo']=str(inside(a['source_repo'],allow_root=True))
        # Queue workers consume frozen concrete identities, never mutable aliases.
        a.pop('registry_id',None)
        a.pop('build_record',None)
    return common.validate_manifest(m)

def source_identity(cfg):
    b=cfg['build'];repo=inside(b['source_repo'],allow_root=True);source=inside(b['source_dir'])
    require(repo==source or repo in source.parents,'source_dir must belong to source_repo')
    require(source.is_dir() and (source/'CMakeLists.txt').is_file(),'CMake source directory missing')
    commit=b.get('source_commit','')
    require(re.fullmatch('[0-9a-f]{40}',commit),'explicit build source commit required')
    env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],env=env,text=True).strip()
    require(git('rev-parse','HEAD')==commit,'build source HEAD differs from configuration')
    subtree=str(source.relative_to(repo)) or '.'
    state=git('status','--porcelain=v1','--untracked-files=all','--',subtree)
    require(not state,'candidate source subtree is not clean and committed')
    require(git('rev-parse','--show-toplevel')==str(repo),'source_repo must be actual Git root')
    return {'repo':str(repo),'source':str(source),'commit':commit,'source_status':state,
            'tracked_state':git('status','--porcelain=v1','--untracked-files=no')}

def build_plan(cfg):
    b=cfg['build'];component=b.get('component','rocfft')
    require(component in ('rocfft','hipfft'),'unsupported component')
    state=source_identity(cfg);p=locations(cfg,'build')
    compiler=b.get('compiler',DTK+'/bin/hipcc')
    require(compiler==DTK+'/bin/hipcc','unregistered compiler profile')
    flags=dict(PROFILE)
    if component=='hipfft':
        flags={k:v for k,v in flags.items() if k not in ('ROCFFT_BUILD_OFFLINE_TUNER','ROCFFT_KERNEL_CACHE_ENABLE','SQLITE_USE_SYSTEM_PACKAGE')}
        flags['BUILD_CLIENTS_BENCH']='OFF'
    flags.update(b.get('cmake',{}))
    for key in flags:
        require(re.fullmatch('[A-Za-z][A-Za-z0-9_]*',key),'invalid CMake key')
        require(key not in ('CMAKE_INSTALL_PREFIX','CMAKE_C_COMPILER','CMAKE_CXX_COMPILER','CMAKE_PREFIX_PATH','hiprtc_DIR'),'reserved CMake path/compiler key')
    require(flags.get('GPU_TARGETS')=='gfx936' and flags.get('CMAKE_BUILD_TYPE')=='Release','unregistered GPU/build profile')
    prefix=[inside(ROOT/'extern/rocm-cmake'),inside(ROOT/'extern/hiprtc')]
    if component=='hipfft':
        require(b.get('rocfft_install'),'hipFFT requires explicit paired rocFFT installation')
        prefix.insert(0,inside(b['rocfft_install']))
        require(common.sha(prefix[0]/'lib/librocfft.so.0.1')==b.get('rocfft_library_sha256'),'paired rocFFT hash mismatch')
    configure=['cmake','-S',state['source'],'-B',str(p['build']),
               '-DCMAKE_C_COMPILER='+compiler,'-DCMAKE_CXX_COMPILER='+compiler,
               '-DCMAKE_INSTALL_PREFIX='+str(p['install']),
               '-DCMAKE_PREFIX_PATH='+';'.join(map(str,prefix)),
               '-Dhiprtc_DIR='+str(inside(ROOT/'extern/hiprtc'))]
    configure.extend('-D'+k+'='+str(v) for k,v in sorted(flags.items()))
    cpus=int(cfg.get('resources',{}).get('cpus',8));require(1<=cpus<=64,'invalid cpus')
    commands=[configure]
    if component=='rocfft':commands.append(['cmake','--build',str(p['build']),'--target','rocfft-rtc-gen','--parallel',str(cpus)])
    commands.extend([['cmake','--build',str(p['build']),'--parallel',str(cpus)],['cmake','--install',str(p['build'])]])
    return {'task':'build','component':component,'source_identity':state,'paths':{k:str(v) for k,v in p.items()},
            'commands':commands,
            'compiler':compiler,'profile':flags,'runtime_validation':'not yet performed'}

def task_plan(task,cfg):
    if task=='build':return build_plan(cfg)
    m=measurement(cfg);p=locations(m,task)
    if task=='report':return {'task':task,'run':str(p['run']),'command':[PYTHON,str(ROOT/'tools/fft_measurement/summarize.py'),str(p['run'])]}
    for arm in common.ARMS:
        require(common.sha(inside(m['arms'][arm]['install'])/'lib/librocfft.so.0.1')==m['arms'][arm]['library_sha256'],arm+': library hash mismatch')
    return {'task':task,'paths':{k:str(v) for k,v in p.items()},'resolved_preregistration':m,
            'processes':720 if task=='measure' else 15,'cases':15,'timing_warmups':3,'event_iterations':50,
            'formal':task=='measure','notice':'Quick correctness is not formal promotion evidence.' if task=='validate' else 'Frozen 8-round three-arm protocol.'}

def allocate(cfg,task):
    p=locations(cfg,task)
    for key in ('run','build','cache'):
        require(not p[key].exists(),'identifier already used: '+str(p[key]))
    if task=='build':require(not p['install'].exists(),'build installation already exists')
    p['run'].mkdir(parents=True);p['logs'].mkdir()
    dumps(p['run']/'.reservation.json',{'task':task,'manifest':cfg})
    dumps(p['run']/'submit-manifest.json',cfg)
    return p

def submit(task,cfg):
    planned=task_plan(task,cfg)
    if task=='report':
        return subprocess.run(planned['command'],check=True)
    frozen=planned.get('resolved_preregistration',cfg)
    p=allocate(frozen,task)
    r=cfg.get('resources',{})
    argv=['sbatch','--parsable','--chdir='+str(ROOT),
          '--output='+str(p['logs']/'slurm_%j.out'),'--error='+str(p['logs']/'slurm_%j.err'),
          '--cpus-per-task='+str(int(r.get('cpus',8))), '--partition='+r.get('partition','hx1hdnormal01'),
          '--time='+r.get('time_limit','02:00:00')]
    if r.get('nodelist'):argv.append('--nodelist='+r['nodelist'])
    argv.extend([str(ROOT/'jobs/workspace_task.slurm'),task,str(p['run']/'submit-manifest.json')])
    dumps(p['run']/'submission-command.json',argv)
    try:
        job=subprocess.check_output(argv,text=True).strip()
        dumps(p['run']/'submission.json',{'job':job,'argv':argv})
        print(json.dumps({'job':job,'run':str(p['run'])}))
    except Exception as error:
        dumps(p['run']/'submission-failed.json',{'error':str(error)})
        raise

def claim(cfg,task):
    p=locations(cfg,task)
    reservation=json.loads((p['run']/'.reservation.json').read_text())
    require(reservation=={'task':task,'manifest':cfg},'reservation does not match frozen configuration')
    require(set(x.name for x in p['run'].iterdir()) <= {'.reservation.json','logs','submit-manifest.json','submission-command.json','submission.json'},'run already contains execution evidence')
    with (p['run']/'.execution-lock').open('x') as f:f.write(os.environ.get('SLURM_JOB_ID','unknown'))
    for key in ('build','cache'):
        require(not p[key].exists(),'artifact path already used: '+str(p[key]));p[key].mkdir(parents=True)
    return p

def environment(cache):
    env=dict(os.environ)
    for k in ('LD_PRELOAD','LD_LIBRARY_PATH','LD_DEBUG','LD_DEBUG_OUTPUT','FFT_TEST_OUT'):
        env.pop(k,None)
    require(not any(k.startswith('ROCFFT_') and k not in ('ROCFFT_RTC_CACHE_READ_DISABLE','ROCFFT_RTC_CACHE_WRITE_DISABLE') for k in env),'unexpected ROCFFT environment override')
    env.update(HIP_PATH=DTK,ROCM_PATH=DTK,HIP_PLATFORM='amd',PATH=DTK+'/bin:'+env.get('PATH',''),
               ROCFFT_RTC_CACHE_READ_DISABLE='1',ROCFFT_RTC_CACHE_WRITE_DISABLE='1',FFT_TEST_ITERS='50',TMPDIR=str(cache),
               LD_LIBRARY_PATH=':'.join(DTK+'/'+x for x in ('hip/lib','dcc/comgr/lib64','lib')),
               SQLITE_3_50_2_SRC_URL='file://'+str(inside(ROOT/'extern/sqlite/sqlite-amalgamation-3500200.zip')))
    return env

def execute_build(cfg):
    planned=build_plan(cfg);p=claim(cfg,'build');env=environment(p['cache'])
    record={'complete':False,'experiment':cfg['experiment'],'component':planned['component'],
            'plan':planned,'job_id':os.environ['SLURM_JOB_ID'],'start':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    dumps(p['run']/'preregistration.json',cfg);dumps(p['run']/'plan.json',planned)
    try:
        for i,argv in enumerate(planned['commands']):
            with (p['logs']/('build_%d.txt'%i)).open('xb') as f:subprocess.run(argv,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
        require(source_identity(cfg)==planned['source_identity'],'source changed during build')
        component=planned['component'];lib=inside(p['install']/'lib'/('lib'+component+'.so.0.1'))
        cache=p['install']/'lib/rocfft/rocfft_kernel_cache.db'
        if cache.exists():cache.rename(cache.with_name(cache.name+'.disabled_by_managed_build'))
        record['compiler_version']=subprocess.check_output([planned['compiler'],'--version'],env=env,text=True)
        record['cmake_cache_sha256']=common.sha(p['build']/'CMakeCache.txt')
        record['effective_cache']={line.split(':',1)[0]:line.split('=',1)[1] for line in (p['build']/'CMakeCache.txt').read_text().splitlines()
                                   if ':' in line and '=' in line and not line.startswith(('#','//'))
                                   and line.split(':',1)[0] in ('GPU_TARGETS','AMDGPU_TARGETS','CMAKE_BUILD_TYPE','CMAKE_CXX_COMPILER','CMAKE_CXX_FLAGS','CMAKE_PREFIX_PATH','SQLITE_SRC_3_50_2_SHA3_256','SQLITE_3_50_2_SRC_URL')}
        record['arm']={'install':str(p['install']),'source_repo':planned['source_identity']['repo'],
                       'source_commit':planned['source_identity']['commit'],'source_state':json.dumps(planned['source_identity'],sort_keys=True),
                       'library_sha256':common.sha(lib),'build_provenance':str(p['run']/'build-provenance.json')}
        record['complete']=True
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat();dumps(p['run']/'build-provenance.json',record)
    dumps(p['run']/'candidate-arm.json',{'build_record':str(p['run']/'build-provenance.json')})
    print(p['run']/'build-provenance.json')

def execute_validate(cfg):
    # Quick candidate correctness uses the same frozen program; no aggregate or promotion.
    m=measurement(cfg);task_plan('validate',m);p=claim(m,'validate');env=environment(p['cache'])
    here=ROOT/'tools/fft_measurement';require(common.sha(here/'fft_test_1d.cpp')==common.SOURCE_SHA,'frozen source changed')
    identity=p['build']/'device_identity';binary=p['build']/'fft_test_1d'
    official=inside(m['arms']['official']['install']);candidate=inside(m['arms']['candidate']['install'])
    commands=[[DTK+'/bin/hipcc','-O3','-std=c++17',str(here/'device_identity.cpp'),'-o',str(identity)],
              [DTK+'/bin/hipcc','-O3','-std=c++17',str(here/'fft_test_1d.cpp'),'-I'+str(official/'include'),'-L'+str(official/'lib'),'-Wl,-rpath,'+str(official/'lib'),'-lrocfft','-o',str(binary)]]
    for i,argv in enumerate(commands):
        with (p['logs']/('compile_%d.txt'%i)).open('xb') as f:subprocess.run(argv,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    require(gpu['count']==1 and gpu['arch'].split(':')[0]==m['gpu_arch'] and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16),'GPU identity mismatch')
    lib=inside(candidate/'lib/librocfft.so.0.1');expected=m['arms']['candidate']['library_sha256']
    env.update(LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(candidate/'lib')+':'+env['LD_LIBRARY_PATH'])
    linked=subprocess.check_output(['ldd',str(binary)],env=env,text=True)
    loaded=[inside(line.strip().split('=>')[-1].strip().split(' ')[0]) for line in linked.splitlines() if 'librocfft.so' in line]
    require('not found' not in linked and len(set(loaded))==1 and loaded[0]==lib,'actual rocFFT loading mismatch')
    (p['logs']/'ldd.txt').write_text(linked)
    dumps(p['run']/'preregistration.json',m)
    record={'complete':False,'formal':False,'gpu':gpu,'job_id':os.environ['SLURM_JOB_ID'],'library_sha256':expected,
            'source_sha256':common.SOURCE_SHA,'binary_sha256':common.sha(binary),'identity_binary_sha256':common.sha(identity),
            'compiler_version':subprocess.check_output([DTK+'/bin/hipcc','--version'],env=env,text=True),'compile_commands':commands,'checks':[]}
    try:
        for n in common.SIZES:
            for func in common.FUNCS:
                require(common.sha(lib)==expected,'library changed')
                require(common.sha(binary)==record['binary_sha256'] and common.sha(identity)==record['identity_binary_sha256'],'quick-check executable changed')
                require(json.loads(subprocess.check_output([str(identity)],env=environment(p['cache']),text=True))==gpu,'GPU changed')
                case=p['run']/'processes'/('%d_%s'%(n,func));case.mkdir(parents=True)
                with (case/'stdout.txt').open('xb') as out,(case/'stderr.txt').open('xb') as err:
                    subprocess.run([str(binary),str(n),'1',func,'1'],env=dict(env,FFT_TEST_OUT=str(case)),stdout=out,stderr=err,check=True)
                rows=common.read_rows(case/'fft_test_1d.csv');require(len(rows)==1,'unexpected quick-check row count');common.validate_row(rows[0],n,func)
                record['checks'].append({'N':n,'func':func,'check':'PASS','csv_sha256':common.sha(case/'fft_test_1d.csv')})
        require(common.sha(lib)==expected,'library changed at completion');record['complete']=True
    finally:dumps(p['run']/'quick-correctness.json',record)
    print(p['run']/'quick-correctness.json')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task',choices=('build','validate','measure','report'))
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--execute',action='store_true',help='submit task, or generate report; default is preview')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    try:
        cfg=load(args.config)
        if args.worker:
            require(not args.execute and args.task!='report','invalid worker mode')
            require(os.environ.get('SLURM_JOB_ID') and len(os.environ.get('SLURM_JOB_GPUS','').split(','))==1 and os.environ.get('SLURM_JOB_GPUS'),'one-GPU Slurm allocation required')
            require(os.environ.get('SLURM_JOB_NUM_NODES','1')=='1','one node required')
            if args.task=='build':execute_build(cfg)
            elif args.task=='validate':execute_validate(cfg)
            else:
                import run
                run.execute(common.manifest(args.config))
        elif args.execute:submit(args.task,cfg)
        else:print(json.dumps(task_plan(args.task,cfg),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        parser.exit(1,'task rejected: '+str(error)+'\n')

if __name__=='__main__':main()
