"""Write the v6 Chinese result report from audited per-process medians."""
import csv
import json
from pathlib import Path
import sys


def main():
    folder = Path(sys.argv[1])
    audit = json.loads((folder/'audit-and-statistics.json').read_text(encoding='utf-8'))
    rows = json.loads((folder/'all-samples-and-statistics.json').read_text(encoding='utf-8'))
    groups = list(csv.DictReader((folder/'类型汇总.csv').open(encoding='utf-8-sig')))
    assert audit['complete'] and len(rows) == 388
    lines = ['# 行端输出第六版：任务991869结果', '',
        '结论：输出简化在部分类型上改善耗时，但没有产生明显的普遍加速。z2d行长289、1331及单行d2z偏向改善；625行长z2d基本持平。相对同CC未融合版的明显退化数量减少，仍未消除。', '',
        '本次只分析已完成结果，没有修改生产代码、追加性能任务或升级稳定版本。', '',
        '## 数据与验收', '',
        '构建991867成功，耗时4分59秒；验证991868成功，耗时3分59秒；性能991869成功，耗时1小时6分44秒。性能在2026年10月28日20:11至21:16（台北时间）运行。', '',
        f"独占节点a03r1n04、单张gfx936；194个N、388个方向组合、四版1552个独立进程，全部46560个正式样本保留。每进程10次预热、30次计时，默认路径、批量一；完整变换逐次同步。全部进程退出正常、独立数值检查通过，最大误差{audit['max_numerical_error']:.6g}。另有56项数值和56项实际融合／输出路径验证全部通过。", '',
        '逐个校验了原始计时、正确性、输出、退出码、库身份、单卡身份、提交清单顺序和文件校验值；重新计算的统计与运行目录汇总一致。没有合并不同批次数据、删除慢点或用平均值分析加速比。', '',
        '| 版本 | 含义 | 库校验值 |', '| --- | --- | --- |']
    labels = dict(baseline='EXP125保留版', previous='通用融合第五版',
                  unfused_cc='修复后的同CC未融合版', candidate='行端输出第六版')
    for arm, name in labels.items():
        lines.append(f"| {name} | {'本轮只修改行端输出' if arm=='candidate' else '复用已验证安装'} | `{audit['references'][arm]['library_sha256']}` |")
    lines += ['', '第五版与第六版默认CC分解相同，输入处理、列端和打包输出保持原方案。EXP125不是官方基线；与其比较包含既有计划和融合布局变化。', '',
        '## 相对第五版：本轮新增改动的效果', '',
        '表中“类型中位加速比”先按每个尺寸计算“第五版30次样本中位数／第六版30次样本中位数”，再对该类型的尺寸比值取中位数。它不是合并样本后的流水加速比，也没有按N加权。', '',
        '| 方向／输出类型 | 项数 | 类型中位加速比 | 中位数更快 | 低于0.95 | 区间与漂移筛查后更快／更慢／不明确 |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    for x in audit['output_groups']:
        if x['reference'] != 'previous':
            continue
        lines.append(f"| {x['type']}／{x['value']} | {x['cases']} | {x['median_case_speedup']:.6f} | {x['faster']} | {x['below_095']} | {x['clear_faster']}／{x['clear_slower']}／{x['unclear']} |")
    lines += ['', '单行直接输出覆盖63个N。z2d修改134项、d2z修改63项，共197项；其余191项属于未改输出的对照。', '',
        '| 行长Q／方向 | 项数 | 相对第五版的类型中位加速比 | 中位数更快 | 差异不明确 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for q in (121, 289, 343, 625, 1331):
        for func in ('z2d', 'd2z'):
            if func == 'd2z' and q not in (625, 1331):
                continue
            x = next(x for x in groups if x['dimension'] == '行长' and int(x['value']) == q
                     and x['type'] == func and x['reference'] == 'previous')
            lines.append(f"| {q}／{func} | {x['cases']} | {float(x['median_case_speedup']):.6f} | {x['faster']} | {x['unclear']} |")
    lines += ['', '289行长z2d有12／15项中位数更低，1331行长有30／33项更低；但按既定分布筛查，分别12项、29项仍标为差异不明确。121行长的三个尺寸全部有漂移标记，不能据其较高比值认定稳定收益。625行长z2d的类型中位比值恰为1。', '',
        '整个194项的类型中位比值为：z2d对第五版1.003712，d2z为1.002075；未改输出类型的中位比值均为1。这轮收益集中在特定结构，不能用整体数值宣称所有类型得到优化。', '',
        '## 相对第五版低于0.95的全部11项', '',
        '| N／方向 | C×Q | 第五版，微秒 | 第六版，微秒 | 加速比 | 本轮修改输出 | 分布判断 |',
        '| --- | --- | ---: | ---: | ---: | --- | --- |']
    severe = sorted(audit['severe_previous'], key=lambda x: x['speedup_previous'])
    for x in severe:
        lines.append(f"| {x['N']} {x['type']} | {x['C']}×{x['Q']} | {x['previous_us']:.6f} | {x['candidate_us']:.6f} | {x['speedup_previous']:.6f} | {'是' if x['output_changed'] else '否'} | {x['assessment_previous']} |")
    lines += ['', '其中10项属于未改输出的类型。只有428750点d2z命中单行直接输出，其样本中间50%区间重叠，并有进程内漂移，当前不能确定为代码造成的稳定退化。最低比值82134点d2z同样未改输出，且区间重叠、存在漂移；不将0.8235直接归因为本轮实现。', '',
        '108864点z2d的两版中间50%区间不重叠且未标漂移，确有本轮耗时偏慢的观察；生成检查证明其输出类型未改，尚无受控设备干预确认原因。不能用“未改代码”否定观测，也不能反向编造降频、缓存等解释。', '',
        '另有两项改动路径虽然比值高于0.95，分布筛查仍为更慢：67600点z2d为0.959276，120000点z2d为0.979381。完整数据保留，不按0.95阈值忽略它们。', '',
        '## 相对同CC未融合版：融合整体净收益', '',
        '| 方向 | 第五版低于0.95 | 第六版低于0.95 | 第六版类型中位加速比 | 第六版中位数更快 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for func in ('z2d', 'd2z'):
        transition = audit['same_CC_severe_transition'][func]
        x = audit['all'][func]['unfused_cc']
        lines.append(f"| {func} | {transition['v5_below_095']} | {transition['v6_below_095']} | {x['median_case_speedup']:.6f} | {x['faster']}／{x['cases']} |")
    lines += ['', '这些第五版和第六版比值都来自本任务的同一张显卡，与同一份未融合对照比较，没有拿旧节点的绝对时间拼接。没有新增低于0.95的项目。阈值数量只是描述结果，不是显著性判断。', '',
        '| z2d的N | 同CC未融合，微秒 | 第六版，微秒 | 加速比 | 分布判断 |',
        '| --- | ---: | ---: | ---: | --- |']
    for x in sorted([x for x in rows if x['speedup_unfused_cc'] < .95], key=lambda x: x['speedup_unfused_cc']):
        lines.append(f"| {x['N']} | {x['unfused_cc_us']:.6f} | {x['candidate_us']:.6f} | {x['speedup_unfused_cc']:.6f} | {x['assessment_unfused_cc']} |")
    lines += ['', '其余仍低于1的项目也在完整表中保留。低于0.95并且未被重叠／漂移标记的三项为681472、320000、2725888点z2d。未达到这一筛查条件不代表没有问题，表示本轮分布不足以确定差异。', '',
        '此前985072中反复退化的七项，本轮全部比第五版的中位耗时更低：', '',
        '| N／z2d | 第五版，微秒 | 第六版，微秒 | 第六版对第五版 | 第五版对同CC未融合 | 第六版对同CC未融合 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for x in audit['known_stable_unfused_losses']:
        lines.append(f"| {x['N']} | {x['previous_us']:.6f} | {x['candidate_us']:.6f} | {x['speedup_previous']:.6f} | {x['previous_speedup_unfused_cc']:.6f} | {x['speedup_unfused_cc']:.6f} |")
    lines += ['', '例如2725888点由238.400005降至223.920003微秒，对第五版1.064666倍；相对同CC未融合由0.889597改善至0.947124，仍有净退化。该项本轮相对第五版区间分离且未标漂移，支持本次输出削减带来局部收益；仍不能据此拆出每条共享指令或屏障节省的微秒。', '',
        '## 二次幂及EXP125对照', '',
        '本轮六个二次幂尺寸全部属于未改输出类型；相对第五版基本持平。第六版没有接管它们，也没有通过这次单行优化修复它们相对EXP125的既有差距。', '',
        '| N／方向 | 第六版对第五版 | 第六版对EXP125 | 第六版对同CC未融合 |',
        '| --- | ---: | ---: | ---: |']
    for x in audit['power_of_two']:
        lines.append(f"| {x['N']} {x['type']} | {x['speedup_previous']:.6f} | {x['speedup_baseline']:.6f} | {x['speedup_unfused_cc']:.6f} |")
    lines += ['', '全部194个尺寸的类型中位加速比对EXP125为：z2d 1.257902、d2z 1.308124。这包含前面各版的CC计划与融合改动，不能当作本轮行端输出的新增收益。', '',
        '## 数据限制与当前决定', '',
        '按既定规则，任一版本前15次与后15次的中间50%区间不重叠，或两版总体中间50%区间重叠，就标为“差异不明确”。相对第五版，z2d有177／194项、d2z有182／194项被标记；这是本次样本的直接限制，不把一组30次计时解释成跨次稳定性。', '',
        '输出工作量削减的静态结论成立；端到端收益明显小于静态指令降幅。当前数据支持保留候选、继续按类型定位剩余成本，不支持宣布全面解决融合退化，也不支持对所有输入索引或列端进行推测性修改。', '',
        '本轮没有阶段时间或新的性能计数，不能把剩余差额确定分配给配对算术、同步、寄存器、全局存储或其他环节；需要进一步诊断时应做单项干预并同时覆盖该类型的多个N。', '',
        '## 文件索引', '',
        '- `全部尺寸散点与顺序图.html`：388组合四版全部样本，可筛选本轮改动／未改路径、行长、列长、二次幂及低于0.95项目。',
        '- `完整六列表格.md`：size／类型、EXP125、A100、当前、加速比、performance。A100精确匹配22个方向组合，其余留空。',
        '- `全部尺寸.csv`、`类型汇总.csv`：全部中位数、区间、加速比与分布判断。',
        '- `低于095-previous.csv`、`低于095-unfused_cc.csv`、`低于095-baseline.csv`：三种对照的完整低值清单。',
        '- `原始逐次样本.csv`、`独立正确性表.csv`：全部46560个样本和1552项进程数值检查。',
        '- `audit-and-statistics.json`、`all-samples-and-statistics.json`：验收、来源校验值、类型统计及绘图数据。', '',
        '服务器原始运行：`/public/home/zhangkewei/zr/experiments/EXP-128/runs/EXP-128-cc-local-row-output-v6-performance-20261028/`。',
        '服务器结果记录：`/public/home/zhangkewei/zr/experiments/EXP-128/records/row-output-v6-20261028/results-991869/`。']
    (folder/'结果分析.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(complete=True, report_bytes=(folder/'结果分析.md').stat().st_size)))


if __name__ == '__main__':
    main()
