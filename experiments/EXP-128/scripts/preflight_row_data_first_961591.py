"""Offline source-order prototype on copies; no production edit or device-performance claim."""
from concurrent.futures import ThreadPoolExecutor
import collections
import hashlib
import json
from pathlib import Path
import re

import compile_actual_rows_961591 as compiler

ROOT=Path('/public/home/zhangkewei/zr')
OLD=ROOT/'experiments/EXP-128/artifacts/preflight/actual-rows-961591'
OUT=ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023/results-961591'
compiler.ART=ROOT/'experiments/EXP-128/artifacts/preflight/data-first-961591'


def rearrange(source):
    start=source.index('// load global into registers\n')
    end=source.index('// calc the thread_in_device',start)
    region=source[start:end]
    pattern=re.compile(r'(const scalar_type cc_row_phase_(\d+) = [^\n]+;\n)'
        r'(R\[\2\] = load_cb\([^\n]+\);\n)'
        r'(R\[\2\] = \{[^\n]+\};\n)')
    matches=list(pattern.finditer(region)); assert matches
    groups=[]
    for match in matches:
        if groups and not region[groups[-1][-1].end():match.start()].strip(): groups[-1].append(match)
        else: groups.append([match])
    changed=region
    for group in reversed(groups):
        a,b=group[0].start(),group[-1].end()
        loads=''.join(m[3] for m in group)
        phases=''.join(m[1]+m[4] for m in group)
        changed=changed[:a]+loads+phases+changed[b:]
    # Only reorder the same whole statements within their original lane guard.
    assert collections.Counter(region.splitlines())==collections.Counter(changed.splitlines())
    assert region.count('load_cb(')==changed.count('load_cb(')
    return source[:start]+changed+source[end:],dict(registers=len(matches),groups=[len(g) for g in groups])


def waits(path):
    text=path.read_text().splitlines()
    end=next(i for i,line in enumerate(text) if 's_barrier' in line)
    head=text[:end]
    return dict(first_barrier_line=end+1,static_wait_all=sum('s_waitcnt vmcnt(0)' in s for s in head),
        static_vm_waits=sum('s_waitcnt vmcnt' in s for s in head),
        static_global_loads=sum('global_load' in s for s in head))


def main():
    compiler.ART.mkdir(exist_ok=True)
    actual=json.loads((OUT/'actual-source-isa.json').read_text())
    numbers={173056,262144,1048576,204800,497664,303750,425984,574992,167042,142688}
    tasks=[]; previous={}
    for item in actual['kernels']:
        if item['N'] not in numbers or item['func']!='d2z_1d' or item['arm']!='candidate' or item['variant']!='original': continue
        path=Path(item['assembly']).with_suffix('.hip.cpp')
        src=path.read_text().removeprefix('#include <hip/hip_runtime.h>\n')
        assert hashlib.sha256(src.encode()).hexdigest()==item['source_sha256']
        changed,proof=rearrange(src)
        tasks.append(dict(N=item['N'],func=item['func'],arm='candidate',variant='data_first',
            name=item['name'],source=changed,source_sha256=hashlib.sha256(changed.encode()).hexdigest(),
            original_source_sha256=item['source_sha256'],reorder=proof))
        previous[item['N']]=item
    assert len(tasks)==10
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(compiler.compile_one,tasks))
    assert all(x['complete'] for x in rows),rows
    for item in rows:
        old=previous[item['N']]
        item['original_resources']=old['resources']
        item['original_instructions']=old['static_instruction_groups']
        item['original_prefix']=waits(Path(old['assembly']))
        item['prototype_prefix']=waits(Path(item['assembly']))
        item['instructions_equal']=old['instruction_text_sha256']==item['instruction_text_sha256']
    result=dict(complete=True,formal=False,device_execution=False,production_source_modified=False,kernels=rows,
        limitation='This source-order prototype is only offline feasibility evidence; numerical device checks and paired performance remain required.')
    (OUT/'data-first-preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=True,kernels=len(rows),changed_isa=sum(not x['instructions_equal'] for x in rows)),indent=2))


if __name__=='__main__': main()
