# EXP127 用户偏移修复后的结果检查

检查日期：2026年10月14日。构建及完整验证任务914128、性能任务914129均成功完成。

源码7942bf0ab470bbabcfd4119a102eb9c92ae88ebf；当前库校验值3f895cf68e71261448f3274e2645550aaeb839e360aea7b59aa7331ab0db58ed。

构建含验证用时28分23秒；性能任务实际执行12分33秒，已于10月14日09:40:13结束。性能显式成功依赖前一个任务。

正确性已通过：78项初步检查、40项稳定版内部卷积计划匹配、80组实数与20组复数独立完整参考，共1400项参考、2800次执行；最大误差4.947359283446996e−15。92项范围检查全部通过，其中82项实际执行、10项计划检查。偏移、分平面、原位、单侧偏移、回调和非法布局均覆盖，核心融合的输入保护、回调次数及外部保护要求保留。

四类各五个尺寸，两个方向共40项均证实实际融合：卷积内部计划保持一致，执行记录中没有独立实数前后处理内核。验证日志、编译程序、计划和库的校验值复核一致。

正式性能数据完整：73个尺寸与类型组合、三个版本、219个独立进程、10950次完整变换测量；批量一、默认计划、双精度、非原位、三次预热后每进程50次逐次同步计时，单卡执行并独占节点。原始样本、执行顺序、库身份及73份图全部核对通过，汇总中位数与原始样本重算结果一致。

本报告只使用逐次耗时的中位数。加速比＝对照中位数÷当前中位数；大于1表示加速。A100缺少匹配中位数，未混入加速比。原运行报告中的均值属于兼容记录，本报告不据其作性能判断。

40项卷积目标的中位数全部低于稳定版，对稳定版加速比为1.005451～1.130753倍；相对官方为1.020106～1.952212倍。评估本轮新增融合主要使用稳定版对照，不能把相对官方的全部收益都归于本轮融合。

| 卷积类型 | d2z对稳定版加速比 | z2d对稳定版加速比 | 更快的组合数 |
| --- | ---: | ---: | ---: |
| N/2为偶数，卷积长度为混合基数 | 1.006743～1.130753 | 1.040792～1.073016 | 10/10 |
| N/2为偶数，卷积长度为二的幂 | 1.024134～1.107356 | 1.055768～1.098425 | 10/10 |
| N/2为奇数，卷积长度为混合基数 | 1.030915～1.066038 | 1.047659～1.095238 | 10/10 |
| N/2为奇数，卷积长度为二的幂 | 1.005451～1.087649 | 1.043191～1.096498 | 10/10 |

上述N/2是实数变换对应的复数变换长度；卷积长度是补零后的内部复数变换长度。每类五个不同N，具体数值见下面的完整表。

37项目标的中间50%样本区间已分开；下面3项仍有重叠，列为“差异不明确”。中位数降低不等于已证明跨次运行稳定加速。

| 尺寸／类型 | 稳定版中位数，微秒 | 当前中位数，微秒 | 对稳定版加速比 | 原始分布及顺序图 |
| --- | ---: | ---: | ---: | --- |
| 65540 z2d | 81.119999 | 75.600002 | 1.073016 | [查看](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65540_z2d_1d.svg) |
| 507378 d2z | 278.638989 | 273.839995 | 1.017525 | [查看](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/507378_d2z_1d.svg) |
| 776406 d2z | 516.479522 | 513.679504 | 1.005451 | [查看](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/776406_d2z_1d.svg) |

33项其他对照按中位数方向计为12项更快、5项相等、16项更慢。其中32项的中间50%样本区间重叠，多个小尺寸的测量前半段和后半段明显换档，暂不能据本次数据确认系统退化或其原因。

需要单列的对照是1837462 d2z：稳定版293.759495微秒、当前297.120005微秒，加速比0.988690，耗时增加1.14%，中间50%样本区间分开。该项没有进入新增卷积前后处理融合，后续查因应检查其实际旧路径及执行顺序，不能直接归因于新边界内核。

