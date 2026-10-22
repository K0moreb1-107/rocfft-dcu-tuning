"""Save the accepted row-simplified code and its complete regression list as a version."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('/public/home/zhangkewei/zr')
RECORD=ROOT/'experiments/EXP-128/records/rowsimplify-retry1-20261022'
TAG='exp128-cc-row-simplify-v3-20261023'


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def main():
    assert git('branch','--show-current')=='exp-128-cc-local-real'
    assert not git('tag','--list',TAG),'version tag already exists; inspect it before changing anything'
    assert not (RECORD/'版本记录.json').exists(),'version already prepared; inspect it before repeating'
    audit=json.loads((RECORD/'results-960099/audit-and-statistics.json').read_text())
    rows=json.loads((RECORD/'results-960099/all-samples-and-statistics.json').read_text())
    selected=[r for r in rows if r['speedup_previous']<.95]
    assert audit['complete'] and len(selected)==24
    table=RECORD/'相对上一版低于095清单.md'
    version=dict(version=TAG,branch='exp-128-cc-local-real',parent_commit=git('rev-parse','HEAD'),
        description='EXP128 通用CC行端简化v3，保留当前代码及全部已知性能退化。',
        build_job='960028',validation_job='960098',performance_job='960099',
        arms=audit['arms'],implementation_commit='16a469e4d2a1c3bf98a702a286a27673bdc03dd8',
        validation='26 sizes; 52 numerical and 52 actual-dispatch checks passed',
        performance=dict(N=194,cases=388,processes=1164,samples=34920,median_only=True),
        regression_filter='previous median / candidate median < 0.95',regression_count=24,
        regression_counts={f:sum(r['type']==f for r in selected) for f in ('z2d','d2z')},
        regression_list=str(table),regression_list_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
        analysis=str(RECORD/'results-960099'),source_rebuilt=False,stable_promoted=False,pushed=False)
    manifest=RECORD/'版本记录.json'
    manifest.write_text(json.dumps(version,ensure_ascii=False,indent=2)+'\n')
    files=[str(p.relative_to(ROOT)) for p in (manifest,table,Path(__file__))]
    subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Save EXP128 row-simplified v3 version and complete sub-0.95 regressions',
                    '--',*files],cwd=ROOT,check=True)
    commit=git('rev-parse','HEAD')
    subprocess.run(['git','tag','-a',TAG,commit,'-m',
        'EXP128通用CC行端简化v3；验证960098与性能960099通过，保留24项相对v2低于0.95的记录。'],cwd=ROOT,check=True)
    assert git('rev-parse',TAG+'^{commit}')==commit
    print(json.dumps(dict(complete=True,commit=commit,tag=TAG,branch='exp-128-cc-local-real',
        regressions=len(selected),record=str(manifest),stable_promoted=False,pushed=False),ensure_ascii=False))


if __name__=='__main__':
    main()
