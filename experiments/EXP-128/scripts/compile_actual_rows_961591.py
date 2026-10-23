"""Compile the exact logged RTC row source; reconstructed specifications are not runtime evidence."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa

RUN=ROOT/'experiments/EXP-128/runs/EXP-128-cc-rows-v3-regression-diagnostic-20261023'
OUT=ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023/results-961591'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/actual-rows-961591'


def compile_one(item):
    stem=ART/('%d-%s-%s-%s'%(item['N'],item['func'],item['arm'],item['variant']))
    source=stem.with_suffix('.hip.cpp'); assembly=stem.with_suffix('.s')
    source.write_text('#include <hip/hip_runtime.h>\n'+item['source'])
    data={k:v for k,v in item.items() if k!='source'}
    command=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936',
             '--cuda-device-only','-S','-mcumode',str(source),'-o',str(assembly)]
    p=subprocess.run(command,env=mgr.environment(ART),capture_output=True,text=True,timeout=150)
    stem.with_suffix('.err').write_text(p.stderr)
    if p.returncode:
        return dict(data,complete=False,error=p.stderr[-2000:])
    result=dict(data,complete=True,command=command,assembly=str(assembly),**analyze_isa(assembly.read_text()))
    print('COMPILED',item['N'],item['func'],item['arm'],item['variant'],flush=True)
    return result


def main():
    record=json.loads((RUN/'diagnostic-result.json').read_text()); ART.mkdir(exist_ok=True)
    tasks=[]
    for item in record['traces']:
        text=(Path(item['folder'])/'metadata/rtc.txt').read_text()
        sources={name:src[:-1] for name,src in re.findall(
            r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S)}
        role=5 if item['func']=='z2d_1d' else 7
        names=[name for name in sources if '_role%d_'%role in name and '_CB' not in name]
        assert len(names)==1,names
        name=names[0]; src=sources[name]
        tasks.append(dict(N=item['N'],func=item['func'],arm=item['arm'],variant='original',
            source=src,source_sha256=hashlib.sha256(src.encode()).hexdigest(),name=name,
            evidence=str(Path(item['folder'])/'metadata/rtc.txt')))
    for item in record['ablations']:
        if item['metadata'] or item['variant']=='identity': continue
        rule=next(x for x in item['rules'] if x['name'] in item['required_source_names'])
        path=Path(rule['replacement']); src=path.read_text()
        assert hashlib.sha256(src.encode()).hexdigest()==rule['replacement_sha256']
        tasks.append(dict(N=item['N'],func=item['func'],arm=item['arm'],variant=item['variant'],
            source=src,source_sha256=rule['replacement_sha256'],name=rule['name'],evidence=str(path)))
    assert len(tasks)==142,len(tasks)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(compile_one,tasks))
    failures=[x for x in rows if not x['complete']]
    result=dict(complete=not failures,device_execution=False,exact_logged_sources=True,
        source_run='961591',kernels=rows,failures=failures,
        limitation='Static ISA compiled from exact logged sources with listed hipcc flags. Runtime resource allocations and performance are separate measured evidence.')
    (OUT/'actual-source-isa.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    assert not failures,failures
    print(json.dumps(dict(complete=True,kernels=len(rows),output=str(OUT/'actual-source-isa.json'))),flush=True)


if __name__=='__main__': main()
