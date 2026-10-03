# 旧路径退役与历史程序适配说明

日期：2026-10-03。用户选择顶层整洁、保留历史原件、日后按需适配。
本轮只移除五个顶层符号链接并记录适配方法；未改写旧程序、旧脚本或原始数据，未编译、未运行 GPU 测试。

## 路径映射

移除的是符号链接，实际目录没有删除。以后不要默认重新创建顶层链接。

| 已退役旧路径 | 仍保留的真实目录 |
| --- | --- |
| `/public/home/zhangkewei/zr/exp-078-sbrc-two-tier` | `/public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier` |
| `/public/home/zhangkewei/zr/exp119-stage1-install-clean` | `/public/home/zhangkewei/zr/experiments/EXP-119/artifacts/install/exp119-stage1-install-clean` |
| `/public/home/zhangkewei/zr/exp122-A-install` | `/public/home/zhangkewei/zr/experiments/EXP-122/artifacts/install/exp122-A-install` |
| `/public/home/zhangkewei/zr/install-exp090-candidate` | `/public/home/zhangkewei/zr/experiments/EXP-090/artifacts/install/install-exp090-candidate` |
| `/public/home/zhangkewei/zr/install-exp096-official` | `/public/home/zhangkewei/zr/experiments/EXP-096/artifacts/install/install-exp096-official` |

日常新实验使用顶层 main/EXP-NNN 分支、manage.py 和当前配置。归档 worktree 是不可变历史快照，不能直接在里面开展新实验或自动修改原件。
旧记录中的路径和旧 JSON 的 input_dir/files 原样保留；它们是原始来源信息。读取时按本表映射旧前缀，不必更改历史数据本身。

## 已确认需要适配的旧测量程序

以下四个 ELF 程序的 RUNPATH 写死旧安装路径；这里只检查了加载元数据，没有启动程序。

| 保留的原程序 | 原库目录 | 未来应指定的实际库目录 |
| --- | --- | --- |
| `/public/home/zhangkewei/zr/archives/worktrees/exp-123-cufft-format-benchmark/exp123_rocfft_csv/bin/fft_test_1d` | `/public/home/zhangkewei/zr/exp122-A-install/lib` | `/public/home/zhangkewei/zr/experiments/EXP-122/artifacts/install/exp122-A-install/lib` |
| `/public/home/zhangkewei/zr/archives/worktrees/exp-123-cufft-format-benchmark/exp123_rocfft_csv/bin/fft_test_1d_baseline` | `/public/home/zhangkewei/zr/exp119-stage1-install-clean/lib` | `/public/home/zhangkewei/zr/experiments/EXP-119/artifacts/install/exp119-stage1-install-clean/lib` |
| `/public/home/zhangkewei/zr/archives/worktrees/exp-123-cufft-format-benchmark/exp123_rocfft_csv/bin/fft_test_1d_official` | `/public/home/zhangkewei/zr/install-exp096-official/lib` | `/public/home/zhangkewei/zr/experiments/EXP-096/artifacts/install/install-exp096-official/lib` |
| `/public/home/zhangkewei/zr/archives/worktrees/exp-123-cufft-format-benchmark/exp123_rocfft_csv/bin/fft_test_1d_retest` | `/public/home/zhangkewei/zr/install-exp096-official/lib` | `/public/home/zhangkewei/zr/experiments/EXP-096/artifacts/install/install-exp096-official/lib` |

`fft_test_1d_baseline` 中的 baseline 指当时 EXP-119 的对照，不等于当前 previous 或 EXP-091 历史基线。
EXP-122 实际安装目前是 approved previous；EXP-096 实际安装目前是官方对照。EXP-119 只是历史环境，不能因名称或旧程序用途自动成为新实验对照。

## 未来复用时的步骤

1. 明确是复现历史实验，还是进行新的正式测量；明确程序、源提交、库身份和要保留的计时定义。
2. 保持历史原件不变，将需要适配的脚本或源码复制到新实验的独立目录；保存原件校验值、改动差异和实际来源。
3. 按上述映射核对安装、源码、输入、工作目录和输出目录。不要只替换 ROOT：旧 ROOT 曾同时承担源码、程序、日志和结果位置，归档位置和新运行输出位置现在应分别指定。
4. 在未来获得实际运行授权后核验 GPU/运行时、DTK/HIP/编译器和所有外部依赖。本轮没有读取或确认 zr 外的环境，旧脚本中的 DTK 路径只能视为历史信息。
5. 原二进制可尝试用明确的 LD_LIBRARY_PATH/LD_PRELOAD 指向本表的真实库；先验证实际加载库的路径、SHA256、API/ABI和来源。环境变量只覆盖此次调用，不修改用户全局环境。否则在新实验独立 artifacts 中重新构建；计时源码保持冻结原件，不为修复路径改变算法、正确性或计时参数。
6. 新输出、日志、原始 CSV、配置和来源信息写入新实验的 `experiments/EXP-NNN/runs/<run-id>/`。不覆盖归档结果，不在顶层生成杂项。
7. 运行前后核对库和源码身份、正确性以及测量合同。历史复现报告明确标注原定义；新正式测量遵循现行规程，不能把旧结果改写为新验收证据。

