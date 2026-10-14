# EXP127转置融合：链接修复后的结果

功能和正确性通过；性能分化明显。转置内融合的27个目标组合中25个中位数更低；已有TR／RT中的逐行配对融合为6/23。当前候选仍需优化逐行配对部分，稳定版本保持现状。

检查日期：2026年10月14日。构建验证任务920231成功，用时56分02秒，于22:29:38结束；性能任务920232成功，用时20分39秒，于22:50:17结束。时间均为新加坡时间。

源码提交：2ef393567f2637f356bfc75db78bce53ad0f42fd。当前库校验值：9eaa2f80d76c11f3008c97ee015ab482fb8947d98d28dcd5a14374f45ff9de38。

正确性与实际融合已复核：121项初步检查、93项对照计划匹配、2800份独立完整参考、5600次执行全部通过，独立参考最大误差为4.947359283446996e−15。208项范围检查通过，其中188项实际执行、20项只建立计划；上述计划及范围检查中包括3项容量回退计划和6项相应执行／回调检查。输入保护、输出完整、保护区域、回调次数及缩放均按原登记验证。

五类各五个N，两个方向共50个目标组合，全部有实际融合证据。内部计算分解、FFT基数及中间相位与已验收卷积版一致；原有TR／RT及递归融合保留。逐行配对按登记调整块内任务数，边界处理并入首／末内核，执行记录中没有独立实数前后处理内核。测试条件为一维、双精度、批量一、非原位、连续布局、零用户偏移、偶数N大于65536；目标N从65610到6000000。不能把已测覆盖等同于任意尺寸均已验证。

正式性能数据完整：113个尺寸／类型组合、三版本339个独立进程、16950个逐次样本及113份图，全部校验通过，汇总与原始样本重算一致。每进程三次预热后50次逐次同步的完整变换计时，仅测默认路径，单卡执行且节点独占。

本轮主要对照是已验收的卷积版7942bf0ab470bbabcfd4119a102eb9c92ae88ebf及库3f895cf68e71261448f3274e2645550aaeb839e360aea7b59aa7331ab0db58ed；官方为已登记EXP096库。原程序及原图中的“稳定对照”是通用栏名，本轮实际指卷积版，并非稳定分支上的CC版。

全部性能结论只用原始逐次耗时的中位数。加速比＝卷积版中位数÷当前中位数，大于1表示加速；相对官方的全部收益不能都归于新增转置融合。均值仅留在原始兼容记录；A100没有匹配中位数，未混入比较。

50个新增目标组合中31个中位数更低、19个更高。18项更快、12项更慢的中间50%样本区间已分开；其余20项仍有重叠，列为差异不明确。区间分开属于本次样本证据，不能单独证明跨次运行的稳定收益。

| 实际边界实现 | 中位数更低 | z2d更低 | d2z更低 | 对卷积版加速比范围 | 区间分开的退化 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 转置内融合 | 25/27 | 15/15 | 10/12 | 0.903475～1.176382 | 0 |
| 已有TR／RT中的逐行配对融合 | 6/23 | 2/10 | 4/13 | 0.730711～1.173835 | 12 |

转置内融合的两项中位数上升均有区间重叠；12项区间分开的退化全部来自逐行配对。这是需要按整个实现类型查因的证据。逐行配对增加完整复数共享交换区、块内同步，并将原奇数块内任务数向下取偶数；这些额外开销已由源码和计划确认，但本次没有占用率、访存等待或指令计数诊断，不能认定某一项就是实际瓶颈。

| 默认转置类型 | d2z中位数更低／5 | d2z加速比范围 | z2d中位数更低／5 | z2d加速比范围 |
| --- | ---: | ---: | ---: | ---: |
| 首尾均保留独立转置 | 4/5 | 0.903475～1.163321 | 5/5 | 1.011111～1.176382 |
| 首段已有TR，末段保留转置 | 4/5 | 0.968343～1.119687 | 1/5 | 0.823862～1.173835 |
| 首段保留转置，末段已有RT | 2/5 | 0.731111～1.093220 | 5/5 | 1.062382～1.152466 |
| 首尾已有TR／RT | 2/5 | 0.730711～1.034854 | 1/5 | 0.858128～1.013841 |
| 第一行阶段为递归分解 | 2/5 | 0.961108～1.109425 | 5/5 | 1.076326～1.118388 |

