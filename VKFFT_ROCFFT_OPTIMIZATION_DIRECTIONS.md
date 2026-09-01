# rocFFT / VkFFT Kernel 优化持续实验记录

> 本文件是本任务唯一的持续实验记录。后续任何优化、编译、测试、回滚或结论，都必须在本文件末尾追加一个新的实验条目，或修改对应条目的“后续修订”部分；不得只在聊天中留下不可复现的结论。

## 0. 维护规则

每次新实验必须按以下字段记录：

1. 实验编号和日期。
2. 目标问题规模、变换类型、batch、GPU 架构和当前基线。
3. 假设：为什么这个改动可能有效，以及它对应 VkFFT 的哪个机制。
4. 修改文件、精确代码区域和启用条件。
5. 构建任务、正确性任务、benchmark 任务和 PMC 任务编号。
6. correctness 数值结果。
7. kernel 分解、端到端时间和资源计数。
8. 与基线的差值、是否保留，以及回滚原因。
9. 对 64K、128K、256K、512K 的可扩展性判断。
10. 下一步和未验证风险。

实验前必须保存当前 baseline；实验中一次只改变一个结构性因素；实验后必须先验证正确性，再比较性能。若实验回归，只回滚当前实验补丁，不覆盖用户已有的其它修改。

## 1. 任务背景和目标

目标是在 BW 卡（当前编译目标为 `gfx936`）上优化 double-complex、out-of-place、z2z FFT，重点是长度 512K、batch 1000，同时考察 64K、128K、256K 是否受益。当前 rocFFT 使用 RTC Stockham kernel，512K z2z 主要经过类似 TRTRT/CC 的分解，主要耗时 kernel 为：

- `fft_rtc_fwd_len_1024_factors_8_8_4_4_wgs_256_tpt_128_halfLds_dim_2_dp_op_CI_CI_sbcc_twdbase8_3step_dirReg`
- `fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned`

优化目标不是只寻找某组 WGS/TPT/radix 参数，而是借鉴 VkFFT 的 kernel 组织方式，减少 global-memory 往返、改善 LDS/register 数据复用、控制 bank conflict，并同时检查 VGPR、LDS、VALU、VMEM 和 occupancy。

## 2. 代码和实验环境

源码仓库：

`/public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2`

主要源码：

- `projects/rocfft/library/src/device/generator/stockham_gen_base.h`
- `projects/rocfft/library/src/device/generator/stockham_gen_cc.h`
- `projects/rocfft/library/src/device/generator/stockham_gen_rc.h`
- `projects/rocfft/library/src/device/kernels/configs/config_sbcc.py`
- `projects/rocfft/library/src/tree_node.cpp`
- `projects/rocfft/library/src/rocfft_kernel_config_search.cpp`

VkFFT 参考目录：

- `VkFFT/vkFFT/vkFFT/vkFFT_CodeGen/vkFFT_KernelsLevel1/vkFFT_RadixStage.h`
- `VkFFT/vkFFT/vkFFT/vkFFT_CodeGen/vkFFT_KernelsLevel1/vkFFT_RadixShuffle.h`
- `VkFFT/vkFFT/vkFFT/vkFFT_CodeGen/vkFFT_KernelsLevel1/vkFFT_RadixKernels.h`
- `VkFFT/vkFFT/vkFFT/vkFFT_CodeGen/vkFFT_KernelsLevel0/vkFFT_KernelStartEnd.h`
- `VkFFT/vkFFT/vkFFT/vkFFT_PlanManagement/vkFFT_HostFunctions/vkFFT_Scheduler.h`

构建和测试脚本：

- `build.slurm`：构建 rocFFT、hipFFT 并安装到 `/public/home/zhangkewei/zr/install`。
- `run_bench.sh LENGTH BATCH TYPE TAG`：使用 `hipprof --stats` 执行 10 次 benchmark。
- `validate_cc_length.slurm LENGTH`：编译并运行 z2z correctness 检查。
- `job.slurm`、`runall.sh`：批量测试入口。
- `pmc_*.slurm`：使用 `hipprof --pmc --pmc-type 3` 收集硬件计数器。

当前集群可用分区为 `hx1hdnormal01`。原实验脚本中的 `hx1hdexclu12` 已失效，`build.slurm`、`job.slurm`、`run_bench.sh` 和 `validate_cc_length.slurm` 已改为可用分区。该修改只恢复实验入口，不改变 FFT 算法。

## 3. 指标定义和判断方法

- `TotalDurationNs / Calls`：hipprof 统计的平均 kernel 时间。
- FFT 总时间：主要 SBCC 和 SBRC kernel 平均时间之和；不把随机数据生成 kernel 当作 FFT 优化收益。
- `VGPR`：每个线程使用的向量寄存器数量。VGPR 增加可能降低一个 CU 上同时驻留的 wave 数量。
- `SGPR`：标量寄存器数量。
- `LDS`：AMD GPU 的片上 local data share，也就是 rocFFT 代码中的 shared memory。LDS 访问按 bank 分布，冲突会让一个访问请求被拆成多次服务。
- `SQ_INSTS_VMEM_RD/WR`：global/flat memory 读写指令计数。
- `SQ_INSTS_LDS`：LDS 指令计数。
- `SQ_INSTS_VALU`：向量算术指令计数。
- `SQ_LDS_BANK_CONFLICT`：LDS bank conflict 计数。该指标降低不等于端到端时间必然降低，还要考虑地址计算、同步、occupancy 和其它 kernel。

判断原则：正确性是硬门槛；性能至少重复一次完整的 10-call benchmark，并尽量用第二次重复或 PMC 交叉验证。小于约 0.5% 的变化不能只用一次测量下结论。

## 4. VkFFT 和 rocFFT 的结构对照

VkFFT 的典型思路是：

`global memory -> LDS/register 重排 -> FFT -> LDS 内转置 -> large twiddle -> 下一阶段 FFT -> 写回`

rocFFT 也采用 Stockham/多步分解和 LDS/register 路径，并不是完全没有 4-step；区别在于不同 plan 可能在 kernel 之间写回 global memory，再由下一个 kernel 读取，特别是 TRTRT 路线。因而不能把 VkFFT 的完整 4-step 直接复制到 rocFFT，而应逐阶段比较：

- 哪些数据已经在寄存器中，能否避免再次进入 global memory。
- 哪些 twiddle 是线程私有的，哪些在一个 transform 或一个 wave 内相同。
- LDS 是否只承担当前阶段的 tile，能否在安全的生命周期内复用。
- barrier 是否确实需要 block 范围，是否可用 wave 范围同步。

VkFFT 的 `resolveBankConflictFirstStages` 通过地址重映射打散早期 LDS 访问；`registerBoost` 让一个线程处理多份数据；`setReadToRegisters` 根据问题形状选择 global-to-register 或经 LDS；`useCoalescedLUTUploadToSM` 让少量 stage twiddle 合并搬入 shared；分层 radix-8 通过较少 LUT 组和额外复数乘法换取更少的表读取。

rocFFT 已有 `dirReg`、half-LDS、large-twiddle 表和 Stockham 多步分解，所以借鉴重点是这些机制的决策条件和数据布局，而不是再发明同名抽象。

## 5. 历史工作总览

### 5.1 确认 512K z2z 的主要路径

通过 hipprof/kernel 名称和 PMC 确认，512K z2z 主要包含 1024 点 SBCC 和 512 点 SBRC kernel；早期版本走 TRTRT 时有多次 transpose/global-memory 往返。后来调整 TRTRT 与 CC 的适用阈值，使该场景可走 CC 路线，在 LDS 内完成更多重排和 large-twiddle 处理，减少全局访存。

这一步的原因是：512K 的问题不是单个 radix 蝶形太慢，而是多个阶段之间的 global memory 往返和 transpose launch 累积。该策略曾把 512K 总体加速比提高到约 `1.20x`，具体原始中间值应以当时保存的 benchmark 文件为准。

### 5.2 transpose padding：消除 bank conflict

修改 `rtc_transpose_gen.cpp` 中 LDS 二维数组的第二维，将：

```cpp
lds.size2D = Literal{specs.tileX};
```

改为带 padding 的布局，例如：

```cpp
lds.size2D = Literal{specs.tileX + 1};
```

原理是让原本 stride 等于 tile 宽度的线程访问不再周期性落入同一 bank。hipprof PMC 显示 transpose bank conflict 从约 `4.5e9` 降至 0，但端到端收益只有约 5%。

结论是 transpose 的 bank conflict 确实存在，但 512K 总时间主要由更大范围的 FFT/global-memory 行为决定；不能只围绕 conflict 计数继续优化。

### 5.3 transpose 与 SBRR/TR/RT 融合

利用 rocFFT 已有融合机制，调整 WGS/TPT，使一个 block 中的并发数量满足融合条件，将 transpose 与相邻 SBRR/RT 操作合并。512K 场景曾得到约 `1.11x` 加速。

该实验说明 launch 数量和中间 global store/load 可以显著影响结果，但融合不能无条件应用：512 融合有效，而 1024 融合曾导致 kernel 形态变差、总时间变长。因此后续必须按 kernel 形态和 occupancy 判断，不把融合当作普遍规则。

### 5.4 SBCC half-LDS

对 double precision SBCC 256/512/1024 启用 half-LDS。half-LDS 的含义不是把数据精度变成 half，而是通过分时处理实部/虚部或复数 tile，减少同时需要的 LDS 字节数，使更多 block/wave 有机会驻留；代价是处理轮数、同步和 LDS 访问可能增加。

当前保留的配置方向为：

| kernel | factors | 配置逻辑 |
|---|---|---|
| SBCC-256 | `[8,4,8]` | DP half-LDS，WGS 实际 256，TPT 32 |
| SBCC-512 | `[8,8,8]` | DP half-LDS，WGS 实际 256，TPT 64 |
| SBCC-1024 | `[8,8,4,4]` | DP half-LDS，WGS 256，TPT 128 |

配置文件中 `workgroup_size` 是 half-LDS 处理前的配置值，`list_large_kernels` 会使 DP kernel 的实际 WGS 发生变化，因此必须以生成 kernel 名称和 PMC 为准，而不是只看 Python 配置字面值。half-LDS 在 512K 以及部分较小规模上带来小幅收益，但不是所有长度都适合。

### 5.5 XOR LDS swizzle

在 `stockham_gen_base.h` 添加 `lds_address()`，对 DP half-LDS 的 512/1024 长度使用：

```text
length 512:  addr ^ (addr >> 4)
length 1024: addr ^ (addr >> 6)
```

该地址映射把连续的逻辑地址映射到更分散的物理 bank，目标是修复 Stockham group stride 与 bank 数之间的周期性冲突。它减少的是 SBCC/Stockham 内部 LDS 访问的冲突，不是 transpose kernel 的冲突；transpose 使用 padding，是两个不同位置的优化。

PMC 曾观察到 bank conflict 显著下降，结合 half-LDS 后整体相对早期 baseline 提升约 23.5%。但 XOR 会增加整数地址计算，且同一映射不一定适合所有 stage。因此后续要做 stage-aware swizzle，而不是对所有长度和所有 stage 无条件套用。

