"""Render one small self-contained sample explorer and the six-column result table."""
import json
from pathlib import Path
import sys


def main():
    folder = Path(sys.argv[1])
    data = json.loads((folder/'all-samples-and-statistics.json').read_text(encoding='utf-8'))
    assert len(data) == 388 and sum(len(v) for r in data for v in r['samples_us'].values()) == 46560
    template = Path(__file__).with_name('cc_row_output_v6_template.html').read_text(encoding='utf-8')
    assert template.count('__ROW_DATA__') == 1
    page = template.replace('__ROW_DATA__', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    (folder/'全部尺寸散点与顺序图.html').write_text(page, encoding='utf-8')
    lines = ['# 第六版完整性能表：任务991869', '',
             'baseline为EXP125保留版，不是官方基线。当前为行端输出第六版；均为本轮同卡默认计划、批量一、10／30样本中位数。', '',
             '| size／类型 | baseline时间，微秒 | A100时间，微秒 | 当前时间，微秒 | 加速比 | performance |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in data:
        a100 = '—' if row['a100_us'] is None else f"{row['a100_us']:.6f}"
        perf = '—' if row['a100_performance_percent'] is None else f"{row['a100_performance_percent']:.2f}%"
        lines.append(f"| {row['N']} {row['type']} | {row['baseline_us']:.6f} | {a100} | {row['candidate_us']:.6f} | {row['speedup_baseline']:.6f} | {perf} |")
    lines += ['', '加速比＝EXP125中位数／第六版中位数；performance＝A100中位数／第六版中位数×100%。',
              'A100是随包参考，仅精确匹配尺寸、方向及10／30记录；无匹配留空。它不替代同卡对照，随包源码与二进制对应关系未获得构建凭据。',
              '第五版、同CC未融合版及逐次散点详见同目录“全部尺寸.csv”和交互图。']
    (folder/'完整六列表格.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(complete=True, cases=len(data), samples=46560,
                          html_bytes=(folder/'全部尺寸散点与顺序图.html').stat().st_size)))


if __name__ == '__main__':
    main()
