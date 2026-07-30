import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import re

def main():
    results_dir = '/public/home/zhangkewei/zr/results'
    output_dir = '/public/home/zhangkewei/zr/results/speedup_0727'
    os.makedirs(output_dir, exist_ok=True)

    # 只取 0727 日期的文件
    files = [f for f in os.listdir(results_dir) if f.endswith('.csv.hipkernel.csv') and '20260727' in f]

    # 时间戳: 105738 = 优化后, 125754 = 原始
    ts_optimized = '105738'
    ts_original = '125754'

    data = []

    for f in files:
        match = re.match(r'([a-z0-9]+)_([0-9a-z]+)_tuning_\d+_(\d+)\.csv\.hipkernel\.csv', f)
        if match:
            fft_type = match.group(1)
            size = match.group(2)
            timestamp = match.group(3)

            filepath = os.path.join(results_dir, f)
            df = pd.read_csv(filepath)

            # 排除非 FFT kernel 的行
            mask = df['Name'].str.contains('generate_random|impose_hermitian|Total|twiddle_gen', regex=True)
            fft_df = df[~mask]

            # 求和 AverageNs 得到 FFT 执行总时间
            total_duration_ns = fft_df['TotalDurationNs'].sum()
            total_duration_ms = total_duration_ns / 1e6

            data.append({
                'type': fft_type,
                'size': size,
                'timestamp': timestamp,
                'time_ms': total_duration_ms
            })

    if not data:
        print("No valid data found.")
        return

    df_res = pd.DataFrame(data)

    # 映射时间戳到标签
    ts_map = {ts_original: 'Original', ts_optimized: 'Optimized'}
    df_res['version'] = df_res['timestamp'].map(ts_map)

    # 过滤掉没有同时包含两个版本的类型/大小组合
    grouped = df_res.groupby(['type', 'size'])['timestamp'].apply(set)
    valid_groups = grouped[grouped.apply(lambda x: ts_original in x and ts_optimized in x)]
    valid_keys = set(valid_groups.index)
    df_res = df_res[df_res.apply(lambda row: (row['type'], row['size']) in valid_keys, axis=1)]

    # 排序: 64k < 128k < 256k < 512k
    size_order = {'64k': 1, '128k': 2, '256k': 3, '512k': 4}
    df_res['size_order'] = df_res['size'].map(size_order)
    df_res = df_res.sort_values(by=['type', 'size_order'])

    fft_types = sorted(df_res['type'].unique())

    n_types = len(fft_types)
    if n_types == 0:
        print("No valid FFT types found.")
        return

    # 计算子图布局: 一行最多3个
    n_cols = min(n_types, 3)
    n_rows = (n_types + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows))
    if n_types == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)
    elif n_cols == 1:
        axes = axes.reshape(-1, 1)

    # 隐藏多余的子图
    for idx in range(n_types, n_rows * n_cols):
        r, c = divmod(idx, n_cols)
        axes[r][c].set_visible(False)

    for idx, ftype in enumerate(fft_types):
        r, c = divmod(idx, n_cols)
        ax = axes[r][c]

        df_type = df_res[df_res['type'] == ftype]
        sizes = sorted(df_type['size'].unique(), key=lambda x: size_order.get(x, 99))

        orig_times = []
        opt_times = []
        speedups = []

        for s in sizes:
            df_s = df_type[df_type['size'] == s]
            t_orig = df_s[df_s['version'] == 'Original']['time_ms'].values
            t_opt = df_s[df_s['version'] == 'Optimized']['time_ms'].values

            to = t_orig[0] if len(t_orig) > 0 else 0
            tp = t_opt[0] if len(t_opt) > 0 else 0

            orig_times.append(to)
            opt_times.append(tp)
            speedups.append(to / tp if tp > 0 else 1)

        x = np.arange(len(sizes))
        width = 0.35

        ax.bar(x - width/2, orig_times, width, label='Original', color='skyblue')
        bars_opt = ax.bar(x + width/2, opt_times, width, label='Optimized', color='salmon')

        ax.set_title(f'FFT Type: {ftype.upper()}')
        ax.set_xlabel('Size')
        ax.set_ylabel('Total Time (ms)')
        ax.set_xticks(x)
        ax.set_xticklabels(sizes)
        ax.legend()
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        # 添加加速比标注
        max_val = max(max(orig_times), max(opt_times)) if orig_times and opt_times else 1
        for i, bar in enumerate(bars_opt):
            height = max(orig_times[i], opt_times[i])
            ax.text(bar.get_x() + bar.get_width() / 2, height + 0.03 * max_val,
                    f'{speedups[i]:.2f}x', ha='center', va='bottom',
                    fontweight='bold', color='red', fontsize=10)

    fig.suptitle('FFT Kernel Tuning Speedup (2026-07-27)\nOriginal (125754) vs Optimized (105738)',
                 fontsize=14, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    output_path = os.path.join(output_dir, 'speedup_0727_chart.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Chart saved to {output_path}")

    # 同时输出一个 CSV 汇总表
    summary = df_res[['type', 'size', 'version', 'time_ms']].pivot_table(
        index=['type', 'size'], columns='version', values='time_ms').reset_index()
    summary['speedup'] = summary['Original'] / summary['Optimized']
    summary.to_csv(os.path.join(output_dir, 'speedup_summary.csv'), index=False, float_format='%.3f')
    print(f"Summary CSV saved to {os.path.join(output_dir, 'speedup_summary.csv')}")
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()