[1837462 d2z原始图](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/1837462_d2z_1d.svg)

稳定版在117652、131070、262138、262142、524286的z2z诊断仍失败；当前版全部通过。这是此前已确认并修复的继承缺陷，五项旧库结果只保留作诊断，未混入73项正式性能比较。

卷积阶段已完成正确性及本次性能测量，保留为已验证候选。稳定分支、标签和安装未更新；转置路径尚待下一阶段。本次仅检查、分析并保存记录，未重新测量或提交新任务。

完整比较如下。各耗时为微秒，全部来自本次逐次样本中位数；点击尺寸／类型查看该组合的三版本散点及测量顺序。

| 尺寸／类型 | 官方中位数 | 稳定版中位数 | 当前中位数 | 对稳定版加速比 | 对官方加速比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| [64K z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65536_z2z_1d.svg) | 28.000001 | 27.200000 | 27.360000 | 0.994152 | 1.023392 |
| [64K d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65536_d2z_1d.svg) | 29.920001 | 25.920000 | 25.920000 | 1.000000 | 1.154321 |
| [64K z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65536_z2d_1d.svg) | 30.080000 | 27.200000 | 27.200000 | 1.000000 | 1.105882 |
| [65538 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65538_z2z_1d.svg) | 113.760002 | 139.039993 | 140.160002 | 0.992009 | 0.811644 |
| [65538 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65538_d2z_1d.svg) | 78.079998 | 81.360001 | 76.320000 | 1.066038 | 1.023061 |
| [65538 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65538_z2d_1d.svg) | 79.760000 | 83.200000 | 76.800004 | 1.083333 | 1.038542 |
| [65540 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65540_d2z_1d.svg) | 80.799997 | 86.480003 | 76.480001 | 1.130753 | 1.056485 |
| [65540 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65540_z2d_1d.svg) | 77.119999 | 81.119999 | 75.600002 | 1.073016 | 1.020106 |
| [65610 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65610_d2z_1d.svg) | 41.439999 | 41.040000 | 37.760001 | 1.086864 | 1.097458 |
| [65610 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65610_z2d_1d.svg) | 39.680000 | 41.600000 | 39.039999 | 1.065574 | 1.016393 |
| [65824 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65824_d2z_1d.svg) | 36.880000 | 33.280000 | 33.280000 | 1.000000 | 1.108173 |
| [65824 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/65824_z2d_1d.svg) | 35.839999 | 36.720000 | 34.880001 | 1.052752 | 1.027523 |
| [67914 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/67914_d2z_1d.svg) | 41.600000 | 38.880002 | 41.120000 | 0.945525 | 1.011673 |
| [67914 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/67914_z2d_1d.svg) | 41.919999 | 41.439999 | 41.439999 | 1.000000 | 1.011583 |
| [69972 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/69972_d2z_1d.svg) | 43.680001 | 40.640000 | 40.160000 | 1.011952 | 1.087649 |
| [69972 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/69972_z2d_1d.svg) | 45.040000 | 44.560000 | 41.919999 | 1.062977 | 1.074428 |
| [81920 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/81920_d2z_1d.svg) | 34.559999 | 29.440001 | 29.759999 | 0.989247 | 1.161290 |
| [81920 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/81920_z2d_1d.svg) | 33.199999 | 31.919500 | 32.159999 | 0.992522 | 1.032338 |
| [97682 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/97682_d2z_1d.svg) | 49.440000 | 38.720001 | 40.560000 | 0.954635 | 1.218935 |
| [97682 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/97682_z2d_1d.svg) | 40.320002 | 47.119999 | 47.440000 | 0.993255 | 0.849916 |
| [117652 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/117652_d2z_1d.svg) | 96.000001 | 89.120001 | 80.480002 | 1.107356 | 1.192843 |
| [117652 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/117652_z2d_1d.svg) | 92.160001 | 89.280002 | 81.280001 | 1.098425 | 1.133858 |
| [117654 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/117654_d2z_1d.svg) | 92.160001 | 87.360002 | 80.320001 | 1.087649 | 1.147410 |
| [117654 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/117654_z2d_1d.svg) | 92.799999 | 90.000000 | 82.079500 | 1.096498 | 1.130611 |
| [128K z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/131072_z2z_1d.svg) | 32.000002 | 29.920001 | 29.840000 | 1.002681 | 1.072386 |
| [128K d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/131072_d2z_1d.svg) | 31.280000 | 27.680000 | 27.680000 | 1.000000 | 1.130058 |
| [128K z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/131072_z2d_1d.svg) | 33.760000 | 27.439999 | 27.519999 | 0.997093 | 1.226744 |
| [166698 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/166698_d2z_1d.svg) | 43.760000 | 33.599999 | 33.760000 | 0.995261 | 1.296209 |
| [166698 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/166698_z2d_1d.svg) | 42.399999 | 35.840001 | 35.599999 | 1.006742 | 1.191011 |
| [201038 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/201038_d2z_1d.svg) | 157.279998 | 130.720004 | 126.800001 | 1.030915 | 1.240379 |
| [201038 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/201038_z2d_1d.svg) | 158.159502 | 132.479995 | 120.959997 | 1.095238 | 1.307536 |
| [201840 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/201840_d2z_1d.svg) | 154.719993 | 129.439995 | 120.320000 | 1.075798 | 1.285904 |
| [201840 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/201840_z2d_1d.svg) | 156.879999 | 130.400002 | 123.119999 | 1.059129 | 1.274204 |
| [256K z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/262144_z2z_1d.svg) | 43.839999 | 35.599999 | 37.839999 | 0.940803 | 1.158562 |
| [256K d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/262144_d2z_1d.svg) | 36.800001 | 33.119999 | 33.280000 | 0.995192 | 1.105769 |
| [256K z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/262144_z2d_1d.svg) | 37.200000 | 33.440001 | 31.600000 | 1.058228 | 1.177215 |
| [370546 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/370546_d2z_1d.svg) | 365.759999 | 303.519994 | 291.040003 | 1.042881 | 1.256734 |
| [370546 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/370546_z2d_1d.svg) | 364.959493 | 302.480012 | 288.719997 | 1.047659 | 1.264060 |
| [371288 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/371288_d2z_1d.svg) | 363.519996 | 297.919989 | 290.639997 | 1.025048 | 1.250757 |
| [371288 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/371288_z2d_1d.svg) | 366.399497 | 299.920008 | 286.159500 | 1.048087 | 1.280403 |
| [507378 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/507378_d2z_1d.svg) | 366.639510 | 278.638989 | 273.839995 | 1.017525 | 1.338882 |
| [507378 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/507378_z2d_1d.svg) | 369.359002 | 283.919498 | 269.520000 | 1.053426 | 1.370433 |
| [507752 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/507752_d2z_1d.svg) | 361.839488 | 278.400004 | 271.839499 | 1.024134 | 1.331078 |
| [507752 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/507752_z2d_1d.svg) | 367.199495 | 290.558994 | 269.600004 | 1.077741 | 1.362016 |
| [512K z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/524288_z2z_1d.svg) | 96.159000 | 64.639501 | 64.239997 | 1.006219 | 1.496871 |
| [512K d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/524288_d2z_1d.svg) | 48.319500 | 39.840002 | 41.999999 | 0.948571 | 1.150464 |
| [512K z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/524288_z2d_1d.svg) | 46.239998 | 42.240001 | 39.519999 | 1.068826 | 1.170040 |
| [559910 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/559910_d2z_1d.svg) | 692.798972 | 368.958995 | 354.878992 | 1.039676 | 1.952212 |
| [559910 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/559910_z2d_1d.svg) | 694.159001 | 378.959507 | 360.559002 | 1.051033 | 1.925230 |
| [560372 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/560372_d2z_1d.svg) | 696.639478 | 373.359501 | 365.119994 | 1.022567 | 1.907974 |
| [560372 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/560372_z2d_1d.svg) | 694.159001 | 379.679993 | 364.798993 | 1.040792 | 1.902853 |
| [681468 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/681468_d2z_1d.svg) | 697.519004 | 382.239014 | 379.678994 | 1.006743 | 1.837128 |
| [681468 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/681468_z2d_1d.svg) | 697.679996 | 390.639499 | 368.879512 | 1.058989 | 1.891349 |
| [681470 z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/681470_z2z_1d.svg) | 1328.158975 | 645.839989 | 640.159011 | 1.008874 | 2.074733 |
| [681470 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/681470_d2z_1d.svg) | 714.879483 | 388.799995 | 372.960001 | 1.042471 | 1.916773 |
| [681470 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/681470_z2d_1d.svg) | 697.919488 | 392.079487 | 362.879992 | 1.080466 | 1.923279 |
| [776406 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/776406_d2z_1d.svg) | 696.319520 | 516.479522 | 513.679504 | 1.005451 | 1.355552 |
| [776406 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/776406_z2d_1d.svg) | 699.040502 | 521.678984 | 500.079989 | 1.043191 | 1.397857 |
| [776688 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/776688_d2z_1d.svg) | 700.480014 | 521.599501 | 507.439524 | 1.027905 | 1.380421 |
| [776688 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/776688_z2d_1d.svg) | 696.239501 | 534.479499 | 497.839987 | 1.073597 | 1.398521 |
| [888202 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/888202_d2z_1d.svg) | 718.720019 | 528.239489 | 505.839497 | 1.044283 | 1.420846 |
| [888202 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/888202_z2d_1d.svg) | 701.678514 | 528.319508 | 499.199003 | 1.058334 | 1.405609 |
| [888376 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/888376_d2z_1d.svg) | 698.879004 | 532.079518 | 500.639975 | 1.062799 | 1.395971 |
| [888376 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/888376_z2d_1d.svg) | 702.239990 | 526.880026 | 497.198999 | 1.059696 | 1.412392 |
| [999996 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/999996_d2z_1d.svg) | 701.999009 | 525.119990 | 507.679999 | 1.034352 | 1.382759 |
| [999996 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/999996_z2d_1d.svg) | 701.119006 | 527.039498 | 499.199986 | 1.055768 | 1.404485 |
| [999998 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/999998_d2z_1d.svg) | 705.359489 | 535.679996 | 504.559517 | 1.061679 | 1.397971 |
| [999998 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/999998_z2d_1d.svg) | 721.999496 | 527.278990 | 497.358993 | 1.060158 | 1.451667 |
| [1M z2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/1048576_z2z_1d.svg) | 182.239994 | 118.319999 | 118.479501 | 0.998654 | 1.538156 |
| [1M d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/1048576_d2z_1d.svg) | 113.279998 | 72.159998 | 71.840003 | 1.004454 | 1.576837 |
| [1M z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/1048576_z2d_1d.svg) | 114.079997 | 74.560001 | 74.640002 | 0.998928 | 1.528403 |
| [1837462 d2z](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/1837462_d2z_1d.svg) | 295.119509 | 293.759495 | 297.120005 | 0.988690 | 0.993267 |
| [1837462 z2d](/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013/plots/1837462_z2d_1d.svg) | 296.160012 | 295.199990 | 295.919999 | 0.997567 | 1.000811 |

服务器原始目录：

/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-build-20261013

/public/home/zhangkewei/zr/experiments/EXP-127/runs/EXP-127-blue-scopefix-performance-20261013

校验依据及原始样本索引保存在本地检查目录review-914128-914129；本文件旁的73份原始图与服务器文件逐字一致。
