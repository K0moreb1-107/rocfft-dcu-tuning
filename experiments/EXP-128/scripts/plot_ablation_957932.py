"""Standalone diagnostic scatter and sample-order plots, using all timing samples."""
import html
import json
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path('/public/home/zhangkewei/zr')
RECORD = ROOT/'experiments/EXP-128/records/regression-955252-20261022/ablation-957127/results-957932'
ART = ROOT/'experiments/EXP-128/artifacts/analysis/ablation-957932'
ORDER = ('original','identity','column_merge','column_restore','row_hoist','pre_mirror','combined','input_restore')
COLORS = dict(zip(ORDER, ('#64748b','#94a3b8','#eab308','#b45309','#2563eb','#0d9488','#c026d3','#ef4444')))


def main():
    data = json.loads((RECORD/'分析数据.json').read_text())
    records = data['timing']
    keys = list(dict.fromkeys((row['N'],row['type']) for row in records))
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=.08,
                        subplot_titles=['每列保留该进程全部30次计时', '进程内测量序号与耗时'])
    info = []
    for key in keys:
        group = sorted((row for row in records if (row['N'],row['type']) == key),
                       key=lambda row:ORDER.index(row['variant']))
        begin = len(fig.data)
        for position, row in enumerate(group):
            color = COLORS[row['variant']]
            visible = key == keys[0]
            common = dict(visible=visible, name=row['label'], legendgroup=str(key)+row['variant'])
            fig.add_trace(go.Scatter(x=[position+(((i*11)%31)-15)/110 for i in range(30)],
                y=row['samples_us'], customdata=list(range(1,31)), mode='markers',
                marker=dict(color=color,size=6,opacity=.7), showlegend=False,
                hovertemplate=row['label']+'<br>第%{customdata}次：%{y:.5f}微秒<extra></extra>',
                **common),row=1,col=1)
            fig.add_trace(go.Scatter(x=[position],y=[row['median_us']],mode='markers',
                marker=dict(symbol='line-ew',size=19,color=color,line=dict(width=3,color=color)),
                error_y=dict(type='data',array=[row['p75_us']-row['median_us']],
                             arrayminus=[row['median_us']-row['p25_us']],thickness=5,width=9,color=color),
                showlegend=False,
                hovertemplate='中位数：%{y:.5f}微秒<br>中间50%区间：'+
                    f"{row['p25_us']:.5f}～{row['p75_us']:.5f}微秒<extra></extra>",
                **common),row=1,col=1)
            fig.add_trace(go.Scatter(x=list(range(1,31)),y=row['samples_us'],mode='lines+markers',
                line=dict(color=color,width=1.5),marker=dict(color=color,size=4),showlegend=True,
                hovertemplate=row['label']+'<br>第%{x}次：%{y:.5f}微秒<extra></extra>',
                **common),row=1,col=2)
        values = [value for row in group for value in row['samples_us']]
        low, high = min(values), max(values)
        margin = max((high-low)*.08, 1.)
        info.append(dict(key=key, begin=begin, end=len(fig.data),
                         title=f"{key[0]} {key[1]}；列长{group[0]['C']}，行长{group[0]['Q']}",
                         ticktext=[row['label'] for row in group], range=[low-margin,high+margin]))
    buttons = []
    for item in info:
        buttons.append(dict(label=str(item['key'][0])+' '+item['key'][1], method='update',args=[
            dict(visible=[item['begin'] <= index < item['end'] for index in range(len(fig.data))]),
            {'title.text':item['title'], 'xaxis.tickvals':list(range(len(item['ticktext']))),
             'xaxis.ticktext':item['ticktext'],'xaxis.range':[-.5,len(item['ticktext'])-.5],
             'yaxis.range':item['range'],'yaxis2.range':item['range']}]))
    first = info[0]
    fig.update_layout(template='plotly_white',height=690,title=first['title'],
        font=dict(family='Microsoft YaHei, Noto Sans CJK SC, sans-serif',size=12),
        margin=dict(l=70,r=30,t=120,b=165),legend=dict(orientation='h',y=-.23,x=0),
        updatemenus=[dict(buttons=buttons,x=0,y=1.17,xanchor='left',yanchor='top',active=0)])
    fig.update_xaxes(tickvals=list(range(len(first['ticktext']))),ticktext=first['ticktext'],
                     tickangle=-22,range=[-.5,len(first['ticktext'])-.5],row=1,col=1)
    fig.update_xaxes(title_text='各进程内的正式测量序号',dtick=5,range=[0,31],row=1,col=2)
    fig.update_yaxes(title_text='耗时，微秒',range=first['range'],row=1,col=1)
    fig.update_yaxes(range=first['range'],row=1,col=2)
    ART.mkdir(parents=True,exist_ok=True)
    page = fig.to_html(include_plotlyjs=True,full_html=True,config=dict(responsive=True,displaylogo=False))
    introduction = '''<div style="font-family:Microsoft YaHei,sans-serif;max-width:1200px;margin:24px auto;line-height:1.65">
<h2>任务957932受控诊断：全部散点与顺序图</h2>
<p>下拉选择20个尺寸与方向组合。左图每列是一个进程的全部30次测量，粗竖线标中间50%区间，横线标中位数。
右图显示各进程内的测量顺序。所有慢点保留，未混入16个信息采集进程的计时。</p>
<p>同一已验证库、默认分解、同一独占显卡；每进程预热10次。这里比较本轮原代码与受控替换代码，
不替换此前正式性能表。中间50%区间重叠时，差异不明确；曲线变化不直接归因于频率、温度或缓存。</p></div>'''
    page = page.replace('<body>','<body>'+introduction,1)
    path = ART/'散点与顺序图.html'
    path.write_text(page)
    assert len(keys) == 20 and sum(len(row['samples_us']) for row in records) == 2370
    print(json.dumps(dict(path=str(path),bytes=path.stat().st_size,cases=len(keys),timing_samples=2370)))


if __name__ == '__main__':
    main()
