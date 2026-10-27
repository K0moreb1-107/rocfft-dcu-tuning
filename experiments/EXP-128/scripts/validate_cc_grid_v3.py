"""Check numerical results and executed v3 CC geometry for each requested blank cell."""
import argparse
import datetime
import json
import re
import runpy
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
from tools.workspace_manager import manager as mgr
from tools.workspace_manager.validation_finish import finish
import cufft261012_contract as contract

V3=runpy.run_path(str(ROOT/'experiments/EXP-128/scripts/validate_cc_local_rows.py'))
run,write,trace_case,check_cases=(V3[key] for key in ('run','write','trace_case','check_cases'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','build-record','run','build','cache'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args()
    cfg=mgr.load(a.config)
    settings=cfg['validation']
    mgr.require(settings['profile']=='cc-v3-controlled-grid-two-checks', 'wrong validation profile')
    matrix=json.loads(mgr.inside(settings['matrix']).read_text())
    group=matrix['groups'][settings['group']]
    by_n={entry['N']:entry for entry in group}
    mgr.require(len(group)==len(by_n) and set(settings['sample_N'])==set(by_n),'incorrect geometry coverage')
    built=json.loads(a.build_record.read_text())
    mgr.require(built['complete'], 'candidate build incomplete')
    install=mgr.inside(built['arm']['install'])
    origin=json.loads((install/'grid-build.json').read_text())
    mgr.require(origin['group']==settings['group']
        and origin['base_commit']=='8da0abb02ae6f5591e448d3e10adef8919aae40f'
        and origin['only_static_divisor_table_changed']
        and origin['all_executable_bytes_identical'] and origin['all_bytes_outside_table_identical']
        and origin['matrix_sha256']==mgr.common.sha(mgr.inside(settings['matrix']))
        and origin['library_sha256']==built['arm']['library_sha256'], 'wrong v3 table-copy provenance')
    mgr.require({int(m):c for m,c in origin['changed_divisors'].items()}
                =={entry['N']//2:entry['C'] for entry in group}, 'changed map differs from requested cells')
    library=install/'lib/librocfft.so.0.1'
    folder=mgr.inside(a.run)/'measurement-validation'
    folder.mkdir()
    helpers=mgr.inside(a.cache)/'helpers'
    helpers.mkdir()
    env=mgr.environment(mgr.inside(a.cache))
    env['FFT_TEST_ITERS']='30'
    selected=dict(env,LD_PRELOAD=str(library),LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    started=time.monotonic()
    record=dict(complete=False,formal=False,profile=settings['profile'],
        source_commit=built['arm']['source_commit'],library_sha256=built['arm']['library_sha256'],
        matrix_sha256=mgr.common.sha(mgr.inside(settings['matrix'])),group=settings['group'],
        base_v3_commit=origin['base_commit'],numerical=[],dispatch=[],failures=[],
        callbacks_enabled=False,scales=[1.],
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())
    def save():
        record['elapsed_seconds']=time.monotonic()-started
        write(a.run/'cc-grid-validation.json',record)
    try:
        identity,binary=helpers/'device-identity',helpers/'measurement-v3'
        for output,source,flags in [
            (identity,ROOT/'tools/fft_measurement/device_identity.cpp',[]),
            (binary,ROOT/'tools/fft_measurement'/contract.SOURCE_NAME,
             ['-I'+str(install/'include'),'-L'+str(install/'lib'),
              '-Wl,-rpath,'+str(install/'lib'),'-lrocfft','-lstdc++fs'])]:
            run([mgr.DTK+'/bin/hipcc','-O2','-std=c++17','--offload-arch=gfx936',
                 '-mcumode',source,*flags,'-o',output],env,folder,'compile-'+output.name)
        gpu=json.loads(subprocess.check_output([str(identity)],env=env,text=True))
        mgr.require(gpu['count']==1 and gpu['arch'].split(':')[0]=='gfx936'
            and re.fullmatch('[0-9a-f]{32}',gpu['uuid']) and int(gpu['uuid'],16), 'single gfx936 required')
        record['gpu']=gpu
        check_cases(record,settings['sample_N'],settings['smoke_N'],
            lambda n,func:trace_case(binary,by_n[n],func,selected,folder/(str(n)+'-'+func)),save)
        finish(record,built,gpu,env,library,identity)
    except Exception as error:
        record['failure']=dict(error=type(error).__name__,message=str(error))
        raise
    finally:
        save()
    print(json.dumps(dict(complete=True,cells=len(group),numerical=len(record['numerical']),
                         dispatch=len(record['dispatch']),elapsed_seconds=record['elapsed_seconds'])))


if __name__=='__main__':
    main()
