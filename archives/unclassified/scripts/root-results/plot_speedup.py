import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import re

def main():
    results_dir = '/public/home/scnethpc2688/zr/results'
    files = [f for f in os.listdir(results_dir) if f.endswith('.csv.hipkernel.csv')]
    
    data = []
    
    for f in files:
        # e.g., d2z_128k_tuning_20260709_190045.csv.hipkernel.csv
        match = re.match(r'([a-z0-9]+)_([0-9a-z]+)_tuning_\d+_(\d+)\.csv\.hipkernel\.csv', f)
        if match:
            fft_type = match.group(1)
            size = match.group(2)
            timestamp = match.group(3)
            
            filepath = os.path.join(results_dir, f)
            df = pd.read_csv(filepath)
            
            # Filter out non-FFT rows
            # We exclude 'generate_random', 'impose_hermitian', 'Total' and 'twiddle_gen'
            mask = df['Name'].str.contains('generate_random|impose_hermitian|Total|twiddle_gen', regex=True)
            fft_df = df[~mask]
            
            # Sum AverageNs to get the time per FFT execution
            total_duration_ns = fft_df['AverageNs'].sum()
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
    
    # We assume timestamp 190045 is Original, 191206 is Optimized
    # Let's map timestamps to labels
    timestamps = sorted(df_res['timestamp'].unique())
    if len(timestamps) == 2:
        ts_map = {timestamps[0]: 'Original', timestamps[1]: 'Optimized'}
    else:
        # Fallback if there are not exactly 2 timestamps
        ts_map = {ts: f"Run_{ts}" for ts in timestamps}
        
    df_res['version'] = df_res['timestamp'].map(ts_map)
    
    # Custom sort for sizes: 64k, 128k, 256k, 512k
    size_order = {'64k': 1, '128k': 2, '256k': 3, '512k': 4}
    df_res['size_order'] = df_res['size'].map(size_order)
    df_res = df_res.sort_values(by=['type', 'size_order'])
    
    fft_types = sorted(df_res['type'].unique())
    
    fig, axes = plt.subplots(1, len(fft_types), figsize=(18, 6), sharey=False)
    if len(fft_types) == 1:
        axes = [axes]
        
    for ax, ftype in zip(axes, fft_types):
        df_type = df_res[df_res['type'] == ftype]
        sizes = sorted(df_type['size'].unique(), key=lambda x: size_order[x])
        
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
        
        # Add speedup annotations
        for i, bar in enumerate(bars_opt):
            height = max(orig_times[i], opt_times[i]) # Put text slightly above the max of the two bars
            ax.text(bar.get_x() + bar.get_width() / 2, height + 0.05 * max(orig_times + opt_times),
                    f'{speedups[i]:.2f}x', ha='center', va='bottom', fontweight='bold', color='red')

    plt.tight_layout()
    output_path = '/public/home/scnethpc2688/zr/results/speedup_chart.png'
    plt.savefig(output_path, dpi=300)
    print(f"Chart saved to {output_path}")

if __name__ == "__main__":
    main()
