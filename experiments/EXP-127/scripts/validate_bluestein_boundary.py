"""Managed Bluestein boundary correctness, ownership and default-plan evidence."""
import argparse
import datetime
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
import numpy as np

PATTERNS=('impulse','last','dc','nyquist','middle','tones','random')

def run_logged(command,env,case):
    case.mkdir(parents=True)
    with (case/'stdout.txt').open('xb') as out,(case/'stderr.txt').open('xb') as err:
        subprocess.run(list(map(str,command)),env=env,stdout=out,stderr=err,check=True)

def references(n,direction,callbacks,scratch):
    m=n//2;index=np.arange(n);rows=[];metadata=[]
    for pattern in PATTERNS:
        x=np.zeros(n)
        if pattern=='impulse':x[0]=0.5
        elif pattern=='last':x[-1]=-0.375
        elif pattern=='dc':x.fill(0.25)
        elif pattern=='nyquist':x=np.where(index%2,-0.375,0.375)
        elif pattern=='middle':x=0.5*np.cos(2*np.pi*(m//2)*index/n)
        elif pattern=='tones':
            x=0.5*np.cos(2*np.pi*7*index/n)+0.125*np.sin(2*np.pi*(m-3)*index/n)
            x+=0.25*np.cos(2*np.pi*(m//3)*index/n)
        else:x=np.random.default_rng(127+n).normal(size=n)
        value=x if direction=='d2z' else np.fft.rfft(x)
        if direction=='z2d' and pattern=='random':
            rng=np.random.default_rng(127+n)
            value=rng.normal(size=m+1)+1j*rng.normal(size=m+1)
            value[0]=value[0].real;value[-1]=value[-1].real
        complex_transform=direction in ('cforward','cinverse')
        if complex_transform:
            value=x.astype(np.complex128)+0.25j*np.roll(x,3)
            if pattern=='random':
                value+=1j*np.random.default_rng(127+n+1).normal(size=n)
        raw=np.ascontiguousarray(value,dtype='<f8' if direction=='d2z' else '<c16')
        input_path=scratch/(pattern+'-input.bin');raw.tofile(input_path)
        if callbacks:value=value*0.75+(np.arange(len(value))%7)*0.03125
        if complex_transform:
            transformed=np.fft.fft(value) if direction=='cforward' else np.fft.ifft(value)*n
        else:
            transformed=np.fft.rfft(value) if direction=='d2z' else np.fft.irfft(value,n=n)*n
        for scale in (1.0,0.375):
            expected=transformed*scale
            if callbacks:expected=expected*1.125+(np.arange(len(expected))%5)*0.015625
            path=scratch/(pattern+'-'+str(scale)+'-expected.bin')
            np.ascontiguousarray(expected,dtype='<c16' if direction!='z2d' else '<f8').tofile(path)
            rows.append('%s %.17g %s %s'%(pattern,scale,input_path,path))
            metadata.append(dict(pattern=pattern,scale=scale,input=str(input_path),expected=str(path),
                                 input_sha256=mgr.common.sha(input_path),
                                 expected_sha256=mgr.common.sha(path),seed=127+n))
    path=scratch/'reference-list.txt';path.write_text('\n'.join(rows)+'\n')
    return path,metadata

def plan_nodes(text):
    matches=list(re.finditer(r'(?m)^([ \t]*)scheme: (CS_[A-Z0-9_]+)',text));nodes=[]
    fields=('dimension','batch','length','direction','lengthBlue')
    for i,match in enumerate(matches):
        block=text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        nodes.append(dict(scheme=match.group(2),indent=len(match.group(1)),**{key:next(iter(re.findall(
            r'(?m)^\s*'+key+r': ([^\r\n]+)',block)),None) for key in fields}))
    return nodes

def convolution_signature(text):
    nodes=plan_nodes(text);start=next(i for i,n in enumerate(nodes) if n['scheme']=='CS_BLUESTEIN')
    # The six ordinary convolution children are preserved. Ignore the two user
    # boundary leaves and their parent view, not any inner FFT decomposition.
    ignored={'CS_BLUESTEIN','CS_KERNEL_CHIRP','CS_KERNEL_PAD_MUL','CS_KERNEL_RES_MUL',
             'CS_KERNEL_CMPLX_TO_R','CS_KERNEL_R_TO_CMPLX'}
    result=[]
    for node in nodes[start+1:]:
        if node['indent']<=nodes[start]['indent']:break
        if node['scheme'] not in ignored:
            result.append({k:v.strip() if isinstance(v,str) else v for k,v in node.items() if k!='indent'})
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','build-record','run','build','cache'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();cfg=mgr.load(args.config)
    built=json.loads(mgr.inside(args.build_record).read_text())
    mgr.require(built['complete'] and built['arm']['source_commit']==cfg['build']['source_commit'],'build identity mismatch')
    mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity'],'source changed')
    mgr.validation_hook(cfg)
    coverage=json.loads(mgr.inside(cfg['validation']['coverage']).read_text())
    mgr.require(len(coverage['sizes'])==20 and len(coverage['families'])==4,'incomplete size registration')
    run=mgr.inside(args.run);build=mgr.inside(args.build)/'validation';build.mkdir()
    scratch=mgr.inside(args.cache)/'reference';scratch.mkdir()
    env=mgr.environment(mgr.inside(args.cache));install=mgr.inside(built['arm']['install'])
    lib=install/'lib/librocfft.so.0.1';digest=built['arm']['library_sha256']
    env.update(LD_PRELOAD=str(lib),LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    source=ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
    identity=build/'device_identity';frozen=build/'fft_test_1d';guard=build/'real_boundary_guard'
    mgr.require(mgr.common.sha(ROOT/'tools/fft_measurement/fft_test_1d.cpp')==mgr.common.SOURCE_SHA,'frozen tool changed')
    commands=[
      [mgr.DTK+'/bin/hipcc','-O3','-std=c++17',str(ROOT/'tools/fft_measurement/device_identity.cpp'),'-o',str(identity)],
      [mgr.DTK+'/bin/hipcc','-O3','-std=c++17',str(ROOT/'tools/fft_measurement/fft_test_1d.cpp'),
       '-I'+str(install/'include'),'-L'+str(install/'lib'),'-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-o',str(frozen)],
      [mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',cfg['validation']['guard_source'],
       '-I'+str(install/'include'),'-I'+str(source/'shared'),'-L'+str(install/'lib'),
       '-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-o',str(guard)]]
    for i,command in enumerate(commands):
        with (run/'logs'/('validate-compile-%d.txt'%i)).open('xb') as out:
            subprocess.run(command,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
    mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936','wrong GPU profile')
    mgr.require(re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16),'wrong GPU UUID')
    binaries={str(p):mgr.common.sha(p) for p in (identity,frozen,guard)}
    for binary in (frozen,guard):
        linked=subprocess.check_output(['ldd',str(binary)],env=env,text=True)
        loaded=[mgr.inside(line.strip().split('=>')[-1].strip().split(' ')[0])
                for line in linked.splitlines() if 'librocfft.so' in line]
        mgr.require('not found' not in linked and len(set(loaded))==1 and loaded[0]==lib,'wrong candidate library')
        (run/'logs'/(binary.name+'-ldd.txt')).write_text(linked)
    stable=cfg['validation']['matched_stable'];stable_lib=mgr.inside(stable['library'])
    mgr.require(mgr.common.sha(stable_lib)==stable['sha256'],'matched stable changed')
    stable_env=dict(env,LD_PRELOAD=str(stable_lib),LD_LIBRARY_PATH=str(stable_lib.parent)+':'+env['LD_LIBRARY_PATH'])
    record=dict(complete=False,formal=False,job_id=os.environ['SLURM_JOB_ID'],gpu=gpu,
        allocation=mgr.common.single_gpu_allocation(os.environ),source_commit=built['arm']['source_commit'],
        library_sha256=digest,matched_stable=stable,binaries=binaries,compile_commands=commands,
        default_path_only=True,numpy_version=np.__version__,quick_checks=[],matched_plans=[],
        guard_groups=[],complex_guard_groups=[],stable_diagnostics=[],scope_checks=[],failures=[],families={},
        reference='Independent full-length NumPy real FFT; retained recipe and all binary hashes',
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())
    def audit():
        mgr.require(mgr.common.sha(lib)==digest and mgr.common.sha(stable_lib)==stable['sha256'],'library changed')
        for p,h in binaries.items():mgr.require(mgr.common.sha(p)==h,'validator changed')
        mgr.require(json.loads(subprocess.check_output([str(identity)],env=env,text=True))==gpu,'device changed')
    def logged_env(case,base=env,layer='45'):
        return dict(base,ROCFFT_LAYER=layer,ROCFFT_LOG_TRACE_PATH=str(case/'trace.txt'),
            ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'),
            ROCFFT_LOG_PROFILE_PATH=str(case/'profile.txt'),FFT_TEST_OUT=str(case))
    try:
        quick=[{'N':int(n),'func':f+'_1d','kind':'target'} for n in coverage['sizes'] for f in ('d2z','z2d')]
        quick+=coverage['controls']
        for item in quick:
            n=item['N'];func=item['func'];case=run/'quick'/('%d_%s'%(n,func));audit()
            try:
                run_logged([frozen,n,1,func,1],logged_env(case,layer='41'),case)
                rows=mgr.common.read_rows(case/'fft_test_1d.csv');mgr.require(len(rows)==1,'wrong quick row count')
                mgr.common.validate_row(rows[0],n,func)
                text=(case/'plan.txt').read_text()+(case/'stdout.txt').read_text()
                if item['kind']!='target':mgr.require('_real_pre_blue_v1' not in text and '_real_post_blue_v1' not in text,'scope leaked')
                if n in coverage['fused_complex_controls'] and func=='z2z_1d':
                    rtc=(case/'rtc.txt').read_text()
                    mgr.require('Fused chirp + padding w/ fwd FFT' in text
                        and 'static SBRC initial global-to-register load' in rtc,
                        'complex regression did not cover the repaired default path')
                    for role in ('fwd_chirp','fwd_chirp_mul','inv_chirp_mul'):
                        mgr.require('bluestein_load_rc_'+role+'_device' in rtc,
                                    'complex regression missing convolution stage')
                record['quick_checks'].append(dict(item,check='PASS',csv_sha256=mgr.common.sha(case/'fft_test_1d.csv')))
            except (subprocess.CalledProcessError,ValueError) as error:
                record['failures'].append(dict(stage='quick',case=item,error=str(error),evidence=str(case)))
        mgr.require(not record['failures'],'quick failures; see retained evidence')
        # Retained-library failures remain diagnostic evidence, never accepted
        # correctness or a time comparison against a mathematically invalid arm.
        for n in coverage['fused_complex_controls']:
            case=run/'stable-diagnostic'/str(n);audit()
            try:
                run_logged([frozen,n,1,'z2z_1d',1],logged_env(case,stable_env,'41'),case)
            except subprocess.CalledProcessError as error:
                mgr.require(error.returncode==2,'stable diagnostic runtime error')
            rows=mgr.common.read_rows(case/'fft_test_1d.csv')
            mgr.require(len(rows)==1,'incomplete stable diagnostic')
            record['stable_diagnostics'].append(dict(N=n,formal=False,row=rows[0],
                csv_sha256=mgr.common.sha(case/'fft_test_1d.csv'),
                plan_sha256=mgr.common.sha(case/'plan.txt'),rtc_sha256=mgr.common.sha(case/'rtc.txt')))
        for n in coverage['fused_complex_controls']:
            for direction in ('cforward','cinverse'):
                for callbacks in (False,True):
                    audit();case=run/'complex-guards'/str(n)/direction/('callbacks' if callbacks else 'plain')
                    reference_dir=scratch/str(n)/direction/('callbacks' if callbacks else 'plain')
                    reference_dir.mkdir(parents=True)
                    reference_list,refs=references(n,direction,callbacks,reference_dir)
                    try:
                        run_logged([guard,n,direction,reference_list,'callbacks' if callbacks else 'plain'],logged_env(case),case)
                        stdout=(case/'stdout.txt').read_text();plan=(case/'plan.txt').read_text()
                        mgr.require(stdout.count('REAL_BOUNDARY_GUARD_PASS')==len(refs)
                            and 'REAL_BOUNDARY_ALL_PASS cases=%d'%len(refs) in stdout,'incomplete complex reference')
                        mgr.require('Fused chirp + padding w/ fwd FFT' in plan
                            and '_real_pre_blue_v1' not in plan and '_real_post_blue_v1' not in plan,
                            'complex regression changed scope/plan')
                        record['complex_guard_groups'].append(dict(N=n,direction=direction,callbacks=callbacks,
                            check='PASS',references=refs,executions=2*len(refs),
                            evidence_sha256={p:mgr.common.sha(case/p)
                                for p in ('stdout.txt','stderr.txt','plan.txt','rtc.txt','profile.txt')}))
                    except (subprocess.CalledProcessError,ValueError) as error:
                        record['failures'].append(dict(stage='complex-guard',N=n,direction=direction,callbacks=callbacks,
                            error=str(error),evidence=str(case)))
        for n_text,g in coverage['sizes'].items():
            n=int(n_text);m=n//2
            for direction in ('z2d','d2z'):
                quick_case=run/'quick'/('%d_%s_1d'%(n,direction))
                stable_case=run/'matched-stable'/str(n)/direction
                run_logged([frozen,n,1,direction+'_1d',1],logged_env(stable_case,stable_env,'41'),stable_case)
                rows=mgr.common.read_rows(stable_case/'fft_test_1d.csv');mgr.require(len(rows)==1,'wrong stable row count')
                mgr.common.validate_row(rows[0],n,direction+'_1d')
                before=(stable_case/'plan.txt').read_text();after=(quick_case/'plan.txt').read_text()
                mgr.require(convolution_signature(before)==convolution_signature(after),'inner convolution plan changed')
                record['matched_plans'].append(dict(N=n,direction=direction,check='PASS',
                    before_sha256=mgr.common.sha(stable_case/'plan.txt'),after_sha256=mgr.common.sha(quick_case/'plan.txt')))
                for callbacks in (False,True):
                    audit();case=run/'guards'/str(n)/direction/('callbacks' if callbacks else 'plain')
                    reference_dir=scratch/str(n)/direction/('callbacks' if callbacks else 'plain')
                    reference_dir.mkdir(parents=True)
                    reference_list,refs=references(n,direction,callbacks,reference_dir)
                    try:
                        run_logged([guard,n,direction,reference_list,'callbacks' if callbacks else 'plain'],logged_env(case),case)
                        stdout=(case/'stdout.txt').read_text();rtc=(case/'rtc.txt').read_text();plan=(case/'plan.txt').read_text()+stdout
                        count=len(refs)
                        mgr.require(stdout.count('REAL_BOUNDARY_GUARD_PASS')==count
                            and 'REAL_BOUNDARY_ALL_PASS cases=%d'%count in stdout,'incomplete independent references')
                        schemes=re.findall(r'CS_KERNEL_[A-Z0-9_]+',(case/'profile.txt').read_text())
                        mgr.require(schemes.count('CS_KERNEL_PAD_MUL')==2*count
                            and schemes.count('CS_KERNEL_RES_MUL')==2*count
                            and schemes.count('CS_KERNEL_FFT_MUL')==2*count,'ordinary convolution not executed')
                        mgr.require(not any(s.startswith(('CS_KERNEL_R_TO_CMPLX','CS_KERNEL_CMPLX_TO_R')) for s in schemes),
                                    'independent real processing was executed')
                        role='_real_pre_blue_v1' if direction=='z2d' else '_real_post_blue_v1'
                        names=set(re.findall(r'bluestein_(?:pad|res)_mul[A-Za-z0-9_]*',rtc))
                        fused=sorted(name for name in names if role in name)
                        mgr.require(fused and role in plan,'missing compiled real boundary identity')
                        nodes=plan_nodes(plan)
                        blues=[p for p in nodes if p['scheme']=='CS_BLUESTEIN']
                        mgr.require(blues,'missing Bluestein plan')
                        length_blue=int(blues[0]['lengthBlue'].strip())
                        kind='Lpow2' if length_blue&(length_blue-1)==0 else 'Lmixed'
                        actual_group='Bluestein-M'+('odd' if m%2 else 'even')+'-'+kind
                        mgr.require(actual_group==g['group'] and length_blue>=2*m-1,'wrong actual size family')
                        descriptor='N=%d M=%d pair_tasks=%d'%(n,m,m//2+1)
                        mgr.require(descriptor in plan and 'phase_entries=%d'%((n+3)//4) in plan,'wrong descriptor or phase table')
                        mgr.require(convolution_signature(plan)==convolution_signature(after),'guard changed interior plan')
                        record['guard_groups'].append(dict(N=n,direction=direction,callbacks=callbacks,check='PASS',
                            M=m,L=length_blue,actual_group=actual_group,references=refs,executions=2*count,
                            kernel_names=fused,evidence_sha256={p:mgr.common.sha(case/p)
                                for p in ('stdout.txt','stderr.txt','plan.txt','rtc.txt','profile.txt')}))
                    except (subprocess.CalledProcessError,ValueError) as error:
                        record['failures'].append(dict(stage='guard',N=n,direction=direction,callbacks=callbacks,
                            error=str(error),evidence=str(case)))
        scopes=[dict(mode=mode,direction=direction,N=None,plan_only=mode=='single')
            for mode in coverage['scope_modes'] for direction in ('d2z','z2d')]
        scopes+=coverage['offset_scope_cases']
        mgr.require(len(scopes)==coverage['expected_scope_checks'],'wrong scope registration')
        for item in scopes:
            mode,direction,n=item['mode'],item['direction'],item['N']
            audit();case=run/'scope'/mode/(str(n) if n is not None else 'original')/direction
            argv=[guard,'scope',mode,direction]+([n] if n is not None else [])
            try:
                run_logged(argv,logged_env(case),case)
                text=(case/'stdout.txt').read_text()+(case/'plan.txt').read_text()
                mgr.require('REAL_BOUNDARY_SCOPE_PASS' in text,'scope validation incomplete')
                mgr.require('_real_pre_blue_v1' not in text and '_real_post_blue_v1' not in text,'new role leaked outside scope')
                # All retained and generic CC fusion entries must respect the
                # same user-view gate, not just the new Bluestein boundary.
                if mode.startswith('offset'):
                    mgr.require(not any(role in text for role in
                        ('real IO:','EXP126 pair backend=','EXP125 local real','EXP125 real post:')),
                        'retained real pair role leaked into user-offset layout')
                record['scope_checks'].append(dict(item,check='PASS',
                    evidence_sha256={p:mgr.common.sha(case/p) for p in ('stdout.txt','stderr.txt','plan.txt')}))
            except (subprocess.CalledProcessError,ValueError) as error:
                record['failures'].append(dict(item,stage='scope',error=str(error),evidence=str(case)))
        mgr.require(not record['failures'],'independent correctness/scope failures; see retained evidence')
        for family,sizes in coverage['families'].items():
            mgr.require(len(sizes)==len(set(sizes))==5,'each family requires five distinct sizes')
            for n in sizes:
                groups=[e for e in record['guard_groups'] if e['N']==n]
                mgr.require(len(groups)==4 and all(e['actual_group']==family for e in groups),'incomplete actual family coverage')
            record['families'][family]=dict(sizes=sizes,actual_fusion='PASS')
        mgr.require(len(record['quick_checks'])==coverage['expected_quick_checks']
            and len(record['matched_plans'])==40 and len(record['guard_groups'])==80
            and len(record['scope_checks'])==coverage['expected_scope_checks']
            and len(record['complex_guard_groups'])==20 and len(record['stable_diagnostics'])==5,
            'incomplete matrix')
        audit();mgr.require(mgr.source_identity(cfg)==built['plan']['source_identity'],'source changed during validation')
        record['complete']=True
    finally:
        record['end']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        mgr.dumps(run/'bluestein-boundary-validation.json',record)
    print(run/'bluestein-boundary-validation.json')

if __name__=='__main__':main()
