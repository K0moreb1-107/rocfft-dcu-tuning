#!/usr/bin/env python3
"""EXP-125 h: build and packed-table correctness, no formal timing."""
import datetime, json, os, re, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

def run_logged(argv,env,directory):
    directory.mkdir(parents=True,exist_ok=False)
    with (directory/'stdout.txt').open('xb') as out,(directory/'stderr.txt').open('xb') as err:
        subprocess.run(argv,env=env,stdout=out,stderr=err,check=True)

def main():
    build_cfg=mgr.load(Path(sys.argv[1]));cfg=mgr.load(Path(sys.argv[2]))
    mgr.require(os.environ.get('SLURM_JOB_ID') and os.environ.get('SLURM_JOB_GPUS')
                and len(os.environ['SLURM_JOB_GPUS'].split(','))==1,'one GPU allocation required')
    mgr.execute_build(build_cfg)
    built=json.loads(Path(cfg['candidate_build_record']).read_text())
    mgr.require(built['complete'] and built['arm']['source_commit']==cfg['source_commit'],'build identity mismatch')
    def audit_source():
        def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
        mgr.require(git('rev-parse','HEAD') == cfg['source_commit'], 'source HEAD changed')
        mgr.require(git('branch','--show-current') == 'exp-125-local-real-f', 'source branch changed')
        mgr.require(not git('status','--porcelain','--untracked-files=all','--',
                            'rocm-libraries-rocm-7.2.2/projects/rocfft'), 'kernel source is dirty')
        for name, checksum in cfg['source_file_sha256'].items():
            mgr.require(mgr.common.sha(ROOT/name) == checksum, 'kernel source changed: '+name)
        mgr.require(mgr.common.sha(ROOT/'experiments/EXP-125/source/post-memory-h/source.tar')
                    == cfg['source_archive_sha256'], 'frozen source archive changed')
    audit_source()
    paths=mgr.claim(cfg,'validate');env=mgr.environment(paths['cache'])
    candidate=mgr.inside(built['arm']['install']);lib=candidate/'lib/librocfft.so.0.1'
    sha=built['arm']['library_sha256'];official=mgr.inside(cfg['official_install'])
    mgr.require(mgr.common.sha(official/'lib/librocfft.so.0.1')==cfg['official_library_sha256'],'official identity changed')
    frozen=ROOT/'tools/fft_measurement/fft_test_1d.cpp'
    mgr.require(mgr.common.sha(frozen)==mgr.common.SOURCE_SHA==cfg['measurement_source_sha256'],'frozen program changed')
    guards={name:ROOT/item['source'] for name,item in cfg['guard_programs'].items()}
    for name,source in guards.items():
        mgr.require(mgr.common.sha(source)==cfg['guard_programs'][name]['sha256'],'guard program changed')
    identity=paths['build']/'device_identity';binary=paths['build']/'fft_test_1d'
    programs={name:paths['build']/name for name in guards}
    commands=[
        [mgr.DTK+'/bin/hipcc','-O3','-std=c++17',str(ROOT/'tools/fft_measurement/device_identity.cpp'),'-o',str(identity)],
        [mgr.DTK+'/bin/hipcc','-O3','-std=c++17',str(frozen),'-I'+str(official/'include'),
         '-L'+str(official/'lib'),'-Wl,-rpath,'+str(official/'lib'),'-lrocfft','-o',str(binary)],
    ]
    for name,source in guards.items():
        commands.append([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',str(source),'-I'+str(candidate/'include'),
                         '-I'+str(Path(build_cfg['build']['source_dir'])/'shared'),'-L'+str(candidate/'lib'),'-Wl,-rpath,'+str(candidate/'lib'),'-lrocfft','-o',str(programs[name])])
    for i,command in enumerate(commands):
        with (paths['logs']/('compile-%d.txt'%i)).open('xb') as out:
            subprocess.run(command,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]==cfg['gpu_arch']
                and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16),'GPU identity mismatch')
    env.update(LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(candidate/'lib')+':'+env['LD_LIBRARY_PATH'])
    binaries={str(p):mgr.common.sha(p) for p in (binary,identity,*programs.values())}
    for program in (binary,*programs.values()):
        linked=subprocess.check_output(['ldd',str(program)],env=env,text=True)
        loaded=[Path(line.strip().split('=>')[-1].strip().split(' ')[0]).resolve()
                for line in linked.splitlines() if 'librocfft.so' in line]
        mgr.require('not found' not in linked and set(loaded)=={lib.resolve()},'loaded candidate mismatch')
        (paths['logs']/('ldd-'+program.name+'.txt')).write_text(linked)
    record={'complete':False,'formal':False,'experiment':'EXP-125','candidate':'post-memory-h',
            'job_id':os.environ['SLURM_JOB_ID'],'gpu':gpu,'source_commit':cfg['source_commit'],
            'build_job_id':built['job_id'],'validation_revision':'packed twiddles, callbacks and cache coexistence',
            'baseline_commit':cfg['baseline_commit'],'library_sha256':sha,'binaries':binaries,
            'compile_commands':commands,'checks':[],'fusion_evidence':[],'cache_checks':[],
            'start':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    mgr.dumps(paths['run']/'preregistration.json',cfg)
    def identity_check():
        mgr.require(mgr.common.sha(lib)==sha,'candidate library changed')
        mgr.require(all(mgr.common.sha(Path(p))==s for p,s in binaries.items()),'binary changed')
        mgr.require(json.loads(subprocess.check_output([str(identity)],env=mgr.environment(paths['cache']),text=True))==gpu,'GPU changed')
    try:
        for mode in ('registers','lds'):
            funcs=mgr.common.FUNCS if mode=='registers' else ('d2z_1d','z2d_1d')
            for n in mgr.common.SIZES:
                for function in funcs:
                    identity_check();case=paths['run']/'processes'/mode/('%d_%s'%(n,function))
                    case_env=dict(env,ROCFFT_EXP125_LOCAL_REAL_LOAD=mode,ROCFFT_EXP125_REAL_POST_LOAD=mode,FFT_TEST_OUT=str(case))
                    run_logged([str(binary),str(n),'1',function,'1'],case_env,case)
                    rows=mgr.common.read_rows(case/'fft_test_1d.csv');mgr.require(len(rows)==1,'wrong quick-check row count')
                    mgr.common.validate_row(rows[0],n,function)
                    record['checks'].append({'mode':mode,'N':n,'func':function,'status':'PASS',
                        'csv_sha256':mgr.common.sha(case/'fft_test_1d.csv')})
            for direction,callbacks in (('post',False),('post',True),('pre',False)):
                name='post_guard_h' if direction=='post' else 'spectral_guard_f'
                count=7 if direction=='post' else 6
                for n in mgr.common.SIZES:
                    identity_check();case=paths['run']/'guards'/(direction+('-callback' if callbacks else '-plain'))/mode/str(n)
                    case_env=dict(env,ROCFFT_EXP125_LOCAL_REAL_LOAD=mode,ROCFFT_EXP125_REAL_POST_LOAD=mode,
                        ROCFFT_LAYER='44',ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'),
                        ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'),ROCFFT_LOG_PROFILE_PATH=str(case/'profile.txt'))
                    run_logged([str(programs[name]),str(n)]+(['callback'] if callbacks else []),case_env,case)
                    stdout=(case/'stdout.txt').read_text(errors='replace')
                    rtc=(case/'rtc.txt').read_text(errors='replace')
                    plan=(case/'plan.txt').read_text(errors='replace')+stdout
                    profile=(case/'profile.txt').read_text(errors='replace')
                    marker='REAL_POST_ALL_PASS' if direction=='post' else 'LOCAL_REAL_ALL_PASS'
                    mgr.require(stdout.count('status=PASS')==count and marker in stdout,'guard checks incomplete')
                    names=set(re.findall(r'fft_rtc_[A-Za-z0-9_]+',rtc))
                    suffix='reg' if mode=='registers' else 'lds'
                    if direction=='post':
                        mgr.require('EXP125 real post: paired mirror rows and fused half spectrum stores' in plan
                                    and 'CS_KERNEL_R_TO_CMPLX' not in plan,'wrong post transform tree')
                        specialized={p for p in names if '_paired_post_rows_' in p}
                        plain={p for p in specialized if '_CB' not in p}
                        mgr.require(len(plain)==1 and all('_paired_post_rows_N%d_%s'%(n,suffix) in p for p in specialized),
                                    'ordinary specialized post RTC kernel missing or mismatched')
                        mgr.require(all('_twd_packed_' in p for p in specialized), 'old post layout was compiled')
                        mgr.require(all(('_post_stream' if '_CB' in p else '_post_preload') in p
                                        for p in specialized), 'post read policy mismatch')
                        if callbacks:
                            mgr.require(any('_CB' in p and '_post_stream' in p for p in specialized),
                                        'callback post kernel missing')
                        mgr.require('twiddle_gen_packed_real_post_dp' in rtc, 'packed table generator missing')
                        mgr.require('_local_real_' not in rtc,'inverse fusion code leaked into post kernel')
                    else:
                        mgr.require('EXP125 local real: folded Hermitian columns' in plan
                                    and 'EXP125 local real: paired rows and adjacent real stores' in plan
                                    and 'CS_KERNEL_CMPLX_TO_R' not in plan,'wrong pre transform tree')
                        specialized={p for p in names if '_local_real_' in p}
                        mgr.require(any('_local_real_columns_N%d_%s'%(n,suffix) in p for p in specialized)
                                    and any('_local_real_rows_N%d_%s'%(n,suffix) in p for p in specialized),'existing pre RTC kernels missing')
                    schemes=re.findall(r'CS_KERNEL_[A-Z0-9_]+',profile)
                    mgr.require(schemes==['CS_KERNEL_STOCKHAM_BLOCK_CC','CS_KERNEL_STOCKHAM_BLOCK_RC']*count,
                                'expected exactly two ordered executed leaves per transform')
                    record['fusion_evidence'].append({'direction':direction,'callbacks':callbacks,'mode':mode,'N':n,'cases':count,
                        'guards':'PASS','input_unchanged':'PASS','executed_leaves_per_transform':2,
                        'kernel_names':sorted(specialized),'plan_sha256':mgr.common.sha(case/'plan.txt'),
                        'rtc_sha256':mgr.common.sha(case/'rtc.txt'),'profile_sha256':mgr.common.sha(case/'profile.txt')})
        identity_check()
        audit_source()
        for mode in ('registers','lds'):
            for n in mgr.common.SIZES:
                identity_check();case=paths['run']/'cache-coexistence'/mode/str(n)
                case_env=dict(env,ROCFFT_EXP125_REAL_POST_LOAD=mode,ROCFFT_LAYER='44',
                    ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'),
                    ROCFFT_LOG_PROFILE_PATH=str(case/'profile.txt'))
                run_logged([str(programs['post_cache_guard_h']),str(n)],case_env,case)
                stdout=(case/'stdout.txt').read_text(errors='replace')
                rtc=(case/'rtc.txt').read_text(errors='replace')
                plan=(case/'plan.txt').read_text(errors='replace')+stdout
                mgr.require(stdout.count('status=PASS')==12 and 'POST_CACHE_ALL_PASS' in stdout,
                            'cache coexistence checks incomplete')
                mgr.require('CS_KERNEL_R_TO_CMPLX' in plan and 'EXP125 real post: paired mirror rows and fused half spectrum stores' in plan,
                            'ordinary and packed plans did not coexist')
                mgr.require('twiddle_gen_packed_real_post_dp' in rtc and 'twiddle_gen_N_dp' in rtc,
                            'both table layouts were not generated')
                record['cache_checks'].append({'mode':mode,'N':n,'checks':12,'status':'PASS',
                    'stdout_sha256':mgr.common.sha(case/'stdout.txt'),'rtc_sha256':mgr.common.sha(case/'rtc.txt')})
        identity_check();audit_source()
        mgr.require(len(record['checks'])==25 and len(record['fusion_evidence'])==30
                    and len(record['cache_checks'])==10,'incomplete validation matrix')
        record['complete']=True
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        mgr.dumps(paths['run']/'paired-post-validation.json',record)
    print(paths['run']/'paired-post-validation.json')
if __name__=='__main__':main()
