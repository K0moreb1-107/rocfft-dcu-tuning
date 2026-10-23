"""Offline native-layout policy: partial first-stage lanes use bounded register groups."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess

import compile_actual_rows_961591 as compiler
from preflight_row_data_first_961591 import waits

ROOT=Path('/public/home/zhangkewei/zr')
OUT=ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023/results-961591'
compiler.ART=ROOT/'experiments/EXP-128/artifacts/preflight/grouped-input-961591'
PATTERN=re.compile(r'(const scalar_type cc_row_phase_(\d+) = [^\n]+;\n)'
    r'(R\[\2\] = load_cb\([^\n]+\);\n)(R\[\2\] = \{[^\n]+\};\n)')


def body(text,at):
    a=text.index('{',at); depth=1; i=a+1
    while depth:
        if text[i]=='{': depth+=1
        if text[i]=='}': depth-=1
        i+=1
    return text[a+1:i-1],a,i


def grouped(source,size):
    start=source.index('// load global into registers\n'); end=source.index('// calc the thread_in_device',start)
    region=source[start:end]; classifier=region.index('if(cc_input_row == 0)')
    carrier,a,b=body(region,classifier); ordinary,c,e=body(region,region.index('else',b))
    carrier_re=re.compile(r'(R\[(\d+)\] = \{load_cb\([^\n]+\};\n)')
    loads={int(m[2]):m[1] for m in carrier_re.finditer(carrier)}
    matches=list(PATTERN.finditer(ordinary)); assert matches and len(matches)==len(loads)
    norm=lambda text:re.sub(r'\s+','',text)
    assert norm(carrier_re.sub(lambda m:'@'+m[2],carrier))==norm(PATTERN.sub(lambda m:'@'+m[2],ordinary))
    groups=[]
    for m in matches:
        if groups and len(groups[-1])<size and not ordinary[groups[-1][-1].end():m.start()].strip(): groups[-1].append(m)
        else: groups.append([m])
    changed=ordinary
    for group in reversed(groups):
        old=ordinary[group[0].start():group[-1].end()]
        load=''.join(loads[int(m[2])] for m in group)
        changed=changed[:group[0].start()]+'if(cc_input_row == 0) {\n'+load+'} else {\n'+old+'}\n'+changed[group[-1].end():]
    replacement=region[:classifier]+changed+region[e:]
    # Same array addresses, phase expressions and per-register math; guards are the only added statements.
    assert all(replacement.count(m[3])==1 for m in matches)
    assert all(replacement.count(m[1])==1 for m in matches)
    assert all(replacement.count(value)==1 for value in loads.values())
    return source[:start]+replacement+source[end:],dict(registers=len(matches),group_sizes=[len(g) for g in groups])


def main():
    compiler.ART.mkdir(exist_ok=True)
    actual=json.loads((OUT/'actual-source-isa.json').read_text()); tasks=[]; previous={}; unchanged=[]
    for item in actual['kernels']:
        if item['func']!='d2z_1d' or item['arm']!='candidate' or item['variant']!='original': continue
        name=item['name']; q=int(re.search(r'_len_(\d+)',name)[1]); first=int(re.search(r'_factors_(\d+)',name)[1]); tpt=int(re.search(r'_tpt_(\d+)',name)[1])
        if tpt<=q//first:
            unchanged.append(dict(N=item['N'],Q=q,first_factor=first,tpt=tpt,source_sha256=item['source_sha256']));continue
        if item['N'] not in (173056,262144,1048576,204800): continue
        path=Path(item['assembly']).with_suffix('.hip.cpp')
        src=path.read_text().removeprefix('#include <hip/hip_runtime.h>\n')
        previous[item['N']]=item
        for size in (1,2):
            changed,proof=grouped(src,size)
            tasks.append(dict(N=item['N'],func=item['func'],arm='candidate',variant='group'+str(size),
                name=name,source=changed,source_sha256=hashlib.sha256(changed.encode()).hexdigest(),
                reorder=proof,source_is_actual=True))
    # Q=100 is another partial-lane layout in the full native matrix; include it rather than hard-code two lengths.
    matrix=ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt'
    lines=[line for line in matrix.read_text().splitlines() if line.split()[:3]==['102400','512','100']]
    assert len(lines)==1
    single=compiler.ART/'matrix.txt';single.write_text(lines[0]+'\n')
    native=compiler.ART/'native';native.mkdir(exist_ok=True)
    p=subprocess.run([str(ROOT/'experiments/EXP-128/artifacts/preflight/rowsimplify-20261022/generate'),str(single),str(native)],
        env=compiler.mgr.environment(compiler.ART),capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    src=(native/'512-100-7-0.cpp').read_text()
    name=re.search(r'extern "C" __global__.*? void ([^(]+)\(',src)[1]
    for size in (1,2):
        changed,proof=grouped(src,size)
        tasks.append(dict(N=102400,func='d2z_1d',arm='candidate',variant='group'+str(size),name=name,
            source=changed,source_sha256=hashlib.sha256(changed.encode()).hexdigest(),reorder=proof,source_is_actual=False))
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(compiler.compile_one,tasks))
    assert len(rows)==10 and all(x['complete'] for x in rows),rows
    for item in rows:
        item['prototype_prefix']=waits(Path(item['assembly']))
        if item['N'] in previous:
            old=previous[item['N']]
            item['original_prefix']=waits(Path(old['assembly']))
            item['original_resources']=old['resources']
    report=dict(complete=True,device_execution=False,production_source_modified=False,kernels=rows,
        untouched_full_lane_cases=unchanged,policy='tpt > Q / first_factor; no N or Q equality gate',
        limitation='Group widths 1 and 2 are offline candidates, not validated device improvements. Q100 source is reconstructed, not a runtime source from this diagnostic.')
    (OUT/'grouped-input-preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=True,compiled=len(rows),untouched_full_lane_cases=len(unchanged)),indent=2))


if __name__=='__main__': main()
