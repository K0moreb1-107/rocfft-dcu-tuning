"""Inspect every negative comparison and compile the changed-row diagnostic interventions."""
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr');sys.path[:0]=[str(ROOT),str(ROOT/'experiments/EXP-128/scripts')]
from tools.workspace_manager import manager as mgr
from cc_v5_regression_common import select,restore_row
from isa_cc_957127 import analyze_isa

RECORD=ROOT/'experiments/EXP-128/records/v5-regression-20261027'
ART=ROOT/'experiments/EXP-128/artifacts/preflight/v5-regression-20261027'
V4=ROOT/'experiments/EXP-128/artifacts/preflight/grouped-20261026/default'
V5=ROOT/'experiments/EXP-128/artifacts/preflight/boundary-v5-20261027/default'
DATA=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/results-983952-984725'


def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    RECORD.mkdir(exist_ok=True);ART.mkdir(exist_ok=True)
    rows=json.loads((DATA/'all-samples-and-statistics.json').read_text());selection=select(rows)
    assert selection['original_below_one']==dict(previous=95,unfused_cc=43)
    assert selection['original_below_095']==dict(previous=17,unfused_cc=18)
    write(RECORD/'selection.json',selection)
    facts=[]
    for x in selection['cases']:
        role=5 if x['func']=='z2d_1d' else 7;column=role-1
        item=dict(x)
        item['sources']={}
        for stage,r in [('column',column),('row',role)]:
            a,b=V4/f"{x['C']}-{x['Q']}-{r}-0.cpp",V5/f"{x['C']}-{x['Q']}-{r}-0.cpp"
            old,new=a.read_text(),b.read_text();same=old==new.replace('_cc_local_v5_','_cc_local_v4_')
            item['sources'][stage]=dict(v4=str(a),v5=str(b),v4_sha256=sha(a),v5_sha256=sha(b),equal_except_version_name=same)
            if stage=='column':assert same,'unexpected column modification'
            else:
                assert same!=x['row_changed'],'row-change classification disagrees with actual generated source'
                item['row_load']='registers' if re.search(r'_cc_local_v5_[^\s(]+_reg\(',new) else 'LDS'
                item['row_source_has_pre_scatter']='cc_pre_task' in new
                item['row_source_barriers']=new.count('__syncthreads()')
        facts.append(item)
    severe=[x for x in facts if x['ratios']['previous']<.95]
    assert len(severe)==17 and sum(x['sources']['row']['equal_except_version_name'] for x in severe)==10
    net=[x for x in facts if x['ratios']['unfused_cc']<.95]
    assert len(net)==18 and all(x['Q']%2 and x['row_load']=='LDS' for x in net)
    write(RECORD/'source-facts.json',dict(complete=True,device_execution=False,cases=facts,
        unchanged_columns=len(facts),v4_severe_unchanged_rows=10,net_severe_LDS_rows=18,
        limitation='Native generated sources; actual dispatch/source confirmation and stage/counter measurements follow.'))
    jobs={}
    def compile_job(path,label):
        text=path.read_text();name=re.search(r'extern "C" __global__.*? void ([^(]+)\(',text)[1]
        jobs.setdefault((sha(path),label),dict(path=str(path),label=label,name=name))
    for x in facts:
        if any(x['ratios'][a]<.95 for a in ('previous','unfused_cc')):
            compile_job(Path(x['sources']['row']['v5']),f"{x['N']}-{x['func']}-v5")
    restorations=[]
    for trial in selection['ablations']:
        case=next(x for x in facts if (x['N'],x['func'])==(trial['N'],trial['func']))
        role=5 if trial['func']=='z2d_1d' else 7
        for cb in (0,1):
            old=V4/f"{case['C']}-{case['Q']}-{role}-{cb}.cpp";new=V5/old.name
            restored=restore_row(new.read_text(),old.read_text(),trial['variant'])
            assert restored==old.read_text().replace('_cc_local_v4_','_cc_local_v5_')
            path=ART/(f"{case['N']}-{case['func']}-{trial['variant']}-{cb}.cpp");path.write_text(restored)
            compile_job(path,path.stem);restorations.append(dict(trial,callback=cb,path=str(path),sha256=sha(path)))
        compile_job(V4/f"{case['C']}-{case['Q']}-{role}-0.cpp",f"{case['N']}-{case['func']}-v4")
    def compile_one(x):
        stem=ART/x['label'];path=stem.with_suffix('.hip.cpp');asm=stem.with_suffix('.s')
        path.write_text('#include <hip/hip_runtime.h>\n'+Path(x['path']).read_text())
        cmd=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936','--cuda-device-only','-mcumode','-S',path,'-o',asm]
        p=subprocess.run(list(map(str,cmd)),env=mgr.environment(ART),capture_output=True,text=True,timeout=150)
        stem.with_suffix('.err').write_text(p.stderr)
        result=dict(x,complete=p.returncode==0,command=list(map(str,cmd)))
        if p.returncode:result['error']=p.stderr[-2000:]
        else:result.update(analyze_isa(asm.read_text()))
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:compiled=list(pool.map(compile_one,jobs.values()))
    failed=[x for x in compiled if not x['complete']]
    result=dict(complete=not failed,device_execution=False,kernels=compiled,restorations=restorations,failures=failed,
        limitation='Static ISA/resources are compiler evidence, not executed wait cycles or performance.')
    write(RECORD/'compile-preflight.json',result)
    print(json.dumps(dict(complete=not failed,cases=len(selection['cases']),case_arms=len(selection['clean_schedule']),
        mandatory_profile_arms=len(selection['mandatory_detailed']),row_interventions=len(selection['ablations']),
        compiled=len(compiled),failures=failed,v4_severe_unchanged_rows=10,net_severe_LDS_rows=18),ensure_ascii=False,indent=2))
    mgr.require(not failed,'diagnostic source preflight failed')


if __name__=='__main__':main()