### 5.6 radix、寄存器和 LUT 递推

在 SBCC-1024 上把 radix-16 `[16,16,4]` 改成最大 radix 为 8 的 `[8,8,4,4]`，降低寄存器压力。历史测量中总时间从约 `54.07 ms` 降到 `49.45 ms`，说明较大 radix 的算术减少可能被 VGPR/occupancy 损失抵消。

在 large-twiddle 处理中使用递推：先取一个 `TW_NSteps` 结果，后续相邻输出用复数乘法推进，而不是每个输出都重新从 global LUT 取表。历史结果曾把 `49.45 ms` 进一步降到约 `44.73 ms`；该结果说明 LUT load 与表索引确实有开销，但递推增加 VALU 和寄存器，必须结合 radix、问题长度和 precision 评估。

在更小 z2z 规模上测试过 radix-16、radix-8 和 radix-4 相关配置；结果文件包括：

- `z2z_64k_b1000_lutradix16_*.csv.hipkernel.csv`
- `z2z_128k_b1000_lutradix16_*.csv.hipkernel.csv`
- `z2z_256k_b1000_lutradix16_*.csv.hipkernel.csv`
- `z2z_64k_b1000_radix8_exact_*.csv.hipkernel.csv`
- `z2z_128k_b1000_radix8_exact_*.csv.hipkernel.csv`
- `z2z_256k_b1000_radix8_exact_*.csv.hipkernel.csv`
- `z2z_64k_b1000_radix4_*.csv.hipkernel.csv`
- `z2z_128k_b1000_radix4_*.csv.hipkernel.csv`
- `z2z_256k_b1000_radix4_*.csv.hipkernel.csv`

这些实验的主要结论是：小长度可能能承受较大 radix，但收益不是单调的；应优先看 VGPR、kernel 资源和完整 FFT 时间，不能只看蝶形数量。

### 5.7 SBRC scalar-LDS

在 `stockham_gen_rc.h` 中对特定 DP SBRC-512 `[8,8,8]`、TPT=128、direct-to/from-register 路径启用内部 scalar-LDS。初始 SBRC transpose 仍需要完整 complex LDS；数据进入寄存器后，内部 Stockham exchange 可只按 scalar/real LDS 路径处理。

该修改的原因是减少内部 LDS 数据宽度和资源压力，同时不破坏最初的复数 transpose。它只在精确的长度、factors、TPT、precision 条件下启用，避免影响其它 real/complex kernel。

## 6. 当前源码中的保留修改

### 6.1 `stockham_gen_base.h`

当前保留 `lds_address()` 和两个 LDS load/store generator 调用点。只有 DP、half-LDS、length 512/1024 使用 XOR 映射，其它情况返回原始地址。

### 6.2 `stockham_gen_cc.h`

当前保留 large-twiddle recurrence，条件为 length 256/512/1024、最后一个 factor 为 4 或 8、单一 DP precision。核心逻辑：

1. 用 `TW_NSteps(large_twiddles, idx)` 得到当前线程的起始 twiddle。
2. 第一个寄存器直接乘该 twiddle。
3. 后续寄存器把当前 twiddle 与预先计算的步长 `t` 做复数乘法递推。

这改变的是同一线程处理的多个 large-twiddle 项，不是最近实验中失败的“跨线程共享 step”。

### 6.3 `stockham_gen_rc.h`

保留特定 SBRC-512 DP scalar-LDS 条件，初始复杂 LDS 和内部 scalar-LDS 生命周期分开处理。

### 6.4 `config_sbcc.py`

保留 SBCC 256/512/1024 的 DP half-LDS、runtime compile 和 factors 配置，当前 1024 使用 `[8,8,4,4]`，没有恢复 radix-16 默认路径。

## 7. 稳定 baseline

在恢复版构建 `737211` 后，512K、z2z、batch 1000 的 baseline 文件为：

`results/z2z_512k_b1000_baseline_current_20260818_104945.csv.hipkernel.csv`

主要结果：

| kernel | 平均时间 |
|---|---:|
| SBCC-1024 | `25.995145 ms` |
| SBRC-512 | `17.547460 ms` |
| 两个 FFT kernel 合计 | `43.542605 ms` |

随机输入生成 kernel 约 `218.796 ms`，不是 FFT 本身，应从 FFT 优化比较中单独排除。

baseline correctness：

```text
relative_l2  = 6.646073e-16
relative_max = 9.451432e-16
max_abs      = 3.551690e-12
```

最终恢复版构建 `750916`、correctness 任务 `750936` 再次得到同样的误差；恢复版 benchmark `750939` 的主要结果为 SBCC `26.021847 ms`、SBRC `17.551593 ms`，合计 `43.573440 ms`。与 `43.542605 ms` 的差异约 0.07%，属于节点/运行噪声范围，不能视为算法回归。

## 8. VkFFT 方向实验记录

### EXP-001：共享 large-twiddle recurrence step

日期：2026-08-18。

目标：512K z2z 的 SBCC-1024，WGS=256、TPT=128、DP、half-LDS。

假设：`trans_local` 对同一个 transform 内的线程相同，`TW_NSteps(large_twiddles, 256 * trans_local)` 是公共值。让每个 wave 的偶/奇 transform leader 读取一次，再用 `__shfl` 广播，可以减少重复的 large-twiddle LUT load。

修改：在 `stockham_gen_cc.h` 的 `large_twiddles_multiply()` 中，针对精确的 length 1024 / TPT 128 / WGS 256 条件，用：

```cpp
if((threadIdx.x & 63) == (threadIdx.x & 1))
    t = TW_NSteps(...);
t.x = __shfl(t.x, threadIdx.x & 1);
t.y = __shfl(t.y, threadIdx.x & 1);
```

没有改变其它长度和配置。

验证：构建 `750801`；correctness `750806`；benchmark `750807` 和重复 benchmark `750813`；PMC `750815`。

结果：correctness 通过。SBCC-1024 为 `26.046021--26.051301 ms`，比 baseline `25.995145 ms` 慢约 `0.20%`；两 FFT kernel 合计约 `43.599--43.602 ms`，比 baseline 慢约 `0.13%`。PMC 中 `VMEM_RD`、`VALU` 和 LDS 指令未出现目标性下降，说明主要表访问来自每线程的 `W` 项，而不是这个公共 step。新增 shuffle 和数据搬运抵消收益。

决策：回滚。该实验说明“公共 step”不是正确的共享粒度；后续要么共享实际被多个线程重复使用的 LUT 项，要么减少 LUT 项数量本身。

### EXP-002：ordinary-stage cooperative LUT cache

日期：2026-08-18。

目标：同一 512K SBCC-1024 `[8,8,4,4]` kernel 的第二个 radix-8 stage。VkFFT 在 `stageSize < warpSize` 且 LUT 足够小时使用 coalesced LUT upload；对 rocFFT 当前表布局，该 stage 访问前 56 个 DP complex twiddle，总计 896 B。

修改：

1. 在 kernel 起始处由前 56 个线程把 `twiddles[0..55]` 合并写入 LDS 尾部 `lds_complex[1024..1079]`。
2. 在 `apply_twiddle_generator()` 中，对 `cumheight == factors.front()` 的 stage 从该 LDS 区域读取。
3. 在 `tree_node.cpp` 中为精确 kernel 增加 `56 * sizeof(double complex) = 896 B` 动态 LDS。
4. 其它 stage、长度和 factors 仍使用原 global twiddle 读取。

验证：构建 `750857`；correctness `750871`；benchmark `750872`；PMC `750884`。

结果：correctness 通过。动态 LDS 从 `16384 B` 增至 `17280 B`；PMC 的 `VMEM_RD` 从 `31.744M` 降到 `24.832M`，证明目标 global load 被消除；但 LDS 指令增至 `105.728M`，bank conflict 略升，并新增一次 block barrier。SBCC-1024 为 `26.085001 ms`，两 FFT kernel 合计约 `43.629363 ms`，分别比 baseline 慢约 `0.35%` 和 `0.20%`。

决策：回滚。这个工作集足够小，GPU global/L0/L1 cache 已经能有效吸收重复读取；显式 LDS cache 把 cache hit 换成额外搬运、同步和 LDS 访问，不值得保留。

## 9. 已知结果文件和复现入口

最近实验结果：

- baseline：`results/z2z_512k_b1000_baseline_current_20260818_104945.csv.hipkernel.csv`
- EXP-001：`results/z2z_512k_b1000_twd_wave_broadcast_20260818_111151.csv.hipkernel.csv`
- EXP-001 repeat：`results/z2z_512k_b1000_twd_wave_broadcast_repeat_20260818_111338.csv.hipkernel.csv`
- EXP-002：`results/z2z_512k_b1000_ordinary_twd_cache_20260818_112921.csv.hipkernel.csv`
- EXP-002 PMC：`results/pmcall_524288_ordinary_twd_cache.csv.csv`
- 恢复版：`results/z2z_512k_b1000_restored_after_revert_20260818_113859.csv.hipkernel.csv`

复现命令：

```bash
cd /public/home/zhangkewei/zr
sbatch build.slurm
sbatch validate_cc_length.slurm 524288
sbatch run_bench.sh 524288 1000 0 <tag>
```

如需强制验证 RTC 生成源码，提交任务时设置：

```bash
--export=ALL,ROCFFT_RTC_CACHE_READ_DISABLE=1,ROCFFT_LAYER=32,ROCFFT_LOG_RTC_PATH=/public/home/zhangkewei/zr/results/<tag>.log
```

## 10. 下一步研究顺序

1. 分层 radix-8 twiddle：直接验证 VkFFT 用 3 组 twiddle 通过复数乘法组合 7 个 twiddle 的方案，先只对第二个 radix-8 stage 开启。必须比较 global load、VALU、VGPR 和误差。
2. stage-aware XOR：对 `[8,8,4,4]` 的早期 stage 使用 XOR，对后期 `stageSize=64/256` 使用线性 LDS，避免无条件地址映射。
3. wave-level synchronization：优先 SBCC-256 和 SBCC-512；SBCC-1024 TPT=128、SBRC-512 TPT=128 先保留 block barrier。
4. 用相同方法测试 256K、128K、64K，只有跨规模稳定或明确加长度条件时才合并到通用路径。
5. 最后才研究 32-bit offset；base pointer 保持 64-bit，只缩窄确认安全的局部 offset。

当前不继续推进：无约束的 WGS/TPT/radix 穷举、默认 radix-16、把整个 LUT 无条件搬到 LDS、或只凭 bank-conflict 计数决定保留方案。

## 11. 当前状态摘要

- 保留：CC 阈值调整、SBCC DP half-LDS、512/1024 XOR LDS 地址、large-twiddle 单线程递推、SBRC 特定 scalar-LDS、radix-8 为主的 1024 分解。
- 已验证但回滚：transpose padding 之外的无条件 transpose 方向、512K 的 large-twiddle wave broadcast、ordinary-stage 56 项 LDS cache。
- 当前安装目录已恢复到回滚后的源码状态，并通过 512K correctness。
- 后续实验必须从本文件的下一个 `EXP-xxx` 编号开始，补充结果后再决定是否修改“当前状态摘要”。

