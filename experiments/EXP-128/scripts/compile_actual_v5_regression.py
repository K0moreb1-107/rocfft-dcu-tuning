"""Offline comparison of actual default RTC sources from diagnostic 985072."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from cc_v5_regression_common import rtc_sources
from isa_cc_957127 import analyze_isa

RUN=ROOT/'experiments/EXP-128/runs/EXP-128-cc-v5-regression-diagnostic-20261027'
OUT=ROOT/'experiments/EXP-128/records/v5-regression-20261027/results-985072'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/v5-regression-actual-985072'


def main():
    ART.mkdir(parents=True,exist_ok=True)
    result=json.loads((RUN/'diagnostic-result.json').read_text());assert result['complete']
    traces={(x['N'],x['func'],x['arm']):x for x in result['traces']}
    tasks=[]
    for n in (69938,97104,129472,142688,425920,640000,646866,2725888):
        for arm in ('candidate','unfused_cc'):
            tasks.append(dict(N=n,func='z2d_1d',arm=arm,stage='row'))
    for arm in ('candidate','unfused_cc'):
        tasks.append(dict(N=2725888,func='z2d_1d',arm=arm,stage='column'))
    for n in (161840,1048576):
        for arm in ('candidate','previous'):
            for stage in ('column','row'):tasks.append(dict(N=n,func='z2d_1d',arm=arm,stage=stage))
    def compile_one(task):
        trace=traces[task['N'],task['func'],task['arm']];assert trace['valid']
        position=(0 if task['stage']=='column' else 1)+(task['arm']=='unfused_cc')
        name=trace['trace']['kernel_names'][position]
        path=Path(trace['folder'])/'metadata/rtc.txt';source=rtc_sources(path.read_text())[name]
        stem=ART/('%d-%s-%s-%s'%(task['N'],task['func'],task['arm'],task['stage']))
        original=stem.with_suffix('.cpp');original.write_text(source)
        unit=stem.with_suffix('.hip.cpp');assembly=stem.with_suffix('.s')
        unit.write_text('#include <hip/hip_runtime.h>\n'+source)
        argv=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936','--cuda-device-only',
              '-mcumode','-S',str(unit),'-o',str(assembly)]
        proc=subprocess.run(argv,env=mgr.environment(ART),text=True,capture_output=True,timeout=180)
        stem.with_suffix('.err').write_text(proc.stderr)
        entry=dict(task,name=name,source=str(original),source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            metadata=str(path),command=argv,complete=proc.returncode==0)
        if proc.returncode:entry['error']=proc.stderr[-3000:]
        else:entry.update(analyze_isa(assembly.read_text()))
        return entry
    with ThreadPoolExecutor(max_workers=2) as pool:entries=list(pool.map(compile_one,tasks))
    value=dict(complete=all(x['complete'] for x in entries),device_execution=False,
        limitation='Actual dispatched RTC source compiled offline with common flags. Static instructions are not dynamic counts or measured wait cycles.',
        kernels=entries)
    (OUT/'actual-isa-summary.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=value['complete'],compiled=len(entries),failures=[x for x in entries if not x['complete']]),ensure_ascii=False))
    assert value['complete']


if __name__=='__main__':main()
