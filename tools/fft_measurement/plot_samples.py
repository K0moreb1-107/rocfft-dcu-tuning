"""Standalone two-column distributions and chronological event traces."""
import math
import os
from pathlib import Path
import warnings

from common import cases
from sample_contract import arms, iterations, statistics_for


def render(run, manifest, samples):
    run = Path(run)
    output = run/'plots'
    output.mkdir()
    os.environ.setdefault('MPLCONFIGDIR', str(output/'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    selected = arms(manifest)
    labels = {'official': '官方基线', 'previous': '稳定对照', 'candidate': '当前版本'}
    colors = {'official': '#2878b8', 'previous': '#677b97', 'candidate': '#e58b29'}
    settings = {'svg.fonttype': 'none', 'font.family': 'sans-serif', 'axes.unicode_minus': False,
                'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False}
    if os.name == 'nt' and Path('C:/Windows/Fonts/msyh.ttc').is_file():
        from matplotlib import font_manager
        font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
        settings['font.family'] = font_manager.FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name()
    paths = []
    with plt.rc_context(settings):
        for n, func in cases(manifest):
            fig, (distribution, sequence) = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True,
                                                         gridspec_kw={'width_ratios': [1, 1.6]})
            fig.subplots_adjust(left=.08, right=.98, top=.78, bottom=.24, wspace=.18)
            fig.suptitle('%d / %s：批量为一，每版本%d次计时'
                         %(n, func.removesuffix('_1d'), iterations(manifest)), fontsize=15)
            for position, arm in enumerate(selected):
                values = samples[(n, func, arm)]
                microseconds = [value*1000 for value in values]
                stats = statistics_for(values)
                color = colors[arm]
                offsets = [.08*math.sin(i*2.31) for i in range(1, len(values)+1)]
                distribution.scatter([position+x for x in offsets], microseconds,
                                     s=21, color=color, alpha=.65, linewidths=0)
                distribution.add_patch(Rectangle((position-.16, stats['p25_ms']*1000), .32,
                                                  (stats['p75_ms']-stats['p25_ms'])*1000,
                                                  color=color, alpha=.12, linewidth=0))
                for statistic, style in (('median', '-'), ('mean', '--')):
                    distribution.hlines(stats[statistic+'_ms']*1000, position-.22, position+.22,
                                        color=color, linestyle=style, linewidth=1.6)
                sequence.plot(range(1, len(values)+1), microseconds, color=color, marker='o',
                              markersize=3, linewidth=.85, alpha=.8, label=labels[arm])
            distribution.set_xticks(range(len(selected)), [labels[arm] for arm in selected])
            distribution.set_xlim(-.45, len(selected)-.55)
            distribution.set_ylabel('完整变换耗时（微秒）')
            distribution.set_title('全部样本的分布', fontsize=12)
            distribution.legend(handles=[Line2D([0], [0], color='#3d4e60', linestyle='--', label='均值'),
                                          Line2D([0], [0], color='#3d4e60', label='中位数')],
                                loc='best', frameon=False, fontsize=9)
            sequence.set_title('各版本内的测量先后', fontsize=12)
            sequence.set_xlabel('测量序号（各版本分别计时）')
            sequence.legend(frameon=False, fontsize=9)
            sequence.set_xlim(.5, len(values)+.5)
            for axes in (distribution, sequence):
                axes.grid(axis='y', color='#dbe3e9', linewidth=.7)
                axes.set_axisbelow(True)
            fig.text(.5, .09, '全部样本保留；浅色区域为中间50%的样本区间。横向展开仅用于避开重叠。',
                     ha='center', fontsize=10)
            fig.text(.5, .035, '同一组记录的两种画法；相同序号不代表两个版本同步或配对测量。',
                     ha='center', fontsize=9, color='#66798b')
            path = output/('%d_%s.svg'%(n, func))
            try:
                # SVG retains Unicode text: the viewing browser supplies CJK fallback fonts.
                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', message='Glyph .* missing from current font.*')
                    fig.savefig(path, format='svg', facecolor='white')
            finally:
                plt.close(fig)
            paths.append(path.relative_to(run).as_posix())
    return paths
