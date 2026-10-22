"""Offline ISA comparison of the exact accepted RTC text; no device timings."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

RECORD = ROOT/'experiments/EXP-128/records/regression-955252-20261022/analysis-957127'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/regression-957127'


def analyze_isa(text):
    instructions = re.findall(r'^\s*((?:s_|v_|ds_|buffer_|flat_|global_)[a-z0-9_]+)([^\n]*)',text,re.M)
    counts = Counter(name for name,_ in instructions)
    groups = dict(total=len(instructions),
        fp64=sum(count for name,count in counts.items() if '_f64' in name),
        vector_integer=sum(count for name,count in counts.items() if name.startswith('v_')
                           and not any(tag in name for tag in ('_f64','_f32','_f16'))),
        exec_control=sum(count for name,count in counts.items() if name.startswith('s_')
                          and any(tag in name for tag in ('branch','exec','fork','join'))),
        barriers=counts['s_barrier'],
        ds_reads=sum(count for name,count in counts.items() if name.startswith('ds_read')),
        ds_writes=sum(count for name,count in counts.items() if name.startswith('ds_write')),
        global_loads=sum(count for name,count in counts.items() if name.startswith(('global_load','buffer_load','flat_load'))),
        global_stores=sum(count for name,count in counts.items() if name.startswith(('global_store','buffer_store','flat_store'))))
    resources = {key:int(re.search(r'\.'+key+r':\s*(\d+)',text).group(1))
                 for key in ('vgpr_count','sgpr_count','vgpr_spill_count','private_segment_fixed_size')}
    sequence = '\n'.join(name+args for name,args in instructions)
    return dict(resources=resources,static_instruction_groups=groups,mnemonics=dict(counts),
                instruction_text_sha256=hashlib.sha256(sequence.encode()).hexdigest())


def compile_one(item):
    source = Path(item['offline_source'])
    assembly = source.with_name(source.name.removesuffix('.hip.cpp')+'.s')
    command = [mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936',
               '--cuda-device-only','-S','-mcumode',str(source),'-o',str(assembly)]
    proc = subprocess.run(command,env=mgr.environment(ART),capture_output=True,text=True,timeout=120)
    assembly.with_suffix('.compile.err').write_text(proc.stderr)
    if proc.returncode:
        raise RuntimeError(str(source)+': '+proc.stderr[-1000:])
    result = dict(item,assembly=str(assembly),command=command,**analyze_isa(assembly.read_text()))
    print(item['N'],item['func'],item['arm'],item['position'],result['static_instruction_groups'],flush=True)
    return result


def main():
    data = json.loads((RECORD/'source-comparison.json').read_text())
    tasks = []
    for item in data['kernels']:
        for kernel in item['kernels']:
            if 'offline_source' not in kernel:
                continue
            n,func,arm = item['N'],item['func'],item['arm']
            # All stages for primary examples; previous only for incremental examples.
            if ((n in (65536,131072,167042,69938) and arm in ('baseline','candidate')) or
                (n == 142688 and arm in ('baseline','candidate','previous')) or
                (n in (82134,346112,497664) and arm in ('previous','candidate'))):
                tasks.append(dict(N=n,func=func,arm=arm,**kernel))
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(compile_one,tasks))
    (RECORD/'isa-summary.json').write_text(json.dumps(dict(complete=True,device_execution=False,
        limitation='Static instruction counts are not executed instruction counts or device timings. '
                   'Resources derive from offline compilation of exact accepted RTC sources.',
        kernels=result),ensure_ascii=False,indent=2)+'\n')
    print('COMPLETE',len(result),flush=True)


if __name__ == '__main__':
    main()