每类五个N分别为：

- 首尾均保留独立转置：69972、214326、663552、1995840、6000000。
- 首段已有TR，末段保留转置：65610、145002、319488、841500、2539732。
- 首段保留转置，末段已有RT：67914、135252、270336、567000、1193400。
- 首尾已有TR／RT：65824、133280、294912、589560、1170450。
- 第一行阶段为递归分解：1837462、2839714、4343092、5345344、5797836。

需要优先关注的实例：

- 589560 d2z：77.280000→105.760001微秒，加速比0.730711，耗时增加36.85%；逐行配对，中间50%样本区间分开。测量序号图显示两版虽有早期换档，后半段仍有较大差距。
- 2539732 z2d：256.320000→311.120003微秒，加速比0.823862，耗时增加21.38%；逐行配对，区间分开。
- 6000000 z2d：629.598975→535.199493微秒，加速比1.176382，耗时降低14.99%；转置内融合，区间分开。

12项区间分开的目标退化如下，耗时均为微秒。共享交换区来自实际计划登记，不是占用率测量。

| 尺寸／类型 | 卷积版中位数 | 当前中位数 | 加速比 | 块内任务数变化 | 共享交换区，字节 |
| --- | ---: | ---: | ---: | ---: | ---: |
| [133280 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/133280_d2z_1d.svg) | 38.720001 | 42.240001 | 0.916667 | 7→6 | 26208 |
| [135252 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/135252_d2z_1d.svg) | 40.240001 | 55.039499 | 0.731111 | 7→6 | 27840 |
| [589560 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/589560_d2z_1d.svg) | 77.280000 | 105.760001 | 0.730711 | 7→6 | 55584 |
| [589560 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/589560_z2d_1d.svg) | 79.520002 | 91.200002 | 0.871930 | 7→6 | 49056 |
| [841500 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/841500_z2d_1d.svg) | 89.439500 | 103.439499 | 0.864655 | 5→4 | 35968 |
| [1170450 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1170450_d2z_1d.svg) | 125.039998 | 144.639999 | 0.864491 | 5→4 | 49024 |
| [1170450 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1170450_z2d_1d.svg) | 119.039498 | 138.720006 | 0.858128 | 5→4 | 49024 |
| [1193400 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1193400_d2z_1d.svg) | 139.679499 | 159.840003 | 0.873871 | 5→4 | 49024 |
| [1837462 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1837462_d2z_1d.svg) | 294.479996 | 303.519502 | 0.970218 | 7→6 | 27840 |
| [2539732 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/2539732_z2d_1d.svg) | 256.320000 | 311.120003 | 0.823862 | 7→6 | 55584 |
| [2839714 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/2839714_d2z_1d.svg) | 451.600000 | 468.639001 | 0.963642 | 7→6 | 27840 |
| [4343092 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/4343092_d2z_1d.svg) | 604.959488 | 629.439503 | 0.961108 | 7→6 | 55584 |

其余63项对照按中位数计为32项更快、5项相等、26项更慢；51项区间重叠。另有5项更快、7项更慢的区间分开。7项区间分开的退化都属于保留的卷积路径，耗时增加约1.05%～3.20%，因此不能宣称非目标完全无退化。对应计划及卷积正确性回归已通过，实际原因尚未诊断。

| 保留卷积路径的退化 | 卷积版中位数 | 当前中位数 | 加速比 |
| --- | ---: | ---: | ---: |
| [201038 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/201038_z2d_1d.svg) | 119.119998 | 121.280000 | 0.982190 |
| [507378 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/507378_z2d_1d.svg) | 267.359495 | 275.920004 | 0.968975 |
| [507752 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/507752_d2z_1d.svg) | 270.719498 | 275.759503 | 0.981723 |
| [560372 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/560372_z2d_1d.svg) | 353.278995 | 358.159497 | 0.986373 |
| [681468 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681468_d2z_1d.svg) | 369.120002 | 375.839502 | 0.982121 |
| [681468 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681468_z2d_1d.svg) | 366.558999 | 371.280000 | 0.987285 |
| [888376 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/888376_z2d_1d.svg) | 493.839994 | 499.039501 | 0.989581 |

