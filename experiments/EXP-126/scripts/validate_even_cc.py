"""Managed post-build correctness and actual CC fusion evidence; no formal timing."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr
import numpy as np

PATTERNS = ('impulse', 'last', 'dc', 'nyquist', 'middle', 'tones', 'random')

def run_logged(argv, env, case):
    case.mkdir(parents=True)
    with (case/'stdout.txt').open('xb') as out, (case/'stderr.txt').open('xb') as err:
        subprocess.run(list(map(str, argv)), env=env, stdout=out, stderr=err, check=True)

def reference_list(n, c, q, direction, callbacks, scratch):
    """Full-length independent NumPy reference, excluding candidate pair formulas."""
    m = n//2
    index = np.arange(n)
    rows = []
    metadata = []
    for tag in PATTERNS:
        x = np.zeros(n)
        if tag == 'impulse': x[0] = 0.5
        elif tag == 'last': x[-1] = -0.375
        elif tag == 'dc': x.fill(0.25)
        elif tag == 'nyquist': x = np.where(index%2, -0.375, 0.375)
        elif tag == 'middle': x = np.cos(2*np.pi*(m//2)*index/n)*0.5
        elif tag == 'tones':
            x = (0.5*np.cos(2*np.pi*7*index/n) + 0.125*np.sin(2*np.pi*(m-3)*index/n)
                 + 0.25*np.cos(2*np.pi*(c+q)*index/n))
        else: x = np.random.default_rng(126+n).normal(size=n)
        value = x if direction == 'd2z' else np.fft.rfft(x)
        if direction == 'z2d' and tag == 'random':
            rng = np.random.default_rng(126+n)
            value = rng.normal(size=m+1) + 1j*rng.normal(size=m+1)
            value[0] = value[0].real;value[-1] = value[-1].real
        raw = np.ascontiguousarray(value, dtype='<f8' if direction == 'd2z' else '<c16')
        input_path = scratch/(tag+'-input.bin');raw.tofile(input_path)
        if callbacks:
            offset = np.arange(len(value))
            value = value*0.75 + (offset%7)*0.03125
        transformed = np.fft.rfft(value) if direction == 'd2z' else np.fft.irfft(value, n=n)*n
        for scale in (1.0, 0.375):
            expected = transformed*scale
            if callbacks: expected = expected*1.125 + (np.arange(len(expected))%5)*0.015625
            expected = np.ascontiguousarray(expected, dtype='<c16' if direction == 'd2z' else '<f8')
            path = scratch/(tag+'-'+str(scale)+'-expected.bin');expected.tofile(path)
            rows.append('%s %.17g %s %s' % (tag, scale, input_path, path))
            metadata.append(dict(pattern=tag, scale=scale, input_sha256=mgr.common.sha(input_path),
                                 expected_sha256=mgr.common.sha(path), seed=126+n))
    list_path = scratch/'reference-list.txt';list_path.write_text('\n'.join(rows)+'\n')
    return list_path, metadata

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    cfg = mgr.load(args.config)
    built = json.loads(mgr.inside(args.build_record).read_text())
    mgr.require(built['complete'] and built['component']=='rocfft', 'candidate build incomplete')
    mgr.require(built['arm']['source_commit']==cfg['build']['source_commit'], 'candidate source mismatch')
    mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity'], 'candidate source changed')
    mgr.validation_hook(cfg)
    validation = cfg['validation']
    coverage = json.loads(mgr.inside(validation['coverage']).read_text())
    geometry = coverage['geometries']
    mgr.require(len(geometry)==coverage['expected_size_count']
                and all(65536<int(n)<=2147483647 for n in geometry), 'wrong large-even scope')
    run = mgr.inside(args.run);build = mgr.inside(args.build)/'validation';build.mkdir()
    scratch = mgr.inside(args.cache)/'reference';scratch.mkdir()
    env = mgr.environment(mgr.inside(args.cache))
    install = mgr.inside(built['arm']['install']);lib=install/'lib/librocfft.so.0.1'
    expected_lib = built['arm']['library_sha256']
    env.update(LD_PRELOAD=str(lib), LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    source = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
    identity = build/'device_identity';frozen=build/'fft_test_1d';guard=build/'even_cc_guard'
    mgr.require(mgr.common.sha(ROOT/'tools/fft_measurement/fft_test_1d.cpp')==mgr.common.SOURCE_SHA,
                'frozen timing source changed')
    commands = [
        [mgr.DTK+'/bin/hipcc','-O3','-std=c++17',str(ROOT/'tools/fft_measurement/device_identity.cpp'),'-o',str(identity)],
        [mgr.DTK+'/bin/hipcc','-O3','-std=c++17',str(ROOT/'tools/fft_measurement/fft_test_1d.cpp'),
         '-I'+str(install/'include'),'-L'+str(install/'lib'),'-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-o',str(frozen)],
        [mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',validation['guard_source'],
         '-I'+str(install/'include'),'-I'+str(source/'shared'),'-L'+str(install/'lib'),
         '-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-o',str(guard)]]
    for i,command in enumerate(commands):
        with (run/'logs'/('validate-compile-%d.txt'%i)).open('xb') as stream:
            subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
    mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936', 'wrong GPU profile')
    mgr.require(re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16), 'wrong GPU UUID')
    binaries = {str(p):mgr.common.sha(p) for p in (identity,frozen,guard)}
    for binary in (frozen,guard):
        linked = subprocess.check_output(['ldd',str(binary)], env=env, text=True)
        loaded=[mgr.inside(line.strip().split('=>')[-1].strip().split(' ')[0])
                for line in linked.splitlines() if 'librocfft.so' in line]
        mgr.require('not found' not in linked and len(set(loaded))==1 and loaded[0]==lib,'wrong loaded candidate')
        (run/'logs'/(binary.name+'-ldd.txt')).write_text(linked)
    record = dict(complete=False, formal=False, job_id=os.environ['SLURM_JOB_ID'],
                  gpu=gpu, allocation=mgr.common.single_gpu_allocation(os.environ),
                  source_commit=built['arm']['source_commit'], library_sha256=expected_lib,
                  default_path_only=True, numpy_version=np.__version__,
                  reference='independent full-length NumPy FFT; reusable reference scratch, retained input/reference hashes and recipe',
                  binaries=binaries, compile_commands=commands, quick_checks=[], fusion_evidence=[], coverage={},
                  start=datetime.datetime.now(datetime.timezone.utc).isoformat())
    def audit():
        mgr.require(mgr.common.sha(lib)==expected_lib,'library changed')
        for path,checksum in binaries.items(): mgr.require(mgr.common.sha(path)==checksum,'validator binary changed')
        mgr.require(json.loads(subprocess.check_output([str(identity)],env=env,text=True))==gpu,'GPU changed')
    try:
        quick = [(int(n),f) for n in geometry for f in ('d2z_1d','z2d_1d')]
        quick += [(n,f) for n in coverage['stable_regression_sizes'] for f in mgr.common.FUNCS]
        for n,func in quick:
            audit();case=run/'quick'/('%d_%s'%(n,func))
            # Preserve the actual plan and generated source even if a quick
            # correctness check fails before the richer guard matrix begins.
            case_env=dict(env,FFT_TEST_OUT=str(case),ROCFFT_LAYER='40',
                          ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'),
                          ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'))
            run_logged([frozen,n,1,func,1],case_env,case)
            rows=mgr.common.read_rows(case/'fft_test_1d.csv')
            mgr.require(len(rows)==1,'wrong quick-check row count');mgr.common.validate_row(rows[0],n,func)
            record['quick_checks'].append(dict(N=n,func=func,check='PASS',csv_sha256=mgr.common.sha(case/'fft_test_1d.csv')))
        for n_text,g in geometry.items():
            n=int(n_text);c=g['C'];q=g['Q']
            for direction in ('z2d','d2z'):
                for callbacks in (False,True):
                    audit();case=run/'guards'/str(n)/direction/('callbacks' if callbacks else 'plain')
                    list_path, refs = reference_list(n,c,q,direction,callbacks,scratch)
                    case_env=dict(env,ROCFFT_LAYER='44',ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'),
                                  ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'),ROCFFT_LOG_PROFILE_PATH=str(case/'profile.txt'))
                    run_logged([guard,n,direction,list_path,'callbacks' if callbacks else 'plain'],case_env,case)
                    stdout=(case/'stdout.txt').read_text();rtc=(case/'rtc.txt').read_text();plan=(case/'plan.txt').read_text()+stdout
                    count=len(refs)
                    mgr.require(stdout.count('EVEN_CC_GUARD_PASS')==count and 'EVEN_CC_ALL_PASS cases=%d'%count in stdout,
                                'incomplete reference/guard checks')
                    schemes=re.findall(r'CS_KERNEL_[A-Z0-9_]+',(case/'profile.txt').read_text())
                    mgr.require(len(schemes)==4*count and schemes.count('CS_KERNEL_STOCKHAM_BLOCK_CC')==2*count
                                and schemes.count('CS_KERNEL_STOCKHAM_BLOCK_RC')==2*count,'expected exactly two executed CC leaves')
                    mgr.require('CS_L1D_CC' in plan and 'CS_L1D_TRTRT' not in plan
                                and 'CS_KERNEL_R_TO_CMPLX' not in plan and 'CS_KERNEL_CMPLX_TO_R' not in plan,
                                'separate real processing or transpose path remains')
                    role='paired_pre_columns' if direction=='z2d' else 'generic_paired_post'
                    names=set(re.findall(r'fft_rtc_[A-Za-z0-9_]+',rtc))
                    specialized={name for name in names if '_'+role+'_v1_' in name}
                    suffix='_%s_v1_C%d_Q%d_N%d_lds'%(role,c,q,n)
                    mgr.require(specialized and all(suffix in name for name in specialized),'wrong fused generator identity')
                    if direction=='d2z':mgr.require('twiddle_gen_packed_real_post_generic_v1_dp' in rtc,'wrong post table generator')
                    layouts=set(re.findall(r'EXP126 pair geometry C=(\d+) Q=(\d+) T=(\d+) W=(\d+) LDS=(\d+)',plan))
                    mgr.require(len(layouts)==1,'ambiguous or absent actual paired geometry')
                    actual_c,actual_q,t,w,lds=map(int,next(iter(layouts)))
                    mgr.require((actual_c,actual_q)==(c,q) and t>=2 and t%2==0,'wrong matrix pair layout')
                    axis=q if direction=='z2d' else c
                    tail=bool(((axis+1)//2)%(t//2))
                    record['fusion_evidence'].append(dict(N=n,direction=direction,callbacks=callbacks,
                        cases=count,executed_leaves_per_transform=2,check='PASS',C=c,Q=q,T=t,W=w,LDS=lds,
                        true_pair_tail=tail,kernel_names=sorted(specialized),references=refs,
                        evidence_sha256={p:mgr.common.sha(case/p) for p in ('stdout.txt','stderr.txt','plan.txt','rtc.txt','profile.txt')}))
        for family, sizes in coverage['families'].items():
            mgr.require(len(sizes)==5 and len(set(sizes))==5,'family must contain five distinct sizes')
            for n in sizes:
                rows=[e for e in record['fusion_evidence'] if e['N']==n]
                mgr.require(len(rows)==4,'size lacks both directions and callback/plain evidence')
                if family.endswith('tail'):
                    direction='z2d' if family=='pre_tail' else 'd2z'
                    mgr.require(all(e['true_pair_tail'] for e in rows if e['direction']==direction),'candidate did not cover true pair tail')
                else:
                    g=geometry[str(n)];parity=('O' if g['C']%2 else 'E')+('O' if g['Q']%2 else 'E')
                    mgr.require(parity==family,'wrong parity family')
            record['coverage'][family]=dict(sizes=sizes,actual_fusion='PASS')
        audit();mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity'],'source changed during validation')
        mgr.require(len(record['quick_checks'])==len(quick) and len(record['fusion_evidence'])==len(geometry)*4,
                    'incomplete validation matrix')
        record['complete']=True
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        mgr.dumps(run/'even-cc-validation.json',record)
    print(run/'even-cc-validation.json')

if __name__=='__main__':main()
