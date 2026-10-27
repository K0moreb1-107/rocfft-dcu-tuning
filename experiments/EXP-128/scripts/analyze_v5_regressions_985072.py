"""Evidence-bounded analysis of completed v5/v4 and same-CC fusion diagnostics."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path('/public/home/zhangkewei/zr')
RECORD=ROOT/'experiments/EXP-128/records/v5-regression-20261027'
RUN=ROOT/'experiments/EXP-128/runs/EXP-128-cc-v5-regression-diagnostic-20261027'
OUT=RECORD/'results-985072'
LABEL={'previous':'第四版','unfused_cc':'同分解未融合版','candidate':'第五版'}


def load(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def ratio(a,b):return a['statistics_ms']['median_ms']/b['statistics_ms']['median_ms']
def med(entry):return entry['statistics_ms']['median_ms']*1000
def fmt(value,d=3):return '—' if value is None else f'{value:.{d}f}'


def main():
    result=load(RUN/'diagnostic-result.json');accept=load(OUT/'evidence-acceptance.json')
    assert result['complete'] and not result['failures'] and not result['timestamp_warnings']
    assert accept['original_result_sha256']==hashlib.sha256((RUN/'diagnostic-result.json').read_bytes()).hexdigest()
    selected=load(RECORD/'selection.json');facts=load(RECORD/'source-facts.json')
    source={(x['N'],x['func']):x for x in facts['cases']}
    actual={(x['N'],x['func']):x for x in result['source_comparisons']}
    times={(x['N'],x['func'],x['arm'],x['phase']):x for x in result['timing']+result['anchors']}
    traces={(x['N'],x['func'],x['arm']):x for x in result['traces']}
    pmc={(x['N'],x['func'],x['arm'],x['mode'],x['variant']):x for x in load(OUT/'pmc-summary.json')['entries']}
    def counter(n,f,arm,mode,position,field,variant='original'):
        item=pmc.get((n,f,arm,mode,variant))
        return item['stages'][position]['fields'][field]['median'] if item else None
    def traffic(n,f,ref,mode):
        key='size of L2 cache '+mode
        left=pmc.get((n,f,ref,mode,'original'));right=pmc.get((n,f,'candidate',mode,'original'))
        if not left or not right:return None
        a,b=(x['summed_fields'][key]['median'] for x in (left,right))
        return dict(reference=a,candidate=b,reduction_percent=100*(1-b/a),unit=left['summed_fields'][key]['unit'])
    trials={}
    for index,trial in enumerate(selected['ablations']):
        entries=[x for x in result['interventions'] if x['index']==index]
        assert len(entries)==6 and all(x['valid'] for x in entries)
        trials[trial['N'],trial['func']]=dict(trial,processes=[dict(arm=x['arm'],variant=x.get('variant','plain'),
            median_us=med(x),p25_us=x['statistics_ms']['p25_ms']*1000,p75_us=x['statistics_ms']['p75_ms']*1000,
            samples_us=[v*1000 for v in x['samples_ms']],phase=x['phase'],source_audit=x.get('source_audit')) for x in entries])
    comparisons=[];plots=[]
    for case in selected['cases']:
        n,f=case['N'],case['func']
        for ref in case['references']:
            rounds=[]
            for phase in ('repeat-1','repeat-2','end-anchor'):
                a=times.get((n,f,ref,phase));b=times.get((n,f,'candidate',phase))
                if not a or not b:continue
                rounds.append(dict(phase=phase,speedup=ratio(a,b),reference_median_us=med(a),candidate_median_us=med(b),
                    reference_iqr_us=[a['statistics_ms'][k]*1000 for k in ('p25_ms','p75_ms')],
                    candidate_iqr_us=[b['statistics_ms'][k]*1000 for k in ('p25_ms','p75_ms')],
                    reference_drift_percent=100*(statistics.median(a['samples_ms'][15:])/statistics.median(a['samples_ms'][:15])-1),
                    candidate_drift_percent=100*(statistics.median(b['samples_ms'][15:])/statistics.median(b['samples_ms'][:15])-1)))
            assert len(rounds)>=2
            plot=dict(N=n,type=f.removesuffix('_1d'),C=case['C'],Q=case['Q'],reference=ref,
                original_speedup=case['ratios'][ref],rounds=[])
            for item in rounds:
                phase=item['phase'];a,b=(times[n,f,arm,phase] for arm in (ref,'candidate'))
                plot['rounds'].append(dict(item,reference_samples=[v*1000 for v in a['samples_ms']],candidate_samples=[v*1000 for v in b['samples_ms']]))
            plots.append(plot)
            if case['ratios'][ref]>=1:continue
            entry=dict(N=n,type=f.removesuffix('_1d'),func=f,C=case['C'],Q=case['Q'],reference=ref,
                original_speedup=case['ratios'][ref],original_assessment=case['assessments'][ref],rounds=rounds,
                row_changed=case['row_changed'],row_load=source[n,f]['row_load'],
                actual_source_comparison=actual.get((n,f)),source_facts=source[n,f]['sources'],
                intervention=trials.get((n,f)),L2_read=traffic(n,f,ref,'read'),L2_write=traffic(n,f,ref,'write'))
            a=traces.get((n,f,ref));b=traces.get((n,f,'candidate'))
            if a and b:
                old=[k['stats_us']['median'] for k in a['trace']['kernels']];new=[k['stats_us']['median'] for k in b['trace']['kernels']]
                assert len(new)==2 and len(old)==(3 if ref=='unfused_cc' else 2)
                entry['stage_trace']=dict(reference=old,candidate=new,
                    reference_window_sum_us=a['trace']['window_kernel_sum_us']['median'],
                    candidate_window_sum_us=b['trace']['window_kernel_sum_us']['median'],
                    reference_window_gap_us=a['trace']['window_gap_us']['median'],candidate_window_gap_us=b['trace']['window_gap_us']['median'],
                    reference_names=a['trace']['kernel_names'],candidate_names=b['trace']['kernel_names'])
                old_row=2 if ref=='unfused_cc' else 1
                entry['row_counters']={key:dict(reference=counter(n,f,ref,'general',old_row,key),
                    candidate=counter(n,f,'candidate','general',1,key)) for key in ('vgpr count','shared memory size',
                    'scratch size','shared memory operation','shared memory bank conflict','L1 cache unit is stalled')}
            persistent=all(x['speedup']<.98 for x in rounds[:2])
            if ref=='previous':
                if not entry['row_changed']:
                    entry['finding']='行列生成源码均相同；实际来源核对与资源证据见记录。时间差不能归因于本轮行端改动；执行差异尚未定位。' if persistent else '原退化幅度未稳定复现；行列生成源码相同，不将其归因于本轮改动。'
                    if n==161840:entry['finding']+='该项实际源代码、离线指令序列及设备资源均一致；跟踪行阶段反而更快，证据不支持确定的软件根因。'
                elif n==1048576:
                    entry['finding']='两轮约5%偏慢复现，阶段差额集中在行端；设备共享操作计数下降20%、银行冲突下降、容量与寄存器相同，一级缓存停顿占比上升。尚缺本项旧输出恢复对照，不能仅据停顿占比确定原因。'
                elif entry['intervention']:
                    entry['finding']='原明显退化未在三轮稳定复现；整段旧代码恢复及恒等替换已完成，结果另表列出。现有恢复数据不能解释为本轮改动造成原5%至10%退化。'
                else:entry['finding']='两轮未持续低于0.98；只有轻微或变号时间差，尚无可确认的代码退化原因。'
            elif persistent and 'stage_trace' in entry:
                entry['finding']='持续净退化；阶段跟踪将主要新增成本定位在融合行端。配对计算、索引与实数写出适配及共享存储操作增加；各部分耗时尚未单独拆分，不能归因于容量增加或仅凭停顿百分比定因。'
            else:
                entry['finding']='原净退化幅度未稳定复现；该行端仍有融合适配开销，但省去的独立前处理及列端差额可抵消它。按各轮及阶段数据判断，不将历史比值直接当作确定退化。'
            comparisons.append(entry)
    assert len(comparisons)==138
    summary={}
    for ref in ('previous','unfused_cc'):
        group=[x for x in comparisons if x['reference']==ref];severe=[x for x in group if x['original_speedup']<.95]
        summary[ref]=dict(original_negative=len(group),original_below095=len(severe),
            below_one_both_rounds=sum(all(y['speedup']<1 for y in x['rounds'][:2]) for x in group),
            below098_both_rounds=sum(all(y['speedup']<.98 for y in x['rounds'][:2]) for x in group),
            severe_below095_all_three=sum(len(x['rounds'])==3 and all(y['speedup']<.95 for y in x['rounds']) for x in severe),
            severe_below098_all_three=sum(len(x['rounds'])==3 and all(y['speedup']<.98 for y in x['rounds']) for x in severe))
    write(OUT/'comparison-analysis.json',dict(complete=True,job_id='985072',formal=False,summary=summary,comparisons=comparisons,
        interpretation='Below-one counts are directional observations, not significance or software-causality claims. Rounds and instrumentation remain separate.'))
    for ref in ('previous','unfused_cc'):
        rows=[]
        for x in comparisons:
            if x['reference']!=ref:continue
            ratios={r['phase']:r['speedup'] for r in x['rounds']};stage=x.get('stage_trace');metrics=x.get('row_counters')
            rows.append({'N':x['N'],'类型':x['type'],'列长':x['C'],'行长':x['Q'],'原比值':x['original_speedup'],
                '复测一':ratios['repeat-1'],'复测二':ratios['repeat-2'],'末尾复测':ratios.get('end-anchor',''),
                '行端源码改变':x['row_changed'],'行端加载':x['row_load'],
                '对照行阶段微秒':stage['reference'][-1] if stage else '', '第五版行阶段微秒':stage['candidate'][-1] if stage else '',
                '对照行共享操作计数':metrics['shared memory operation']['reference'] if metrics else '',
                '第五版行共享操作计数':metrics['shared memory operation']['candidate'] if metrics else '',
                '二级缓存读取减少百分比':x['L2_read']['reduction_percent'] if x['L2_read'] else '',
                '二级缓存写入减少百分比':x['L2_write']['reduction_percent'] if x['L2_write'] else '', '证据结论':x['finding']})
        with (OUT/('相对'+LABEL[ref]+'逐项分析.csv')).open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write(OUT/'plot-data.json',plots)
    lines=['# 第五版退化诊断985072：结果与原因分析','',
        '结论：相对第四版，原17项低于0.95的明显退化，没有一项在本轮三次检查中始终低于0.95，不能据此认定第五版改动造成这些幅度的退化。相对同分解未融合版，奇数行长z2d存在可重复的净退化，主要新增耗时定位在融合行端；额外配对、索引、分支、实数写出与共享访问操作已有源码、编译和设备证据。各部分各占多少微秒尚未分离。','',
        '另有1048576点z2d的约5%偏慢在两遍复测中复现，属于第四版对照中的独立待定问题。其共享存储操作减少，不能套用奇数行长的解释。','',
        '## 验收和口径','',
        f"任务在{result['host']}的一张独占gfx936显卡完成，2026年10月27日18:54开始、20:14结束（新加坡时间），调度退出0。完成574个两遍计时进程、117组独立元数据及阶段跟踪、362个性能计数进程、66个恢复对照计时、65个末尾计时。共1301次独立数值检查，最大误差{accept['maximum_error']:.3g}，没有失败或时间戳异常。",'',
        '每个进程十次预热、三十次正式样本，全部保留，按中位数比较。两遍前后反转顺序。原正式数据保持原样；本报告只比较本任务同卡数据，不跨历史节点比较绝对时间。阶段时间来自分析器，不能替换无分析器的总时间；每段中位数之和也不等于整条流水中位数。', '',
        '“二级缓存读取／写入量”保留设备工具原单位，不等于显存读写量。“共享存储操作”是工具操作计数，不能直接换算字节。“一级缓存停顿”是占比，不是等待周期。静态指令数不等于实际执行次数。','',
        '## 两组复测概况','', '| 对照 | 原比值小于1 | 两遍仍小于1 | 两遍均低于0.98 | 原低于0.95的项目中，三轮均低于0.95 |','| --- | ---: | ---: | ---: | ---: |']
    for ref,counts in summary.items():lines.append(f"| {LABEL[ref]} | {counts['original_negative']} | {counts['below_one_both_rounds']} | {counts['below098_both_rounds']} | {counts['severe_below095_all_three']} |")
    lines += ['', '以上计数只描述复测方向和幅度，不作为统计显著性或软件根因判据。完整95项、43项分别见两份逐项分析表。', '',
        '## 相对第四版：逐项核对原17项明显退化','',
        '其中10项z2d的实际行列源码忽略版本名后均与第四版相同。161840点还核对了实际源代码的离线机器指令：两阶段指令序列、寄存器、共享存储容量和设备操作计数一致，三轮总时间比值仍有变化，阶段跟踪却更快；当前不能将其归因为第五版的代码变化，也没有频率记录可据以宣称降频。','',
        '| N／类型 | 行端源码改变 | 原比值 | 复测一 | 复测二 | 末尾 | 阶段行耗时：第四版→第五版，微秒 |','| --- | --- | ---: | ---: | ---: | ---: | --- |']
    for x in comparisons:
        if x['reference']!='previous' or x['original_speedup']>=.95:continue
        rr=x['rounds'];stage=x['stage_trace'];lines.append(f"| {x['N']} {x['type']} | {'是' if x['row_changed'] else '否'} | {x['original_speedup']:.3f} | {rr[0]['speedup']:.3f} | {rr[1]['speedup']:.3f} | {rr[2]['speedup']:.3f} | {stage['reference'][-1]:.2f}→{stage['candidate'][-1]:.2f} |")
    lines += ['', '### 旧代码恢复证据','',
        '每项保留相邻第五版原样计时及两次恒等替换，恢复时只更换整个旧输入或旧输出区域，库、计划、函数参数和原寄存器映射保持一致；数值和实际源码替换全部通过。以下列每进程中位数，不合并不同时间进程。', '',
        '| N／类型 | 第四版原样 | 第五版原样两次 | 恒等替换两次 | 恢复旧行端 |','| --- | ---: | --- | --- | ---: |']
    for trial in trials.values():
        entries=trial['processes'];old=[x['median_us'] for x in entries if x['arm']=='previous'][0]
        plain=[x['median_us'] for x in entries if x['arm']=='candidate' and x['variant']=='plain']
        identity=[x['median_us'] for x in entries if x['variant']=='identity']
        restored=[x['median_us'] for x in entries if x['variant'].startswith('restore')][0]
        lines.append(f"| {trial['N']} {trial['func'].removesuffix('_1d')} | {old:.2f} | {'／'.join(f'{v:.2f}' for v in plain)} | {'／'.join(f'{v:.2f}' for v in identity)} | {restored:.2f} |")
    lines += ['', '恢复结果没有稳定重现原5%至10%的第四版优势。例如497664点，第四版原样43.20微秒，恢复旧输出仍为46.08微秒；恒等替换为44.00和45.92微秒，不能用这组数据认定新输出逻辑是原退化原因。447216点d2z的恒等替换自身从48.00变至45.44微秒，同样不足以把恢复前后的全部差异归给输入代码。原样进程和恒等控制的变化也完整保留。','',
        '### 1048576点z2d仍需单独处理','',
        '该项两遍比值为0.945和0.955；阶段跟踪的列端32.16→31.36微秒，行端32.56→36.40微秒。行端设备向量寄存器均68，共享存储均32768字节，操作计数81920→65536（减少20%），银行冲突6.44%→4.91%，一级缓存停顿21.12%→29.32%；二级缓存读写量没有上升。离线静态指令845→668、共享读取指令34→20，且无溢出。这排除了“新增共享操作、银行冲突或流量上升”作为现有解释；为何停顿占比上升，尚无独立恢复对照确认，不能当作已定因。','',
        '## 相对同分解未融合版：逐项核对原18项明显退化','',
        '18项都是奇数行长z2d。下面列出相同分解的独立前处理、列端和行端成本。行端始终是SBRC内部前处理融合，没有改回SBCC前端融合。', '',
        '| N | C×Q | 原比值 | 复测一 | 复测二 | 末尾 | 独立前处理省去，微秒 | 列端：未融合→第五版 | 行端：未融合→第五版 |','| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |']
    for x in comparisons:
        if x['reference']!='unfused_cc' or x['original_speedup']>=.95:continue
        rr=x['rounds'];stage=x['stage_trace'];a,b=stage['reference'],stage['candidate']
        lines.append(f"| {x['N']} | {x['C']}×{x['Q']} | {x['original_speedup']:.3f} | {rr[0]['speedup']:.3f} | {rr[1]['speedup']:.3f} | {rr[2]['speedup']:.3f} | {a[0]:.2f} | {a[1]:.2f}→{b[0]:.2f} | {a[2]:.2f}→{b[1]:.2f} |")
    lines += ['', '97104、425920、255552、646866、681472、1362944、2725888这7项，在三轮中始终低于0.95。原18项中另有4项三轮始终低于0.98，但并非每轮都低于0.95。原表未达严重阈值而本次持续复现的120224、215622、223608、287496、298144、596288、745360点，也已经自动补齐阶段和性能计数，完整证据见逐项表。','',
        '### 已定位的成本与排除项','',
        '2725888点：省去独立前处理48.00微秒，但列端70.24→89.44微秒，行端85.12→141.84微秒。单是行端增加的56.72微秒就超过省去的前处理；列端还增加19.20微秒。阶段窗口总核耗时中位数203.36→230.80微秒，与无分析器复测中持续偏慢同向。','',
        '该项整条流水二级缓存读取74943.59→42965.62千字节（减少42.67%），写入67728.50→47749.67千字节（减少29.50%）。因此不能把净退化解释为“没有减少读写”。行端寄存器均116、共享存储均21296字节、临时溢出空间均零；共享存储操作180224→199680（增加10.80%），银行冲突0.715%→1.423%，一级缓存停顿39.47%→46.59%。银行冲突和停顿是并行观察证据，各自导致多少微秒尚未分离。','',
        '97104点的289行长：行端12.80→18.80微秒，省去独立前处理4.64微秒，列端8.96→9.12微秒；共享存储操作4896→7824（增加59.80%），寄存器168→172，容量均32368字节。129472点同类操作6528→10432，增幅相同。这是行类型共同增加的实际操作，不是只针对一个尺寸的现象；尚未证明寄存器增加改变了驻留组数。','',
        '共享存储容量未增加，离线屏障数也相同：289行为5→5、343行为7→7、625行为9→9、1331行为7→7。两版原本都使用共享存储完成原生行变换的装载／写出，不能将融合版使用共享存储本身或“新增两个屏障”当作净退化原因。相同屏障数也不保证同步等待时间相同，本任务没有逐屏障等待周期，未将差额单独归给同步。确认的差别是前处理配对、共享存储访问方式、索引分支和实数输出适配的工作量。','',
        '### 实际源代码的离线编译对照','',
        '| N／行长 | 静态总指令：未融合→第五版 | 向量整数指令 | 共享读取指令 | 屏障指令 |','| --- | --- | --- | --- | --- |']
    isa=load(OUT/'actual-isa-summary.json');lookup={(x['N'],x['stage'],x['arm']):x for x in isa['kernels']}
    for n,q in ((69938,121),(97104,289),(129472,289),(142688,343),(425920,1331),(640000,625),(646866,1331),(2725888,1331)):
        a,b=(lookup[n,'row',arm]['static_instruction_groups'] for arm in ('unfused_cc','candidate'))
        cells=[f"{a[k]}→{b[k]}" for k in ('total','vector_integer','ds_reads','barriers')]
        lines.append(f"| {n}／{q} | {' | '.join(cells)} |")
    lines += ['', '以上为26个实际执行源代码的离线编译结果的一部分。不能把静态写出指令11→44直接当作动态流量增加四倍；代码包含互斥输出分支，真实流量以前述设备计数为准。源码和完整指令摘要见`actual-isa-summary.json`。','',
        '### 为什么同一行长不都退化','',
        '511104点也用1331行，但独立前处理省去9.44微秒，列端17.76→14.40微秒，基本抵消行端20.80→33.52微秒的增加，所以三轮净比值约1.00、1.00、1.04。实际列内核旋转因子表基数也不同：未融合为6、融合为8，对应共享存储33792→30720字节、操作29882→16616。不能把它与2725888点“列端也变慢”的情况混作同一种总收益。两版几何分解相同，融合实现选择的旋转因子配置属于逐段成本的一部分。','',
        '## 有依据的后续优化方向','',
        '优先处理行端适配的公共开销。对每块只有一行的类型，输出只能逐行写实数，却仍生成跨行配对、头尾对齐及向量／标量多分支。1331行实际每块121线程、一行；可以在生成时选单行公式，统一写出实部和虚部分量，删除不可能发生的跨行分支，并只为真正的不完整频率组生成边界判断。这按每块行数和映射条件选择，覆盖整个类型，不列尺寸白名单，也不增加全局读取或临时缓冲。','',
        '进一步可评估按原生输出寄存器映射直接写实数，省去行端共享存储输出中转。未融合版此处也没有启用寄存器直接写出，因此不能声称这一步已经被未融合对照验证为更优。必须先核对原生输出排列、尾组和两段实数位置，再用同库单项恢复／替换测试确认收益；这属于候选方案，尚未在设备实现验收。','',
        '多行块的289、343等类型保留必要的配对，但将完整块／尾块、奇偶起点和频率尾组分类在生成时或块入口完成，复用地址计算，避免在每个输出位置重复判断。前处理要区分配对计算与装载／写出的贡献，不先假定关闭共享存储或减少容量就能解决问题。','',
        '第四版对照暂不全面回退。1048576点先作为完整块打包写出类型的代表，做仅恢复旧输出的严格对照；如果确实随之恢复性能，再检查写出指令的发射次序和依赖。后续生产方案仍按共同映射条件接入，不加入该尺寸白名单。仅凭一级缓存停顿百分比上升，不宣称已发现请求排队、缓存抖动或降频。','',
        '本次只分析并保存诊断，没有修改FFT生产实现，也没有推送或升级稳定版本。','',
        '## 证据索引','',
        '- `comparison-analysis.json`：全部138个负比值比较，含每轮样本统计、源码身份、阶段时间、计数及结论。',
        '- 两份`相对…逐项分析.csv`：第四版95项、未融合版43项。',
        '- `散点与顺序图.html`：各轮各进程分开展示，不合并或剔除样本。',
        '- `pmc-summary.json`：362组性能计数摘要，每组保留原始30窗口文件的路径、校验值和工具单位。',
        '- `actual-isa-summary.json`：26个实际执行源代码的离线编译及资源摘要。',
        '- `evidence-acceptance.json`：完整性、设备、数值和原始结果校验值。',
        '- 原始运行目录：`'+str(RUN)+'`。', '']
    (OUT/'结果与原因分析.md').write_text('\n'.join(lines))
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>985072 退化诊断散点与顺序图</title>
<style>body{font:16px system-ui,sans-serif;margin:28px auto;max-width:1220px;color:#172936;background:#f7f9fb}h1{font-size:25px}select{font:inherit;padding:9px;width:100%;max-width:880px}.card{background:white;border:1px solid #d7e0e7;border-radius:10px;padding:18px;margin:16px 0}.plots{display:flex;flex-wrap:wrap;gap:20px}svg{max-width:100%;height:auto}small{color:#526779}.r{font-weight:600}p{line-height:1.65}</style>
<h1>第五版退化诊断985072</h1><p>同卡、十次预热／三十次样本。每轮分开展示；散点保留全部样本，横线为中位数，浅色区为中间50%。右侧按测量序号显示漂移。时间单位：微秒。</p><p><a href="结果与原因分析.md">结果与原因分析</a>　<a href="相对第四版逐项分析.csv">第四版逐项表</a>　<a href="相对同分解未融合版逐项分析.csv">未融合版逐项表</a></p><select id="pick"></select><main id="body"></main><script>
const data=__DATA__,labels={previous:'第四版',unfused_cc:'同分解未融合版'},colors=['#476c91','#d07b43'];
const pick=document.getElementById('pick');data.forEach((x,i)=>{let o=document.createElement('option');o.value=i;o.textContent=`${x.N} ${x.type}　${x.C}×${x.Q}　对照${labels[x.reference]}　原比值${x.original_speedup.toFixed(3)}`;pick.add(o)});
function quant(a,p){a=[...a].sort((x,y)=>x-y);let k=(a.length-1)*p,l=Math.floor(k);return a[l]+(a[Math.min(l+1,a.length-1)]-a[l])*(k-l)}
function draw(groups,sequence){const w=sequence?650:420,h=310,m={l:55,r:20,t:22,b:50},all=groups.flatMap(x=>x.values),lo=Math.min(...all),hi=Math.max(...all),pad=Math.max((hi-lo)*.10,.5),a=lo-pad,b=hi+pad,Y=v=>h-m.b-(v-a)/(b-a)*(h-m.b-m.t),X=(g,i)=>sequence?m.l+i/29*(w-m.l-m.r):m.l+(g+.5)*(w-m.l-m.r)/2;let s=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`;
for(let i=0;i<5;i++){let v=a+(b-a)*i/4,y=Y(v);s+=`<line x1="${m.l}" y1="${y}" x2="${w-m.r}" y2="${y}" stroke="#e5ebef"/><text x="${m.l-7}" y="${y+4}" text-anchor="end" font-size="11">${v.toFixed(2)}</text>`}
groups.forEach((g,k)=>{let c=colors[k],q1=quant(g.values,.25),q3=quant(g.values,.75),mid=quant(g.values,.5);if(!sequence){let x=X(k,0);s+=`<rect x="${x-45}" y="${Y(q3)}" width="90" height="${Y(q1)-Y(q3)}" fill="${c}" opacity=".16"/><line x1="${x-50}" x2="${x+50}" y1="${Y(mid)}" y2="${Y(mid)}" stroke="${c}" stroke-width="2"/><text x="${x}" y="${h-27}" text-anchor="middle" font-size="12">${g.name}</text><text x="${x}" y="${h-9}" text-anchor="middle" font-size="12">${mid.toFixed(3)}</text>`}else{s+=`<polyline fill="none" stroke="${c}" opacity=".75" points="${g.values.map((v,i)=>X(k,i)+','+Y(v)).join(' ')}"/>`}
g.values.forEach((v,i)=>{let x=X(k,i)+(sequence?0:Math.sin((i+1)*12.7)*22);s+=`<circle cx="${x}" cy="${Y(v)}" r="2.7" fill="${c}" opacity=".7"><title>${g.name} 样本${i+1}：${v.toFixed(6)}微秒</title></circle>`})});if(sequence)s+=`<text x="${m.l}" y="${h-20}" font-size="12">1</text><text x="${w-m.r}" y="${h-20}" text-anchor="end" font-size="12">30</text><text x="${w/2}" y="${h-5}" text-anchor="middle" font-size="12">测量序号</text>`;return s+'</svg>'}
function render(){let x=data[pick.value],s='';x.rounds.forEach(r=>{let g=[{name:labels[x.reference],values:r.reference_samples},{name:'第五版',values:r.candidate_samples}],name={'repeat-1':'复测一','repeat-2':'复测二','end-anchor':'末尾复测'}[r.phase];s+=`<section class="card"><p class="r">${name}　中位数比值 ${r.speedup.toFixed(4)}</p><div class="plots">${draw(g,false)}${draw(g,true)}</div><small>前后半段中位数变化：对照${r.reference_drift_percent.toFixed(2)}%，第五版${r.candidate_drift_percent.toFixed(2)}%。此数值描述漂移，不自动解释原因。</small></section>`});document.getElementById('body').innerHTML=s}pick.addEventListener('change',render);render();</script></html>'''
    (OUT/'散点与顺序图.html').write_text(html.replace('__DATA__',json.dumps(plots,ensure_ascii=False)))
    print(json.dumps(dict(complete=True,summary=summary,output=str(OUT)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