路径覆盖示意（仅记录供未来核验后使用，本轮未执行；不能据此认定 GPU 程序可用）：

```bash
ZR_ROOT=/public/home/zhangkewei/zr
INSTALL_DIR="$ZR_ROOT/experiments/EXP-122/artifacts/install/exp122-A-install"
OLD_BIN="$ZR_ROOT/archives/worktrees/exp-123-cufft-format-benchmark/exp123_rocfft_csv/bin/fft_test_1d"
# 核验实际 librocfft.so.0.1 与所选源/构建记录；保留运行时所需的其他搜索路径。
# 未来调用时使用以下环境覆盖，并在新的运行目录内执行明确的参数：
# LD_LIBRARY_PATH="$INSTALL_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# LD_PRELOAD="$INSTALL_DIR/lib/librocfft.so.0.1"
# 原 RUNPATH 不会因设置变量而被改写；必须另行证明最终加载的是预期库。
```

## 旧提交脚本

原件在 `/public/home/zhangkewei/zr/archives/worktrees/exp-123-cufft-format-benchmark/exp123_rocfft_csv/`：

- exp123_test.slurm：旧 ROOT、EXP-122 INSTALL、LD_LIBRARY_PATH 与 LD_PRELOAD。
- exp123_baseline_test.slurm：旧 ROOT、EXP-119 INSTALL、两个加载环境变量。
- exp123_official_baseline_test.slurm：旧 ROOT、官方 INSTALL、两个加载环境变量。
- exp123_outlier_retest.slurm：旧 ROOT、各版本安装路径、加载环境变量和旧复测聚合逻辑。

这些旧脚本设置 LD_PRELOAD，因此仅用环境变量在外部启动而不处理脚本内部赋值，并不能保证适配成功。
复制后逐项适配程序位置、安装路径、输出与日志位置、作业环境；提交前准备日志目录。
旧 outlier 复测方法只用于明确请求的历史复现；新的正式测量使用所有 16 个过程 mean_ms 的算术均值，不剔除异常值。
其他历史脚本和程序尚未逐项核验；日后复现时按相同步骤处理，不能据本清单认定全部旧程序已可运行。

## EXP-091 原始基线

这是已验证 EXP-090 优化版本在当时 DCU 环境上的固定历史测量结果，不是官方 ROCm 源码结果。
真实 runtime 源提交：0473680e99b181e4660643425f53382f3a6afad7；原安装为 EXP-090 candidate。
EXP-091 本身完成测量、诊断和分析，没有引入新的 kernel/planner 源码优化。

条件：double precision、z2z、batch=1、out-of-place；64K/128K/256K/512K。
作业 856749，hipprof --stats，-N 10000，每个规模五次独立进程；主结果是五次 canonical 时间的中位数。
canonical 使用 TotalDurationNs，扣除 bench 初始化额外内核后除以 N+1=10001；保留变换和 twiddle 时间。
这是旧 profiling GPU-kernel 指标，不能直接与现行 HIP 事件 mean_ms 相除比较。

| 规模 | 原始 canonical 中位数（ms） |
| --- | ---: |
| 64K | 0.017346298 |
| 128K | 0.019450103 |
| 256K | 0.023224602 |
| 512K | 0.051072366 |

原始基线资料真实位置：

- `/public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749/`：每规模 r1–r5 的原始 CSV/相关资料；共 20 个 hipkernel CSV。
- `/public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749.json`：逐次结果、均值/中位数/波动等原始汇总。
- `/public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749.txt`：文本汇总。

它放在 EXP-078 工作目录中，是当时实验沿用该工作目录形成的历史布局，不代表被测 runtime 是 EXP-078。
这些资料保留用于解释和复现旧实验。当前新实验的 official/previous 来自安装注册表，A100 另有固定原始参考，主测量按 docs/technical/FFT_MEASUREMENT_PROTOCOL.md 执行。

## 本轮审计

`.worktree-archives/top-level-compatibility-retirement-20261003/` 保存原链接目标、原文档、旧二进制/脚本校验值、基线与安装库的保护校验值及检查结果。
实际适配、编译和 GPU 运行均留到用户日后明确需要复用时。
