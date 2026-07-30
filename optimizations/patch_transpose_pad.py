#!/usr/bin/env python3
"""
在 rtc_transpose_gen.cpp 中给 LDS 添加 1 列 padding,
消除 32×32 tile 双精度转置的 LDS bank conflict。
原理: 将 lds[tileX][tileX] 改为 lds[tileX][tileX+1],
     行 stride 从 32 变为 33, bank=(4x+4y)%32 均匀分布。
"""

import os, re

FILE = os.path.expanduser(
    "~/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/rtc_transpose_gen.cpp"
)

def apply_pad(pad=1):
    with open(FILE, 'r') as f:
        content = f.read()

    # LDS 声明: __shared__ scalar_type lds[32][32]
    # 改为: __shared__ scalar_type lds[32][33]
    content = re.sub(
        r'(Variable lds\{"lds", "__shared__ scalar_type", false, false, specs\.tileX\};\s*\n\s*lds\.size2D = )Literal\{specs\.tileX\};',
        r'\1Literal{specs.tileX + ' + str(pad) + r'};',
        content
    )

    with open(FILE, 'w') as f:
        f.write(content)
    print(f"已修改 LDS padding: tileX+{pad}")

def remove_pad():
    with open(FILE, 'r') as f:
        content = f.read()
    content = re.sub(
        r'Literal\{specs\.tileX \+ \d+\};',
        r'Literal{specs.tileX};',
        content
    )
    with open(FILE, 'w') as f:
        f.write(content)
    print("已恢复 LDS padding (无padding)")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "remove":
        remove_pad()
    else:
        apply_pad()