### EXP-003：radix-8 三基 twiddle 组合（已完成，回滚）

日期：2026-08-19。

目标：512K z2z、batch 1000 中的 1024 点 SBCC `[8,8,4,4]` kernel，限定第二个 radix-8 stage（`width=8`、`cumheight=8`；初始记录误写为 64）。同节点实验前 baseline 任务为 `755035`。

假设：该 stage 当前每个线程从普通 twiddle LUT 读取相位的 1--7 次幂，共 7 个 DP complex 表项。由于这些表项满足幂次关系，可只读取 1、2、4 次幂，再用 4 次复数乘法组合出 3、5、6、7 次幂。该方案对应 VkFFT 用分层/组合 twiddle 减少 LUT 项数量的思路，预期把目标 stage 的 global twiddle load 从 7 次降到 3 次；代价是增加 VALU 和少量临时寄存器。

计划修改：在 `stockham_gen_base.h` 的 `apply_twiddle_generator()` 中加入精确条件分支，只影响 length 1024、factors `[8,8,4,4]`、DP 的第二个 radix-8 stage；其它 stage、长度、precision 和 factor 组合保持原路径。

首次有效实现（修正后）：构建任务 `755090`；RTC/correctness 任务 `755112`；benchmark `755115`；PMC `755114`。RTC 生成源码确认第二个 radix-8 pass 已从 7 个表项改为读取 1、2、4 次幂并组合其余幂次。

correctness：`relative_l2=6.603230e-16`，`relative_max=9.756395e-16`，`max_abs=3.666290e-12`，通过。

性能：同节点 baseline `755035` 的 SBCC-1024 为 `26.016337 ms`、SBRC-512 为 `17.545433 ms`，合计 `43.561770 ms`；修正实验 `755115` 的 SBCC-1024 为 `26.643450 ms`、SBRC-512 为 `17.544153 ms`，合计 `44.187603 ms`。总 FFT 时间约回归 `1.44%`。

PMC（SBCC-1024，实验相对当前 XOR baseline 参考 `pmcall_524288_xor6_no256.csv.csv`）：`VGPR 68 -> 76`，`SQ_INSTS_VMEM_RD 31.744M -> 27.648M`，`SQ_INSTS_VALU 654.336M -> 670.720M`，`SQ_INSTS_LDS 98.304M -> 98.304M`，`SQ_LDS_BANK_CONFLICT 458.752M -> 458.752M`。目标 global LUT 读取减少约 12.9%，但额外复数乘法增加 VALU，并使 VGPR 上升 8，最终抵消并超过访存收益。

决策：回滚。该结构在当前 512K SBCC-1024 上不值得保留。首次错误条件 `cumheight == 64` 的任务 `755049/755064/755067/755070` 仅作为实现校正记录，不作为性能结论。对 64K/128K/256K 未做本轮修改后的验证，因此不能宣称可扩展；理论上更小规模若具有更低 VGPR 基线可能重新评估，但必须使用长度和资源条件，不能直接泛化。

后续修订：分层 twiddle 仍可研究，但下一版应避免同时保留 1、2、4 三个复数寄存器，优先考虑单线程已有递推状态、特殊角度常量或仅对更高 LUT 压力且 VGPR 余量足够的 kernel 启用；在没有新假设前不重新启用本补丁。

恢复稳定状态：回滚构建任务 `755136`，恢复版 correctness 任务 `755144`，结果为 `relative_l2=6.646073e-16`、`relative_max=9.451432e-16`、`max_abs=3.551690e-12`。远端源码已移除 EXP-003 新增的 W2/W4 和组合分支，安装目录恢复到实验前稳定状态。

实现校正：首次构建使用了错误的 `cumheight == 64` 条件。rocFFT 的 pass 循环传入的是当前 pass 之前的因子乘积，所以 `[8,8,4,4]` 的第二个 radix-8 pass 实际为 `width == 8 && cumheight == 8`；`cumheight == 64` 对应后续 radix-4 pass。首次任务 `755049/755064/755067/755070` 因此只验证了未命中的原路径，不能用于判断该优化收益。修正后重新构建和测试，任务编号另行补录。
### EXP-004：VkFFT 机制深度对照（分析阶段）

日期：2026-08-20。

目标：在不进行 WGS/TPT/radix 穷举的前提下，比较 VkFFT 与当前 rocFFT 生成器在数据驻留、寄存器读写、LDS 重排、large-twiddle 和同步粒度上的机制差异，确定下一项结构性实验。

#### 1. Read-to-register 对照结论