本轮接受功能与正确性验证及完整性能数据，保留为候选。性能尚不具备全类型普遍收益；后续应优先定位逐行配对实现及上述卷积对照差异。稳定分支、标签和安装保持现状，未新提交任务、未修改计算源码、未推广或推送。

完整中位数比较如下。尺寸／类型链接指向保留的三版本全部样本散点与测量序号图。

| 尺寸／类型 | 官方中位数，微秒 | 卷积版中位数，微秒 | 当前中位数，微秒 | 对卷积版加速比 | 对官方加速比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| [65536 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65536_z2z_1d.svg) | 28.000001 | 27.200000 | 27.360000 | 0.994152 | 1.023392 |
| [65536 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65536_d2z_1d.svg) | 30.560000 | 25.920000 | 25.920000 | 1.000000 | 1.179012 |
| [65536 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65536_z2d_1d.svg) | 32.320000 | 27.200000 | 27.200000 | 1.000000 | 1.188235 |
| [65538 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65538_z2z_1d.svg) | 113.440000 | 139.999501 | 138.640001 | 1.009806 | 0.818234 |
| [65538 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65538_d2z_1d.svg) | 79.200000 | 81.600003 | 76.400001 | 1.068063 | 1.036649 |
| [65538 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65538_z2d_1d.svg) | 78.720003 | 77.119999 | 77.680003 | 0.992791 | 1.013388 |
| [65540 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65540_d2z_1d.svg) | 77.199999 | 76.640002 | 76.720003 | 0.998957 | 1.006256 |
| [65540 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65540_z2d_1d.svg) | 83.200000 | 76.959997 | 75.839996 | 1.014768 | 1.097046 |
| [65610 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65610_d2z_1d.svg) | 39.759999 | 40.320002 | 37.439998 | 1.076923 | 1.061966 |
| [65610 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65610_z2d_1d.svg) | 42.399999 | 39.039999 | 39.119499 | 0.997968 | 1.083858 |
| [65824 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65824_d2z_1d.svg) | 34.720000 | 34.480000 | 34.400001 | 1.002326 | 1.009302 |
| [65824 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/65824_z2d_1d.svg) | 36.640000 | 35.840001 | 38.079999 | 0.941177 | 0.962185 |
| [67914 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/67914_d2z_1d.svg) | 41.600000 | 41.280001 | 37.760001 | 1.093220 | 1.101695 |
| [67914 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/67914_z2d_1d.svg) | 42.080000 | 41.120000 | 35.680000 | 1.152466 | 1.179372 |
| [69972 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/69972_d2z_1d.svg) | 41.280001 | 37.439998 | 41.439999 | 0.903475 | 0.996139 |
| [69972 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/69972_z2d_1d.svg) | 42.720001 | 41.439999 | 38.480001 | 1.076923 | 1.110187 |
| [81920 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/81920_d2z_1d.svg) | 32.560000 | 31.840000 | 31.679999 | 1.005051 | 1.027778 |
| [81920 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/81920_z2d_1d.svg) | 33.119999 | 32.000002 | 31.840000 | 1.005025 | 1.040201 |
| [97682 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/97682_d2z_1d.svg) | 41.520000 | 42.879999 | 40.240001 | 1.065606 | 1.031809 |
| [97682 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/97682_z2d_1d.svg) | 44.480000 | 44.000000 | 44.319998 | 0.992780 | 1.003610 |
| [117652 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/117652_d2z_1d.svg) | 92.000000 | 82.719997 | 83.200000 | 0.994231 | 1.105769 |
| [117652 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/117652_z2d_1d.svg) | 92.000000 | 84.480003 | 80.320001 | 1.051793 | 1.145418 |
| [117654 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/117654_d2z_1d.svg) | 92.639998 | 81.520002 | 81.440002 | 1.000982 | 1.137525 |
| [117654 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/117654_z2d_1d.svg) | 92.639998 | 82.719997 | 80.879997 | 1.022750 | 1.145401 |
| [131072 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/131072_z2z_1d.svg) | 30.640000 | 29.839500 | 29.759999 | 1.002671 | 1.029570 |
| [131072 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/131072_d2z_1d.svg) | 31.840000 | 27.599500 | 27.840000 | 0.991361 | 1.143678 |
| [131072 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/131072_z2d_1d.svg) | 32.320000 | 27.680000 | 27.680000 | 1.000000 | 1.167630 |
| [133280 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/133280_d2z_1d.svg) | 40.640000 | 38.720001 | 42.240001 | 0.916667 | 0.962121 |
| [133280 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/133280_z2d_1d.svg) | 42.560000 | 39.039999 | 39.200000 | 0.995918 | 1.085714 |
| [135252 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/135252_d2z_1d.svg) | 43.520000 | 40.240001 | 55.039499 | 0.731111 | 0.790705 |
| [135252 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/135252_z2d_1d.svg) | 44.159999 | 44.960000 | 42.320000 | 1.062382 | 1.043478 |
| [145002 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/145002_d2z_1d.svg) | 45.600001 | 41.600000 | 42.959999 | 0.968343 | 1.061453 |
| [145002 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/145002_z2d_1d.svg) | 48.480000 | 43.680001 | 45.120001 | 0.968085 | 1.074468 |
| [166698 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/166698_d2z_1d.svg) | 44.560000 | 33.520000 | 33.440001 | 1.002392 | 1.332536 |
| [166698 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/166698_z2d_1d.svg) | 45.440000 | 35.840001 | 33.360001 | 1.074341 | 1.362110 |
| [201038 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/201038_d2z_1d.svg) | 154.560000 | 120.159999 | 122.399502 | 0.981703 | 1.262750 |
| [201038 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/201038_z2d_1d.svg) | 155.279502 | 119.119998 | 121.280000 | 0.982190 | 1.280339 |
| [201840 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/201840_d2z_1d.svg) | 152.799994 | 124.159999 | 121.440001 | 1.022398 | 1.258234 |
| [201840 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/201840_z2d_1d.svg) | 156.080000 | 122.720003 | 124.559499 | 0.985232 | 1.253056 |
| [214326 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/214326_d2z_1d.svg) | 47.359999 | 46.080001 | 43.359999 | 1.062731 | 1.092251 |
| [214326 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/214326_z2d_1d.svg) | 44.960000 | 43.680001 | 43.200001 | 1.011111 | 1.040741 |
| [262144 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/262144_z2z_1d.svg) | 40.959999 | 37.759500 | 37.760001 | 0.999987 | 1.084746 |
| [262144 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/262144_d2z_1d.svg) | 36.800001 | 33.280000 | 33.199999 | 1.002410 | 1.108434 |
| [262144 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/262144_z2d_1d.svg) | 37.280001 | 33.280000 | 33.280000 | 1.000000 | 1.120192 |
| [270336 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/270336_d2z_1d.svg) | 50.080001 | 47.200002 | 47.040001 | 1.003401 | 1.064626 |
| [270336 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/270336_z2d_1d.svg) | 52.239999 | 50.239999 | 45.279998 | 1.109541 | 1.153710 |
| [294912 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/294912_d2z_1d.svg) | 50.239999 | 47.520000 | 45.919500 | 1.034854 | 1.094089 |
| [294912 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/294912_z2d_1d.svg) | 51.600000 | 46.879999 | 46.239998 | 1.013841 | 1.115917 |
| [319488 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/319488_d2z_1d.svg) | 52.159999 | 50.560001 | 46.399999 | 1.089655 | 1.124138 |
| [319488 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/319488_z2d_1d.svg) | 51.759999 | 52.400000 | 44.640001 | 1.173835 | 1.159498 |
| [370546 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/370546_d2z_1d.svg) | 362.879008 | 288.560003 | 291.839495 | 0.988763 | 1.243420 |
| [370546 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/370546_z2d_1d.svg) | 367.359996 | 285.600007 | 287.439004 | 0.993602 | 1.278045 |
| [371288 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/371288_d2z_1d.svg) | 362.319499 | 290.479496 | 285.120010 | 1.018797 | 1.270761 |
| [371288 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/371288_z2d_1d.svg) | 368.720010 | 289.440006 | 290.398985 | 0.996698 | 1.269701 |
| [507378 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/507378_d2z_1d.svg) | 365.920007 | 278.399497 | 275.120005 | 1.011920 | 1.330038 |
| [507378 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/507378_z2d_1d.svg) | 371.999487 | 267.359495 | 275.920004 | 0.968975 | 1.348215 |
| [507752 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/507752_d2z_1d.svg) | 363.120005 | 270.719498 | 275.759503 | 0.981723 | 1.316800 |
| [507752 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/507752_z2d_1d.svg) | 373.439506 | 272.079512 | 271.599993 | 1.001766 | 1.374961 |
| [524288 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/524288_z2z_1d.svg) | 95.839500 | 63.840002 | 64.159997 | 0.995013 | 1.493758 |
| [524288 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/524288_d2z_1d.svg) | 48.400000 | 41.600000 | 39.600000 | 1.050505 | 1.222222 |
| [524288 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/524288_z2d_1d.svg) | 46.159999 | 42.399999 | 39.760001 | 1.066398 | 1.160966 |
| [559910 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/559910_d2z_1d.svg) | 693.518996 | 361.359492 | 365.920007 | 0.987537 | 1.895275 |
| [559910 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/559910_z2d_1d.svg) | 697.119504 | 359.599501 | 358.318999 | 1.003574 | 1.945528 |
| [560372 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/560372_d2z_1d.svg) | 693.598986 | 359.359503 | 359.599993 | 0.999331 | 1.928807 |
| [560372 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/560372_z2d_1d.svg) | 699.998975 | 353.278995 | 358.159497 | 0.986373 | 1.954434 |
| [567000 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/567000_d2z_1d.svg) | 67.199998 | 66.720001 | 70.079997 | 0.952055 | 0.958904 |
| [567000 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/567000_z2d_1d.svg) | 68.159997 | 69.600001 | 65.279998 | 1.066177 | 1.044118 |
| [589560 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/589560_d2z_1d.svg) | 75.519502 | 77.280000 | 105.760001 | 0.730711 | 0.714065 |
| [589560 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/589560_z2d_1d.svg) | 76.159999 | 79.520002 | 91.200002 | 0.871930 | 0.835088 |
| [663552 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/663552_d2z_1d.svg) | 70.400000 | 68.960004 | 66.239998 | 1.041063 | 1.062802 |
| [663552 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/663552_z2d_1d.svg) | 74.320000 | 71.840003 | 67.279998 | 1.067777 | 1.104637 |
| [681468 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681468_d2z_1d.svg) | 716.479003 | 369.120002 | 375.839502 | 0.982121 | 1.906343 |
| [681468 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681468_z2d_1d.svg) | 700.639486 | 366.558999 | 371.280000 | 0.987285 | 1.887092 |
| [681470 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681470_z2z_1d.svg) | 1324.798942 | 647.918999 | 634.238988 | 1.021569 | 2.088801 |
| [681470 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681470_d2z_1d.svg) | 693.919003 | 376.880005 | 367.599502 | 1.025246 | 1.887704 |
| [681470 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/681470_z2d_1d.svg) | 697.439015 | 367.679507 | 365.599006 | 1.005691 | 1.907661 |
| [776406 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/776406_d2z_1d.svg) | 700.959980 | 507.520020 | 505.438983 | 1.004117 | 1.386834 |
| [776406 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/776406_z2d_1d.svg) | 698.319495 | 499.999985 | 498.798996 | 1.002408 | 1.400002 |
| [776688 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/776688_d2z_1d.svg) | 696.399987 | 506.960005 | 504.719019 | 1.004440 | 1.379778 |
| [776688 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/776688_z2d_1d.svg) | 699.359506 | 498.239994 | 499.359488 | 0.997758 | 1.400513 |
| [841500 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/841500_d2z_1d.svg) | 89.280002 | 93.759999 | 91.200002 | 1.028070 | 0.978947 |
| [841500 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/841500_z2d_1d.svg) | 90.240002 | 89.439500 | 103.439499 | 0.864655 | 0.872394 |
| [888202 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/888202_d2z_1d.svg) | 703.199983 | 506.079972 | 502.159506 | 1.007807 | 1.400352 |
| [888202 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/888202_z2d_1d.svg) | 701.919496 | 498.558998 | 497.278988 | 1.002574 | 1.411521 |
| [888376 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/888376_d2z_1d.svg) | 699.679017 | 504.799992 | 507.039487 | 0.995583 | 1.379930 |
| [888376 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/888376_z2d_1d.svg) | 702.879012 | 493.839994 | 499.039501 | 0.989581 | 1.408464 |
| [999996 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/999996_d2z_1d.svg) | 703.680009 | 508.319497 | 503.760010 | 1.009051 | 1.396856 |
| [999996 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/999996_z2d_1d.svg) | 706.638992 | 502.319008 | 499.839500 | 1.004961 | 1.413732 |
| [999998 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/999998_d2z_1d.svg) | 703.359008 | 509.039521 | 507.440001 | 1.003152 | 1.386093 |
| [999998 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/999998_z2d_1d.svg) | 705.199510 | 497.359499 | 499.359995 | 0.995994 | 1.412207 |
| [1048576 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1048576_z2z_1d.svg) | 181.039996 | 118.720002 | 118.720002 | 1.000000 | 1.524933 |
| [1048576 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1048576_d2z_1d.svg) | 113.840003 | 71.840003 | 72.480001 | 0.991170 | 1.570640 |
| [1048576 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1048576_z2d_1d.svg) | 113.520000 | 74.800000 | 74.720003 | 1.001071 | 1.519272 |
| [1170450 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1170450_d2z_1d.svg) | 124.639500 | 125.039998 | 144.639999 | 0.864491 | 0.861722 |
| [1170450 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1170450_z2d_1d.svg) | 118.880004 | 119.039498 | 138.720006 | 0.858128 | 0.856978 |
| [1193400 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1193400_d2z_1d.svg) | 137.039997 | 139.679499 | 159.840003 | 0.873871 | 0.857357 |
| [1193400 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1193400_z2d_1d.svg) | 138.559997 | 140.720002 | 131.760001 | 1.068002 | 1.051609 |
| [1837462 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1837462_d2z_1d.svg) | 286.320001 | 294.479996 | 303.519502 | 0.970218 | 0.943333 |
| [1837462 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1837462_z2d_1d.svg) | 295.999497 | 298.718989 | 272.799999 | 1.095011 | 1.085042 |
| [1995840 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1995840_d2z_1d.svg) | 227.199994 | 225.359999 | 205.119498 | 1.098677 | 1.107647 |
| [1995840 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/1995840_z2d_1d.svg) | 233.759999 | 227.520004 | 203.999497 | 1.115297 | 1.145885 |
| [2539732 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/2539732_d2z_1d.svg) | 264.239505 | 263.439998 | 235.280000 | 1.119687 | 1.123085 |
| [2539732 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/2539732_z2d_1d.svg) | 251.120001 | 256.320000 | 311.120003 | 0.823862 | 0.807148 |
| [2839714 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/2839714_d2z_1d.svg) | 454.079986 | 451.600000 | 468.639001 | 0.963642 | 0.968933 |
| [2839714 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/2839714_z2d_1d.svg) | 450.239003 | 444.479495 | 412.959993 | 1.076326 | 1.090273 |
| [4343092 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/4343092_d2z_1d.svg) | 625.840008 | 604.959488 | 629.439503 | 0.961108 | 0.994281 |
| [4343092 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/4343092_z2d_1d.svg) | 636.559010 | 631.039500 | 564.240009 | 1.118388 | 1.128171 |
| [5345344 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/5345344_d2z_1d.svg) | 871.038973 | 873.519003 | 801.439494 | 1.089938 | 1.086843 |
| [5345344 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/5345344_z2d_1d.svg) | 864.479005 | 876.399994 | 794.319004 | 1.103335 | 1.088327 |
| [5797836 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/5797836_d2z_1d.svg) | 754.079998 | 754.318982 | 679.919004 | 1.109425 | 1.109073 |
| [5797836 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/5797836_z2d_1d.svg) | 767.198980 | 750.239015 | 681.678981 | 1.100575 | 1.125455 |
| [6000000 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/6000000_d2z_1d.svg) | 624.159485 | 621.679008 | 534.400016 | 1.163321 | 1.167963 |
| [6000000 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014/plots/6000000_z2d_1d.svg) | 616.319001 | 629.598975 | 535.199493 | 1.176382 | 1.151569 |

服务器原始运行目录：

/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-build-20261014

/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-tr-s2-linkfix-performance-20261014

本地检查目录review-920231-920232保留逐项复核、全部样本及校验值；本文件旁的113份矢量图与服务器原件逐字一致，五张位图只用于预览。
