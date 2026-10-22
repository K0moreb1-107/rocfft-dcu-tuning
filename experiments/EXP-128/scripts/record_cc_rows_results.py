"""Commit verified row-simplification results while retaining the experimental status."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('/public/home/zhangkewei/zr')
OUT=ROOT/'experiments/EXP-128/records/rowsimplify-retry1-20261022/results-960099'


def main():
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='exp-128-cc-local-real'
    index=json.loads((OUT/'证据索引.json').read_text())
    audit=json.loads((OUT/'audit-and-statistics.json').read_text())
    assert index['complete'] and audit['complete'] and audit['processes']==1164 and audit['samples']==34920
    for rel,identity in index['files'].items():
        path=(OUT/rel).resolve()
        assert path.is_relative_to(OUT)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==identity['sha256'],rel
    outcome=dict(complete=True,validation_job='960098',performance_job='960099',
        candidate_build_job='960028',analysis_record=str(OUT),
        numerical_and_dispatch_accepted=True,performance_data_accepted=True,
        decision='Retain candidate. Generic row improvements coexist with a d2z Q=512 class regression; no stable promotion.',
        source_scope='Generic row classification and folded-index simplification only.',
        aggregate=audit['all'],same_run_severe_transition=audit['same_run_severe_transition'],
        stable_promoted=False,pushed=False,AGENTS_modified=False,new_jobs_submitted=False)
    accepted=OUT.parent/'验收结果.json'
    accepted.write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+'\n')
    files=[p for p in OUT.rglob('*') if p.is_file()]
    files += [accepted,Path(__file__),ROOT/'experiments/EXP-128/scripts/analyze_cc_rows_results.py']
    relative=[str(p.relative_to(ROOT)) for p in files]
    subprocess.run(['git','add','--',*relative],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record verified EXP128 row simplification results and Q512 regressions',
                    '--',*relative],cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    print(json.dumps(dict(complete=True,record=str(OUT),commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=len(files),stable_promoted=False,pushed=False)))


if __name__=='__main__':
    main()