VkFFT 的 \`setReadToRegisters()\` 根据 read type、\`localSize\`、首个/末个 radix、每线程寄存器需求、FFT 维度和 Rader 情况决定是否直接 Global→Register；\`setWriteFromRegisters()\` 对输出采用对称判断。它不是简单的全局开关。

rocFFT 当前 \`stockham_gen_base.h\` 已经实现了对应的全局路径：

\`\`\`
direct_to_from_reg = true
    → direct_load_to_reg = true
    → Global → Register
    → FFT device function
    → Register → Global
\`\`\`

当内部 Stockham pass 需要跨线程重排时，生成器会根据 \`lds_is_real\` 选择 full-LDS 或 half-LDS，并在 pass 之间插入 LDS store/load 与同步。也就是说，当前 SBCC 已经具备“首尾直接寄存器、内部阶段使用 LDS”的基本结构，直接把 \`direct_load_to_reg\` 再打开不会形成新的优化。

本次源码对照依据：

- rocFFT：\`stockham_gen_base.h\` 的 \`set_direct_to_from_registers()\`、\`generate_global_function()\`、\`reg2lds_full/reg2lds_half\`；
- rocFFT：\`stockham_gen_cc.h\` 的 SBCC large-twiddle 与 LDS 配置；
- VkFFT：\`vkFFT_ReadWrite.h\` 的 \`setReadToRegisters()\` 和 \`setWriteFromRegisters()\`；
- VkFFT：\`vkFFT_RadixStage.h\` 对 \`readToRegisters\`、stage size 和寄存器容量的联合判断。

判断：不直接修改 \`direct_load_to_reg\`。若继续沿该方向，必须把判断下沉到“首个 stage 是否需要跨线程交换”这一层，并证明它能删除实际的 LDS 往返，而不是产生 Global→Register→LDS 的重复搬运。

#### 2. RegisterBoost 对照结论

VkFFT 的 \`registerBoost\` 不是单纯增加寄存器变量，而是让一个线程分批处理多组逻辑数据，并在每批之间执行必要的 Shared↔Register 重排和 barrier。其收益来自减少部分 launch 或增加局部数据复用，代价是 VGPR、同步和 occupancy 压力。

EXP-003 已经实验证明：减少 LUT global load 的同时，VGPR \`68→76\`、VALU 增加，最终总时间回归约 \`1.44%\`。因此当前 512K SBCC-1024 不适合直接扩大每线程长期保存的数据量。后续只能尝试局部、受限的 register boost，并且不得与多基 twiddle 组合同时启用。

#### 3. LDS tile 和 4-step 对照结论

VkFFT 的大规模 FFT 不要求把完整 N 点行或列一次性放入 LDS，而是将数据分成固定 tile，在 tile 生命周期内完成：

\`\`\`
Global load → LDS/register → 局部 FFT → LDS transpose → large twiddle
→ 下一局部 FFT → Global store
\`\`\`

rocFFT 当前 transpose 和 SBCC 已经使用 tile/LDS，但部分 TRTRT 路线仍会在阶段之间写回 Global，再由下一 kernel 重新读取。VkFFT 最值得借鉴的不是重新实现一个 tile transpose，而是延长已有 tile 的驻留周期，将 large-twiddle 和下一阶段局部 FFT 放在同一数据驻留周期中。

这是高收益但高风险方向，需要同时验证 tile 索引、LDS 布局、同步、twiddle 指数和不同长度的 correctness；暂不作为第一项代码实验。

#### 4. RadixShuffle、LUT 和同步粒度

VkFFT 会区分线程内 permutation、同一 wave 内交换和跨 wave 的 tile 交换：

- 线程内 permutation：优先寄存器重排；
- 同一 wave 的小范围交换：可考虑 wave shuffle/DPP；
- 跨 wave 或大 tile 转置：保留 LDS。

这说明 rocFFT 小 radix 的部分 LDS 访问可能存在被寄存器重排替代的空间，但必须先确认具体访问是否真的局限在同一 wave。当前 XOR swizzle 只能针对访问模式启用，不能替代这种层次化判断。

VkFFT 的 LUT 机制也不是简单地把整张 LUT 搬入 LDS，而是按 radix/stage 组织 LUT，并在满足复用和资源条件时协同上传。EXP-002 的整表 LDS cache 已经回归；后续应优先研究 stage-local LUT 或生命周期更短的复用方式。

#### 5. 后续实验顺序

在完成本分析记录后，后续只改变一个结构因素，按以下顺序推进：

1. 小 radix 的线程内寄存器重排，先检查 SBCC-256/512 生成代码中是否存在只为 permutation 而产生的 LDS 往返；
2. 若访问跨 wave，再尝试受限的 wave-level exchange，仅限 SBCC-256/512，SBCC-1024 和 SBRC-512 保留 block barrier；
3. 研究 large-twiddle 与 transpose tile 生命周期融合，优先针对 512K z2z；
4. 最后再评估有限 registerBoost。

每项实验必须先 correctness，再 benchmark，再 PMC；同时测试 512K，并用 256K、128K、64K 检查是否出现规模相关回归。若生成代码已经具备目标机制，则记录为“已存在/不构成新实验”，不重复修改。
### EXP-005：SBCC-256/512 的 wave-level synchronization（分析记录）

日期：2026-08-21。

分析结论：检查 stockham_gen_base.h 后确认，rocFFT 每个 Stockham pass 的 LDS store/load 不是单纯的线程内 permutation。写入地址由 tid / cumheight、tid % cumheight 和当前 radix 共同决定，用于改变下一 pass 的 Stockham 数据布局；因此不能直接删除这些 LDS 往返，也不能把它们简单改成寄存器交换。该项“线程内寄存器重排”方向对当前生成器不构成安全的通用优化。

可继续验证的 VkFFT 借鉴点是同步粒度。当前配置中：

- SBCC-256：workgroup_size=128、threads_per_transform=32，每个 transform 只占半个 wave；
- SBCC-512：workgroup_size=128、threads_per_transform=64，每个 transform 占一个 wave；
- block 内包含多个相互独立的 transform，目标 transform 的 LDS 地址由 transform offset 隔离。

假设：对于 DP、half-LDS、上述精确配置，Stockham 内部 LDS store→load 的同步可从 block-wide __syncthreads() 缩小为 wave-level __syncwarp()，从而减少 block barrier 的等待范围；SBCC-1024 和 SBRC-512 保留原 block barrier。该假设只有在 HIP/AMD 编译器确认 __syncwarp() 可用且具有 LDS 可见性语义时才成立。

实验边界：

- 只修改同步指令，不修改 WGS、TPT、radix、LDS 地址或 twiddle；
- 只作用于 DP 的 SBCC-256 [8,4,8] 和 SBCC-512 [8,8,8]；
- 先构建和 correctness，再 benchmark；若 RTC 编译器不支持 __syncwarp() 或 correctness 失败，立即回滚；
- 记录 512K 主场景以及 256K/128K/64K 的规模影响。512K z2z 主要使用 SBCC-1024/SBRC-512，因此该实验可能不会改变 512K 主路径，若如此应如实记录为“局部机制验证”，不宣称对主目标有效；
- PMC 重点观察 barrier、LDS 指令、VGPR 和 kernel 时间，而不是只看 bank conflict。



### EXP-005：SBCC-256/512 wave-level synchronization（已完成，回滚）

日期：2026-08-21。

实现：新增 SyncWaveThreads 生成节点，并在 DP、half-LDS、SBCC-256 [8,4,8] 与 SBCC-512 [8,8,8] 的实际运行时 WGS=256、TPT=32/64 条件下，将 Stockham 内部同步从 __syncthreads() 替换为 __syncwarp()。首次条件误写为 WGS=128，benchmark 未命中；修正后重新构建任务 759650，确认目标 kernel 实际命中 wave-sync 路径。

correctness：命中条件后的 256 点任务 759664，relative_l2=3.373793e-16、relative_max=5.234222e-16、max_abs=3.177644e-14；512 点任务 759665，relative_l2=3.589588e-16、relative_max=3.284774e-16、max_abs=3.362198e-14；均通过。512K 回归任务 759631 也通过，但主 512K z2z 路径不命中本实验条件。

A/B benchmark：wave-sync 256x256（759659）SBCC kernel 平均 1.867142 ms；block barrier 对照（759643）1.839125 ms，回归约 1.52%。wave-sync 512x512（759660）9.650830 ms；block barrier 对照（759644）9.422975 ms，回归约 2.42%。总 hipprof 时间分别约回归 0.09% 和 0.18%。

PMC 未继续提交，因为 correctness 虽通过，但 kernel 时间已稳定回归，且 wave-level 同步没有减少 LDS 指令或数据搬运。决策：回滚默认策略，恢复 __syncthreads()；保留分析记录，不把 __syncwarp() 作为默认生成路径。

### EXP-006：算法级候选方向（分析记录）

日期：2026-08-30。

本条目先记录公开资料和当前 rocFFT 代码对照得到的候选，不把尚未实测的方向写成优化结论。后续实测从 EXP-007 开始，每次只改变一个结构因素。

#### 公开资料与可借鉴机制

1. VkFFT 的公开 README 和代码（`vkFFT_KernelsLevel1/PrePostProcessing/vkFFT_4step.h`、`vkFFT_RadixShuffle.h`、`vkFFT_ReadWrite.h`、`vkFFT_RegisterBoost.h`）表明：大 FFT 使用固定大小的局部 tile；寄存器内先完成线程私有重排，同一 SIMD/wave 内才交换，跨 wave 才使用 shared/LDS；4-step 只在局部 tile 中转置和乘 twiddle，超过片上容量就增加分解层次，而不是把完整 N 放进 LDS。

2. TurboFFT（论文 `arXiv:2412.05824` 及其公开仓库）强调 architecture-aware global-memory coalescing、padding-free shared-memory layout、最后一级 FFT 的输出组织和模板化 kernel。对当前问题的直接启发是：不能只看 LDS bank-conflict 计数或 VMEM 指令数，还要看最终 global transaction、L2/TCC 命中、地址合并和 tile 的 producer/consumer 布局。

3. FFTc/MLIR（论文 `arXiv:2308.00497`）把 layout、permutation、vectorization 和 code generation 作为统一对象。对 rocFFT 的启发是：如果 producer 的输出布局能够直接满足 consumer 的输入布局，可以从计划层消除显式 transpose/global handoff；只在 kernel 内增加一个 transpose 并不等于实现了 4-step。

4. rocFFT 自身的 `stockham_pp_gen_cc.h` 已实现 3D partial-pass：在 global-to-LDS 和完整 FFT 之间执行另一个方向的部分 pass。它证明了“把相邻维度的部分工作放进同一 tile”在生成器中有基础，但目前 `factors_pp.size() > 1` 和 1D CC 的 SBCC/SBRC 组合还没有通用支持。

#### 候选方向和可证伪假设

1. **改变 Cooley-Tukey 分解边界**：512K 当前为 `SBCC-1024 + SBRC-512`，先做 `SBCC-2048 + SBRC-256`。数学上仍是同一个二维分解，但改变局部 radix 深度、LDS tile 形状、每线程寄存器驻留量、第二阶段列宽和 large-twiddle 的访问组织。这是最容易复用现有 CC/RC 框架的结构性实验，不是 WGS/TPT 穷举。

2. **1D partial-pass / producer-consumer tile**：参考 VkFFT 的 tile 生命周期和 rocFFT partial-pass，把 SBRC 的首个 radix pass 或 SBCC 的末个 radix pass 放到相邻 kernel 的 LDS 生命周期中，目标是减少一次完整 global intermediate。必须先解决跨 block 的 tile 依赖、Stockham 布局契约、barrier 范围和边界 tile；不能通过简单拼接两个 global kernel 实现。

3. **transform-major 的两层通信**：当前 rocFFT 的多个 transform 在一个 block 内交错，不能直接把 LDS 访问换成 wave shuffle。若重新组织为 transform-major，使一个 transform 的通信完全位于一个 wave，才有机会借鉴 VkFFT 的 shuffle/DPP；跨 wave 的列转置仍保留 LDS。EXP-005 已证明仅缩小 barrier 而不改变通信图会回归，因此后续必须同时改变数据布局才值得实现。

4. **large-twiddle 的基数/存储层次联合选择**：当前 FP64 512K SBCC 使用 `twdbase8_3step`，即 `TW_NSteps` 从 3 个 256 项子表合成大 twiddle；这已经是分解查表，但仍需比较 base-6 三步（更小表、更多地址位操作/不同 cache 行为）和 base-8 三步，重点观察 global load、L2/TCC 命中、VALU 和 VGPR，而不是仅按表大小判断。

5. **layout-aware final store**：参考 TurboFFT，检查 SBCC 最后一个 Stockham pass 的输出地址是否能直接匹配 SBRC 的下一阶段读取顺序，或者至少按 TCC transaction 重排线程写回。该方向只有在实际减少不合并 transaction 或中间布局转换时才成立；单纯改变线性索引属于参数/地址微调，优先级低于分解和 partial-pass。

6. **局部 32-bit offset**：参考 rocFFT 公开的 32-bit index 工作，只在 kernel 内把已证明不超过 32-bit 的 tile-local offset 缩窄，base pointer 和 batch/stride 仍保持 64-bit。目标是降低地址计算的寄存器压力；先做静态范围证明和编译资源对照，不能直接把所有 `size_t` 替换成 `unsigned int`。

#### 实验顺序与退出条件

先验证 2048x256；若生成器或资源限制使其不可行，保留源码不变并记录失败原因。之后依次单独验证 DP large-twiddle base-6、布局感知写回和 partial-pass 的最小原型。每个方向按 correctness -> 512K benchmark -> PMC -> 256K/128K/64K 扩展验证；若 512K 回归超过测量噪声或任一规模 correctness 失败，回退该条修改。无约束 WGS/TPT/radix 穷举、默认 radix-16、整表搬入 LDS 和无条件 tile fusion 不列入本轮实验。

### EXP-007：1D partial-pass 的 tile ownership 静态模型（已完成，未提交 kernel 原型）

日期：2026-09-01。

#### 1. 实验身份与边界

- 分支：`exp-007-partial-pass-ownership`。
- 实验前稳定源码：`1ea41d1977135f9525d140463e09da72fffc826e`（`rocfft-opt-pre-tile-lifetime`）。
- 本轮分析源码状态：`e5c705891e561b32457b611958206ea5ac173f5a`。该提交相对稳定源码只修正文档编码，rocFFT 源码相同。
- 实验前标签：`pre-exp-007-partial-pass-ownership-20260901`。
- 实验工件提交：`2bea0ff3f191fff9a4e1e47bc6ca37b7b5cfae11`（静态模型、完整 EXP-007 记录和 `agents.me`）。
- 目标：DP z2z、batch 1000、`-N 10`，长度 64K、128K、256K、512K；设备、profile 命令和 canonical 时间口径遵守 `agents.me`。
- 新增分析工具：`partial_pass_tile_ownership.py`。输入是实际 plan log 中的 length、stride、factor、WGS、`trans_per_block` 和 GridParams，不从 kernel 名称反推配置。
- rocFFT kernel、planner 和 generator 均未修改，因此本轮不产生新的可执行优化，也不把任何计时差异归因于 EXP-007。

本轮要回答的问题不是“两个 kernel 能否在语法上拼到一起”，而是：在不重复计算 producer、不依赖跨 workgroup 同步的前提下，现有 SBCC workgroup 输出的数据是否足以让某个现有 SBRC workgroup 继续完成至少一个 Stockham pass，并最终消除两者之间的 N 元素 global handoff。

#### 2. 中间布局与 ownership 定义

依据当前 `CC1DNode::AssignParams_internal()`，令 producer 长度为 `[K,M]`。SBCC 输出 stride 为 `[M,1]`，SBRC 输入的逻辑视图 stride 为 `[1,M]`。同一个物理元素可写成：

```text
producer: H_P[q,a]
consumer: H_C[a,q]
physical address = q*M + a
```

这里 `q in [0,K)`、`a in [0,M)`。因此转置是 producer/consumer 对同一物理矩阵的不同逻辑视图，并不是一个 producer tile 与一个 consumer tile 的一一重命名。

如果 plan 中 SBCC 的 `trans_per_block=P`，一个 producer workgroup 拥有 `K x P` 的竖条；如果 SBRC 的 `trans_per_block=C`，一个 consumer workgroup 需要 `C x M` 的横条。两者通常只在 `C x P` 的小矩形上相交。完整 ownership 关系如下：

| N | producer `[K,M]` | producer tile 数 | consumer tile 数 | producer-consumer 相交边数 |
|---:|---:|---:|---:|---:|
| 64K | `[256,256]` | 32 | 32 | 1,024 |
| 128K | `[256,512]` | 64 | 64 | 4,096 |
| 256K | `[512,512]` | 128 | 128 | 16,384 |
| 512K | `[1024,512]` | 128 | 256 | 32,768 |

四个规模都是 many-to-many Cartesian handoff：每个完整 consumer tile 依赖所有 producer tiles，每个 producer tile 的结果又会被所有 consumer tiles 分片使用。因此，简单地把“一个现有 SBCC workgroup”和“一个现有 SBRC workgroup”配成一个 fused workgroup，无法获得完整输入 ownership。

#### 3. Consumer-prefix 精确依赖

模型按 SBRC 的实际 Stockham factor 前缀枚举依赖，而不是假设首个 radix 消费相邻列。若 consumer 长度为 `M`，前缀 radix 乘积为 `S`，一个前缀 group 的输入列间距为 `M/S`。

512K 的 consumer 是 SBRC-512 `[8,8,8]`。首个 radix-8 group 实际读取：

```text
a = [0, 64, 128, 192, 256, 320, 384, 448]
```

这八列分别来自八个不同的 SBCC producer tiles，不是一个 tile 中的八个相邻 transform。四规模的首个 consumer pass 静态资源筛选为：

| N | 首个 prefix | owner 需计算的 producer transforms | 按当前 producer TPT 的 WGS | producer 输出 live set（complex/scalar） | 保留当前连续 producer 宽度时的 WGS |
|---:|---:|---:|---:|---:|---:|
| 64K | radix-4 | 4 | 128 | 16/8 KiB | 1,024 |
| 128K | radix-8 | 8 | 256 | 32/16 KiB | 2,048 |
| 256K | radix-8 | 8 | 512 | 64/32 KiB | 2,048 |
| 512K | radix-8 | 8 | 512 | 128/64 KiB | 2,048 |

表中的“WGS 可容纳”只是必要条件，不是可实现性或性能证明。尤其在 512K 中，WGS=512 的 owner 必须从八个相隔 64 列的 producer transforms 收集数据，破坏当前 SBCC 每个 block 连续处理四列的 ownership 和 global access 方式；若同时保留该连续宽度，则需要 32 个 producer transforms、估算 WGS=2048，超过当前 1024 的硬筛选上限。

更重要的是，执行首个 radix 后仍剩余 consumer factors。结果必须写到某个跨 workgroup 可见的位置，再由 continuation kernel 继续，所以 N 元素级 inter-kernel handoff 仍存在，只是中间状态的布局和边界发生变化。对当前“消除 SBCC→SBRC global store/load”的目标，移动一个不完整 prefix 不足以成立。

在“完整 producer 之后接 consumer prefix”的模型中，只有完成整个 consumer prefix 才能在同一个 owner 内结束第二维 FFT并真正消除当前 handoff。四规模对应的当前-TPT WGS 下界分别为 8192、16384、32768、32768；producer 输出 complex live set 分别为 1、2、4、8 MiB，均远超单 workgroup 的 WGS/LDS 资源范围。该结论否定的是“沿用当前完整 producer 计算和现有 workgroup 粒度的直接融合”，不是对所有新分解、跨 kernel partial-state 协议或不同 ownership 算法的普遍不可能性证明。

#### 4. 与历史 tile-lifetime 实现的区别

历史提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678` 已经遇到同一个 Cartesian ownership 问题。`logs/exp017_plan.log` 对 512K 明确记录：

