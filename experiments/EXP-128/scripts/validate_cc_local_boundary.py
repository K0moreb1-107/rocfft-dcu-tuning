"""Validate numerical results and actual v5 / same-CC unfused execution only."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
from cc_dispatch import inspect_dispatch
from validate_cc_local_grouped import CaseError,run,read_numerical_outputs,check_cases,write
import cufft261012_contract as contract


def row_features(name,source,c,q,func):
    lanes=int(re.search(r'_tpt_(\d+)',name)[1])
    wgs=int(re.search(r'_wgs_(\d+)',name)[1]);rows=wgs//lanes
    mgr.require(rows*lanes==wgs,'invalid row workgroup geometry')
    if func=='z2d_1d':
        packed=c%2==0 and rows%2==0 and c%rows==0
        markers=('cc_packed_slot','cc_packed_component','cc_packed_pair') if packed else ('cc_output_p0',)
        mgr.require(all(x in source for x in markers),'actual output implementation differs')
        mgr.require(('cc_output_first' not in source) if packed else ('cc_output_first' in source),
                    'output classification does not match its generic geometry rule')
        return dict(packed_output=packed,threads_per_transform=lanes,rows_per_block=rows)
    mgr.require(name.endswith('_reg'),'d2z direct register input is required')
    first=int(re.search(r'_factors_(\d+)',name)[1]);count=q//first
    a=source.index('// load global into registers\n');b=source.index('// calc the thread_in_device',a)
    region=source[a:b];dense=re.sub(r'\s+','',region)
    recurrent=q>count+min(count,lanes)
    groups=(first+1)//2 if lanes>count else 1
    mgr.require(dense.count('if(cc_input_row==0)')==groups,'native input classification changed')
    if lanes>count:
        mgr.require('if(threadIdx.x%'+str(lanes)+'<'+str(count)+')' in dense,'active-lane guard missing')
    queries=1+(count+lanes-1)//lanes if recurrent else first*((count+lanes-1)//lanes)
    mgr.require(region.count('TW_NSteps<')==queries,'phase lookup count differs from native recurrence')
    mgr.require(('cc_phase_delta' in region)==recurrent,'phase recurrence selection differs')
    mgr.require('cc_spectrum_p0' in source,'folded output missing')
    return dict(phase_recurrence=recurrent,first_factor=first,threads_per_transform=lanes,
        rows_per_block=rows,classification_groups=groups,source_phase_lookups=queries,
        phase_lookups_per_ordinary_row=count+min(count,lanes) if recurrent else q)


def validate_names(names,c,q,func,fused):
    if fused:
        roles=(4,5) if func=='z2d_1d' else (6,7)
        mgr.require(len(names)==2 and all('_cc_local_v5_role%d_C%d_Q%d_'%(role,c,q) in name
            for role,name in zip(roles,names)),'both generic v5 adapters must execute')
        return names
    mgr.require(len(names)==3,'unfused CC must execute exactly three stages')
    forbidden=('_cc_local_v','_local_real_columns','_local_real_rows','_paired_post_rows')
    mgr.require(not any(marker in name for marker in forbidden for name in names),'unfused control executed fusion')
    boundary=names[0] if func=='z2d_1d' else names[2]
    prefix='c2r_even_pre_' if func=='z2d_1d' else 'r2c_even_post_'
    mgr.require(boundary.startswith(prefix),'independent boundary stage missing or misplaced')
    fft=names[1:] if func=='z2d_1d' else names[:2]
    for name,length,scheme in zip(fft,(c,q),('sbcc','sbrc')):
        mgr.require('_len_'+str(length)+'_' in name and '_'+scheme+'_' in name,
                    'unfused CC geometry differs: '+name)
    return fft


def build_switches(cache,fused):
    for key in ('ROCFFT_CC_REAL_FUSION','ROCFFT_CC_LOCAL_REAL_FUSION'):
        found=re.search(r'^'+key+r':(?:BOOL|UNINITIALIZED)=(ON|OFF)$',cache,re.M)
        mgr.require(found and found[1]==('ON' if fused else 'OFF'),'wrong build switch: '+key)


def trace_case(binary,case,func,env,folder,fused):
    n,c,q=(case[k] for k in ('N','C','Q'))
    profile=folder/'profile';harness=profile/'harness';data=folder/'metadata'
    for p in (harness,profile/'data',data):p.mkdir(parents=True)
    selected=dict(env,FFT_TEST_OUT=str(harness),ROCFFT_LAYER='40',
        ROCFFT_LOG_PLAN_PATH=str(data/'plan.txt'),ROCFFT_LOG_RTC_PATH=str(data/'rtc.txt'))
    run([mgr.DTK+'/bin/hipprof','--hip-trace','--trace-args','--output-type','0',
         '-o',profile/'trace','-d',profile/'data',binary,n,1,func],selected,profile,'trace')
    child=re.search(r'exited with status:\s*(\d+)',(profile/'trace.err').read_text())
    numerical=read_numerical_outputs(harness,n,func,int(child[1]) if child else None)
    try:
        plan=(data/'plan.txt').read_text()
        sources=dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
            (data/'rtc.txt').read_text(),re.M|re.S))
        launches,checked=inspect_dispatch(plan,json.loads((profile/'trace.json').read_text())['traceEvents'],func)
        names=[x['name'] for x in launches];fft=validate_names(names,c,q,func,fused)
        mgr.require(all(name in sources for name in fft),'actual FFT source missing')
        features=row_features(names[1],sources[names[1]],c,q,func) if fused else dict(fusion=False)
    except Exception as error:raise CaseError('dispatch',str(error)) from error
    return dict(N=n,func=func,check=numerical),dict(N=n,func=func,C=c,Q=q,
        row_features=features,actual_names=names,dispatch=checked,
        source_sha256={name:hashlib.sha256(sources[name].encode()).hexdigest() for name in fft})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','build-record','run','build','cache'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();cfg=mgr.load(a.config);settings=cfg['validation']
    mgr.require(settings['profile']=='cc-boundary-v5-two-checks' and settings['variant'] in ('fused','unfused_cc'),
                'wrong validation profile')
    fused=settings['variant']=='fused'
    built=json.loads(a.build_record.read_text());mgr.require(built['complete'],'build incomplete')
    build_switches((a.build/'CMakeCache.txt').read_text(),fused)
    coverage_path=mgr.inside(settings['coverage']);coverage=json.loads(coverage_path.read_text())
    by_n={x['N']:x for x in coverage['public']}
    mgr.require(set(settings['sample_N'])<=by_n.keys(),'representative missing from matrix')
    install=mgr.inside(built['arm']['install']);library=install/'lib/librocfft.so.0.1'
    folder=mgr.inside(a.run)/'measurement-validation';folder.mkdir()
    helpers=mgr.inside(a.cache)/'helpers';helpers.mkdir()
    env=mgr.environment(mgr.inside(a.cache));env['FFT_TEST_ITERS']='30'
    selected=dict(env,LD_PRELOAD=str(library),LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started=time.monotonic()
    record=dict(complete=False,formal=False,profile=settings['profile'],variant=settings['variant'],
        source_commit=built['arm']['source_commit'],library_sha256=built['arm']['library_sha256'],
        coverage_sha256=mgr.common.sha(coverage_path),scope=settings['scope'],numerical=[],dispatch=[],failures=[],
        callbacks_enabled=False,scales=[1.],start=datetime.datetime.now(datetime.timezone.utc).isoformat())
    def save():
        record['elapsed_seconds']=time.monotonic()-started
        write(a.run/'cc-boundary-validation.json',record)
    try:
        identity,binary=helpers/'device-identity',helpers/'measurement-v3'
        for output,source,flags in [
            (identity,ROOT/'tools/fft_measurement/device_identity.cpp',[]),
            (binary,ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,['-I'+str(install/'include'),
                '-L'+str(install/'lib'),'-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-lstdc++fs'])]:
            run([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936','-mcumode',
                source,*flags,'-o',output],env,folder,'compile-'+output.name)
        gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
        mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936'
            and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16),'single gfx936 required')
        record['gpu']=gpu
        check_cases(record,settings['sample_N'],settings['smoke_N'],
            lambda n,func:trace_case(binary,by_n[n],func,selected,folder/(str(n)+'-'+func),fused),save)
        finish(record,built,gpu,env,library,identity)
    except Exception as error:
        record['failure']=dict(error=type(error).__name__,message=str(error));raise
    finally:save()
    print(json.dumps(dict(complete=True,numerical=len(record['numerical']),dispatch=len(record['dispatch']),
        elapsed_seconds=record['elapsed_seconds'])))


if __name__=='__main__':main()
