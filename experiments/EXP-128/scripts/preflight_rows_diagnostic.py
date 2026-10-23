"""Compile diagnostic row restorations, including callback code, before device submission."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr
from diagnose_rows_v3_regression import replace_row_parts
from isa_cc_957127 import analyze_isa

ART=ROOT/'experiments/EXP-128/artifacts/preflight/rows-v3-regression-20261023'
RECORD=ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023'


def main():
    selection=json.loads((RECORD/'selection.json').read_text())
    cases={(r['N'],r['func']):r for r in selection['cases']}
    folder=ART/'restore-preflight';folder.mkdir(exist_ok=True)
    tasks=[];full_equal=0
    for trial in selection['ablations']:
        case=cases[trial['N'],trial['func']];c,q=case['C'],case['Q']
        role=5 if trial['func']=='z2d_1d' else 7
        for callback in (0,1):
            old=(ART/'previous'/f'{c}-{q}-{role}-{callback}.cpp').read_text()
            current=(ART/'candidate'/f'{c}-{q}-{role}-{callback}.cpp').read_text()
            name=re.search(r'\b(fft_rtc_[A-Za-z0-9_]+)\(',current)[1]
            changed=replace_row_parts(current,old,name,trial['variant'])
            if trial['variant']=='restore_both' or role==5:
                assert changed==old.replace('_cc_local_v2_','_cc_local_v3_'),(trial,callback,'full restore differs')
                full_equal+=1
            stem=folder/('%d-%s-%s-%d'%(case['N'],case['func'],trial['variant'],callback))
            path=stem.with_suffix('.hip.cpp');path.write_text('#include <hip/hip_runtime.h>\n'+changed)
            tasks.append(dict(trial,callback=callback,source=str(path),name=name,stem=str(stem)))
    def compile_one(item):
        path=Path(item['source']);stem=Path(item['stem']);asm=stem.with_suffix('.s')
        command=[mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--offload-arch=gfx936','--cuda-device-only','-mcumode']
        command+=['-fsyntax-only',str(path)] if item['callback'] else ['-S',str(path),'-o',str(asm)]
        result=subprocess.run(command,env=mgr.environment(ART),capture_output=True,text=True,timeout=150)
        stem.with_suffix('.err').write_text(result.stderr)
        value=dict(item,complete=result.returncode==0,command=command)
        if result.returncode: value['error']=result.stderr[-2000:]
        elif not item['callback']: value.update(analyze_isa(asm.read_text()))
        return value
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(compile_one,tasks))
    failures=[r for r in results if not r['complete']]
    report=dict(complete=not failures,device_execution=False,compiled=len(results),
        full_restoration_equals_v2_except_version_name=full_equal,variants=results,failures=failures)
    (RECORD/'restoration-preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=report['complete'],compiled=len(results),full_restores=full_equal,failures=failures,
        Q512=[{k:r[k] for k in ('N','variant','resources','static_instruction_groups')}
              for r in results if r['N']==262144 and not r['callback'] and r['complete']]),ensure_ascii=False,indent=2))
    mgr.require(report['complete'],'diagnostic restoration compile failed')


if __name__=='__main__': main()