```text
producer tiles per plane: 128
consumer tiles per plane: 256
producer tiles required per consumer tile: 128
cross-stage tile pairs: 32768
requires producer tile replication: true
```

该提交的 `rtc_stockham_gen.cpp` 在每个 `consumer_block_id` 内执行：

```text
for producer_tile_id in [0, producerTilesPerConsumerTile):
    remap producer_block_id
    rerun producer_global.body
```

因此每个 consumer workgroup 都重跑全部 128 个 producer tiles；256 个 consumer workgroups 共执行 32768 次 producer tile，而原计划每 batch 只执行 128 个 producer tiles。也就是每个原 producer tile 被不同 consumer owners 重算 256 次。它通过计算复制换取局部 handoff，不是非冗余的 partial-pass ownership，源码结构本身已经解释了该方向为何性能很差。

本轮模型与旧实现的实质区别是先建立 producer/consumer 的静态依赖图，并把“不允许 producer 重算”作为约束；它没有再次实现同一 fused loop。结果表明，在该约束下，现有 tile 粒度不能直接完成 handoff。

#### 5. rocFFT 现有 partial-pass 不能直接复用的原因

当前源码确实已有 `stockham_pp_gen_cc.h`、`stockham_pp_gen_rr.h` 和 `stockham_gen.cpp` 的 partial-pass 支持，但其调用来自 `tree_node_3D.cpp`。代码契约依赖 `parent_length`、off-dimension、两组 partial-pass factors 和成对 kernel；`stockham_pp_gen_cc.h` 还明确列出 `factors_pp.size() > 1` 尚待支持，并拒绝 x/z off-dimension。当前没有普通 1D `CC1DNode` 的 SBCC→SBRC ownership/continuation contract。因此，“rocFFT 已有 partial-pass”只能证明生成器有局部机制基础，不能证明当前 1D CC handoff 已经可用。

#### 6. 计划、任务和性能记录

plan/capture 任务均完成且退出码为 0：64K `797706`、128K `797711`、256K `797713`、512K `797716`。plan 原始记录：

```text
logs/exp007_plan_65536.log
logs/exp007_plan_131072.log
logs/exp007_plan_262144.log
logs/exp007_plan_524288.log
```

静态模型完整输出：`logs/exp007_ownership_model_final_20260901.log`。capture CSV 与 `agents.me` 的 fixed baseline 按同一公式计算：

| N | fixed baseline `T_compute_ms` | stable capture `T_compute_ms` | baseline/capture | 相对 baseline 改善 |
|---:|---:|---:|---:|---:|
| 64K | 3.732493091 | 3.635459818 | 1.026690784x | 2.599691% |
| 128K | 8.954852000 | 7.929874818 | 1.129255153x | 11.446054% |
| 256K | 19.360417545 | 18.148907182 | 1.066753902x | 6.257667% |
| 512K | 70.509517909 | 40.647207727 | 1.734670642x | 42.352169% |

capture 文件：

```text
results/z2z_64k_b1000_exp007_plan_64k_20260901_162327.csv.hipkernel.csv
results/z2z_128k_b1000_exp007_plan_128k_20260901_162435.csv.hipkernel.csv
results/z2z_256k_b1000_exp007_plan_256k_20260901_162516.csv.hipkernel.csv
results/z2z_512k_b1000_exp007_plan_512k_20260901_162556.csv.hipkernel.csv
```

这些 capture 测的是 EXP-007 开始前已经存在的稳定可执行版本。由于 EXP-007 没有修改可执行源码，`speedup_prev=1.000000x`、`improvement_prev=0.000000%` 是源码身份关系，不是一次新优化的实测收益；表中相对 fixed baseline 的差异属于此前保留优化和测量环境的综合结果，不能归因于静态 ownership 模型。

correctness：不适用。本轮没有新 kernel、planner、RTC 代码或安装产物，因而没有可与前一版本区别的 FFT correctness 对象；不冒充提交一次未改变二进制的 correctness 为新算法验证。静态工具已通过远端 `python3 -m py_compile partial_pass_tile_ownership.py`，四份 plan 均通过尺寸、stride、factor 乘积、grid block、WGS 和 `trans_per_block` 一致性检查。PMC：不适用，原因相同。

#### 7. 决策

1. **否定**“一个现有 SBCC producer tile 对一个现有 SBRC consumer tile”的简单融合；四个目标规模都有 many-to-many ownership。
2. **不再采用**历史实现中“一个 consumer owner 重算全部 producer tiles”的方案；它用 256 倍 producer tile 执行次数换取 512K 的局部 handoff。
3. **不把所有 partial-pass 算法判为无效**。改变 Cooley-Tukey 分解、输出 partial state、引入新的 continuation layout 或重新定义 tile owner，可能形成不同算法，但必须重新证明非冗余 ownership、global traffic 和资源上界。
4. 首个 consumer pass relocation 在四规模上通过单纯 WGS 筛选，但不能消除 N 元素 inter-kernel handoff，并会引入 strided producer ownership；除非后续先给出能减少总 global bytes/transactions 的新 continuation contract，否则不进入代码实现。

最终结论：EXP-007 是一次可证伪的结构筛选，不是性能优化。它关闭了“沿用现有 SBCC/SBRC workgroup 直接做 non-redundant partial-pass fusion”这条实现路径，同时保留对真正改变分解与 ownership 的算法设计空间。

### EXP-052：512K z2z 的 2048x256 Cooley-Tukey 边界（已完成，回滚）

日期：2026-09-01。

#### 实验身份

- 分支：`exp-052-cc-2048x256`。
- 起始提交：`e0e9e8e084d6ad24cab721eda60a9b09fb39fe24`；其 rocFFT 源码与当前有效源码 `1ea41d1977135f9525d140463e09da72fffc826e` 相同。
- 实验前标签：`pre-exp-052-cc-2048x256-20260901`。
- 实验源码提交：`6651a38b7e7e1075a0a52db7754d964a6f2b5492`。
- 前一有效版本 canonical 时间：64K `3.635459818 ms`、128K `7.929874818 ms`、256K `18.148907182 ms`、512K `40.647207727 ms`。这些值来自 EXP-007 对未改动稳定安装的标准 capture。
- 本轮使用编号 052，是因为 Git 历史中的旧主分支已经保存 EXP-001 至 EXP-051；不复用旧编号。

#### 假设与单变量设计

512K DP 当前使用 `SBCC-1024 + SBRC-512`。本轮改为 `SBCC-2048 + SBRC-256`，检验改变 Cooley-Tukey 分解边界能否改善两个 kernel 的计算/访存平衡。kernel 数量和 N 元素 global intermediate 不变，因此若有收益，应来自局部 FFT 深度、tile 形状、consumer 列宽、large-twiddle 地址分布或两个阶段负载平衡，而不是减少 launch 或 global 读写次数。

为避免把参数枚举混入结构实验，SBCC-2048 采用与稳定 SBCC-1024 等价的资源尺度：

```text
stable SBCC-1024: WGS=256, TPT=64,  TPB=4, 1024/64=16 complex/thread,
                  DP scalar half-LDS = 1024*4*8 = 32768 B
EXP-052 SBCC-2048: WGS=256, TPT=128, TPB=2, 2048/128=16 complex/thread,
                   DP scalar half-LDS = 2048*2*8 = 32768 B
```

新 factorization 固定为 `[8,8,8,4]`，只使用最大 radix-8；DP 保持 half-LDS、direct-to/from-register 和 base-8 large-twiddle 路径。producer 每 batch 的预计 workgroup 数仍为 `512/4 = 256/2 = 128`。不同时改变 XOR、recurrence、WGS=256 或其它已保留机制。

#### 源码修改

1. `library/src/node_factory.cpp`：把 double 512K 的 CC 分解项从 `{524288,1024}` 改为 `{524288,2048}`。
2. `library/src/device/kernels/configs/config_sbcc.py`：增加 DP SBCC-2048 `[8,8,8,4]`、基础 WGS=128、TPT=128、half-LDS、RTC 配置；large-kernel 生成过程对 DP half-LDS 将实际 WGS 扩为 256。
3. `agents.me` 的测量定义不变。

`config_sbcc.py` 已通过远端 `python3 -m py_compile`，两处源码通过 `git diff --check`。

#### 构建、plan 与 correctness

