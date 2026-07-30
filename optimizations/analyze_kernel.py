#!/usr/bin/env python3
"""从 hipkernel.csv 提取 SBRR 和 transpose 时间，追加到结果 CSV"""
import pandas as pd, sys, os

csv_file = sys.argv[1]
trial_name = sys.argv[2]
results_csv = sys.argv[3]

try:
    df = pd.read_csv(csv_file)
except:
    with open(results_csv, 'a') as f:
        f.write(f"{trial_name},READ_ERROR,READ_ERROR,READ_ERROR,READ_ERROR\n")
    sys.exit(1)

# Extract key kernels
def find_avg_ns(pattern):
    rows = df[df['Name'].str.contains(pattern, na=False)]
    return int(rows['AverageNs'].sum()) if not rows.empty else 0

sbrr_512   = find_avg_ns(r'fft_rtc.*len_512.*sbrr')
sbrr_1024  = find_avg_ns(r'fft_rtc.*len_1024.*sbrr')
transpose_total = find_avg_ns(r'transpose')
fft_total  = find_avg_ns(r'transpose|fft_rtc') / 1e6

with open(results_csv, 'a') as f:
    f.write(f"{trial_name},{sbrr_512},{sbrr_1024},{transpose_total},{fft_total:.2f}\n")

print(f"  {trial_name}: SBRR_512={sbrr_512}ns SBRR_1024={sbrr_1024}ns Transpose={transpose_total}ns Total={fft_total:.2f}ms")