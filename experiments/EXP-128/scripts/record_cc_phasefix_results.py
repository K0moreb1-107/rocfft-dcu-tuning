"""Commit accepted analysis records without promoting the candidate or touching other changes."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
OUT = ROOT/'experiments/EXP-128/records/phasefix-20261022/results-955252'


def main():
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip() == 'exp-128-cc-local-real'
    audit = json.loads((OUT/'audit-and-statistics.json').read_text())
    index = json.loads((OUT/'证据索引.json').read_text())
    assert audit['complete'] and audit['processes'] == 1164 and audit['samples'] == 34920
    assert index['complete'] and index['portable_checks']['viewer_javascript_syntax']
    for rel, identity in index['files'].items():
        path = (OUT/rel).resolve()
        assert path.is_relative_to(OUT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == identity['sha256'], rel
    directions = ROOT/'VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md'
    marker = 'EXP128 通用CC改进验收：955250／955251／955252'
    text = directions.read_text()
    if marker not in text:
        text += '''

### EXP128 通用CC改进验收：955250／955251／955252

2026-10-22，分支exp-128-cc-local-real；实现修正1e7491bdf423，实际候选构建源码21ad4f809a3b、库ae4a6437b266。列分支合并／相位递推及d2z行直接加载按通用能力接入，N≥65536，二次幂不优先旧后端。65536点相位查表段数越界已修正；原失败955132及日志保留。

12个代表尺寸的24项数值／实际融合路径验证通过，耗时约115秒。三版同卡相邻交替、默认路径、10／30，194个N、388个组合、1164个独立进程及34920个样本全部复核通过，最大误差5.033011e-15。

只用中位数；逐项加速比的中位数：z2d对EXP125为1.196948、对上一版EXP128为1.039778；d2z分别为1.202686、1.000008。列长289的8项z2d对上一版均改善，范围1.4563～2.1179；d2z整体近持平。65536点d2z慢12.88%，208×343及其他残余退化保留。分布重叠／顺序效应单独标注，不据一组数据承诺跨次稳定性。

EXP125是固定保留对照，不是官方；上一版为590ab6a8fc01。完整运行在experiments/EXP-128/runs/EXP-128-cc-local-phasefix-performance-20261022/；验收、六列表格、全量散点、逐次样本、类型统计及证据索引在experiments/EXP-128/records/phasefix-20261022/results-955252/。结论：保留当前候选和全部证据；不晋升稳定版，不因性能退化自动添加特例或继续优化。
'''
        directions.write_text(text)
    files = [path for path in OUT.rglob('*') if path.is_file()]
    files += [directions, ROOT/'experiments/EXP-128/scripts/analyze_cc_phasefix_results.py',
              ROOT/'experiments/EXP-128/scripts/record_cc_phasefix_results.py']
    relative = [str(path.relative_to(ROOT)) for path in files]
    subprocess.run(['git','add','--',*relative],cwd=ROOT,check=True)
    subprocess.run(['git','commit','--only','-m','Record verified EXP128 generic CC median performance and retained regressions',
                    '--',*relative],cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    print(json.dumps(dict(complete=True,commit=commit,files=len(files),record=str(OUT),
                         stable_promoted=False,pushed=False,AGENTS_modified=False)))


if __name__ == '__main__':
    main()