- 构建任务 `798018`，状态 `COMPLETED`、退出码 `0:0`，耗时 `00:05:30`；rocFFT 和 hipFFT 均成功安装。
- correctness/plan 任务 `798036`，状态 `COMPLETED`、退出码 `0:0`。
- plan 原始文件：`logs/exp052_plan_512k.log`。实际命中 SBCC-2048 `[8,8,8,4]`、WGS=256、TPB=2、32768 B LDS、base-8/3-step；SBRC-256 `[4,4,4,4]`、WGS=256、TPB=8、32768 B LDS。producer/consumer grid 分别为 128/256 blocks per batch，符合设计。
- correctness：`relative_l2=6.610588e-16`、`relative_max=1.056702e-15`、`max_abs=3.970911e-12`，通过。

#### 标准性能结果

主 benchmark 任务 `798038`：

```text
results/z2z_512k_b1000_exp052_cc2048x256_20260901_182158.csv.hipkernel.csv
T_compute_ms = 42.914154182
speedup_prev = 0.947174854x
improvement_prev = -5.577127%
speedup_baseline = 1.643036412x
improvement_baseline = 39.137076%
```

重复任务 `798042`：

```text
results/z2z_512k_b1000_exp052_cc2048x256_repeat_20260901_182416.csv.hipkernel.csv
T_compute_ms = 42.948510818
speedup_prev = 0.946417162x
improvement_prev = -5.661651%
```

两次结果一致，回归明显超过运行噪声。按每次 FFT 的 kernel `TotalDurationNs/11` 拆分：

| kernel stage | 前一有效版本 | EXP-052 | 变化 |
|---|---:|---:|---:|
| SBCC producer | 23.090815273 ms（1024） | 27.722818273 ms（2048） | +4.632003000 ms，+20.059937% |
| SBRC consumer | 17.553483364 ms（512） | 15.188485000 ms（256） | -2.364998364 ms，-13.473100% |

分解边界确实减轻了 consumer，但 producer 的额外局部 pass、地址/交换工作和更长 2048 点 tile 造成的代价更大，净增加约 `2.267005 ms`。当前证据不能把各微观来源进一步分离，但已足以否定该固定资源等价配置的整体收益。

#### 决策与回滚

决策：回滚。512K correctness 虽通过，但两次 canonical 性能均稳定回归约 5.6%。根据预先退出条件，不继续 PMC，也不运行 64K/128K/256K 性能任务；这三个规模的分解表未修改，新增 2048 配置不会被其 plan 使用，不能将未运行结果写成跨规模收益。

`node_factory.cpp` 的 512K 项已恢复为 `{524288,1024}`，并删除实验性 SBCC-2048 配置。失败源码提交保留在 `exp-052-cc-2048x256` 历史中；结果记录与源码回滚提交为 `0e809e7f5e70a431c4d8a51b5525829d5012265b`。后续 EXP-053 从有效源码重新建立，不继承本实验的 2048x256 改动。

### EXP-053：512K DP large-twiddle base-6 四步与 LDS LUT（已完成，回滚）

日期：2026-09-01。

#### 实验身份与前一版本

- 分支：`exp-053-large-twiddle-base6`。
- 起始提交：`e0e9e8e084d6ad24cab721eda60a9b09fb39fe24`；rocFFT 源码与有效提交 `1ea41d1977135f9525d140463e09da72fffc826e` 相同。
- 实验前标签：`pre-exp-053-large-twiddle-base6-20260901`。
- 前一有效 512K canonical 时间：`40.647207727 ms`，来自 `results/z2z_512k_b1000_exp007_plan_512k_20260901_162556.csv.hipkernel.csv`。
- fixed official 7.2.2 baseline：`70.509517909 ms`，来自 `agents.me` 指定的 512K baseline 文件。

#### 假设与实现校正

EXP-006 把候选简写成了“base-6 三步”，但源码和长度位数证明该说法不成立。512K 为 `2^19`，而 base-6 三步只能覆盖 `2^(6*3)=2^18=262144`；必须使用四步才能覆盖 19 位指数。当前 base-8 三步表为 `3*256=768` 个 DP complex（12288 B），base-6 四步表为 `4*64=256` 个 DP complex（4096 B）。

rocFFT 当前对 `largeTwdBase < 8` 的 SBCC 路径会由 workgroup 合并上传整个 large-twiddle 表到 LDS。因此本轮检验的是一个明确的基数/存储层次组合：用一次 256 项 cooperative upload 和 LDS 重用，替代后续 base-8 三表 global/L1/L2 读取；代价是每次 `TW_NSteps` 从两次复数乘法增加到三次，并且 SBCC-1024 动态 LDS 预计从 32768 B 增至 36864 B，可能把 LDS 限制的 block occupancy 从 2 降为 1。该资源风险是实验的核心权衡，不能只按 LUT 字节数预测收益。

#### 精确修改与作用域

1. `tree_node_1D.cpp::SBCCNode::KernelCheck()`：仅对 double precision、局部 length 1024、`large1D == 524288` 强制选择小 base 分解；其它 precision、局部长度和 large1D 保持 kernel 原配置。
2. `plan.cpp::get_large_twd_base_steps()`：允许 base 4/5/6 使用四步；base-8 的四步禁令不变。
3. `large_twiddles.h` 与 legacy/AOT `rocfft_butterfly_template.h` 的 `TW_NSteps()`：实现编译期 `Steps >= 4` 的第 4 组位提取和第 3 次复数乘法，继续拒绝 5 步以上分解，避免不同生成路径语义不一致。
4. `stockham_gen_cc.h`：LDS cooperative upload 项数从硬编码 `3*(1<<base)` 改为 `steps*(1<<base)`，防止四步时漏传第 4 个 64 项子表。
5. 不修改 WGS、TPT、Stockham factors、XOR、half-LDS、large-twiddle recurrence 或 SBRC；`agents.me` 的测试定义不变。

#### 验证计划与退出条件

先完整构建，再运行 512K correctness/plan。plan 必须命中 `twdbase6_4step`，large twiddle table length 必须为 256，动态 LDS 应为 36864 B；任一不符即停止性能结论并修正实现。correctness 通过后按 DP z2z、batch 1000、`-N 10`、`hipprof --stats` 测 512K，并至少重复一次。

若 512K 明确回归或 occupancy 降为 1 且无法由 LUT 流量收益抵消，则按预设退出条件回滚，不做 PMC 和小规模泛化。若有稳定收益，再收集 SBCC PMC 的 VMEM_RD、LDS、VALU、VGPR、LDS bytes/occupancy，并检查 64K/128K/256K；由于启用条件精确限制为 512K，这三个规模在本轮应保持源码路径不变，除非后续另建实验扩展条件。

#### 任务与结果

- 实验源码提交：`8c79f1c08b247ef87eeea23034f63d2fb850fcdf`。
- 构建任务：`798080`，`COMPLETED`、`0:0`。
- correctness/plan 任务：`798111`，`COMPLETED`、`0:0`；plan 为 `logs/exp053_plan_512k.log`。
- benchmark：`798115`；重复 benchmark：`798116`，均在 `a01r3n01` 完成。

correctness：`relative_l2=6.583685e-16`、`relative_max=9.756395e-16`、`max_abs=3.666290e-12`，通过。

plan 精确命中预期结构：

```text
SBCC-1024 [8,8,4,4], WGS=256, TPB=4
largeTwdBase=6, largeTwdSteps=4
large twiddle table length=256
dynamic LDS=36864 B
SBCC kernel occupancy=1（前一有效 base-8 路径为 2）
```

标准性能结果：

| run | raw CSV | canonical `T_compute_ms` | vs previous | vs fixed baseline |
|---|---|---:|---:|---:|
| `798115` | `results/z2z_512k_b1000_exp053_base6_4step_20260901_191919.csv.hipkernel.csv` | `51.053061909` | `0.796175708x`，`-25.600416%` | `1.381102627x`，`+27.594085%` |
| `798116` | `results/z2z_512k_b1000_exp053_base6_4step_repeat_20260901_191934.csv.hipkernel.csv` | `51.055912455` | `0.796131256x`，`-25.607429%` | `1.381025517x`，`+27.590042%` |

按每次 FFT 的主要 kernel 时间拆分：

| kernel | previous valid | EXP-053 first | EXP-053 repeat |
|---|---:|---:|---:|
| SBCC-1024 | `23.090815273 ms` | `33.504562182 ms` | `33.500867364 ms` |
| SBRC-512 | `17.553483364 ms` | `17.545721545 ms` | `17.552281455 ms` |

SBRC 保持噪声范围内不变；约 `10.41 ms` 的净回归全部来自 SBCC。base-6 四步虽然把 large-twiddle 表从 768 个 complex 缩到 256 个并改为 LDS 读取，但增加一次复数乘法，且额外 4096 B LDS 使 occupancy 从 2 降到 1，后者主导了性能。

#### 决策与回滚

决策：拒绝并回滚。两次结果稳定回归约 `25.6%`，明显超过噪声，证明该 base/LDS 组合不适合当前 32 KiB half-LDS 的 SBCC-1024。它只完成方向 5 的基数/存储层次诊断，不等同于“large twiddle 与 Stockham 阶段边界联合设计”。

按预设退出条件不做 PMC，也不运行 64K/128K/256K；启用 gate 仅匹配 512K DP，因此这些规模未改变路径，不能写成实测结果。后续若研究方向 5，必须在不把 SBCC LDS 推过双 block 驻留阈值的前提下复用已死亡的 LDS 区域，或移动 large-twiddle 所在阶段，而不是再次无条件追加 LUT LDS。

实验源提交保留在本分支历史；RTC/AOT 四步实现、planner gate 和动态上传项数均恢复到起始稳定源码。结果记录与源码回滚提交为 `8cb5ad915c9f5f805630e617798f48cc1b2dea9d`。

### EXP-054：two-tier register/LDS 的同一线程局部 Stockham 交换（已完成，跨规模待确认）

日期：2026-09-01。

实验前状态：分支 `exp-054-two-tier-register-lds`，起点为当前有效源码的回滚后状态；实验前标签为 `pre-exp-054-two-tier-register-lds-20260901`。安装目录在本实验前仍含 EXP-053 的失败安装产物，先由构建任务 `798133` 重建后再测量。

目标：验证 VkFFT 的“寄存器承担局部重排、LDS 只承担跨线程通信”能否在 rocFFT 的 Stockham 生成器中形成真实收益。该实验不是替换 barrier，也不是改变 WGS/TPT/radix 参数；只在 DP SBCC-1024、因素 `[8,8,4,4]`、TPT=64 的一个已证明同线程边界启用。

静态映射证明：pass 2 的 radix-4 store 对线程 `s`、局部行 `h`、列 `w` 写入 `j = h*256 + s + w*64`。pass 3 的 radix-4 load 对目标线程 `s`、行 `h2`、列 `w2` 读取 `j = s + h2*64 + w2*256`。两式相等时源寄存器为 `R[w2*4+h2]`，目标寄存器为 `R[h2*4+w2]`，因此每个线程只需对自己的 4x4 register tile 做转置，不需要跨线程交换。该证明只覆盖这个精确边界，不推广到其它 factors、TPT 或长度。

