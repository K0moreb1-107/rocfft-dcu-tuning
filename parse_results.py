import re
from collections import defaultdict

with open('tune_all.log', 'r') as f:
    lines = f.readlines()

results = defaultdict(list)
for line in lines:
    # Match: 测 512_sbcc: f=[8, 8, 8], wgs=512, tpt=64 ... [建库: 38.7s | 运行: 5.0s] [成功] 6.3244 ms
    # Match: 跳过 512_sbcc: f=[8, 8, 8], wgs=512, tpt=64 [已存在, 耗时 6.3244 ms]
    m_run = re.search(r'(测|跳过)\s+([0-9]+_sb[rc]c):\s+f=(\[.*?\]),\s+wgs=([0-9]+),\s+tpt=([0-9]+).*?(?:\]\s+|耗时\s+)([0-9\.]+)\s+ms', line)
    if m_run:
        kernel = m_run.group(2)
        f_val = m_run.group(3)
        wgs = int(m_run.group(4))
        tpt = int(m_run.group(5))
        time_val = float(m_run.group(6))
        # Exclude those fake 122.7ms times!
        if time_val < 100.0:
            results[kernel].append((time_val, f_val, wgs, tpt))

print("=== Optimal Configurations ===")
for kernel, runs in results.items():
    if not runs:
        continue
    best = min(runs, key=lambda x: x[0])
    print(f"Kernel: {kernel}")
    print(f"  Best Time: {best[0]} ms")
    print(f"  f={best[1]}, wgs={best[2]}, tpt={best[3]}")
    print("-" * 30)