预期变化：删除 pass 2 的 register-to-LDS store、同步和 pass 3 的 LDS-to-register load、同步；保留 pass 1/2 之间的 LDS 通信和其它所有路径。由于当前目标使用 half-LDS，原来的 real/imag 两次 LDS 往返也由同一个 register 4x4 transpose 一并替代。用一个已有临时寄存器完成原地交换，观察 VGPR、LDS 指令、occupancy 和端到端时间。

退出条件：生成源码映射不符合上述索引，或 correctness 失败，立即回滚；correctness 通过但 SBCC/总时间稳定回归，则保留失败分支和证据并回滚，不向稳定分支合并。若有收益，必须再以相同机制检查 64K/128K/256K 的可证明局部边界后才可保留。

#### 实测收尾

- 实验源码提交：`3f5b6b56afbc1b911d913ce4d1d192d66a8c7778`，分支 `exp-054-two-tier-register-lds`。
- 构建任务：`798133`；正确性任务：`798187`；benchmark 任务：`798188`、重复任务 `798191`；PMC 任务：`798224`；RTC 源码任务：`798225`。
- correctness：`relative_l2=6.645150e-16`、`relative_max=9.451432e-16`、`max_abs=3.551690e-12`，通过。
- benchmark 原始文件：`results/z2z_512k_b1000_exp054_reglocal_20260901_200110.csv.hipkernel.csv` 和 `results/z2z_512k_b1000_exp054_reglocal_repeat_20260901_200143.csv.hipkernel.csv`。
- 按 `agents.me` 的 `TotalDurationNs` 公式，512K `T_compute_ms` 分别为 `39.513440909` 和 `39.517802636`。前一有效版本为 `40.647207727 ms`，对应 `speedup_prev=1.028693x/1.028580x`、改善 `2.789286%/2.778555%`；相对固定官方 baseline `70.509517909 ms`，对应 `speedup_baseline=1.784444x/1.784247x`、改善 `43.960132%/43.953946%`。
- 两次 CSV 的 kernel 结构均为 SBCC-1024 `tpt_64` 加 SBRC-512 `tpt_128`；实验相对前一版本只在 `stockham_gen_base.h` 删除目标边界的 register-LDS 往返并插入线程内 4×4 register transpose。
- PMC 文件为 `results/pmcall_524288_crosswave.csv`。实验计数记录为：SBCC `arch_vgpr=136`、`SQ_INSTS_LDS=65536000`、`SQ_INSTS_VALU=594944000`、`SQ_INSTS_VMEM_RD=26112000`、`SQ_INSTS_VMEM_WR=8192000`、`SQ_LDS_BANK_CONFLICT=196608000`；SBRC `arch_vgpr=64`、`SQ_INSTS_LDS=73728000`、`SQ_INSTS_VALU=540672000`、`SQ_INSTS_VMEM_RD=29696000`、`SQ_INSTS_VMEM_WR=8192000`、`SQ_LDS_BANK_CONFLICT=458752000`。历史对照使用 `tpt_128` kernel 名称，资源配置不同，故这里只作实验硬件计数存档，不宣称严格 PMC A/B 差值。

#### 决策

512K correctness 通过，且两次 benchmark 都改善约 2.8%，因此保留该实验分支作为候选；但按预先条件，尚未测 64K/128K/256K，尚不能合并到稳定分支或宣称跨规模有效。EXP-055 专门验证该局部映射在四个目标长度上的可扩展性，并同时记录静态否证的配置。
### EXP-055：two-tier register/LDS 的跨规模静态审计与验证（进行中）

日期：2026-09-01。

实验前状态：分支 `exp-055-two-tier-cross-scale`，起始提交 `9d6986ce`；该提交只包含 EXP-054 的文档收尾和已验证的 register-local 源码，源码安装产物沿用构建任务 `798133`。

目标：检查 EXP-054 的线程内 Stockham 交换是否能安全扩展到 64K、128K、256K 和 512K，并把“可证明的寄存器局部边界”与“仅因 factors 相似而猜测可复用”区分开。

静态条件：目标 kernel 分别为 SBCC-256 `[8,4,8]`/TPT=32、SBCC-256 `[8,8,8]`/TPT=32、SBCC-512 `[8,8,8]`/TPT=64、SBCC-1024 `[8,8,4,4]`/TPT=64。只有最后一项已有 store/load 索引等式证明；其它三项先输出索引关系和寄存器 tile 形状，不满足完整线程内置换时不得启用。

测试计划：四个长度各运行 DP z2z、batch=1000、`-N 10`、`hipprof --stats`，并各运行 correctness；保存 plan、raw CSV 和日志。性能以 `agents.me` 的 `TotalDurationNs` 公式同时比较 EXP-054 分支和固定官方 baseline。

退出条件：任一 correctness 失败立即停止并保留分支；若 64K/128K/256K 的源码路径未命中 EXP-054 gate，则将其记为静态否证/未扩展，不把未改动路径的差异归因于本实验。只有四规模均通过且没有稳定回归，才考虑把 gate 扩大。

本轮不改源码，只验证当前窄 gate 的跨规模行为；后续若要扩展其它 factors，必须另建实验并先给出寄存器到寄存器的地址双射证明。
### EXP-055：two-tier register/LDS 的跨规模静态审计与验证（已完成）

实验提交：`e4b9e519`（分支 `exp-055-two-tier-cross-scale`）；源码未再修改，验证对象是 EXP-054 提交 `3f5b6b56`。

四个 correctness 任务均完成：512K `798270`（`relative_l2=6.645150e-16`、`relative_max=9.451432e-16`、`max_abs=3.551690e-12`），128K `798273`（`6.358661e-16`、`8.085363e-16`、`1.482295e-12`），256K `798274`（`6.416370e-16`、`7.623083e-16`、`2.033692e-12`），64K `798275`（`6.717716e-16`、`1.114184e-15`、`1.277397e-12`）。

标准 benchmark 任务：64K `798271`，128K `798277`，256K `798272`，512K `798276`。原始 CSV 分别为：

- `results/z2z_64k_b1000_exp055_64k_20260901_204026.csv.hipkernel.csv`：`T_compute_ms=3.633526091`。
- `results/z2z_128k_b1000_exp055_128k_20260901_204055.csv.hipkernel.csv`：`T_compute_ms=7.932437818`。
- `results/z2z_256k_b1000_exp055_256k_20260901_204031.csv.hipkernel.csv`：`T_compute_ms=18.144264727`。
- `results/z2z_512k_b1000_exp055_512k_20260901_204048.csv.hipkernel.csv`：`T_compute_ms=39.479096727`。

相对 EXP-054/其前一有效结果 `3.635459818/7.929874818/18.148907182/39.513440909 ms`，四个长度的 speedup 分别为 `1.000532x/0.999677x/1.000256x/1.000870x`，改善分别为 `+0.053191%/-0.032321%/+0.025580%/+0.086918%`，均处于单次运行噪声量级。相对固定官方 baseline `3.732493091/8.954852000/19.360417545/70.509517909 ms`，speedup 分别为 `1.027237x/1.128890x/1.067027x/1.785996x`。

静态审计和 kernel 名称确认：64K、128K、256K 分别仍使用 SBCC-256 `[8,4,8]`/TPT=32、SBCC-256 `[8,4,8]`/TPT=32、SBCC-512 `[8,8,8]`/TPT=64，未命中 EXP-054 的 `[8,8,4,4]`/TPT=64 gate；512K 仍为 SBCC-1024 `[8,8,4,4]`/TPT=64。因而没有证据支持把 4×4 register transpose 无条件推广到其它 factors。

决策：EXP-054 的窄 gate 在四规模 correctness 下安全，512K 两次独立 benchmark 保持约 2.8% 改善，且其它规模没有可归因的回归。将 EXP-054 作为候选稳定修改保留；后续结构实验从合并后的稳定提交开始。
### EXP-056：layout-aware handoff / grouped-nearby transform（已完成，结构性否证）

日期：2026-09-01。

实验分支为 `EXP-056-layout-aware-handoff`，最终修复提交为
`fdf652451b32`。实验从 `0c10bb8866a3f8dccbf6e1a4c579f5b34e888743`
建立，目标是 DP z2z、batch=1000、`-N 10` 的 64K/128K/256K/512K。

静态模型 `logs/exp056_static_model.log` 的实际结论是：512K producer
为 SBCC-1024 `[8,8,4,4]`、WGS=256、TPB=4、TPT=64，consumer 为
SBRC-512 `[8,8,8]`、WGS=512、TPB=4、TPT=128；producer/consumer 是
many-to-many handoff，单个 consumer tile 依赖约 128 个 producer tile。
现有线性 handoff 已经保持 consumer 连续读取，因此仅改变中间物理地址
不会消除 global handoff。

源码原型在 `stockham_gen_cc.h` 和 `stockham_gen_rc.h` 中增加了一个
受限的 32x4 blocked 地址映射，并显式保持 producer 一次计算、没有复制
producer 或加入跨 workgroup 同步。初版的表达式渲染修复后仍不能形成可用
的通用 plan。

构建任务 `798399` 完成。修复版 correctness 任务为：

- 512K `798406`：FAILED，日志为 `rocfft_plan_create failed with rocFFT status 1`；
- 256K `798407`：FAILED，日志为 `rocfft_plan_create failed with rocFFT status 1`；
- 128K `798408`：FAILED，日志为 `rocfft_plan_create failed with rocFFT status 1`；
- 64K `798409`：通过，`relative_l2=6.717716e-16`、
  `relative_max=1.114184e-15`、`max_abs=1.277397e-12`。

对应 stdout/stderr 保存在 `logs/exp056v2_*_79840{6,7,8,9}.{out,err}`。
由于目标长度中三个 plan 创建失败，本实验没有合法的标准 benchmark
CSV，也不计算 ` T_compute_ms`、speedup 或加速比；64K 的 correctness
通过不能证明该映射对目标 512K 或其它规模成立。

决策：否定该布局原型并保留失败分支及日志。失败原因的唯一已证事实是
plan 创建阶段返回 status 1，不能把它进一步归因于某个未记录的 RTC
诊断。后续结构实验从稳定的 `0c10bb8866a3f8dccbf6e1a4c579f5b34e888743`
开始，不继承 EXP-056 的源码映射。

### EXP-057：复用已死亡 row-data LDS 的 late large-twiddle（计划）

日期：2026-09-01。

起始稳定提交：`0c10bb8866a3f8dccbf6e1a4c579f5b34e888743`。
目标只限 DP z2z、512K、SBCC-1024 `[8,8,4,4]`、WGS=256、TPT=64、
half-LDS、`largeTwdBase=8`、`largeTwdSteps=3`，不改变 factors/WGS/TPT。

代码事实：`stockham_gen_base.h::generate_global_function()` 当前在
kernel 开始调用 `large_twiddles_load()`；SBCC 的 `large_twiddles_multiply()`
在最终 Stockham pass 的 butterfly 之后执行。对于目标 kernel，最终
pass 已把所需数据读回寄存器，且 direct-register store 路径不再需要
row-data LDS。当前 half-LDS row-data 占用 32768 B；base-8/3-step 表为
768 个 double-complex 项，即 12288 B。现有实现把表放在 row-data 后面，
因此需要额外动态 LDS；EXP-053 已实测额外分配导致 occupancy 从 2 降到
1 并回归约 25.6%。

本实验假设：把 LUT 上传延迟到最终 pass 的 row-data 使用结束之后，
让 `large_twd_lds` 暂时别名 row-data LDS 起始区域；只在目标模板条件和
`direct_load_to_reg` 为真时选择该别名，其他 base、kernel 和非直接寄存器
路径保持原来的尾部 LDS/Global fallback。上传仍使用 block 内 cooperative
写入和两次 block barrier；不增加 LDS 分配，不复制 FFT 计算。

预定修改文件：

1. `device/generator/stockham_gen_base.h`：增加可选的 late-load 钩子或在
   final-pass large-twiddle 调用点插入它；
2. `device/generator/stockham_gen_cc.h`：目标 gate、block-local cooperative
   LUT upload、LUT 指针选择；
3. `tree_node.cpp`：目标 gate 下不再把 large-twiddle 表追加到动态 LDS。

验证顺序为 build → 512K correctness/plan → 标准 benchmark 至少两次 →
必要时 PMC。plan 必须仍显示 SBCC-1024、base-8/3-step、动态 LDS=32768 B，
且 RTC 源码必须同时确认 late upload 和 LDS LUT 读取。若 correctness 失败、
plan 不命中或时间回归超过测量噪声，保留分支和证据并回滚；只有稳定收益
才研究 64K/128K/256K 的独立 gate。

#### EXP-057 实测收尾

实验源码提交：`4cb4a9e216a6c13454dcd24b01c2836e17638770`，分支
`exp-057-late-large-twiddle`。实际只修改
`device/generator/stockham_gen_cc.h`：目标 SBCC-1024 的最终 Stockham
pass 之后，复用已经死亡的 row-data LDS 起始区域，协作上传 base-8、
3-step large-twiddle 表；没有增加动态 LDS 分配。

构建任务 `798544` 完成。正确性任务 `798548`、诊断任务 `798559` 均完成，
结果为 `relative_l2=6.645150e-16`、`relative_max=9.451432e-16`、
`max_abs=3.551690e-12`。诊断 plan 确认目标仍为 SBCC-1024 `[8,8,4,4]`、
WGS=256、TPT=64、half-LDS、dynamic LDS=32768 B；SBRC-512 保持原路径。
RTC 生成源码在 `logs/exp057_rtc_diag.log` 中确认了独立的 global LUT 上传源、
reused LDS pointer 和最终 pass 后的两次 block barrier。

标准 benchmark 任务 `798553` 和重复任务 `798565` 的原始 CSV 为：

- `results/z2z_512k_b1000_exp057_late_lds_20260901_225824.csv.hipkernel.csv`
- `results/z2z_512k_b1000_exp057_late_lds_repeat_20260901_230823.csv.hipkernel.csv`

按 `agents.me` 的 `TotalDurationNs` 公式，随机输入 kernel 已排除，
`N=10` 用 `11` 除：

| run | T_compute_ms | vs EXP-055 `39.479096727 ms` | vs fixed baseline `70.509517909 ms` |
|---|---:|---:|---:|
| `798553` | `39.081512727` | `1.010173199x`, `+1.007075%` | `1.804165525x`, `+44.572713%` |
| `798565` | `39.086885273` | `1.010034349x`, `+0.993466%` | `1.803917540x`, `+44.565094%` |

kernel 拆分显示收益集中在 SBCC-1024：首轮为 `21.531336727 ms`，重复为
`21.530016091 ms`；SBRC-512 分别为 `17.547426909 ms` 和
`17.554003727 ms`，处于测量波动范围。

PMC 文件为 `results/pmcall_524288_exp057_late_lds.csv`，对应的目标 kernel
计数（两次采样结构一致）为：SBCC `arch_vgpr=216`、
`SQ_INSTS_LDS=74752000`、`SQ_INSTS_VALU=601600000`、
`SQ_INSTS_VMEM_RD=20992000`、`SQ_INSTS_VMEM_WR=8192000`、
`SQ_LDS_BANK_CONFLICT=241876000`；SBRC 为 `64`、`73728000`、
`540672000`、`29696000`、`8192000`、`458752000`。与前一版 PMC
`results/pmcall_524288_crosswave.csv` 的同名 SBCC 对照为
VGPR `136 -> 216`、LDS `65536000 -> 74752000`、VALU
`594944000 -> 601600000`、VMEM read `26112000 -> 20992000`、
bank conflict `196608000 -> 241876000`。因此本实验的事实结论是：
减少 LUT global read 的收益被额外 LDS 访问、地址/同步开销和显著更高的
VGPR 部分抵消，端到端净收益约 1%，不能宣称是纯粹的访存优化。

决策：512K 上保留为候选实验提交；由于 gate 精确限制为 `[8,8,4,4]` 的
512K SBCC，64K/128K/256K 尚未改变源码路径，后续必须完成四规模 correctness
和 benchmark 才能合并到稳定分支或扩大 gate。下一实验从 EXP-058 开始。

#### EXP-057 跨规模验证收尾

64K、128K、256K correctness 任务分别为 `798608`、`798609`、`798610`，
均为 `COMPLETED 0:0`。结果依次为：`relative_l2=6.717716e-16 / 6.358661e-16 /
6.416370e-16`，`relative_max=1.114184e-15 / 8.085363e-16 / 7.623083e-16`，
`max_abs=1.277397e-12 / 1.482295e-12 / 2.033692e-12`。

标准 benchmark 任务为 64K `798611`、128K `798612`、256K `798613`：

| N | raw CSV | T_compute_ms | vs EXP-055 | vs fixed baseline |
|---:|---|---:|---:|---:|
| 64K | `results/z2z_64k_b1000_exp057_cross_64k_20260902_000228.csv.hipkernel.csv` | `3.635388091` | `0.999487813x`, `-0.051245%` | `1.026711041x`, `+2.601612%` |
| 128K | `results/z2z_128k_b1000_exp057_cross_128k_20260902_000228.csv.hipkernel.csv` | `7.929888000` | `1.000321545x`, `+0.032144%` | `1.129253276x`, `+11.445907%` |
| 256K | `results/z2z_256k_b1000_exp057_cross_256k_20260902_000228.csv.hipkernel.csv` | `18.145451000` | `0.999934624x`, `-0.006538%` | `1.066957087x`, `+6.275518%` |

三个规模仍使用各自原有 SBCC/SBRC kernel，均不满足 EXP-057 的
SBCC-1024 `[8,8,4,4]` 精确 gate。相对 EXP-055 的差异均小于 `0.052%`，
只能判为无旁路回归，不能归因于 late-LDS。至此 EXP-057 的四规模正确性和
标准性能验证完成；512K 的约 1% 收益可进入后续实验基线，但 gate 不扩大。

### EXP-060：SBCC-1024 wave-local LDS exchange 可行性验证（计划）

起始提交：`9218fe1e11570ce0d29ebad777873930fe5de278`，目标为 512K DP z2z、
batch=1000、`-N 10` 的 SBCC-1024 `[8,8,4,4]`、WGS=256、TPT=64。

VkFFT 的寄存器/SIMD exchange 只有在 source lane 和 destination lane 位于
同一 wave 时才可直接替代 LDS。当前 rocFFT 生成器的 pass-0 store/load 地址
由 Stockham 公式决定，并且 4 个 transform 交错分布在 256 个线程中。本实验
先用与生成器相同的地址公式枚举 source/destination lane，输出每个边界的
同 wave 比例和跨 wave 计数；再尝试一个只处理同 wave 子集的最小生成原型。

停止条件：若一个边界包含跨 wave 依赖，且剩余跨 wave 数据仍需完整 LDS
barrier，则 shuffle 不能消除该 LDS 往返；若混合路径增加分支/地址重排而无
法降低真实 LDS 指令，记录为代码级否证，不提交运行时 kernel。不能用
`__shfl` 替换整个边界，也不能改变 transform ownership。该实验的输出必须
包含静态映射日志；只有在存在完整同 wave 边界且可验证时才进入 build 和
correctness。

### EXP-061：1D partial-pass continuation 与 SBCC/SBRC handoff（计划）

起始提交：`e6d30d7769b1d1e4c85994e546ca776796a8e3fd`，目标是 512K DP z2z、
batch=1000、`-N 10`。本实验从实际 planner/tree 和 RTC generator 代码验证
“SBCC 最后一个 pass + SBRC 第一个 pass”是否存在非冗余的 1D continuation
契约。

检查重点是：1D `CC1DNode::BuildTree_internal` 是否能创建带 partial-pass
参数的子节点；partial-pass kernel 是否能直接消费前一 1D leaf 的输出；以及
在不复制 producer、不增加全局同步的前提下，是否能减少真实 global handoff。
如果现有 partial-pass API 只服务 3D/off-dimension 路径，或 1D ownership
仍要求一个 SBRC tile 读取多个 SBCC workgroups 的结果，则实现一个静态
ownership/byte-accounting probe，并把源码级否证作为结果，不修改普通 1D
planner。禁止重做此前会复制 producer 的完整 fusion。

#### EXP-061 实测/源码结果

探针脚本：`exp061_partial_pass_probe.py`；日志：
`logs/exp061_partial_pass_probe_20260902.log`。它直接读取当前
`tree_node_1D.cpp`、`tree_node.cpp`、`rtc_stockham_gen.cpp` 和记录的
`logs/exp007_plan_524288.log`，输出以下事实：普通 1D CC tree 创建
`CS_KERNEL_STOCKHAM_BLOCK_CC` 和 `CS_KERNEL_STOCKHAM_BLOCK_RC` 两个独立
leaf；512K producer 为 WGS=256、TPB=4、`[8,8,4,4]`，consumer 为
WGS=512、TPB=4、`[8,8,8]`。

因此每个 batch 有 `128` 个 producer tiles 和 `256` 个 consumer tiles，
一个 consumer tile 需要 `128` 个 producer tiles 的结果；中间 handoff
为 `524288` 个 DP complex、`8388608` bytes/batch。探针也确认 partial-pass
RTC generator 存在 `PPT_SBCC/PPT_SBRR` 分支，但 `tree_node.cpp` 的
partial-pass 参数检查只允许 off-dimension=1，x/z 路径显式抛出“不支持”；
普通 1D `CC1DNode::BuildTree_internal` 没有把这两个独立 leaf 改成 PP
producer/consumer 契约。

结论：在当前 planner/RTC 契约下，非冗余 1D partial-pass continuation
不能通过局部改一个 pass 实现。让一个 consumer workgroup 直接拥有完整
输入需要跨 `128` 个 producer tiles 的同步/共享状态；保持当前 ownership
则仍需 global handoff，复制 producer 则会重复计算。因此本轮不提交运行时
kernel，不进行伪 benchmark；EXP-061 作为源码级否证完成，后续若继续，
必须先设计新的 1D tile ownership 和 global layout，而不是复用现有 3D
partial-pass API。
