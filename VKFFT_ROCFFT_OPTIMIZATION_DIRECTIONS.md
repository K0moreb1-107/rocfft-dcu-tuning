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


<a id="historical-main-exp-006"></a>

### EXP-006：stage-aware read-to-register（已完成，回滚） [历史 main · 旧编号 EXP-006]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-006`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Date: 2026-08-21.

Goal: test whether VkFFT setReadToRegisters can remove an LDS round trip for the 512K z2z SBCC-1024 kernel.
Only the DP length=1024 factors=[8,8,4,4] SBCC entry was changed by setting direct_to_from_reg=False; WGS, TPT, radix, LDS addressing, and twiddles were unchanged.

Result: build 759721 and correctness task 759711 produced relative_l2=1.382328e+00, relative_max=1.439529e+00, max_abs=5.409508e+03. Correctness failed.

The option was removed and the default direct-reg path was restored; the restored path passed correctness.

Decision: revert. rocFFT direct_to_from_reg is a global path switch, not a stage-local read policy. Disabling it without a matching Stockham LDS layout breaks pass-to-pass data placement.

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


<a id="historical-main-exp-007"></a>

### EXP-007: limited registerBoost (completed, retained) [历史 main · 旧编号 EXP-007]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-007`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Date: 2026-08-21.

Goal: emulate VkFFT registerBoost by letting each thread process more logical data. Only SBCC-1024 threads_per_transform changed from 128 to 64; DP half-LDS actual WGS remained 256. EXP-003 multi-base twiddle was not enabled.

Build and correctness: build 759745; 512K correctness 759751; 256K, 128K, and 64K correctness also passed. The generated kernel was wgs_256_tpt_64_halfLds.

Performance versus the stable baseline (512K=43.542605 ms, 256K=18.695212 ms, 128K=8.217070 ms, 64K=3.715519 ms):

| size | EXP-007 FFT total | speedup |
|---|---:|---:|
| 512K | 40.682627 ms | 1.070x |
| 256K | 18.135222 ms | 1.031x |
| 128K | 7.921375 ms | 1.037x |
| 64K | 3.633847 ms | 1.022x |

At 512K SBCC-1024 improved from 25.995145 ms to 23.126766 ms; SBRC-512 stayed near 17.55 ms. PMC task 759760 could not start because hipprof lacked libperfetto.so.5, so no resource-counter conclusion is claimed.

Decision: retain only for the exact 1024-point DP half-LDS configuration. It passed correctness and improved all four tested sizes, but the gain decreased at smaller sizes and must not be generalized to every SBCC kernel.


<a id="historical-main-exp-008"></a>

### EXP-008: stage-aware XOR LDS mapping (completed, reverted) [历史 main · 旧编号 EXP-008]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-008`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Date: 2026-08-21.

Hypothesis: VkFFT changes LDS conflict handling by stage. The existing rocFFT XOR mapping was applied to every DP half-LDS access for length 512/1024. This experiment added a generated-pass state and enabled XOR only for early passes (stage <= 1); later passes used the linear LDS address. No WGS, TPT, radix, twiddle, or synchronization change was made.

Build 759796 and 512K correctness 759798 passed: relative_l2=6.644698e-16, relative_max=9.451432e-16, max_abs=3.551690e-12.

Benchmark results: 512K jobs 759800/759799 gave SBCC+SBRC=40.687127 ms versus EXP-007 40.682627 ms; 256K=18.137063 ms versus 18.135222 ms; 128K=7.926573 ms versus 7.921375 ms; 64K=3.632477 ms versus 3.633847 ms. The changes are neutral within noise and show no consistent gain.

Decision: revert. The stable source was restored and installed by build 759803; 512K correctness 759805 passed. The existing all-stage XOR mapping remains retained because it is the better measured configuration.


<a id="historical-main-exp-009"></a>

### EXP-009: small-radix register permutation (feasibility completed) [历史 main · 旧编号 EXP-009]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-009`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Date: 2026-08-21.

Generated-source inspection was used to test the VkFFT RadixShuffle idea. In the actual 1024-point SBCC [8,8,4,4] kernel, pass 0 stores R to LDS with tid/cumheight and tid%cumheight; the next pass reloads a different layout. Pass 1 and pass 2 repeat this cross-thread layout change before the radix-4 butterflies. The data needed by a later butterfly is therefore not confined to one thread's R array.

Conclusion: there is no safe local register-only permutation candidate in this kernel. Removing one LDS load/store without changing the ownership map would read a different transform element and fails the Stockham contract. This direction is not implemented as a fake bypass; a valid version would require a new cross-wave ownership layout and a correctness proof. No code change was retained.


<a id="historical-main-exp-010"></a>

### EXP-010: extend tile lifetime across large-twiddle and next FFT (mechanism completed) [历史 main · 旧编号 EXP-010]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-010`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Date: 2026-08-21.

The RTC source for the stable 1024-point SBCC kernel was inspected. It performs global load -> Stockham LDS/register passes -> final large-twiddle multiplication in registers -> global store. The following SBRC-512 kernel starts from the global buffer and has a separate launch. The source confirms the current CC kernel already fuses its local FFT and large-twiddle operation, but it does not keep the tile alive into the next SBRC kernel.

At 512K the current retained CC route is SBCC-1024 23.126766 ms plus SBRC-512 about 17.55 ms (EXP-007 total 40.682627 ms). Extending the tile across these kernels cannot be enabled in stockham_gen_cc.h alone: it needs a planner-level fused SBCC/SBRC kernel, shared LDS ownership, and a new launch interface. No unsafe partial fusion was retained.

Decision: the VkFFT mechanism is already partially present inside SBCC; the missing cross-kernel lifetime is a high-risk architectural change, not a parameter switch. The experiment is complete as a boundary/feasibility result.


<a id="historical-main-exp-011"></a>

### EXP-011: stage-local/coalesced ordinary LUT (completed via EXP-002, reverted) [历史 main · 旧编号 EXP-011]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-011`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Date: 2026-08-21.

EXP-002 already tested the VkFFT coalesced-LUT idea on the second radix-8 stage of SBCC-1024. It cooperatively uploaded the 56-entry, 896-byte stage-local ordinary twiddle working set to LDS and redirected only that stage's twiddle reads. Correctness passed, VMEM reads dropped from 31.744M to 24.832M, but LDS instructions increased to 105.728M and the SBCC-1024 time regressed from 25.995145 ms to 26.085001 ms.

Decision: revert. The working set is small enough for the GPU cache; explicit LDS staging replaces cache hits with LDS traffic and a barrier. This completes the stage-local LUT direction without retaining a regression.


<a id="historical-main-exp-012"></a>

### EXP-012: final stable installation verification [历史 main · 旧编号 EXP-012]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-012`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


Build 759803 restored the source after EXP-008. Correctness task 759805 passed. Final benchmark 759807 measured SBCC-1024=23.136096 ms and SBRC-512=17.566211 ms, total=40.702307 ms. The small difference from EXP-007 (40.682627 ms) is within run-to-run noise; the final kernel name confirms wgs_256_tpt_64_halfLds and no stage-aware code remains.

Final retained mechanisms: CC threshold selection, DP half-LDS, all-stage XOR LDS mapping for lengths 512/1024, single-thread large-twiddle recurrence, SBRC scalar-LDS, radix-8-oriented 1024 factorization, and the limited registerBoost configuration.


<a id="historical-main-exp-013"></a>

### EXP-013：planner 级 tile 生命周期契约扩展（已完成） [历史 main · 旧编号 EXP-013]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-013`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-22。

#### 原理

当前 SBCC kernel 已经在 kernel 内完成 FFT 与 large-twiddle 乘法，但最后仍然把 tile 写入 global memory，后续 SBRC kernel 再从 global memory 读取。要把这两个阶段真正融合，不能只修改 `stockham_gen_cc.h` 或调整某个 kernel 参数，因为 SBCC 与 SBRC 的 tile 轴、workgroup 归属和启动网格并不是简单的一一对应关系。

SBCC 的 tile 在 CC 转置后对应到 SBRC 的输入维度，两个阶段形成 Cartesian tile relation：一个 SBRC consumer tile 可能需要多个 SBCC producer tile；一个 producer tile 也可能被多个 consumer workgroup 使用。因此 planner 必须先给出 tile 映射、fan-in/fan-out、workgroup ownership 和 LDS 预算，后续 fused generator 与 launch path 才能据此生成安全的跨阶段生命周期。

#### 做了什么

在 `TileLifetimeDescriptor` 和 `ExecPlan::tileLifetimeContracts` 的基础上，补充了 fused launch 所需的候选布局和资源约束。planner 现在能够描述：一个 fused workgroup 负责多少个 producer tile、消费多少个 consumer tile、需要多少个 workgroup，以及 producer tile 是否需要跨 workgroup 复用或复制。

同时保留了现有 global handoff 作为运行时路径。新增信息目前只用于 planner 分析和 plan dump，不会在没有 fused generator 和 launch contract 的情况下启用不安全的融合。

#### 修改内容

1. 在 `/public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/include/tree_node.h` 的 `TileLifetimeDescriptor` 中增加：

   - `fusedProducerTilesPerWorkgroup`
   - `fusedConsumerTilesPerWorkgroup`
   - `fusedWorkgroupCount`
   - `fusedResidentLdsBytes`
   - `fusedResidentLdsFitsDevice`
   - `requiresCrossWorkgroupTileReuse`
   - `requiresProducerTileReplication`

2. 在 `/public/home/zhangkewei/zr/rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/plan.cpp` 中增加 `GridWorkgroupCount()`，并在 `AnalyzeTileLifetimes()` 中计算候选 fused launch：

   - 一个 fused workgroup 暂按一个 consumer tile 建模；
   - `fusedProducerTilesPerWorkgroup` 等于每个 consumer tile 所需的 producer tile 数；
   - fused workgroup 数取 consumer grid 的 `b_x * b_y * b_z`；
   - 当一个 producer tile 覆盖多个 consumer tile 时，标记跨 workgroup 复用和 producer replication；
   - 按 `producer_lds_bytes * producer_tiles_per_consumer + consumer_lds_bytes` 做保守 resident LDS 预算；
   - 增加 `size_t` 溢出保护，并与设备 `sharedMemPerBlock` 比较；
   - ownership 匹配条件补充 producer/consumer `wgs_x` 一致性检查；
   - 在 plan dump 中输出上述 contract 字段。

#### 效果与边界

对于已分析的 512K 配置，planner 可以表达 SBCC TPB=64、SBRC TPB=128、每个 plane 各 8 个 tile、fan-in=8、fan-out=8、跨阶段 tile pair count=64 的映射关系。当前状态仍为 `TILE_MAPPING_AVAILABLE_BUT_FUSED_KERNEL_UNAVAILABLE`，说明映射已经可描述，但 fused kernel 尚不存在。

这次修改没有删除或绕过 SBCC 与 SBRC 之间的 global store/load，没有改变现有 kernel 的运行时行为，也没有声称已经完成性能融合。真正融合仍需要新的 fused compute scheme、SBCC+SBRC 联合 generator、LDS/register ownership layout、function-pool entry 和 fused launch contract。

验证结果：`git diff --check` 通过；远端 `cmake --build ../../../build/rocfft_build --target rocfft -j 8` 通过，最终输出为 `[100%] Built target rocfft`。构建过程中仍有仓库原有 warning，以及环境中的 `llvm-ar: command not found`，但没有出现新增 planner 代码的编译错误。新 build 的 DCU 运行验证仍受到 RTC cache 初始化阶段 `std::bad_alloc` 的环境问题阻断，因此本次效果结论限定为 planner contract 完整性和编译验证。

#### 后续记录约定

从本条之后，每次进行源码修改、实验、构建、验证或回滚，都在本文件末尾追加新的 `EXP-xxx` 条目，并明确记录：原理、做了什么、修改了什么、验证结果、性能或正确性效果，以及是否保留该修改。



<a id="historical-main-exp-014"></a>

### EXP-014：SBCC→SBRC streaming 融合条件诊断 [历史 main · 旧编号 EXP-014]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-014`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-22。

#### 原理

planner 级 tile 生命周期融合必须同时满足 tile 映射、workgroup ownership、LDS 预算、producer/consumer ABI 以及 large-twiddle 生命周期条件。仅凭 planner 已经发现 producer output 与 consumer input 使用同一临时 buffer，不能说明 fused node 可以安全创建；因此先对每个拒绝条件进行运行时观测，不改变原有双 kernel 路径。

`largeTwdBase` 与 `ltwdSteps` 需要联合解释：`base` 只是 large-twiddle 表的分解基数，只有 `steps > 0` 时才代表该节点实际启用了 large-twiddle 计算。RTC generator 也使用 `largeTwdBase > 0 && ltwdSteps > 0` 作为启用条件，不能把 `base=8, steps=0` 当成有效的 large-twiddle fused contract。

#### 做了什么

在 `CCSBRCFuseShim::FuseKernels()` 中增加可选运行时诊断，使用环境变量 `ROCFFT_DEBUG_SBCC_SBRC_FUSION=1` 输出：

- strict 与 streaming 两种 schedule 是否满足条件；
- tile ownership、tile mapping、edge tile 完整性；
- resident/streaming LDS 字节数及设备适配结果；
- producer/consumer direct-reg、WGS、transforms-per-block；
- tile fan-in、tile width、large-twiddle base/steps 和 SBRC transpose type。

同时补充 `environment.h`，清理文件尾部遗留的重复 include 和重复 logger 定义。诊断输出默认关闭，不改变融合判定、ABI 或计算结果。

#### 验证结果

远端 rocFFT 构建和安装成功：

```text
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j 8
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
[100%] Built target rocfft
```

任务 766620 correctness 通过：`relative_l2=6.644698e-16`、`relative_max=9.451432e-16`、`max_abs=3.551690e-12`。

该次目标路径的诊断值为：`strict=false`、`streaming=false`、`ownership=false`、`edge=true`、`resident_lds=8388608/false`、`streaming_lds=32768/true`、producer/consumer direct-reg 为 `true/true`、WGS/TPB 为 `256/4 -> 512/4`、tile requirement/plane 为 `128/128`、tile width 为 `4/4`、large-twiddle 为 `8/0`、transpose 为 `2`。因此融合条件被拒绝，实际计划仍使用原始 SBCC + SBRC 两个 kernel；global store/load 没有删除，性能没有变化。

#### 结论与保留状态

本轮只保留诊断代码和本记录，不宣称已经完成融合。诊断暴露了两个下一步问题：一是需要用目标 SBCC 节点实际的 `ltwdSteps` 判断 large-twiddle contract；二是 fused generator 已经强制 consumer 走共享 LDS 初始读取，不能继续用原 consumer 的 direct-reg 标志阻止融合。后续先修正这两个 contract，再进行 RTC 编译和 correctness 验证。



<a id="historical-main-exp-015"></a>

### EXP-015：解除 consumer direct-reg 的误拒绝条件 [历史 main · 旧编号 EXP-015]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-015`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-22。

#### 原理

streaming fused generator 会通过 `make_fused_specs(node, false)` 强制 SBRC consumer 使用共享 LDS 读取，因此 consumer 原始 kernel 的 `direct_to_from_reg` 只描述未融合路径，不能作为 fused consumer ABI 的安全条件。streaming contract 仍保留 producer direct-reg、tile 映射、workgroup、stride、LDS、large-twiddle 和 `TILE_ALIGNED` 等约束。

#### 做了什么

在 `library/src/fuse_shim.cpp` 的 `streamingFusable` 判定中移除 `!consumerKernel.direct_to_from_reg`，保留 `producerKernel.direct_to_from_reg` 及其余条件。重新构建并安装 rocFFT，提交 DCU 任务 `766809`，开启 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1` 和 `ROCFFT_DEBUG_SBCC_SBRC_FUSION=1`。

#### 验证结果

构建和安装成功，输出为 `[100%] Built target rocfft`。任务 `766809` correctness 通过：`relative_l2=6.644698e-16`、`relative_max=9.451432e-16`、`max_abs=3.551690e-12`，与双 kernel 基线一致。

运行诊断为：`direct_reg=true/true`、`streaming=false`、`ltwd=8/0`。因此 direct-reg 条件已不再是拒绝原因，但融合仍未创建；计划仍是 SBCC + SBRC 两个独立 kernel，中间 global store/load 和性能均未改变。

#### 发现与保留状态

进一步追踪发现，`ProcessNode()` 在 `ApplyFusion()` 前没有执行 leaf `KernelCheck()`，SBCC 的 `ltwdSteps` 仍为默认值 0；同时 `TreeNode::CopyNodeData()` 没有复制 `ltwdSteps`。本轮只保留移除 consumer direct-reg 条件的修正，下一轮修复 large-twiddle 元数据生命周期后再验证真正融合。


<a id="historical-main-exp-016"></a>

### EXP-016：修复 fused RTC 变量的二次前缀改写 [历史 main · 旧编号 EXP-016]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-016`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

融合 RTC 生成器先通过 `FusedStageRewriteVisitor` 把 producer 的 `stride_out` 绑定为外层融合 kernel 的 `producer_stride_out`，随后再通过 `FusedGlobalVariableVisitor` 对 stage 变量统一添加 `producer_` 或 `consumer_` 前缀。变量访问可能经过两个 visitor，因此重写规则必须满足幂等性：已经带当前 stage 前缀的名字不能再次改名。

此前的无条件前缀逻辑把 `producer_stride_out` 变成了 `producer_producer_stride_out`，导致 HIP RTC 编译器报未声明标识符，融合 kernel 无法进入设备编译和运行阶段。

#### 做了什么

在 `library/src/rtc_stockham_gen.cpp` 的 `FusedGlobalVariableVisitor::visit_Variable()` 中增加当前前缀判断：当变量名以本 visitor 的 `prefix` 开头时直接保留原名，同时继续递归改写下标、尺寸表达式。原有参数、stage 常量、scalar type 和 callback 参数的处理保持不变。

#### 修改内容

修改条件为：

```cpp
if(!renamed.count(x.name)
   || x.name.rfind(prefix, 0) == 0
   || x.name == "scalar_type"
   || is_callback_argument(x.name))
```

本次没有改变 producer/consumer 的 tile 映射、LDS 地址、launch grid 或 global handoff 逻辑；仅修复融合 RTC 源码的名字绑定。

#### 验证结果与效果

远端源码检查确认 `producer_stride_out` 现在不会再次添加 `producer_` 前缀，`git diff --check` 通过。修复前的 RTC 错误 `use of undeclared identifier 'producer_producer_stride_out'` 已有明确根因和对应修复；单线程构建、RTC 编译、correctness 和 global store/load 是否真正消除将在本条之后的 DCU 验证中确认。


<a id="historical-main-exp-017"></a>

### EXP-017：前缀修复后的 rocFFT 构建与安装验证 [历史 main · 旧编号 EXP-017]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-017`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

融合 RTC 生成器的源码修改只有在 host 侧生成器重新编译并安装到实际运行时使用的前缀后，才会进入 DCU 作业。先用单线程完整构建可以隔离 C++ 编译问题，再执行安装，随后由独立 DCU 作业验证 planner 是否选择 fused node、RTC 是否能够编译生成的融合 kernel，以及数值结果是否正确。

#### 做了什么

在远端 `/public/home/zhangkewei/zr/build/rocfft_build` 执行：

```text
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j 1
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
```

构建目标包含 `rtc_stockham_gen.cpp`、planner、fusion shim、tree node 和 device resource 相关改动；安装目标为 `/public/home/zhangkewei/zr/install`。

#### 验证结果与效果

构建成功，最终输出为 `[100%] Built target rocfft`；安装成功，`/public/home/zhangkewei/zr/install/lib/librocfft.so.0.1` 已更新。输出中仍有仓库已有的缺少 return、未使用变量、`llvm-ar: command not found` 和无 `libamd_comgr.so` 的环境提示，但没有新增编译错误。

该步骤只证明 host 侧生成器和 planner 可以构建，尚未证明融合 kernel 的 RTC 编译、global store/load 删除或数值正确性；这些效果交由下一次带 DCU 的 EXP-018 验证。

状态：构建与安装保留，等待 DCU 运行验证。



<a id="historical-main-exp-018"></a>

### EXP-018：融合 RTC 首次正确性验证 [历史 main · 旧编号 EXP-018]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-018`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

host 侧 planner 和 fused RTC generator 构建成功后，必须在目标 DCU 上验证生成的单 kernel 是否真正可编译、可启动并保持数值等价。该实验使用目标 SBCC-1024 -> SBRC-512 配置，开启 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1`，并保留融合诊断输出。

#### 做了什么

提交融合 correctness 任务，检查 planner 是否创建 `FusedSBCCSBRCNode`、HIP RTC 是否编译 fused kernel，以及输出与独立 SBCC + SBRC 基线的相对误差。对比路径仍保留为回归基线，没有修改输入、参考结果或测试阈值。

#### 验证结果与效果

fused RTC 能够生成并编译，说明 host generator 的函数合并、参数前缀和 fused launch ABI 已经越过编译阶段；但随机输入正确性失败：

```text
relative_l2=1.113722e+00
relative_max=1.107848e+00
max_abs=4.163108e+03
```

独立双 kernel 基线通过，误差约 `6e-16`。因此本实验没有把 fused correctness 结果标记为通过，也没有宣称已经完成可用的 global store/load 消除。

#### 结论

融合错误发生在 producer/consumer 跨阶段数据 handoff 或线程/布局契约，而不是 RTC 语法编译。下一步需要逐项核对 producer 实际输出 stride、consumer 输入 stride、LDS 索引以及 producer workgroup 扩展后的 lane ownership。



<a id="historical-main-exp-019"></a>

### EXP-019：RTC 生成结果与 handoff stride 核对 [历史 main · 旧编号 EXP-019]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-019`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

跨 kernel 融合不能把 plan dump 中 fused 外层输出 stride 当成 producer 的临时输出 stride。producer 的 physical offset 必须先按 producer 实际 `stride_out` 解码为行列坐标，再映射到 consumer tile 的 LDS 坐标；否则即使索引在边界内，数据也会落入错误的 consumer 行。

#### 做了什么

检查生成的 fused RTC 源码、producer 的参数 ABI、consumer 的输入 stride 和 handoff 表达式。确认目标配置中 producer SBCC 的实际输出 stride 为 `[512,1]`，consumer SBRC 的输入 stride 为 `[1,512]`；当前 handoff 计算等价于：

```text
producer_row = physical_offset / 512
producer_col = physical_offset % 512
lds_index = producer_col + (producer_row - consumer_tile_start) * 512
```

同时确认 fused plan dump 中的 `oStrides=[1,1024]` 属于 fused 外层输出，不属于 producer 临时 buffer，不能用于 handoff 解码。

#### 验证结果与效果

stride scope 和物理布局的静态关系与 consumer LDS 读取布局一致，但 EXP-018 的随机输入错误仍未消除。说明错误不只由把 fused 外层 stride 误用为 producer stride 引起；还需要验证 producer workgroup 被折叠到 consumer WGS 后的线程执行和写入 ownership。

#### 保留状态

本轮没有修改 stride 公式，也没有改变双 kernel 路径。保留 stride 诊断结论，继续做线程 ABI 诊断。



<a id="historical-main-exp-020"></a>

### EXP-020：stride scope 诊断变体 [历史 main · 旧编号 EXP-020]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-020`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

fused generator 中 producer、consumer 和外层 launch 使用不同的 stride 参数命名空间。为了排除 lexical variable visitor 把 `stride_out` 重写到错误 stage 的可能性，需要单独检查生成源码中每个 stride 参数的声明、引用和 handoff 表达式，而不能只观察 planner 的 plan dump。

#### 做了什么

增加并运行 stride scope 诊断，追踪 `FusedStageRewriteVisitor`、`FusedGlobalVariableVisitor` 对 producer `stride_out`、consumer `stride_in` 以及 handoff 中 `stride0_out` 的绑定关系。检查生成的 RTC 源码是否残留 standalone `stride_out` 或错误的二次前缀。

#### 验证结果与效果

生成源码中的 stride 声明和 handoff scope 已能区分 producer 与 consumer，未发现把 fused 外层 `oStrides` 直接当作 producer stride 的证据；但 correctness 仍失败，故该诊断变体没有解决数据错误。

本轮只保留诊断和源码检查，不改变运行时判定。当前最可疑的剩余问题是 producer WGS=256、consumer WGS=512 时，所有 512 个线程重复执行折叠后的 producer lane，可能对 handoff LDS 产生重复写入竞态。



<a id="historical-main-exp-021"></a>

### EXP-021：handoff ABI 与线程映射诊断 [历史 main · 旧编号 EXP-021]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-021`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

producer 的 RTC helper 含有多个 `__syncthreads()`。不能用 `if(threadIdx.x < producerWgs)` 包住整个 producer helper，因为只有部分线程进入 barrier 会死锁。当前可行的第一步是让 512 个线程都执行 producer 计算和 barrier，同时把 `threadIdx.x` 折叠到 256-thread producer lane 空间；随后必须确认 handoff LDS 写入是否需要单写者限制。

#### 做了什么

增加 handoff ABI 诊断，观察 producer/consumer WGS、TPB、tile fan-in、producer block remap、handoff store guard 和 barrier 所在 helper。对受 RTC cache 初始化、作业环境和设备资源影响的任务分别记录失败原因，不把环境失败误判为算法正确性结果。

#### 验证结果与效果

诊断确认目标配置为 producer WGS=256、consumer WGS=512，producer 线程被折叠后 256 个 lane 会被两组外层线程重复执行。部分任务受 RTC 或环境问题阻断，未形成新的 correctness 通过证据；现有随机输入错误仍保持 EXP-018 的量级。

由此形成 EXP-024 的可验证假设：保留所有线程参与 producer barrier，但只允许原始 256 个 producer lane 写 handoff LDS，从而消除重复写者竞态。



<a id="historical-main-exp-022"></a>

### EXP-022：fused resource debug 构建验证 [历史 main · 旧编号 EXP-022]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-022`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

融合路径同时改变 producer/consumer 的 LDS 声明、launch bounds、参数数量和 helper 资源。需要先确认 host 侧资源估算和生成代码调试信息可以构建，避免把运行时资源初始化问题误认为 planner 或 RTC 逻辑错误。

#### 做了什么

增加资源相关诊断与阶段信息，检查 streaming LDS 字节数、producer/consumer resident LDS、launch WGS 和 fused 参数 ABI；重新构建并安装 rocFFT。运行阶段同时保留环境错误原文。

#### 验证结果与效果

host 构建和安装成功，资源诊断能够输出目标 streaming LDS=32768 bytes 以及 producer/consumer WGS=256/512。部分 DCU 运行受 RTC cache 初始化、`std::bad_alloc` 或设备环境影响，不能据此宣称资源契约已经在设备上完全验证。

本轮保留诊断代码和构建结果，没有改变 fused correctness 判定，也没有删除额外的 global store/load。



<a id="historical-main-exp-023"></a>

### EXP-023：fused stage debug 与变量前缀根因定位 [历史 main · 旧编号 EXP-023]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-023`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

融合生成经历多个 visitor：stage rewrite 先把 producer 的 `stride_out` 绑定为 `producer_stride_out`，随后 lexical variable visitor 又会给 stage 参数加 `producer_` 或 `consumer_` 前缀。若第二次 visitor 不具备幂等性，就会生成 `producer_producer_stride_out`，导致 RTC 编译错误。

#### 做了什么

增加 stage 级生成源码诊断并重新构建、安装。检查旧 RTC 日志和生成代码中 producer stride 的最终名字，同时确认 planner、launch 和 handoff 代码没有被该诊断改写。

#### 验证结果与效果

旧 RTC 日志出现 `producer_producer_stride_out`，定位到 `FusedGlobalVariableVisitor::visit_Variable()` 的无条件前缀逻辑。随后在该 visitor 中加入幂等条件：变量名已经以当前 stage 前缀开头时不再添加前缀，同时继续递归改写下标和尺寸表达式。

修复后 `git diff --check` 通过，host 构建和安装成功。该修复解决了 fused RTC 的明确编译根因，但在 EXP-018 的随机 correctness 失败之后仍需继续验证 handoff 数据竞争；因此本轮不能单独视为数值正确性完成。



<a id="historical-main-exp-024"></a>

### EXP-024：producer handoff LDS 单写者修复 [历史 main · 旧编号 EXP-024]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-024`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

当 producer WGS=256、consumer WGS=512 时，fused launch 为了让所有线程到达 producer 内部 barrier，会把 producer 的 `threadIdx.x` 映射为 `threadIdx.x % 256`。这会使每个 producer lane 被两个外层线程重复执行；若重复线程同时写 handoff LDS，即使写入值理论上相同，也会形成无序 LDS 写入竞态。

因此只限制 handoff 写入者，不限制整个 producer helper：`fused_producer_owner = threadIdx.x < producerWgs`。所有 512 个线程仍执行 producer 代码并参与每个 barrier，只有原始 256 个 lane 可以写入 streaming handoff LDS。

#### 做了什么

在 `library/src/rtc_stockham_gen.cpp` 中：

1. 在 fused outer kernel 中声明 `fused_producer_owner`，其值为 `threadIdx.x < node.producerWgs`；
2. 在 `FusedStageRewriteVisitor::handoff_store()` 的 guard 中加入 `fused_producer_owner`；
3. 将 `fused_producer_owner` 加入 stage variable visitor 的已知名字集合，防止被错误改写成 `producer_fused_producer_owner`；
4. 不包裹 producer helper，不改变 producer 内部 barrier、tile remap、consumer 读取或 LDS 地址公式。

#### 验证状态

补丁已通过远端 `patch --dry-run` 后正式应用，`git diff --check` 通过，远端源码确认包含上述三个修改点。单线程构建、安装和 DCU correctness 尚未完成，当前不能宣称该变体已经修复数值错误。

#### 预期效果与后续

若随机 correctness 恢复到独立双 kernel 的约 `6e-16`，说明此前主要错误来自重复 handoff LDS 写入；再进行性能和多尺寸验证。若仍失败，则继续检查 producer/consumer 的 tile fan-in 时序、LDS barrier 位置和 consumer 初始 load 删除范围，并保留本实验结果作为排除重复写者竞态的证据。


<a id="historical-main-exp-025"></a>

### EXP-025：修复 owner 变量的错误 stage 前缀 [历史 main · 旧编号 EXP-025]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-025`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

`fused_producer_owner` 是 fused outer kernel 自己声明的控制变量，不属于 producer global function 的 stage 参数。它被 handoff guard 使用，但声明位于外层 lexical scope；因此不能把它加入 `FusedGlobalVariableVisitor` 的 `renamed` 集合，否则 visitor 会把它改写为 `producer_fused_producer_owner`。

#### 做了什么

EXP-024 首次 DCU 作业 `768071` 在 HIP RTC 编译阶段失败，错误为：

```text
use of undeclared identifier 'producer_fused_producer_owner'
did you mean 'fused_producer_owner'?
```

生成的 RTC 源码同时显示外层声明为 `bool fused_producer_owner = threadIdx.x < 256;`，因此确认问题是变量前缀作用域，而不是 owner 条件或 producer lane 计算。

在 `library/src/rtc_stockham_gen.cpp` 中移除 `renamed.insert("fused_producer_owner")`。由于该变量不在 stage global function 的参数集合中，visitor 会按现有规则保持其原名；producer handoff guard 仍引用外层的 `fused_producer_owner`。

#### 验证状态与效果

修复补丁通过远端 `patch --dry-run` 并正式应用，`git diff --check` 通过，失败作业没有进入设备执行阶段，因此没有新的数值正确性结论。下一步重新构建、安装并提交 DCU correctness，验证 RTC 编译是否通过后再观察单写者变体的数值结果。


<a id="historical-main-exp-026"></a>

### EXP-026：handoff 单写者变体的运行时正确性验证 [历史 main · 旧编号 EXP-026]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-026`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

本实验验证 EXP-024/025 的单写者约束是否能够消除 fused SBCC -> SBRC 的数值错误。producer WGS=256、consumer WGS=512 时，所有 512 个外层线程仍需执行 producer helper 并参与 barrier，但只有前 256 个物理 lane 写 handoff LDS。若错误主要来自重复 producer lane 写 LDS，单写者版本应恢复到独立 SBCC 与 SBRC 双 kernel 的数值误差水平。

#### 做了什么

重新构建并安装包含 `fused_producer_owner` 修复的 rocFFT，提交 DCU 作业 `768079`。作业中确认 RTC 编译成功并实际执行 fused kernel；同时保留 planner 诊断，记录 producer/consumer WGS、TPB、tile fan-in、LDS 资源、large-twiddle 和 transpose 配置。

#### 验证结果与效果

fused kernel 仍然出现明显数值错误：

```text
relative_l2=1.113722e+00
relative_max=1.107848e+00
max_abs=4.163108e+03
```

对应诊断为：

```text
strict=false
streaming=true
ownership=false
edge=true
resident_lds=4194304/false
streaming_lds=32768/true
direct_reg=true/true
wgs/tpb=256/4 -> 512/4
tile_req/plane=128/128
width=4/4
ltwd=8/3
transpose=2
```

独立双 kernel 基线仍约为 `6e-16`。因此，重复 producer lane 写 handoff LDS 不是当前主要根因；EXP-024 的单写者修改保留为有效的数据竞争排除实验，但没有完成数值修复。下一步转向 handoff physical offset 到 consumer LDS layout 的映射、producer tile 循环中的 LDS 复用与 barrier 时序，以及 producer 最终 large-twiddle/store 阶段输出是否确实等价于 SBRC 的输入。


<a id="historical-main-exp-027"></a>

### EXP-027：传递 producer 的 planner intrinsic 模式 [历史 main · 旧编号 EXP-027]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-027`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

普通 SBCC 节点会在 planner 中根据设备、stride、placement 和 kernel 配置设置 `intrinsicMode`。但原有 fused RTC 生成器的 `append_fused_stage_constants()` 无条件生成：

```cpp
static const IntrinsicAccessType producer_intrinsic_mode =
    IntrinsicAccessType::DISABLE_BOTH;
```

这会使 fused producer 与 standalone SBCC 的访问策略脱节。正确的元数据路径应是：

```text
SBCCNode::intrinsicMode -> FusedSBCCSBRCNode::producerIntrinsicMode
                         -> fused RTC stage constant
```

同时，intrinsic 模式必须进入 fused kernel 名称，避免 RTC cache 把不同访问策略的源码视为同一个 kernel。

#### 做了什么

1. 在 `FusedSBCCSBRCNode` 增加 `producerIntrinsicMode` 字段。
2. 在 `CCSBRCFuseShim::FuseKernels()` 中保存原 producer 的 `intrinsicMode`。
3. 扩展 `append_fused_stage_constants()`，按 `DISABLE_BOTH`、`ENABLE_LOAD_ONLY` 或 `ENABLE_BOTH` 生成 producer 常量；consumer 仍保持 `DISABLE_BOTH`，因为 consumer 的 global load 已由 LDS handoff 替代。
4. 在 fused kernel 名称中加入 `_pintrinsic_disabled`、`_pintrinsic_load` 或 `_pintrinsic_readwrite` 后缀。
5. 重新构建 `make -j8 rocfft`，目标成功；使用 `cmake --install .` 安装到 `/public/home/zhangkewei/zr/install`。
6. 提交 DCU 作业 `768268`，保持 EXP-026 的 512K double、固定随机输入和误差阈值，关闭 RTC cache 读取。

#### 修改位置

- `library/src/include/tree_node_1D.h`
- `library/src/fuse_shim.cpp`
- `library/src/rtc_stockham_gen.cpp`

#### 验证结果与效果

作业实际执行 fused kernel，planner 诊断仍为：

```text
strict=false
streaming=true
direct_reg=true/true
wgs/tpb=256/4 -> 512/4
tile_req/plane=128/128
ltwd=8/3
transpose=2
```

数值结果为：

```text
relative_l2=1.113722e+00
relative_max=1.107848e+00
max_abs=4.163108e+03
```

与 EXP-026 完全一致，独立 SBCC + SBRC 双 kernel 基线仍约为 `6e-16`。目标设备为 `gfx936`；现有 SBCC planner 的 `TuneIntrinsicMode()` 对该架构会将 intrinsic 访问关闭，因此该作业实际选择的 producer 模式仍为 `DISABLE_BOTH`，没有形成强制开启 intrinsic 的对照实验。

本轮确认了 producer intrinsic 元数据已经能够穿过 planner/fusion/RTC 接口，且 kernel cache 名称已隔离；但没有改善 correctness，也不能据此判定 intrinsic 是主要根因。下一步需要增加显式 `ENABLE_BOTH` 的诊断变体，或者直接转向 producer 中间 work buffer 的 planner 级生命周期改造，以验证当前 LDS handoff 是否错误地复用了 producer 的 global 输出布局。


<a id="historical-main-exp-028"></a>

### EXP-028：planner 级 global handoff 正确性闭环 [历史 main · 旧编号 EXP-028]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-028`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

本实验先实现一个保持 global store/load 的 planner 级 handoff，用它验证 SBCC -> SBRC 的 tile 生命周期、缓冲区所有权和 fused kernel ABI。producer 仍从用户输入读取并把结果写入 planner 分配的 handoff work buffer；consumer 从同一 work buffer 读取并把最终结果写入用户输出：

```text
producer input  -> user input
producer output -> planner global handoff work buffer
consumer input  -> the same handoff work buffer
consumer output -> user output
```

这样做的意义是先把原来两个独立 kernel 之间的临时 global buffer 生命周期显式纳入 planner，再在正确性成立后继续删除 global store/load。global handoff 模式不把 producer 和 consumer 的 `OperatingBuffer` 身份强行设为相同，而是通过独立的 planner work-buffer offset 建立物理地址契约。

#### 做了什么

1. 为 `TreeNode` 增加额外 work-buffer 大小和 offset 接口；`FusedSBCCSBRCNode` 保存 `globalTileHandoff`、`globalHandoffElements` 和 `globalHandoffOffset`。
2. 在 planner 完成普通 `OB_TEMP` 内存计算后，为 fused node 追加独立 handoff 区域，并把区域 offset 设置为普通临时缓冲区之后的位置。目标作业中 offset 为 `0`，handoff 大小为 `524288` 个 complex 元素。
3. 在 `TransformPowX()` 中把 fused node 的 `bufTemp` 指向 `workBuffer + globalHandoffOffset * complex_type_size`。
4. 扩展 fused kernel ABI：producer 的 output pointer 和 consumer 的 input pointer 在 global 模式下都绑定到 `bufTemp`，producer input 仍使用用户输入，consumer output 仍使用用户输出。
5. RTC 生成器保留 global handoff 模式的 producer global store 和 consumer global load；LDS handoff 模式继续使用 `_lds` 变体。kernel 名称增加 `_global` / `_lds` 后缀，避免 RTC cache 混用不同 ABI 的源码。
6. streaming producer 继续让全部线程参与内部 barrier，仅让 `fused_producer_owner` 写入需要写入的 producer 结果，避免 producer WGS=256、consumer WGS=512 时出现重复写者。
7. 修正 handoff 容量计算：`GetOutputLength()` 是 transpose 后的 row-major 元数据，不能直接和 producer 的 `outStride` 配对。容量改为与 `DetermineBufferMemory()` 一致的物理布局规则：`UseOutputLengthForPadding() ? GetOutputLength() : length` 再结合 `outStride`、`batch`、`oDist` 调用 `compute_ptrdiff()`。

#### 修改文件

远端 rocFFT 源码修改了：

- `projects/rocfft/library/src/include/tree_node.h`
- `projects/rocfft/library/src/include/tree_node_1D.h`
- `projects/rocfft/library/src/fuse_shim.cpp`
- `projects/rocfft/library/src/plan.cpp`
- `projects/rocfft/library/src/powX.cpp`
- `projects/rocfft/library/src/rtc_stockham_kernel.cpp`
- `projects/rocfft/library/src/rtc_stockham_gen.cpp`

验证作业为 `/public/home/zhangkewei/zr/exp028_global_handoff.slurm`，运行时设置：

```bash
ROCFFT_ENABLE_SBCC_SBRC_FUSION=1
ROCFFT_DEBUG_SBCC_SBRC_FUSION=1
ROCFFT_SBCC_SBRC_GLOBAL_HANDOFF=1
ROCFFT_RTC_CACHE_READ_DISABLE=1
```

#### 首次失败与修正

首次 EXP-028 使用 `GetOutputLength()` 计算 handoff 大小，planner 输出：

```text
offset_elements=0 size_elements=262656
```

本例 producer 的 kernel length 为 `[1024, 512]`，producer output stride 为 `[1, 1024]`，而 `GetOutputLength()` 为 transpose 后的 `[512, 1024]`。把二者错误配对只覆盖了 `262656` 个元素；consumer 随后按自身 `[512, 1024]`、`[1, 1024]` 的布局访问，触发 DCU VM fault，未产生数值结果。

修正后按 producer 的物理 length 计算，planner 输出：

```text
offset_elements=0 size_elements=524288
```

double-complex handoff 区域实际为 `524288 * 16 = 8388608` bytes，即 8 MiB，覆盖 producer 和 consumer 的完整访问范围。

#### 构建与验证结果

在 `/public/home/zhangkewei/zr/build/rocfft_build` 执行：

```bash
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j8
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
```

构建和安装成功，目标为 `[100%] Built target rocfft`。远端已有的 COMGR、`llvm-ar` 和 missing-return 警告没有阻止构建。

512K double-complex、随机种子 `20260730` 的 EXP-028 作业 `771136` 输出：

```text
relative_l2=6.647356e-16
relative_max=9.979003e-16
max_abs=3.749943e-12
```

独立 SBCC + SBRC 双 kernel 基线约为 `6e-16`。因此，本轮 global handoff 已恢复到基线量级，且首次 VM fault 已消失，证明 planner work-buffer 生命周期、global handoff ABI 和物理容量修正对本例是正确的。

#### 效果与边界

本轮完成的是“正确性优先”的 planner 级 global handoff，仍然保留 producer global store 和 consumer global load，因此还不是最终的 zero-global-traffic SBCC -> SBRC 融合。它解决了前一轮错误的物理容量和 buffer 身份限制，并提供了后续删除 global store/load 时可复用的 planner offset、size 和 ABI 基础。

下一步应在保持该 global handoff 作为 correctness 对照的前提下，逐步验证真正的 LDS tile lifetime 路径：先比较 global 与 LDS 版本的单 kernel输出，再检查 consumer 的 LDS 初始化删除范围、producer tile 循环的跨 tile barrier 和 transpose 后索引映射，最后再进行多尺寸 correctness 与性能测试。


<a id="historical-main-exp-029"></a>

### EXP-029 [历史 main · 旧编号；原始记录缺失]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-029`。

原分支缺少独立实验记录；后续旧 EXP-031 引用了 EXP-029 的 handoff 下标与源码基线。本项只登记这一原始缺口，不据引用推测实验过程、数据或结论。参见下方旧 EXP-031 的原文。


<a id="historical-main-exp-030"></a>

### EXP-030：修正 LDS handoff 的转置后 LDS 线性布局 [历史 main · 旧编号 EXP-030]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-030`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

SBCC producer 的物理输出布局与 SBRC consumer 的输入逻辑维度互换。当前测试例中，producer 输出物理地址可表示为：

```text
physical = producer_row * 512 + producer_col
```

一个 consumer workgroup 负责 `consumer_tile_width=4` 个 consumer dim1 元素，也就是 producer row 的连续 4 行。独立 SBRC 的 global-to-LDS 路径在当前融合配置中关闭 direct-store，因此它把输入写入线性 LDS：

```text
lds[consumer_dim0 * 512 + local_consumer_dim1]
```

转置关系为 `consumer_dim0 = producer_col`、`local_consumer_dim1 = producer_row - consumer_tile_start`，所以正确的 handoff 下标应为：

```text
producer_col * consumer_length0 + (producer_row - consumer_tile_start)
```

此前实现使用了相反的乘法方向：

```text
producer_col + (producer_row - consumer_tile_start) * consumer_length0
```

它将 producer 的转置 tile 以错误方向写入 LDS。global handoff 能通过是因为 consumer 会再次按照 global 地址和自身 LDS 规则加载；删除 global load 后，这个布局差异直接暴露为 FFT 输入错误。

#### 做了什么

在 `library/src/rtc_stockham_gen.cpp` 的 `FusedStageRewriteVisitor::handoff_index()` 中，将 LDS 下标从 `producer_col + local_row * consumer_length` 改为 `producer_col * consumer_length + local_row`，并添加注释说明该公式与 SBRC 独立 global-to-LDS 路径的对应关系。

#### 修改了什么

只修改 producer 写入 consumer LDS 的地址计算；producer 的物理 offset 分解、consumer tile guard、producer tile 循环、barrier 和 global handoff 分支均保持不变。

#### 效果

已完成两组验证。LDS streaming 作业 `771361` 的结果为：

```text
relative_l2=1.118049e+00
relative_max=1.087613e+00
max_abs=4.087067e+03
```

global handoff 回归作业 `771362` 的结果仍为：

```text
relative_l2=6.647356e-16
relative_max=9.979003e-16
max_abs=3.749943e-12
```

因此，反转下标方向没有修复 LDS 路径，且错误量级与此前版本相同；global handoff 未受影响。该结果排除了“只需要交换两个乘法方向”这一假设，后续必须继续检查 producer `R[]` 到物理输出的排列、consumer 的 `offset_lds`/bank-conflict swizzle，以及删除 global-to-LDS 赋值时是否误删了必要初始化。


<a id="historical-main-exp-031"></a>

### EXP-031：恢复 LDS 基线并准备真实 RTC 地址审计 [历史 main · 旧编号 EXP-031]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-031`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-23。

#### 原理

EXP-030 只改变了 handoff 写入的两个线性下标方向，但数值误差仍约为 `1.1`，说明问题不在单一的行列乘法方向。rocFFT 的 consumer 并不直接以抽象的 `lds[index]` 读取输入：生成代码会结合 `stride_lds`、`offset_lds`、`transform` 和 AMD LDS bank-conflict swizzle 计算实际地址；producer 的 `R[]` 也可能经过 `reg_to_lds` 语义重排后才对应 global store 的物理顺序。因此下一步必须以实际生成的 fused RTC 源码为准，逐条比较独立 SBRC 与 fused consumer 的 global load、LDS store、LDS-to-register load。

#### 做了什么

恢复 EXP-029 的 handoff 下标作为后续实验的稳定基线，并准备通过 `ROCFFT_LAYER=40` 与固定 `ROCFFT_LOG_RTC_PATH` 重新生成 fused RTC 源码。global handoff 路径继续作为正确性对照，不改变其 planner buffer 和 ABI。

#### 修改了什么

在 `library/src/rtc_stockham_gen.cpp` 的 `FusedStageRewriteVisitor::handoff_index()` 中，将实验性的：

```cpp
producer_col * consumer_length + local_row
```

恢复为 EXP-029 的：

```cpp
producer_col + local_row * consumer_length
```

同时更新源码注释，明确该表达式暂作为 producer-tile 基线，consumer 生成地址仍待 RTC 审计。文档中的 EXP-030 效果段补充了 `771361` 和 `771362` 的最终结果。

#### 效果

源码基线已恢复；构建和 correctness 结果将在固定 RTC dump 生成后补充。该实验的目的不是宣称 LDS 已修复，而是确保后续地址审计从 EXP-029 的可复现状态开始。

<a id="historical-main-exp-032"></a>

### EXP-032：将 streaming handoff 放到 producer scratch 之后 [历史 main · 旧编号 EXP-032]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-032`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

producer 即使采用 direct-register 输入输出，也不代表整个 producer kernel 不使用 LDS。radix exchange、`lds_real` 辅助区和 large-twiddle 阶段可能在 producer 的完整 tile 循环期间占用 LDS。因此，consumer 的 handoff tile 不能从 LDS 起始地址覆盖 producer scratch，而必须使用如下连续区域：

```text
[producer scratch LDS][consumer handoff tile]
```

planner 侧需要以字节为单位计算这两个区域的总预算，fusion shim 再把 producer scratch 的大小转换成 handoff 起点，把总预算转换成 fused launch 的 LDS 大小。RTC consumer 同时需要重绑定 `lds_complex` 和 `lds_real`，否则 consumer 会继续读取独立 kernel 的 LDS 名字或未声明的 handoff 名字。

#### 做了什么

1. 在 planner 的 streaming contract 中，将 `fusedStreamingLdsBytes` 改为 `producerLdsBytes + consumerLdsBytes`，保留溢出检查和设备 LDS 容量判断。
2. 在 `library/src/fuse_shim.cpp` 中记录 producer scratch 的元素偏移，并把 fused LDS 元素数改为整个 streaming 区域的大小。
3. 在 `library/src/include/tree_node_1D.h` 中明确 `producerLdsElements` 在 streaming 模式表示 handoff 起点，而不是 producer 的逻辑 tile 长度。
4. 在 `library/src/rtc_stockham_gen.cpp` 中让 streaming 且非 global handoff 的 consumer 同时使用 `fused_handoff_lds` 和 `fused_handoff_lds_real`，并将 handoff 声明放在 producer scratch 之后。
5. 重新构建并安装 rocFFT，构建目标成功。

#### 修改了什么

本轮修改了 planner 的 LDS 预算、fusion shim 的区域布局元数据、tree node 的偏移语义和 RTC consumer 的 LDS 变量绑定；没有改变 producer 的 tile 映射、consumer 的 FFT 算法或 global handoff 的 planner work buffer。

#### 效果

EXP-032 作业 `771516` 的 planner 诊断已经看到 `streaming_lds=65536`，RTC 中也出现了：

```text
fused_handoff_lds = lds_complex + 2048
fused_handoff_lds_real = lds_real + 4096
```

但实际 launch 日志仍是：

```text
dy_lds bytes 32768
```

结果为：

```text
relative_l2=1.000000e+00
relative_max=1.000000e+00
max_abs=3.757833e+03
```

这轮没有完成 correctness，但定位出新的单位契约问题：`LeafNode::SetupGridParam()` 在 `half_lds` 为真时会再次把 host 侧 LDS 分配量除以 2，而 fused streaming 元素数没有补偿该除法。EXP-032 因此成为 EXP-034 的直接根因定位实验。


<a id="historical-main-exp-033"></a>

### EXP-033：隔离 global handoff 与 LDS handoff 的 RTC 变量绑定 [历史 main · 旧编号 EXP-033]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-033`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

global handoff 和 streaming LDS handoff 是两种不同的 ABI：

- global handoff 保留 producer global store 和 consumer global load，consumer 不应访问 `fused_handoff_lds`；
- streaming handoff 删除中间 global 访问，consumer 才应从 producer scratch 之后的 `fused_handoff_lds` 和 `fused_handoff_lds_real` 读取。

因此，RTC consumer 重绑定的条件必须是：

```cpp
node.streamingTileHandoff && !node.globalTileHandoff
```

只检查 `streamingTileHandoff` 会把 global 路径错误地改写成 local LDS 路径，并在生成代码中引用未声明的 `fused_handoff_lds`。

#### 做了什么

在 `library/src/rtc_stockham_gen.cpp` 的 consumer `FusedStageRewriteVisitor` 构造处，将 local handoff 重绑定条件从：

```cpp
node.streamingTileHandoff
```

改为：

```cpp
node.streamingTileHandoff && !node.globalTileHandoff
```

同时保留 fused outer kernel 中只在非 global streaming 路径声明 `fused_handoff_lds` 的逻辑。补丁先通过远端 dry-run，再应用到远端 rocFFT 源码。

#### 修改了什么

本轮只修改 global/streaming 分支的变量绑定条件，没有改变 global handoff buffer 的大小、offset、producer/consumer global 地址或 planner 资源生命周期。

#### 效果

此前 global 回归作业 `771564` 在 RTC 编译阶段失败，根因是 global handoff 路径被错误重绑定并引用了未声明的 local handoff 变量。EXP-033 修复后，global 路径在 EXP-034 作业 `771592` 中重新通过，数值结果恢复到基线量级：

```text
relative_l2=6.647356e-16
relative_max=9.979003e-16
max_abs=3.749943e-12
```

这证明 global handoff 回归隔离条件有效，同时为后续继续优化 streaming 路径保留了可靠的 correctness 对照。


<a id="historical-main-exp-034"></a>

### EXP-034：补偿 half_lds 对 fused streaming LDS 元素数的二次折半 [历史 main · 旧编号 EXP-034]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-034`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

planner contract 的 `fusedStreamingLdsBytes` 是真实字节预算；fusion shim 需要把它转换为 `fusedLdsElements`，之后 `LeafNode::SetupGridParam()` 又会执行：

```cpp
gp.lds_bytes = lds * complex_type_size(precision);
if(kernel.half_lds)
    gp.lds_bytes /= 2;
```

如果 producer 使用 `half_lds`，直接用 `bytes / complexBytes` 填入 fused 元素数会导致最终 launch LDS 只有目标值的一半。正确换算为：

```cpp
fusedStreamingElements
    = ceil(fusedStreamingLdsBytes / complexBytes)
      * (producerKernel.half_lds ? 2 : 1);
```

这样 host 侧后续的 `/2` 恰好抵消，实际动态 LDS 才等于 planner 的字节预算。

#### 做了什么

在远端 `library/src/fuse_shim.cpp` 中，将：

```cpp
(contract.fusedStreamingLdsBytes + complexBytes - 1) / complexBytes
```

改为：

```cpp
((contract.fusedStreamingLdsBytes + complexBytes - 1) / complexBytes)
    * (producerKernel.half_lds ? 2 : 1)
```

补丁通过远端 `patch --dry-run` 后正式应用；目标文件定向 `git diff --check` 通过。远端全仓 `git diff --check` 仍会报告工作树既有的 `rtc_stockham_kernel.h` 文件末尾空行，该问题与本轮修改无关。

#### 构建与验证

在远端 `/public/home/zhangkewei/zr/build/rocfft_build` 执行：

```bash
cmake --build . --target rocfft -j8
cmake --install .
```

构建结果为 `[100%] Built target rocfft`，并安装到 `/public/home/zhangkewei/zr/install`。构建中仍有仓库已有的 COMGR、缺少 return、未使用变量和 `llvm-ar` 警告，没有新增编译错误。

提交 DCU 作业 `771592`，512K double-complex 输入，关闭 RTC cache 读取，同时验证 streaming 和 global handoff：

```text
streaming: relative_l2=6.647356e-16
streaming: relative_max=9.979003e-16
streaming: max_abs=3.749943e-12

global:   relative_l2=6.647356e-16
global:   relative_max=9.979003e-16
global:   max_abs=3.749943e-12
```

streaming plan/launch 日志确认：

```text
streaming_lds=65536/true
dy_lds bytes 65536
```

生成的 streaming RTC 同时包含：

```text
fused_handoff_lds = lds_complex + 2048
fused_handoff_lds_real = lds_real + 4096
```

#### 效果

EXP-034 修复了实际动态 LDS 分配不足的问题，使 producer scratch、complex handoff 和 real handoff 使用同一份正确的 planner 预算；streaming 路径在当前 512K double-complex 目标上恢复到独立 SBCC + SBRC 双 kernel 的 correctness 基线，global handoff 回归也保持正确。

当前已验证的是 correctness 和 ABI/资源契约，不代表已经完成性能收益评估。下一步仍需在多个尺寸、精度、stride 和 large-twiddle 配置上验证 streaming 路径，并测量删除 global store/load 后的实际带宽和端到端收益。

<a id="historical-main-exp-035"></a>

### EXP-035：多尺寸 streaming contract 基线扫描 [历史 main · 旧编号 EXP-035]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-035`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

EXP-034 只验证了 512K double-complex。planner contract 实际已经记录 producer/consumer 的独立 `transforms_per_block`、tile width、WGS、producer tile 数和 consumer tile 数，不能仅凭单一尺寸的通过结果宣称映射可泛化。因此先在相同 fusion 开关、关闭 RTC cache 读取和相同随机种子下扫描多个 1D 长度，区分“融合路径正确”“正确回退到双 kernel”和“RTC/运行时失败”。

#### 做了什么

提交多尺寸验证作业 `771604`，长度为 `65536、131072、262144、524288、1048576`。每个长度单独设置 plan/RTC/trace 日志，启用 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1` 和 debug 诊断，并用 numpy FFT 计算 double-complex reference。

#### 修改了什么

本轮没有修改 rocFFT 源码，只增加了多尺寸验证脚本和每个长度的日志路径。首次作业 `771603` 因远端脚本传输造成 `fijdone` 语法错误，在执行测试前失败；修正脚本后重新提交 `771604`，该基础设施失败不计入算法结果。

#### 效果

有效作业 `771604` 的五个长度全部通过 correctness：

```text
length=65536:   relative_l2=6.731517e-16, relative_max=1.064539e-15
length=131072:  relative_l2=6.358661e-16, relative_max=8.085363e-16
length=262144:  relative_l2=6.415119e-16, relative_max=7.682407e-16
length=524288:  relative_l2=6.647356e-16, relative_max=9.979003e-16
length=1048576: relative_l2=6.300167e-16, relative_max=1.052578e-15
```

其中 `65536、262144、524288` 选择了 streaming fused kernel；`131072` 的 planner 诊断为：

```text
producer_length=256,512
consumer_length=512,256
wgs/tpb=256/8 -> 512/4
streaming_lds=49152/true
```

但 `FuseKernels=null`，原因是当前 shim 仍要求 producer 与 consumer 的 `transforms_per_block` 和 tile width 相等。`1048576` 的作业也通过，但当前方案未形成新的 fused 诊断记录，需在后续实验中单独确认其 planner 选择。

本轮证明当前 streaming 实现对多种已支持配置稳定正确，同时明确了下一处可实现的泛化点：允许 producer tile width 与 consumer tile width 不同，并依赖已有的物理坐标 guard 与独立 tile-loop contract 完成 handoff。


<a id="historical-main-exp-036"></a>

### EXP-036：放宽 producer 与 consumer 的独立 tile width 约束 [历史 main · 旧编号 EXP-036]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-036`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

EXP-035 发现长度 `131072` 的 producer 与 consumer 具有不同的 tile 配置：

```text
producer_length=256,512       consumer_length=512,256
wgs/tpb=256/8 -> 512/4        width=8/4
```

此前 `CCSBRCFuseShim` 把下面两个相等性判断当作融合前提：

```cpp
producerKernel.transforms_per_block == consumerKernel.transforms_per_block
contract.consumerTileWidth == contract.producerTileWidth
```

这两个判断是旧实现的保守快捷条件，不是 handoff 数据正确性的必要条件。融合后的物理 tile 地址由 producer/consumer 的转置布局、tile 坐标和边界 guard 决定；只要 producer 每个 consumer tile 所需的 tile 数与 plane 中的 producer tile 数一致，producer 输出完整、LDS 区域不越界，并且 consumer 使用支持的 `TILE_ALIGNED` 路径，就可以允许两个 stage 使用不同的 tile width。WGS、direct-register、large-twiddle 和 LDS 容量仍必须满足原有 contract。

#### 做了什么

在远端 `library/src/fuse_shim.cpp` 的 `streamingFusable` 判定中移除了：

```cpp
producerKernel.transforms_per_block == consumerKernel.transforms_per_block
contract.consumerTileWidth == contract.producerTileWidth
```

保留了以下安全条件：

- producer/consumer 长度必须互为转置形状；
- producer tile 数量必须覆盖一个 consumer tile plane；
- 转置 stride 布局必须匹配；
- 边界 tile 必须完整；
- fused streaming LDS 必须适合设备；
- producer 必须 direct-register，consumer WGS 不得小于 producer WGS；
- producer large-twiddle 元数据和 consumer `TILE_ALIGNED` 配置必须有效。

重新执行了：

```bash
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j8
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
```

首次验证作业 `771610` 仍使用了旧的 `fuse_shim.cpp.o`，因此 `131072` 仍显示 `FuseKernels=null`。随后确认对象重新编译并重新安装，提交有效验证作业 `771615`。本轮还增加了 global handoff 回归脚本，提交作业 `771631`。

#### 修改了什么

源码只修改了 `library/src/fuse_shim.cpp` 的融合资格 gate，没有修改 RTC 的 producer/consumer ABI、handoff LDS 地址、barrier、FFT 算法或 global handoff 实现。

验证脚本分别覆盖：

- `771615`：关闭 global handoff，扫描 `65536、131072、262144、524288、1048576`；
- `771631`：设置 `ROCFFT_SBCC_SBRC_GLOBAL_HANDOFF=1`，回归 `131072` 和 `524288`。

#### 效果

有效 streaming 作业 `771615` 的五个尺寸全部通过 correctness：

```text
length=65536:   relative_l2=6.731517e-16, relative_max=1.064539e-15, max_abs=1.220480e-12
length=131072:  relative_l2=6.366404e-16, relative_max=8.043640e-16, max_abs=1.474646e-12
length=262144:  relative_l2=6.415119e-16, relative_max=7.682407e-16, max_abs=2.049519e-12
length=524288:  relative_l2=6.647356e-16, relative_max=9.979003e-16, max_abs=3.749943e-12
length=1048576: relative_l2=6.300167e-16, relative_max=1.052578e-15, max_abs=5.812778e-12
```

其中最关键的 `131072` 已经从 EXP-035 的双 kernel 回退变为真正融合：

```text
streaming=true
FuseKernels=success
wgs/tpb=256/8 -> 512/4
tile_req/plane=64/64
width=8/4
streaming_lds=49152/true
```

`1048576` 的 correctness 也通过，但当前 planner 仍可能因为其它配置条件回退，不能仅凭本轮结果宣称所有尺寸都已经融合。

global handoff 回归作业 `771631` 同样通过：

```text
length=131072: relative_l2=6.366404e-16, relative_max=8.043640e-16, max_abs=1.474646e-12
length=524288: relative_l2=6.647356e-16, relative_max=9.979003e-16, max_abs=3.749943e-12
```

对应日志仍保留 global work buffer：`131072` 为 `size_elements=131072`，`524288` 为 `size_elements=524288`。因此，放宽 tile width 相等性没有破坏 global handoff 的 correctness。

本轮效果是扩大了 planner 允许进入 streaming fusion 的配置集合，并让 `131072` 消除了 SBCC 与 SBRC 之间的 global store/load。当前只完成 correctness 和融合选择验证，尚未测量端到端性能、带宽和其它精度/stride 组合的收益。


<a id="historical-main-exp-037"></a>

### EXP-037：TILE_UNALIGNED SBRC 入口探测 [历史 main · 旧编号 EXP-037]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-037`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

`TILE_UNALIGNED` 的 tile 起点不再能直接使用 aligned 路径的固定映射。SBRC consumer 必须根据实际 tile 坐标、stride 和边界 guard 读取 producer 的转置结果；如果 producer tile 不能完整覆盖 consumer plane，就不能把两级 kernel 的生命周期安全地延长到同一个 LDS handoff 区域。因此，本轮先让 planner 自然选择非 2 次幂长度，确认哪些形状真正进入 SBCC -> SBRC 子树，再决定是否扩展非对齐融合 contract。

#### 做了什么

新增 `exp037_unaligned_probe.slurm`，在 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1` 和 debug 日志开启的条件下验证以下长度：

```text
98304、196608、393216、786432、245760、491520
```

作业使用双精度 complex-interleaved 输入，保持现有 correctness 检查和 RTC cache 禁用设置。重点读取 planner 的 scheme、tile layout、边界和 `FuseKernels` 结果。

#### 修改了什么

本轮只增加了探测脚本，没有修改 `TILE_UNALIGNED` 的 SBRC 生成器、fusion shim 或 planner 资格判断。原因是现有 SBRC 非对齐路径仍有未完成的 TODO，贸然复用 aligned handoff 映射会把边界 tile 的正确性假设扩大到未证明的输入集合。

#### 验证与效果

作业 `771649` 的六个长度全部通过 correctness：

```text
98304:  relative_l2=7.401642e-16, relative_max=9.988084e-16
196608: relative_l2=6.915202e-16, relative_max=1.013042e-15
393216: relative_l2=6.870585e-16, relative_max=1.109354e-15
786432: relative_l2=7.059907e-16, relative_max=1.111291e-15
245760: relative_l2=6.265212e-16, relative_max=9.006528e-16
491520: relative_l2=6.696924e-16, relative_max=9.834775e-16
```

只有 `98304` 形成 CCSBRC streaming fusion：

```text
producer_length=512,192
consumer_length=192,512
wgs/tpb=256/4 -> 256/8
tile_req/plane=48/48
streaming_lds=40960/true
FuseKernels=success
```

其它长度选择了 `CS_L1D_TRTRT`，没有可供 shim 处理的 SBCC -> SBRC 子节点。结论是：当前对齐路径的生命周期融合在自然 planner 选择下保持正确，但 `TILE_UNALIGNED` 仍然只是探测结果，尚未实现非对齐 SBRC handoff。


<a id="historical-main-exp-038"></a>

### EXP-038：factorized root 的 planner 强制入口与 solution map 问题定位 [历史 main · 旧编号 EXP-038]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-038`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

默认 planner 对 `1048576` 选择 `CS_L1D_TRTRT`，不会产生 CCSBRC shim。为了验证 1M 的完整 factorized root，需要在实验开关开启时显式建立 `CS_L1D_CC` 根节点。替换 root scheme 后，旧 `ApplySolution` 生成的 `rootScheme` 和 `solution_kernels` 已经不再描述新树，必须同时清理，否则最终的 kernel key 会被旧 solution map 约束。

#### 做了什么

在 `plan.cpp` 增加实验环境变量 `ROCFFT_FORCE_TILE_LIFETIME_CC=1`。入口限制为一维 factorized root，即：

```text
rootPlanData.dimension == 1
rootPlanData.length.size() == 2
```

满足条件时将 root scheme 替换为 `CS_L1D_CC`，并清空 `execPlan.rootScheme` 和 `execPlan.solution_kernels`。

#### 修改了什么

首次实现误用了 `rootPlanData.length.size() == 1`，导致强制入口根本不会触发；随后修正为 factorized root 的 `length.size() == 2`。清空 `rootScheme` 后，第五个 `1024x1024` SBRC 节点仍报：

```text
Kernel not found or mismatches node (solution map issue)
```

这说明仅清理 solution tree 仍不足以解决问题。继续检查后定位到最终根因不是 planner 树，而是默认 SBRC 配置没有 `length=1024` 的可用 kernel。

#### 验证与效果

强制入口的前四个子计划都能够进入 `FuseKernels=success`。作业 `771671` 及清理 solution map 后的复验仍在 1M 第五个节点失败；因此本轮只证明了 planner 入口和失败位置，没有把 1M correctness 宣称为成功。

本轮得到的后续动作是补齐 `1024x1024` SBRC kernel 配置，而不是继续放宽 fusion shim 的正确性条件。


<a id="historical-main-exp-039"></a>

### EXP-039：补齐 1024 SBRC kernel 并完成 1M 全路径融合 [历史 main · 旧编号 EXP-039]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-039`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

1M factorized root 的最后一个节点需要 `1024x1024` 的 SBRC consumer。选择 `WGS=256`、`TPB=2`、factors `[8, 8, 4, 4]` 后，单个 DP SBRC tile 的 LDS 约为 32 KiB；加上 producer scratch 和 handoff 区域后，融合 kernel 的 LDS 需求保持在设备 64 KiB 上限内。该配置同时满足当前 consumer 的 `TILE_ALIGNED` 和 large-twiddle contract。

#### 做了什么

在 `library/src/device/kernels/configs/config_sbrc.py` 增加：

```python
NS(length=1024,
   factors=[8, 8, 4, 4],
   scheme='CS_KERNEL_STOCKHAM_BLOCK_RC',
   workgroup_size=256,
   threads_per_transform=128,
   runtime_compile=True),
```

先执行 `patch --dry-run --fuzz=0`，再正式修改远端 rocFFT 源码。随后重新构建并安装核心 `rocfft` 目标：

```bash
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j 8
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
```

#### 修改了什么

本轮只补充 SBRC 1024 的 RTC 配置，没有改变 producer/consumer ABI、LDS handoff 地址或 FFT 数学过程。全量构建仍会遇到已有旁支问题：`llvm-ar: command not found`、`libamd_comgr.so` 不可用，以及旁支目标中已有的 RTTI 链接错误；核心 `rocfft` 目标成功完成并安装。

#### 验证与效果

强制验证作业 `771698` 的五个长度全部通过 correctness：

```text
131072:  relative_l2=6.366404e-16, relative_max=8.043640e-16
65536:   relative_l2=6.731517e-16, relative_max=1.064539e-15
262144:  relative_l2=6.415119e-16, relative_max=7.682407e-16
524288:  relative_l2=6.647356e-16, relative_max=9.979003e-16
1048576: relative_l2=6.788953e-16, relative_max=1.012090e-15
```

1M 最后一个节点的 planner 诊断为：

```text
producer_length=1024,1024
consumer_length=1024,1024
streaming=true
FuseKernels=success
wgs/tpb=256/4 -> 256/2
tile_req/plane=256/256
width=4/2
streaming_lds=65536/true
```

RTC 日志中的 fused kernel 使用：

```cpp
scalar_type* fused_handoff_lds = lds_complex + 2048;
real_type_t<scalar_type>* fused_handoff_lds_real = lds_real + 4096;
```

函数体读取 `producer_buf_in`，把 producer 结果写入 `fused_handoff_lds`，再由 consumer 从该 LDS 区域读取并最终写入 `consumer_buf_out`。`producer_buf_out` 和 `consumer_buf_in` 各只出现在统一 ABI 参数列表中，没有中间 global store/load。由此证明 1M 路径已经实现了 SBCC -> SBRC 的 local LDS tile handoff。


<a id="historical-main-exp-040"></a>

### EXP-040：将 1M 已验证形状纳入统一融合开关 [历史 main · 旧编号 EXP-040]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-040`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

`ROCFFT_FORCE_TILE_LIFETIME_CC=1` 适合诊断任意一维 factorized root，但不应成为普通实验路径的长期入口。经过 EXP-039 验证后，将 `1048576` 与已验证的 `524288` 一起纳入 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1` 的白名单，可以在保留 opt-in 边界的同时复用同一 planner 入口。未设置该开关时，普通 rocFFT planner 行为保持不变。

#### 做了什么

在 `plan.cpp` 中把融合实验条件从仅允许 `length[0] == 524288` 扩展为：

```cpp
rootPlanData.length[0] == 524288 || rootPlanData.length[0] == 1048576
```

其它限制仍保留：一维 factorized root、双精度、complex-interleaved 输入输出，并且必须显式设置 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1`。重新构建安装后，提交不设置 force 变量的回归作业 `771756`。

作为对照，修改前的 no-force 作业 `771736` 中 1M 前四个节点可以融合，但最后一个 `1024x1024` 节点没有进入 CCSBRC shim；该作业 correctness 仍通过。

#### 修改了什么

本轮只修改 planner 的实验白名单和注释，没有改变 fusion shim、RTC 生成器或默认关闭时的路径。`ROCFFT_FORCE_TILE_LIFETIME_CC=1` 仍保留，用于后续诊断未加入白名单的 factorized root。

#### 验证与效果

作业 `771756` 的五个长度全部 correctness PASS：

```text
131072:  relative_l2=6.366404e-16, relative_max=8.043640e-16, max_abs=1.474646e-12
65536:   relative_l2=6.731517e-16, relative_max=1.064539e-15, max_abs=1.220480e-12
262144:  relative_l2=6.415119e-16, relative_max=7.682407e-16, max_abs=2.049519e-12
524288:  relative_l2=6.647356e-16, relative_max=9.979003e-16, max_abs=3.749943e-12
1048576: relative_l2=6.788953e-16, relative_max=1.012090e-15, max_abs=5.589185e-12
```

1M 的第五个节点在不设置 force 变量时已进入：

```text
streaming=true
FuseKernels=success
wgs/tpb=256/4 -> 256/2
tile_req/plane=256/256
streaming_lds=65536/true
```

因此，当前统一实验开关已经覆盖 512K 和 1M 两个已验证的 DP complex-interleaved factorized-root 形状，并且两者都能在 SBCC 与 SBRC 之间使用 LDS tile 生命周期融合。当前尚未完成端到端性能、带宽、其它精度、任意 stride 以及 `TILE_UNALIGNED` 路径的收益验证；普通 rocFFT 默认行为也尚未改为无条件启用。

<a id="historical-main-exp-041"></a>

### EXP-041：4704 非对齐 SBRC 基线 [历史 main · 旧编号 EXP-041]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-041`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

`4704 = 96 * 49` 是现有 1D factorized map 中明确的 `96 CC + 49 RC` 形状。SBRC(49) 的 block width 为 28，而 consumer 的第二维为 96，不能整除，因此 planner 会选择 `TILE_UNALIGNED`。该形状同时具有 producer 侧不完整尾 tile，是验证边界 guard 和 handoff 地址映射的直接基线。

#### 做了什么

新增并提交 `exp041_unaligned_4704.slurm`，开启 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1`、planner debug 和 RTC 日志，运行双精度 complex-interleaved 的 `length=4704` correctness 验证。

#### 修改了什么

本轮没有修改 rocFFT 源码，只记录自然 planner 选择的 unaligned contract，作为后续 gate 修改前的基线。

#### 效果

作业 `771806` correctness PASS：

```text
relative_l2=5.927176e-16
relative_max=6.836265e-16
max_abs=2.291431e-13
```

planner 诊断为：

```text
producer_length=96,49 -> consumer_length=49,96
wgs/tpb=256/8 -> 196/28
streaming_lds=34240/true
transpose=TILE_UNALIGNED
edge=false
FuseKernels=null
```

该失败首先由 producer/consumer 的 workgroup 方向不满足 streaming launch 条件，同时 producer 和 consumer 都存在尾 tile。普通双 kernel 路径 correctness 不受影响。


<a id="historical-main-exp-042"></a>

### EXP-042：4913 非对齐基线与 large-twiddle 限制 [历史 main · 旧编号 EXP-042]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-042`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

`4913 = 289 * 17` 形成 `289 CC + 17 RC`，SBRC 的实际 block width 为 120，consumer 第二维 289 不整除，因此自然选择 `TILE_UNALIGNED`。该形状的 producer/consumer workgroup 大小接近，适合排除 workgroup 映射因素。

#### 做了什么

新增并提交 `exp042_unaligned_4913.slurm`，记录未修改 gate 时的自然路径；随后在 EXP-043 的 gate 修改后复用同一脚本重新验证。

#### 修改了什么

本轮没有新增源码修改。基线作业为 `771813`；EXP-043 修改后的复验作业为 `771817`。

#### 效果

两次 correctness 均 PASS，误差一致：

```text
relative_l2=4.516251e-16
relative_max=6.184590e-16
max_abs=1.918465e-13
```

修改后的 planner 诊断显示边界 contract 已经可以成立：

```text
producer_length=289,17 -> consumer_length=17,289
wgs/tpb=119/7 -> 120/120
edge=true
streaming_lds=65008/true
transpose=TILE_UNALIGNED
FuseKernels=null
ltwd=5/3
```

此处仍不能融合的原因是 producer 的 `largeTwdBase=5`，低于当前 fused generator 已验证的 `largeTwdBase>=8` contract。本轮没有放宽该限制，因为 large-twiddle 的 LDS staging 与跨阶段生命周期尚未证明。


<a id="historical-main-exp-043"></a>

### EXP-043：实现最小 TILE_UNALIGNED streaming gate [历史 main · 旧编号 EXP-043]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-043`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

aligned 路径把边界完整性编码为两个整除条件，但 direct-register producer 和已有 `TILE_UNALIGNED` SBRC generator 都具备边界 guard。对于这两类路径，可以把“整除”放宽为“整除或由对应 guard 负责尾 tile”，同时保留 workgroup、stride、tile 数量、LDS、large-twiddle 和 direct-register 等其余安全条件。

#### 做了什么

在远端 rocFFT 源码中应用 `exp043_enable_unaligned.patch`，修改两个资格 gate：

```cpp
descriptor.producerLength[1] % descriptor.producerTileWidth == 0
    || producer_kernel.direct_to_from_reg

descriptor.consumerLength[1] % descriptor.consumerTileWidth == 0
    || descriptor.consumerTransposeType == TILE_UNALIGNED
```

并把 `fuse_shim.cpp` 的 streaming 条件从仅接受 `TILE_ALIGNED` 扩展为接受 `TILE_ALIGNED` 或 `TILE_UNALIGNED`。

#### 修改了什么

只修改 `library/src/plan.cpp` 的 `edgeTilesComplete` contract 和 `library/src/fuse_shim.cpp` 的 transpose gate，没有改变 RTC generator 的 unaligned 地址公式。生成器本来已经根据 `TILE_UNALIGNED` 使用边界 load/store guard；本轮只是让 planner contract 和 shim 使用这条已有路径。

重新构建安装核心目标：

```bash
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j 8
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
```

构建成功，保留已有环境告警 `llvm-ar`、`libamd_comgr.so` 和历史 warning。

#### 效果

4913 的复验作业 `771817` correctness PASS，且 `edge=true`，说明 producer 尾 tile 和 consumer unaligned 边界已经通过 contract；由于 `ltwd=5/3`，最终仍按预期回退，没有把低 large-twiddle 配置带入融合。

该实现的安全边界仍包括：producer 必须 direct-register、consumer WGS 不得小于 producer WGS、tile 数必须覆盖完整 plane、stride 必须是已证明的转置布局、streaming LDS 必须适合设备、producer large-twiddle 必须满足 `base>=8` 且 consumer 不带 large-twiddle。


<a id="historical-main-exp-044"></a>

### EXP-044：large-twiddle 合约筛选 [历史 main · 旧编号 EXP-044]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-044`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

EXP-043 表明非对齐边界本身不再是唯一阻塞点。为避免错误地放宽 large-twiddle 生命周期条件，本轮只探测候选，不修改源码，选择现有 1D map 中可能满足 producer/consumer workgroup 关系的形状。

#### 做了什么

新增并运行 `exp044_unaligned_candidates.slurm`，验证 `19683、68600、87808`。

#### 修改了什么

本轮没有修改源码，只增加探测脚本和日志。

#### 效果

作业 `771819` 三个长度全部 correctness PASS：

```text
19683: relative_l2=6.551924e-16, relative_max=8.706021e-16
68600: relative_l2=7.428697e-16, relative_max=1.031632e-15
87808: relative_l2=8.385114e-16, relative_max=1.181396e-15
```

`19683` 形成的是 aligned streaming fusion：`243x81 -> 81x243`，`transpose=2`，`FuseKernels=success`。`68600` 和 `87808` 都形成了真实的 unaligned 边界 contract，日志为 `edge=true`、`transpose=3`，但 producer 的 `largeTwdBase=6`，因此被保留的 `base>=8` 条件拒绝。该结果支持继续寻找 large-twiddle base 足够的候选，而不是放宽 twiddle gate。


<a id="historical-main-exp-045"></a>

### EXP-045：首个真实 TILE_UNALIGNED fused kernel [历史 main · 旧编号 EXP-045]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-045`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

在现有 double-precision 1D map 中筛选 large-twiddle base 可能达到 8、且 consumer WGS 不小于 producer WGS 的候选。目标是验证同一份 handoff LDS 生命周期在 `TILE_UNALIGNED` consumer 上成立，而不仅是 planner contract 变成可用。

#### 做了什么

新增并运行 `exp045_unaligned_large_twiddle_candidates.slurm`，验证 `28672、57344、102400、106496、114688`，关闭 RTC cache 读取并保存每个长度的 planner/RTC 日志。

#### 修改了什么

本轮没有继续修改源码，使用 EXP-043 已实现的两个 gate 和已有 fused RTC generator 进行验证。

#### 效果

作业 `771821` 五个长度全部 correctness PASS：

```text
28672:  relative_l2=6.128284e-16, relative_max=8.423797e-16
57344:  relative_l2=6.197924e-16, relative_max=9.903657e-16
102400: relative_l2=5.768860e-16, relative_max=6.681514e-16
106496: relative_l2=6.096675e-16, relative_max=9.259188e-16
114688: relative_l2=5.825365e-16, relative_max=8.357162e-16
```

其中 `102400` 是本轮首个真实非对齐 fused kernel：

```text
producer_length=512,200
consumer_length=200,512
wgs/tpb=256/4 -> 400/10
streaming=true
streaming_lds=48384/true
ltwd=8/3
transpose=3
FuseKernels=success
```

RTC kernel 名称包含 `_transpose_unaligned`，函数体声明：

```cpp
scalar_type* fused_handoff_lds = lds_complex + 1024;
real_type_t<scalar_type>* fused_handoff_lds_real = lds_real + 2048;
```

函数体从 `producer_buf_in` 读取，写入 `fused_handoff_lds`，consumer 从该 LDS handoff 读取，最后写入 `consumer_buf_out`。`producer_buf_out` 和 `consumer_buf_in` 各只保留在统一 ABI 参数表中，没有中间 global store/load。该结果证明现有 planner 级 tile lifetime 方案已经覆盖至少一个 `TILE_UNALIGNED` SBCC -> SBRC 组合。

其它四个长度当前选择 aligned streaming fusion，仍然通过 correctness。当前尚未测量性能、带宽、任意 stride、其它精度或 global-handoff 模式下的非对齐收益；`TILE_UNALIGNED` 也只在满足已验证 large-twiddle、LDS 和 workgroup 合约的形状上开放。


<a id="historical-main-exp-046"></a>

### EXP-046：放宽 batch 融合准入的初次探测 [历史 main · 旧编号 EXP-046]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-046`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

原有 planner gate 要求 root plan 的 `batch == 1`。这个限制可以避免 fused
SBCC -> SBRC kernel 处理 batch 距离时出现额外映射问题，但也意味着 tile lifetime
融合没有覆盖多 batch。初次探测只去掉 root batch 限制，同时保留 producer 和 consumer
batch 相等，目的是判断现有 producer/consumer ABI、外层 grid 和 handoff LDS 是否已经
天然支持多个 transform。

#### 做了什么

临时修改 `fuse_shim.cpp`，把 batch 条件从“root batch 必须为 1”放宽为“producer 和
consumer batch 相等”。使用 `102400`、双精度 complex-interleaved、batch=2 运行 fused
correctness，并用 batch=1 做回归对照。

#### 修改了什么

本轮只修改了 CCSBRC shim 的准入条件；没有修改 handoff LDS 地址公式，也没有改变
producer/consumer 的 kernel 生成逻辑。batch=2 验证结束后恢复 root batch=1 的安全 gate。

#### 效果

batch=2 进入 fused path 后 correctness 失败：

```text
relative_l2=1.607055e+02
relative_max=5.926409e+02
```

batch=1 回归仍然通过：

```text
relative_l2=5.768860e-16
relative_max=6.681514e-16
```

这说明失败不是 producer/consumer FFT 算术本身，而是多 batch 的 handoff 地址或 block
映射问题。为避免未证明的 batch 路径影响普通使用，root batch=1 gate 随后恢复。


<a id="historical-main-exp-047"></a>

### EXP-047：batch 融合诊断入口与 handoff bug 定位 [历史 main · 旧编号 EXP-047]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-047`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

需要在不改变默认安全路径的前提下，让 batch>1 进入 fused generator，才能观察生成的
RTC ABI 和 LDS handoff。为此增加一个显式诊断环境变量，只在用户主动设置时绕过 root
batch=1 gate；未设置该变量时 planner 仍回退到原有非融合路径。

#### 做了什么

增加诊断入口：

```text
ROCFFT_EXPERIMENTAL_BATCH_FUSION=1
```

在 `102400`、batch=2 下开启 SBCC -> SBRC fusion、关闭 RTC cache 读取并保存 planner
和 RTC 日志。日志确认 producer 和 consumer 都收到 `nbatch=2`，说明 batch 元数据已经
传入 fused generator。

#### 修改了什么

本轮在 `fuse_shim.cpp` 中增加了仅供诊断的 batch gate 和验证脚本入口；没有把该变量
作为默认配置，也没有放宽默认 fusion 开关。handoff 生成器仍使用完整的物理偏移计算
producer 行列，因此本轮主要用于隔离错误，而不是宣称 batch fusion 已实现。

#### 效果

batch=2 再次进入 fused kernel 后仍然失败：

```text
relative_l2=6.836219e+01
relative_max=8.129108e+02
```

定位到实际原因：`physical_offset` 对第二个及后续 batch 已经包含了
`batch * producer_stride_out[2]`，直接执行
`physical_offset / producer_stride0_out` 会把 batch 距离错误解释为 producer 行号，
随后尾部 guard 丢弃 handoff 写入，consumer 从未初始化的 LDS 读取数据。

因此需要先把物理偏移折回当前 batch 的二维平面，再计算 producer 行列；该修复在
EXP-048 实施并验证。


<a id="historical-main-exp-048"></a>

### EXP-048：batch-local handoff 修复与正式 opt-in [历史 main · 旧编号 EXP-048]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-048`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

当前融合 contract 是二维布局，producer 的 batch distance 保存在
`producer_stride_out[2]`。对任意 producer 物理偏移，先计算：

```cpp
batch_local_offset = physical_offset % producer_stride_out[2];
producer_row = batch_local_offset / producer_stride_out[0];
producer_col = batch_local_offset % producer_stride_out[0];
```

这样每个 batch 都在自己的二维输出平面内完成 tile 行列映射；batch 序号仍由外层
launch/grid 和输入输出距离处理，不会污染 handoff LDS 的行号。producer 的 store guard
与 consumer 的 load index 使用同一个 batch-local 坐标，保证写入和读取一致。

#### 做了什么

在 `rtc_stockham_gen.cpp` 的 `handoff_index()` 和 `handoff_store()` 两处加入
`batch_local_offset`，修复 producer 输出写入 handoff LDS 时的 batch 映射。随后重新构建
并安装 rocFFT 核心库：

```bash
cmake --build /public/home/zhangkewei/zr/build/rocfft_build --target rocfft -j 16
cmake --install /public/home/zhangkewei/zr/build/rocfft_build
```

batch=2 和 batch=3 均在 `102400`、双精度 complex-interleaved 形状上验证。修复确认后，
将 batch>1 的准入从仅诊断变量提升为现有 fusion opt-in 的正式能力：
`ROCFFT_ENABLE_SBCC_SBRC_FUSION=1` 即可进入，`ROCFFT_EXPERIMENTAL_BATCH_FUSION=1`
仍保留为兼容诊断别名；未设置 fusion 开关时默认 planner 行为不变。

#### 修改了什么

源码修改包括：

1. `library/src/rtc_stockham_gen.cpp`：`handoff_index()` 与 `handoff_store()` 使用
   batch-local producer 偏移。
2. `library/src/fuse_shim.cpp`：保留 producer/consumer batch 相等条件，并允许 root
   batch>1 在 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1` 或诊断变量显式开启时进入融合。
3. batch fusion 仍限定在已有 2D、非 planar、非 half、无 callback、已证明 stride/grid、
   LDS 和 large-twiddle contract 内；没有改成默认无条件融合。

构建期间 `rocfft` 目标成功编译和链接。完整 `install` 目标曾被实验树中既有的
`rocfft_kernel_config_search` RTTI/typeinfo 链接错误阻断，但 `cmake --install` 成功更新
了 `install/lib/librocfft.so`，不影响本轮核心库验证。

#### 验证与效果

修复后的诊断路径和正式 opt-in 路径均通过 correctness。最终正式 opt-in 作业未设置
`ROCFFT_EXPERIMENTAL_BATCH_FUSION`：

```text
batch=2, job=771906:
relative_l2=5.771721e-16
relative_max=7.495125e-16
max_abs=1.255712e-12

batch=3, job=771907:
relative_l2=5.775117e-16
relative_max=6.476903e-16
max_abs=1.182835e-12
```

两次 planner 日志都确认：

```text
producer_length=512,200 -> consumer_length=200,512
streaming=true
FuseKernels=success
wgs/tpb=256/4 -> 400/10
tile width=4/10
ltwd=8/3
transpose=3 (TILE_UNALIGNED)
```

batch=1 的 `102400` 回归也通过，`relative_l2=5.755204e-16`、
`relative_max=6.731134e-16`；未设置诊断变量但保留 fusion opt-in 的 batch=2 回退同样通过，且 planner 日志
没有进入 fusion apply。这证明 batch-local 修复没有破坏既有单 batch 融合，也没有改变默认
关闭时的安全回退路径。

#### 当前边界

本轮证明的是已验证 2D producer/consumer contract 下的 batch=2/3 handoff 正确性，不等于
所有 rocFFT batch、任意 stride、三维布局、planar/half、callback、global-handoff 或其它
large-twiddle 形状都已支持。`producer_stride_out[2]` 也只在当前二维融合 contract 中有
明确含义。当前 batch fusion 仍需显式设置 `ROCFFT_ENABLE_SBCC_SBRC_FUSION=1`，没有改成
普通 rocFFT 默认路径；性能、带宽和更大 batch 的系统性评测仍待后续完成。


<a id="historical-main-exp-049"></a>

### EXP-049：batch 与自定义 distance 回归 [历史 main · 旧编号 EXP-049]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-049`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

EXP-048 修复了 batch-local handoff 映射，但 batch distance 仍可能影响物理偏移、
producer tile 行列和 consumer LDS 索引。因此需要在多个 batch 和非紧凑 distance 下
验证：外层 batch 距离只能改变每个二维平面的基址，不能改变跨阶段 tile 的局部映射。

#### 做了什么

使用 `exp049_validate_batch_dist.py`，在 `hx1hdnormal01` 的 DCU 节点上开启
`ROCFFT_ENABLE_SBCC_SBRC_FUSION=1`、关闭 RTC cache 读取，验证 `102400` 长度的
batch=1/4/8 以及自定义 distance `102912`、`204800`。

#### 修改了什么

本轮没有修改 rocFFT 源码；新增的输入、输出和验证日志属于实验产物。验证脚本使用
Python 3 生成固定种子的 complex-interleaved double 输入，并与 NumPy FFT 比较。

#### 效果

所有用例均进入 `streaming=true`、`FuseKernels=success`，且 planner 诊断确认
`buffer_connected=true`、`buffer_owned=true`、`external_rw=0/0`。代表性结果为：

```text
batch=1, distance=102400: relative_l2=5.771484e-16, relative_max=7.542166e-16
batch=4, distance=102400: relative_l2=5.773013e-16, relative_max=6.914119e-16
batch=8, distance=102400: relative_l2=5.768642e-16, relative_max=7.544667e-16
batch=4, distance=102912: relative_l2=5.762247e-16, relative_max=8.841025e-16
batch=4, distance=204800: relative_l2=5.765789e-16, relative_max=8.015875e-16
```

这些结果证明 batch-local contract 在当前已支持的二维布局中没有因 batch 数或
distance 增加而破坏正确性；它们不代表任意 stride 或任意高维 plan 已经支持。


<a id="historical-main-exp-050"></a>

### EXP-050：planner 级中间 buffer 生命周期 contract [历史 main · 旧编号 EXP-050]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-050`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

仅凭相邻 child 的 `producer.obOut == consumer.obIn` 还不能安全删除 SBCC 与 SBRC
之间的 global store/load：同一个中间 buffer 可能被 plan tree 的其它叶节点读取或
写入，也可能是特殊的临时 buffer。只有 planner 遍历完整 plan tree，排除当前 producer
和 consumer 后，证明该 buffer 没有其它叶级读写，才能把 global intermediate 的
生命周期缩短为当前 fused workgroup 内的 LDS handoff。

本轮采用以下准入条件：

```text
buffer_connected
    && external_reads == 0
    && external_writes == 0
    && buffer != OB_TEMP_BLUESTEIN
```

证明成立后设置 `canElideGlobalHandoff=true`；未证明时融合 shim 返回空并保留原有
global handoff。显式设置 `ROCFFT_SBCC_SBRC_GLOBAL_HANDOFF=1` 仍可强制走 global
handoff，作为 correctness 回退和对照路径。

#### 做了什么

1. 在 planner 的 `L1D_CC` boundary 上收集 producer/consumer 的 buffer、stride、tile
   和 batch 元数据。
2. 新增 `CountExternalBufferUses()`，递归扫描 plan tree 的叶节点，统计中间 buffer
   在 pair 之外的 external read/write 次数。
3. 将 buffer ownership proof 写入 `TileLifetimeDescriptor`，由 `FuseShim::FuseKernels()`
   使用，而不是由 shim 仅凭局部节点猜测生命周期。
4. 补充 fusion debug 输出，直接显示 `can_elide_global_handoff`、`global_handoff`、
   `buffer_connected`、`buffer_owned` 和 `external_rw`。
5. 重新构建、安装并在 DCU 节点运行 correctness、global fallback、默认关闭路径以及
   RTC 源码 dump 核对。

#### 修改了什么

- `library/src/include/tree_node.h`：补充中间 buffer 外部读写计数、ownership proof、
  buffer connection 和 `canElideGlobalHandoff` 字段，并保留生命周期状态枚举。
- `library/src/plan.cpp`：实现 `CountExternalBufferUses()`，在 `AnalyzeTileLifetimes()`
  中生成 planner 级 ownership contract，并在 ApplyFusion 前后刷新 contract。
- `library/src/fuse_shim.cpp`：融合准入改为要求完整 tile mapping 与
  `canElideGlobalHandoff`；`ROCFFT_SBCC_SBRC_GLOBAL_HANDOFF=1` 走显式 global 回退；
  同时修正 contract 诊断输出的字段分隔。

#### 构建与效果

远端 `rocfft` 目标增量构建和安装成功：

```text
[100%] Built target rocfft
cmake --install ...    # 成功更新 install/lib/librocfft.so
```

构建仍有实验树原有的缺少 return、COMGR 不可用和 `llvm-ar: command not found` 提示，
没有出现本轮新增的编译错误。

代表性 fused 运行日志为：

```text
streaming=true
buffer_connected=true
buffer_owned=true
external_rw=0/0
can_elide_global_handoff=true
global_handoff=false
FuseKernels=success
relative_l2=5.762247e-16
relative_max=8.841025e-16
```

RTC dump 中 `producer_buf_out` 和 `consumer_buf_in` 各只在 fused kernel ABI 签名中
出现 1 次，函数体没有对它们进行中间读写；producer 的跨阶段结果写入
`fused_handoff_lds[...]`，consumer 直接从 `fused_handoff_lds` 调用
`fused_rc_lds_to_reg_input`。这确认本轮不仅是 planner 标记变化，而是实际删除了
producer→consumer 的 global handoff。

显式 global 回退也通过相同 correctness：

```text
global_handoff=true
FuseKernels=success
relative_l2=5.762247e-16
relative_max=8.841025e-16
```

未设置融合开关的默认路径同样通过 `relative_l2=5.771066e-16`、
`relative_max=7.016179e-16`，且没有进入 fusion apply，证明默认 planner 行为没有被
实验性 contract 改写。

#### 当前边界与未实现部分

本轮只证明了当前 2D、complex-interleaved double、非 planar、无 callback、producer
direct-register、producer large-twiddle base 至少为 8、consumer 为 plain SBRC、
已证明转置 stride/grid 和相等 batch contract。仍未实现或未证明：任意 stride 和
aliasing、3D、高维复杂 plan、planar/half、callback、其它 large-twiddle 组合、跨多个
独立 consumer 的 buffer 生命周期、系统性性能/带宽收益，以及普通 rocFFT 默认无条件
启用融合。未满足 ownership proof 的计划仍必须保留 global handoff。


<a id="historical-main-exp-051"></a>

### EXP-051：最终诊断输出与安装回归 [历史 main · 旧编号 EXP-051]

> 来源：历史 `main`，提交 `b64aaedd0b3df7cded280b0d42e382193ea3c678`；旧编号 `EXP-051`。原始日期与数据见正文。以下结论按原测量定义保留，不代表当前稳定源码或现行测量标准。


日期：2026-08-24。

#### 原理

planner ownership contract 的关键布尔量必须能在单条运行日志中区分，否则容易把
“tile ownership 不匹配”和“中间 buffer ownership 已证明”混为一谈。可读诊断不改变
执行逻辑，但能直接审计 global handoff 是否被消除。

#### 做了什么

将 fusion debug 输出拆成独立字段，重新构建并安装 rocFFT，在 DCU 节点复跑
`102400`、batch=1 的 fused correctness。

#### 修改了什么

仅调整 `library/src/fuse_shim.cpp` 中的诊断输出排版，新增字段的语义不变；没有改变
planner gate、RTC 生成器或 kernel ABI。

#### 效果

最终日志清晰显示：

```text
buffer_connected=true
buffer_owned=true
external_rw=0/0
can_elide_global_handoff=true
global_handoff=false
FuseKernels=success
relative_l2=5.771484e-16
relative_max=7.542166e-16
```

`rocfft` 目标重新构建和安装成功，默认既有 warning 仍保持原样；本轮没有新增编译
错误。EXP-050 的 planner contract、LDS handoff 和 global fallback 结论不变。
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

### 最终稳定版本复核（2026-09-02）

收尾时稳定分支 `rocfft-opt-pre-tile-lifetime` 的 rocFFT 源码与
`9218fe1e11570ce0d29ebad777873930fe5de278` 完全一致；稳定构建任务为
`798743`，四规模标准 `runall.sh` 任务为 `798744`。本次只确认已经保留的
EXP-057 路径，没有引入 EXP-058 至 EXP-061 的失败实验源码。

| length | raw CSV | T_compute_ms | speedup vs fixed official baseline |
|---:|---|---:|---:|
| 64K | `results/z2z_64k_tuning_20260902_021037.csv.hipkernel.csv` | `3.636654182` | `1.026354x` (`+2.5677%`) |
| 128K | `results/z2z_128k_tuning_20260902_021037.csv.hipkernel.csv` | `7.932508455` | `1.128880x` (`+11.4166%`) |
| 256K | `results/z2z_256k_tuning_20260902_021037.csv.hipkernel.csv` | `18.145020727` | `1.066982x` (`+6.2777%`) |
| 512K | `results/z2z_512k_tuning_20260902_021037.csv.hipkernel.csv` | `39.087328909` | `1.803897x` (`+44.5645%`) |

时间均按 `TotalDurationNs` 减去 `generate_random_interleaved_data_kernel`，
再除以 `11` 计算；这是 hipprof GPU-kernel 时间，不包含 host launch 和
其它未 profile 的运行时开销。四规模 z2z correctness 未在本次 runall 中
重复执行；512K 稳定版本 correctness 已由 EXP-057/EXP-058 的
`relative_l2`、`relative_max` 和 `max_abs` 结果覆盖。

稳定分支当前应保持 EXP-057 的源码版本；EXP-058、EXP-059、EXP-060、
EXP-061 分支和标签仅作为失败/否证实验档案，不合并。

### EXP-063：SBRC-512 混合 radix `[16,16,2]`（否定）

日期：2026-09-02。实验分支从稳定版本创建，只修改
`device/kernels/configs/config_sbrc.py` 中 length=512 的 SBRC 配置，保持
WGS=512、TPT=128 和 512 点 tile 不变，将 `[8,8,8]` 改为 `[16,16,2]`。
构建任务 `799439` 完成；correctness 任务 `799451` 通过，误差为
`relative_l2=6.587307e-16`、`relative_max=9.235930e-16`、
`max_abs=3.470709e-12`。plan 确认实际命中
`fft_rtc_fwd_len_512_factors_16_16_2_wgs_512_tpt_128`。

标准 DP z2z、batch=1000、`-N 10` benchmark `799456` 的 canonical FFT
时间为 `44.928196 ms`，其中 SBRC-512 为 `23.393422 ms`、SBCC-1024 为
`21.534774 ms`。相对稳定版本 `39.087328909 ms` 回归约 `14.93%`，故该
候选已回退到 `[8,8,8]`，不收集 PMC、不扩展到其它长度，也不合并稳定分支。

### EXP-064：stage-aware XOR LDS mapping（计划）

日期：2026-09-02。起点为 EXP-063 回退后的实验分支，runtime 源码中
SBRC-512 已恢复 `[8,8,8]`。

代码事实：`stockham_gen_base.h::lds_address()` 当前在 DP half-LDS 且
length=512/1024 时，对所有经过该 helper 的 LDS load/store 无条件计算
`addr ^ (addr >> 4)` 或 `addr ^ (addr >> 6)`。生成器同时保留每个
Stockham pass 的 `npass`、`width` 和 `cumheight`，所以可以验证只对早期
跨线程重排边界启用 XOR，而让后期大 stride/线性边界使用原始地址。

假设：XOR 对早期 group-stride LDS 访问有益，但对不需要该打散的后期
访问只增加整数地址指令和地址重排成本。实验只改变地址映射的启用条件，
不改变 radix、WGS、TPT、LDS 容量、同步或 transform ownership。

计划：先给 load/store generator 增加明确的 stage-aware swizzle 参数，
对目标 SBCC-1024 `[8,8,4,4]` 保留早期 pass 的映射、关闭后期 pass 的映射；
同时保留其它路径的现状。先检查生成 RTC 源码，再做 correctness 和
512K canonical benchmark；只有时间改善超过噪声才收集 PMC，并评估是否
需要对 512/256/128/64K 建立独立 gate。
候选已回退到 `[8,8,8]`，不收集 PMC、不扩展到其它长度，也不合并稳定分支。

#### EXP-064 实测收尾

源码修改仅存在于 `stockham_gen_base.h`，并限定为目标 SBCC-1024
`[8,8,4,4]`、WGS=256、TPT=64、DP half-LDS。boundary 0 保留 XOR
地址映射，boundary 1 及之后成对使用原始地址，以保持 store/load 布局
契约；其它 kernel 和同步逻辑不变。构建任务 `799495` 完成。

correctness 任务 `799514` 通过：`relative_l2=6.645150e-16`、
`relative_max=9.451432e-16`、`max_abs=3.551690e-12`。两次标准 DP z2z、
batch=1000、`-N 10` benchmark 均命中目标 SBCC-1024 和原 SBRC-512：

| run | raw CSV | T_compute_ms | vs stable |
|---|---|---:|---:|
| `799519` | `results/z2z_512k_b1000_exp064_20260902_134457.csv.hipkernel.csv` | `39.473405` | `-0.9865%` |
| `799524` | `results/z2z_512k_b1000_exp064repeat_20260902_134638.csv.hipkernel.csv` | `39.470121` | `-0.9781%` |

稳定参考为 `39.087328909 ms`，两次均回归约 `0.98%`，因此该方向在
512K 目标路径也不是稳定优化。按停止条件已回退全部 EXP-064 runtime
改动，不收集 PMC，也不扩展到其它长度；只保留本记录和原始 CSV。

### EXP-065：SBCC-1024 ordinary-twiddle recurrence（计划）

起始稳定提交：`c38e0d3f4daa4fd53d6985f331f873c4e9e16d4b`，目标分支：
`exp-065-ordinary-twiddle-recurrence`。目标为 512K DP z2z、batch=1000、
`-N 10`，精确命中 SBCC-1024 `[8,8,4,4]`、WGS=256、TPT=64、DP
half-LDS、large-twiddle base=8/3-step 路径。

代码事实：`stockham_gen_base.h::apply_twiddle_generator()` 当前对每个
`w=1..width-1` 都直接读取 `twiddles[tidx]`，其中同一线程的 `tidx`
随 `w` 连续增加；该函数与已经存在的 `StockhamKernelCC` large-twiddle
递推是两条不同路径。候选利用同一 radix butterfly 内连续 twiddle 是
同一基 twiddle 的幂这一布局契约：读取 `w=1` 的基值一次，在寄存器中
递推得到后续幂次，再分别乘到 R。它不改 Stockham 数据布局、LDS 地址、
barrier、radix、WGS 或 TPT。

实现限制：只在 DP、length=1024、factors=`[8,8,4,4]`、WGS=256、
TPT=64、目标 SBCC generator 中启用；其它 length、SBRC、precision、
factor 组合保持原路径。修改前先建立实验分支和本计划提交；随后检查
RTC 源码中命中条件、执行 correctness，再按 `agents.me` 的 canonical
`T_compute_ms` 做至少两次 512K benchmark。若 twiddle 表连续项不是幂次
关系、correctness 失败、RTC 未命中，或额外 VALU/VGPR 使两次 benchmark
均无改善，则立即回退 runtime 修改并记录 PMC 或源码证据，不合并稳定分支。

预期收益：减少目标 stage 的 ordinary twiddle global load，理论上最多
从每个 radix-8 butterfly 的 7 次降为 1 次；代价是额外复数乘法和一个
基 twiddle 的寄存器生命周期。收益预估为 0--5%，不是实测结论。即使
512K 目标路径有效，也必须单独评估 64K/128K/256K 是否共享相同的
 generator gate，不能自动扩大适用范围。

#### EXP-065 实测结果

源码提交：`43f9c753`；构建任务：`800561`，首次构建因 const helper
声明错误失败的任务为 `800554`，该失败不产生安装结果。correctness 任务：
`800582`，通过，结果为 `relative_l2=6.604511e-16`、
`relative_max=8.405844e-16`、`max_abs=3.158776e-12`。

两次标准 512K DP z2z、batch=1000、`-N 10` benchmark：

| job | raw CSV | Total row ns | bench-only ns | T_compute_ms | vs stable |
|---:|---|---:|---:|---:|---:|
| `800591` | `results/z2z_512k_b1000_exp065_ordinaryrecur_20260902_203809.csv.hipkernel.csv` | `2833729707` | `2406752681` | `38.816093273` | `1.006987711x`, `+0.693922%` |
| `800592` | `results/z2z_512k_b1000_exp065_ordinaryrecur_20260902_203819.csv.hipkernel.csv` | `2833764484` | `2406751915` | `38.819324455` | `1.006903893x`, `+0.685656%` |

计算使用 `(Total - generate_random_interleaved_data_kernel) / 11`；稳定
参考为 `39.087328909 ms`。两次结果方向一致，平均为 `38.817708864 ms`，
相对稳定版本改善约 `0.690%`。这是 hipprof GPU-kernel canonical 时间，
不包含 host launch 和未 profile 的 runtime 开销。

PMC 任务：`800605`，原始文件：
`results/pmcall_524288_exp065_ordinary_recur.csv`。目标
SBCC-1024 行显示 `arch_vgpr=152`、`SQ_INSTS_LDS=74.752M`、
`SQ_INSTS_VALU=635.904M`、`SQ_INSTS_VMEM_RD=12.800M`、
`SQ_INSTS_VMEM_WR=8.192M`、`SQ_LDS_BANK_CONFLICT=241.876M`。
历史同 TPT=64 的参考文件
`results/pmcall_524288_exp057_late_lds.csv` 显示
`arch_vgpr=216`、`SQ_INSTS_LDS=74.752M`、`SQ_INSTS_VALU=601.600M`、
`SQ_INSTS_VMEM_RD=20.992M`、`SQ_INSTS_VMEM_WR=8.192M`、
`SQ_LDS_BANK_CONFLICT=241.876M`。因此本实现确实减少了 ordinary-twiddle
global read，但增加了约 `5.70%` VALU；LDS 和 bank conflict 没有变化。
PMC 的运行条件包含 `ROCFFT_RTC_CACHE_READ_DISABLE=1`，所以资源计数用于
机制佐证，不替代两次 canonical benchmark。

决策：保留在 EXP-065 分支，并合入稳定分支作为 512K DP z2z 目标路径的
稳定优化。当前 gate 只覆盖 SBCC-1024 `[8,8,4,4]`、WGS=256、TPT=64、
DP half-LDS；不扩大到 64K/128K/256K，后续如需跨规模必须新建实验并独立
correctness/benchmark。该结果不证明 ordinary-twiddle recurrence 对所有
radix 或所有 rocFFT kernel 都有效。

### EXP-070：缩减 late large-twiddle LDS 上传范围（计划）

日期：2026-09-03。起始稳定提交：
`d26bdf9c10785a48dd02f78fe5dc38477c5698d3`；目标分支：
`exp-070-compact-late-ltwd-upload`。目标为 512K DP z2z、batch=1000、
`-N 10` 的 SBCC-1024 `[8,8,4,4]`、WGS=256、TPT=64、DP half-LDS、
large-twiddle base=8/3-step 路径。

代码事实：EXP-057 保留的 late-LDS 路径在最后 Stockham pass 后复用已经
死亡的 row-data LDS，但 `stockham_gen_cc.h::large_twiddles_multiply()` 仍由
每个 workgroup 上传完整 `3 * (1 << 8) = 768` 个 DP complex 表项。
`large_twiddles.h::TW_NSteps()` 将索引 `u` 分成三个 8-bit 段，访问范围分别
为 `[0,255]`、`[256,511]` 和 `512 + ((u >> 16) & 255)`。

实际生成的目标 RTC 源码显示，EXP-057/065 large-twiddle recurrence 只执行
`TW_NSteps(..., 256 * trans_local)` 和
`TW_NSteps(..., q * trans_local)`，其中 `q` 由四组起始项覆盖 `[0,255]`。
512K 的第二维 transform 索引为 `trans_local=0..511`，故最大 `u` 是
`256 * 511 = 130816`，第三段只可能访问 LUT 索引 `512` 或 `513`。
因此目标 tile 实际所需的连续前缀为 `[0,513]`，共 514 项；上传 768 项中
有 254 项不会被读取，占 `33.0729%`。

实现只修改 late-LDS 协作上传循环的上限：当 `trans_local < 512` 时使用
514，否则仍使用完整 `ltwd_entries`。目标 SBCC 每 block 处理四个连续、
4 对齐的 transform，所以 `<512` 判定在 block 内一致；最后一个目标 block
为 `508..511`，下一个 block 为 `512..515`，不会跨越条件边界。该运行时
回退防止同一 kernel 模板处理更大第二维时漏传第三段表项。

该候选不改变 `TW_NSteps`、复数乘法次数、twiddle 数值、LDS 分配大小、
barrier、radix、WGS/TPT、Stockham layout 或 tile ownership。预期只减少
目标 SBCC 每 workgroup 254 次 global-to-LDS DP complex copy；代价是上传
循环多一个统一上限选择和第三轮仅两个线程有效。收益预估为 0--2%，不是
实测结论。

验证顺序：检查生成 RTC 循环上限确为
`trans_local < 512 ? 514 : 768`，并确认所有 `TW_NSteps` 索引满足证明；再做
512K correctness，最后按 `agents.me` 运行至少两次标准 benchmark。若 RTC
未命中、correctness 失败或两次 canonical 时间均不优于 EXP-065 平均
`38.817708864 ms`，则回退 runtime 源码并保留分支、日志和原始 CSV。
只有 512K 目标路径得到重复的同向收益才可作为该精确 gate 的稳定优化；
该实验不自动推广到 64K/128K/256K，因为它们不走同一 SBCC-1024 gate。

### EXP-071：跨规模 ordinary-twiddle recurrence（计划）

日期：2026-09-04。实验分支：`exp-071-cross-scale-ordinary-recurrence`。
实验前源码稳定提交：`d26bdf9c10785a48dd02f78fe5dc38477c5698d3`；
实验前标签：`pre-exp-071-cross-scale-20260904`。

目标：回顾 EXP-065 在 512K DP z2z 的 SBCC-1024 上保留的
ordinary-twiddle recurrence，并验证它能否按实际 planner 配置推广到
64K、128K、256K。标准条件固定为 DP z2z、batch=1000、`-N 10`、
`hipprof --stats`、gfx936；固定 baseline 使用 `agents.me` 中四个
官方 7.2.2 CSV，canonical 时间严格按其 `TotalDurationNs` 公式计算。

代码事实：`stockham_gen_base.h::apply_twiddle_generator()` 的原路径对
每个 `w=1..width-1` 读取一个 ordinary-twiddle LUT 项。对同一个 radix
butterfly，rocFFT 的 stacked twiddle 表满足这些项是同一个基础 twiddle
的连续幂。EXP-065 已在 `[8,8,4,4]` 上用一次基础项加载和寄存器复乘替代
重复 LUT 读取，并通过 correctness 和两次 benchmark 证明收益。

本实验只扩大 gate，不改变 Stockham 布局、LDS 地址、barrier、radix、
WGS、TPT 或 transform ownership。实际目标 gate 为：

| FFT | SBCC factors | actual WGS | TPT | source length |
|---:|---|---:|---:|---:|
| 64K | `[8,4,8]` | 256 | 32 | 256 |
| 128K | `[8,4,8]` | 256 | 32 | 256 |
| 256K | `[8,8,8]` | 256 | 64 | 512 |
| 512K control | `[8,8,4,4]` | 256 | 64 | 1024 |

先以静态公式检查每个 gate 的 `base_tidx` 与原始 `tidx` 的关系：
对于 `w=1..width-1`，递推值必须等于原表项的对应幂；随后检查 RTC
源码命中目标 CC kernel。correctness 必须覆盖四个长度；性能至少对四个
长度各运行两次。任一 correctness 失败、RTC 未命中或某一新增规模两次
都回归，则只保留实验分支和证据，不扩大稳定 gate。若新增规模同向改善，
按每个长度分别比较固定官方 baseline 和实验前有效版本，不能用 512K
结果推断其它规模收益。

本实验不重新测试 EXP-054 的 register-local exchange、EXP-057 的
late-LDS、已有的 half-LDS/XOR/scalar-LDS，也不把它们作为本轮新变量；
这些方向的跨规模状态以历史记录为准。若 ordinary recurrence 通过，
后续再为其它方向建立独立 EXP 编号。

#### EXP-071 实测收尾

实施提交为 `304568dda4fd09139a116c2c77018e128508e4ec`。运行时代码只在
`stockham_gen_base.h::use_ordinary_twiddle_recurrence()` 中增加两个精确
配置：SBCC-256 `[8,4,8]`/WGS=256/TPT=32 和 SBCC-512
`[8,8,8]`/WGS=256/TPT=64；EXP-065 已保留的 SBCC-1024 gate 不变。
构建任务 `805019` 成功，安装完成时间为 2026-09-04 12:51:27。EXP-070
在此之前只有计划文档，没有运行时代码、构建或性能结果；本轮安装相对
稳定提交 `d26bdf9c` 的唯一 runtime 变量就是上述 gate 扩展。

RTC 源码检查任务 `805262` 成功，日志为
`logs/exp071_rtc_65536.log`、`logs/exp071_rtc_131072.log` 和
`logs/exp071_rtc_262144.log`。目标 SBCC-256 的三个 ordinary-twiddle
stage 分别只出现一次 `W = twiddles[...]` 基项加载，SBCC-512 的两个
radix-8 stage 也分别只出现一次基项加载；后续幂由 `W*W`、`t*W` 递推。
这确认生成代码命中了候选路径，而不只是 kernel 名称相同。

四规模 correctness 均通过：

| length | job | relative_l2 | relative_max | max_abs |
|---:|---:|---:|---:|---:|
| 64K | `805192` | `7.124917e-16` | `1.156407e-15` | `1.325805e-12` |
| 128K | `805193` | `6.801758e-16` | `9.776713e-16` | `1.792371e-12` |
| 256K | `805194` | `6.565662e-16` | `8.565374e-16` | `2.285077e-12` |
| 512K control | `805195` | `6.604511e-16` | `8.405844e-16` | `3.158776e-12` |

性能任务 `805230` 在同一个 allocation 和同一 GPU `a01r3n18` 上串行完成
全部八次测量。每次均为 DP z2z、batch=1000、`-N 10`、
`hipprof --stats`。下表严格使用
`(TotalDurationNs - generate_random_interleaved_data_kernel) / 11 / 1e6`：

| length/run | raw CSV | T_compute_ms | vs previous valid | vs fixed official baseline |
|---|---|---:|---:|---:|
| 64K r1 | `results/z2z_64k_b1000_exp071_recur_r1_20260904_142427.csv.hipkernel.csv` | `3.617758818` | `1.005222947x`, `+0.519581%` | `1.031714185x`, `+3.073931%` |
| 64K r2 | `results/z2z_64k_b1000_exp071_recur_r2_20260904_142453.csv.hipkernel.csv` | `3.615984818` | `1.005716109x`, `+0.568362%` | `1.032220344x`, `+3.121460%` |
| 128K r1 | `results/z2z_128k_b1000_exp071_recur_r1_20260904_142432.csv.hipkernel.csv` | `7.925117455` | `1.000932604x`, `+0.093174%` | `1.129933033x`, `+11.499180%` |
| 128K r2 | `results/z2z_128k_b1000_exp071_recur_r2_20260904_142458.csv.hipkernel.csv` | `7.925990818` | `1.000822312x`, `+0.082164%` | `1.129808526x`, `+11.489427%` |
| 256K r1 | `results/z2z_256k_b1000_exp071_recur_r1_20260904_142438.csv.hipkernel.csv` | `17.729775909` | `1.023420760x`, `+2.288478%` | `1.091971926x`, `+8.422554%` |
| 256K r2 | `results/z2z_256k_b1000_exp071_recur_r2_20260904_142503.csv.hipkernel.csv` | `17.728894364` | `1.023471648x`, `+2.293336%` | `1.092026223x`, `+8.427107%` |
| 512K r1 | `results/z2z_512k_b1000_exp071_recur_r1_20260904_142444.csv.hipkernel.csv` | `38.875532000` | `0.998512608x`, `-0.148961%` | `1.813724836x`, `+44.864845%` |
| 512K r2 | `results/z2z_512k_b1000_exp071_recur_r2_20260904_142509.csv.hipkernel.csv` | `38.828992727` | `0.999709396x`, `-0.029069%` | `1.815898713x`, `+44.930849%` |

64K/128K/256K 的 previous-valid 参考分别为稳定复核文件
`results/z2z_64k_tuning_20260902_021037.csv.hipkernel.csv`、
`results/z2z_128k_tuning_20260902_021037.csv.hipkernel.csv`、
`results/z2z_256k_tuning_20260902_021037.csv.hipkernel.csv`，对应
`3.636654182/7.932508455/18.145020727 ms`。这些 kernel 在 EXP-065 中未被
修改。512K previous-valid 取 EXP-065 两次平均 `38.817708864 ms`。固定
官方基线依次为 `3.732493091/8.954852000/19.360417545/70.509517909 ms`。

两次实验平均结果为：

| length | mean T_compute_ms | mean vs previous valid | mean vs fixed baseline |
|---:|---:|---:|---:|
| 64K | `3.616871818` | `1.005469468x`, `+0.543972%` | `1.031967202x`, `+3.097696%` |
| 128K | `7.925554136` | `1.000877455x`, `+0.087669%` | `1.129870776x`, `+11.494303%` |
| 256K | `17.729335136` | `1.023446203x`, `+2.290907%` | `1.091999074x`, `+8.424831%` |
| 512K control | `38.852262364` | `0.999110644x`, `-0.089015%` | `1.814811123x`, `+44.897847%` |

PMC 首次任务 `805241` 因命令错误地覆盖 `LD_LIBRARY_PATH`、缺少
`libperfetto.so.5` 而在采样前失败；修正为追加路径后的任务 `805246`
成功。原始文件为 `results/pmcall_65536_exp071_recur.csv`、
`results/pmcall_131072_exp071_recur.csv`、
`results/pmcall_262144_exp071_recur.csv`。与未启用 recurrence 的同名
SBCC PMC 参考 `pmcall_*_current_20260830.csv` 比较：

| length | arch_vgpr | SQ_INSTS_VMEM_RD | SQ_INSTS_VALU | SQ_INSTS_LDS | VMEM_WR | bank conflict |
|---:|---:|---:|---:|---:|---:|---:|
| 64K | `72 -> 84` | `2.688M -> 1.664M` (`-38.10%`) | `56.704M -> 61.056M` (`+7.67%`) | `4.992M -> 4.992M` | `1.024M -> 1.024M` | `8.192M -> 8.192M` |
| 128K | `68 -> 84` | `5.632M -> 3.584M` (`-36.36%`) | `115.968M -> 122.880M` (`+5.96%`) | `9.984M -> 9.984M` | `2.048M -> 2.048M` | `16.384M -> 16.384M` |
| 256K | `68 -> 84` | `13.312M -> 7.168M` (`-46.15%`) | `272.896M -> 297.472M` (`+9.01%`) | `32.768M -> 32.768M` | `4.096M -> 4.096M` | `32.768M -> 32.768M` |

机制结论与 EXP-065 一致：候选确实把 ordinary-twiddle global loads 换成
寄存器复数乘法；它没有改变 LDS 往返或 bank conflict。256K 的 load
减少足以覆盖额外 VALU/VGPR，得到稳定约 `2.29%` 的整体收益。64K 两次
均小幅改善，平均约 `0.54%`。128K 两次只有约 `0.09%`，应记为性能基本
持平，不能宣称有显著独立收益。512K gate 与 EXP-065 完全相同，当前
`-0.089%` 是未改变源码路径的控制波动，不归因于本轮 gate 扩展。

决策：保留新增 SBCC-512 gate，作为 256K DP z2z 目标路径的稳定优化；
同时保留 SBCC-256 gate，因为它在 64K 两次同向改善、在共享该生成配置的
128K 未产生回归。继续严格限制于已测 DP half-LDS/direct-register 的精确
factors、WGS 和 TPT，不推广到其它 precision、radix 或 kernel。该提交可
合入 `rocfft-opt-pre-tile-lifetime`；最终 merge commit 和稳定 tag 在合并
收尾记录中补充。

稳定合并收尾：实验结果记录提交为
`39d5b8722840e2f482858825a578aa949aace46b`；经全部 correctness、两轮
四规模 benchmark、RTC 源码检查和 PMC 机制验证后，以非快进方式合入
`rocfft-opt-pre-tile-lifetime`。有效 runtime merge commit 为
`b080fd0222506dbee4e58c550748c92130bc0132`，稳定标签为
`stable-exp071-cross-scale-recurrence-20260904`。实验分支和原始证据保留，
用户已有的 `VkFFT` 子模块及验证二进制工作区修改未纳入本次提交。
### EXP-072：SBCC-256 的 DP half-LDS XOR swizzle（计划）

日期：2026-09-04。实验分支：exp-072-sbcc256-xor。起点为当前稳定
提交 7d86ea2a（有效 runtime 为 b080fd02）。目标是把已经在
SBCC-512/1024 使用的 LDS 地址 XOR 映射，按实际地址布局推广到
SBCC-256 [8,4,8]、WGS=256、TPT=32；该 producer 同时出现在
64K 和 128K 的 DP z2z 路径中。

代码事实：stockham_gen_base.h::lds_address() 当前只对 length=512
使用 addr ^ (addr >> 4)，对 length=1024 使用
addr ^ (addr >> 6)，length=256 返回原始地址。EXP-071 生成的
SBCC-256 RTC 中，half-LDS 的非线性地址以 stride_lds=8 展开，
pass 0 的 store 和后续 pass 的 LDS exchange 产生重复的 bank 周期。
因此本实验只加入 length=256、factors=[8,4,8]、DP half-LDS 的
addr ^ (addr >> 3) gate；不影响 SBRC-256 的 [4,4,4,4]，
也不改变 LDS 分配、Stockham layout、barrier、radix、WGS、TPT 或
twiddle 计算。

预期收益：只减少目标 SBCC-256 内部 LDS bank conflict，代价是每次
LDS 地址多一个 XOR/shift；结构分析预估为 0--3%，不是实测结论。
验证顺序为修改后 build，检查 64K/128K RTC 命中，再做四规模中受影响
的 64K/128K correctness，最后按标准条件各运行至少两次 benchmark，
必要时用 PMC 比较 bank-conflict 和地址计算代价。若 correctness 失败、
RTC 未命中、或 64K/128K 两次均无同向收益，则回退 runtime，只保留
实验记录和证据；不把旧的 halfxor_sizes 文件当作本轮有效 A/B，
因为其源码版本和 LDS footprint 与当前稳定版本不同。
#### EXP-072 实测收尾

源码提交为 ee3fe0de，分支为 exp-072-sbcc256-xor；构建任务 805542 于
2026-09-04 16:14:37 成功完成，安装目录为 /public/home/zhangkewei/zr/install。
静态检查确认 RTC 只对 length=256、factors [8,4,8]、DP half-LDS 的 SBCC
生成 addr ^ (addr >> 3)；SBRC-256 的 [4,4,4,4] 不命中该条件。

correctness 任务 805558（64K）和 805559（128K）均通过：

| length | job | relative_l2 | relative_max | max_abs |
|---:|---:|---:|---:|---:|
| 64K | 805558 | 7.124917e-16 | 1.156407e-15 | 1.325805e-12 |
| 128K | 805559 | 6.801758e-16 | 9.776713e-16 | 1.792371e-12 |

性能任务为 805560/805561（64K 两轮）和 805562/805563（128K 两轮），均为
DP z2z、batch=1000、-N 10、hipprof --stats。canonical 时间按
(TotalDurationNs - generate_random_interleaved_data_kernel) / 11 / 1e6 计算：

| length/run | raw CSV | T_compute_ms | vs previous valid | vs fixed official baseline |
|---|---|---:|---:|---:|
| 64K r1 | results/z2z_64k_b1000_exp072_xor_r1_20260904_161912.csv.hipkernel.csv | 3.605203364 | 1.003222837x, +0.322284% | 1.035294182x, +3.529418% |
| 64K r2 | results/z2z_64k_b1000_exp072_xor_r2_20260904_161912.csv.hipkernel.csv | 3.606294000 | 1.002919689x, +0.291969% | 1.034981660x, +3.498166% |
| 128K r1 | results/z2z_128k_b1000_exp072_xor_r1_20260904_162112.csv.hipkernel.csv | 7.890031364 | 1.004499083x, +0.449908% | 1.134999699x, +13.499970% |
| 128K r2 | results/z2z_128k_b1000_exp072_xor_r2_20260904_162112.csv.hipkernel.csv | 7.889722182 | 1.004538759x, +0.453876% | 1.134960215x, +13.496022% |

EXP-071 的 previous-valid 平均时间为 3.616871818/7.925554136 ms，固定官方
7.2.2 baseline 为 3.732493091/8.954852000 ms。两次实验平均为：

| length | mean T_compute_ms | vs previous valid | vs fixed official baseline |
|---:|---:|---:|---:|
| 64K | 3.605748682 | 1.003084834x, +0.308483% | 1.035150650x, +3.515065% |
| 128K | 7.889876773 | 1.004521916x, +0.452192% | 1.134979957x, +13.497996% |

决策：保留该推广。两种受影响规模的两轮测量均同向改善，correctness 和
RTC gate 均通过；收益较小，因此只把 addr ^ (addr >> 3) 保留在 SBCC-256
[8,4,8]、WGS=256、TPT=32、DP half-LDS 条件下，不推广到 SBRC-256 或其它
precision/factor。原始 CSV 和日志保留在 results/ 与 logs/，实验分支保留，
待合入稳定分支后再建立下一项 EXP。
### EXP-073：SBRC-256 DP scalar-LDS 跨规模推广（计划）

日期：2026-09-04。实验分支：exp-073-sbrc256-scalar-lds。
实验前有效提交：e53d182b；实验前标签：pre-exp-073-sbrc256-scalar-lds-20260904。

目标：验证 64K DP z2z 路径的 SBRC-256 [4,4,4,4]、WGS=256、TPT=32 是否
可以安全使用与 SBRC-512 相同的内部 scalar-LDS 机制。当前 64K 路径中的
SBRC-256 是该机制尚未覆盖的实际 consumer；128K/256K/512K 使用的
SBRC-512 [8,8,8]、TPT=128 已在稳定版本中命中现有 gate，本轮不改变它。

代码事实：stockham_gen_rc.h::set_lds_is_real() 目前只在 direct_to_from_reg、
DP、length=512、TPT=128、factors=[8,8,8] 时返回 true。generate_device_function()
在 lds_is_real=true 时保留初始 global-to-complex-LDS transpose 和寄存器装载，
仅把内部 Stockham exchange 的 complex LDS store/load 改为 REAL/IMAG 两个
scalar-LDS 路径；该条件不会改变 Stockham factor、layout、barrier 或 global
读写。64K 的实际 SBRC kernel 已由 EXP-072 CSV 确认为 length=256、
factors=[4,4,4,4]、WGS=256、TPT=32、unitstride_sbrc_aligned。

实施只在 internal_scalar_lds 条件中增加 length=256、TPT=32、
factors=[4,4,4,4]、DP、direct_to_from_reg 这一精确 gate。预期收益为
0--3%，来源可能是内部 LDS 数据路径的资源/访问粒度变化；代价是每个
complex exchange 拆成两个 scalar LDS 操作，可能增加 LDS 指令或地址压力。
必须比较 arch_vgpr、SQ_INSTS_LDS、bank conflict 和 canonical 时间，不能
仅凭 lds_is_real=true 判定有效。

验证：先检查生成 RTC 命中 SBRC-256 scalar-LDS 且其它规模保持原路径；再
运行 64K correctness，并以 128K/256K/512K correctness 作为未受影响控制。
性能对四种长度各运行两轮，固定 DP z2z、batch=1000、-N 10 和 agents.me
的 canonical 公式。若 64K 任一 correctness 失败或两轮均未改善，则保留
实验分支和证据并回退 gate；只有 64K 两轮同向改善且其它规模无回归时，
才合入稳定分支。

#### EXP-073 实测收尾

实验计划提交为 ffa53aa0e4ba236842e2ca79eeba4dbd94b6a293；本轮源码 gate 仅存在于
实验工作树，实验分支为
exp-073-sbrc256-scalar-lds。构建任务 805654 成功；实验源码随后已回退，
因此该分支当前只保留本实验计划、结果记录和证据，稳定分支没有引入该 gate。
RTC 检查日志为 logs/exp073_rtc_65536.log，确认生成的
forward_length256_SBRC_device 使用 const bool lds_is_real = true，
说明新增条件实际命中 SBRC-256，而不是只命中宿主端配置。

正确性任务为 64K 805672、128K 805675、256K 805676 和 512K
805677，全部通过：

| length | job | relative_l2 | relative_max | max_abs |
|---:|---:|---:|---:|---:|
| 64K | 805672 | 7.124917e-16 | 1.156407e-15 | 1.325805e-12 |
| 128K | 805675 | 6.801758e-16 | 9.776713e-16 | 1.792371e-12 |
| 256K | 805676 | 6.565662e-16 | 8.565374e-16 | 2.285077e-12 |
| 512K | 805677 | 6.604511e-16 | 8.405844e-16 | 3.158776e-12 |

标准 benchmark 任务为 64K 805679/805680、128K 805681/805682、
256K 805683/805684 和 512K 805685/805699。原始 CSV 为：

- results/z2z_64k_b1000_exp073_sbrc256_a_20260904_170320.csv.hipkernel.csv
- results/z2z_64k_b1000_exp073_sbrc256_b_20260904_170520.csv.hipkernel.csv
- results/z2z_128k_b1000_exp073_sbrc256_128_a_20260904_170721.csv.hipkernel.csv
- results/z2z_128k_b1000_exp073_sbrc256_128_b_20260904_170921.csv.hipkernel.csv
- results/z2z_256k_b1000_exp073_sbrc256_256_a_20260904_171121.csv.hipkernel.csv
- results/z2z_256k_b1000_exp073_sbrc256_256_b_20260904_171322.csv.hipkernel.csv
- results/z2z_512k_b1000_exp073_sbrc256_512_a_20260904_171522.csv.hipkernel.csv
- results/z2z_512k_b1000_exp073_sbrc256_512_b_20260904_171522.csv.hipkernel.csv

每个结果均使用 T_compute_ms = (TotalDurationNs - generate_random_interleaved_data_kernel) / 11 / 1e6：

| length | EXP-073 mean ms | previous-valid mean ms | speedup vs previous | fixed baseline ms | speedup vs baseline |
|---:|---:|---:|---:|---:|---:|
| 64K | 3.703260000 | 3.605748682 | 0.973668790x (-2.704329%) | 3.732493091 | 1.007893880x (+0.783205%) |
| 128K | 7.889983864 | 7.889876773 | 0.999986427x (-0.001357%) | 8.954852000 | 1.134964552x (+11.891521%) |
| 256K | 17.729552955 | 17.729335136 | 0.999987714x (-0.001229%) | 19.360417545 | 1.091985658x (+8.423706%) |
| 512K | 38.815642545 | 38.852262364 | 1.000943429x (+0.094254%) | 70.509517909 | 1.816523270x (+44.949783%) |

64K 的新增 gate 两次均回归，平均从 3.605748682 ms 增加到
3.703260000 ms，回归约 2.704%。128K、256K 和 512K 的 RTC 没有
命中新 SBRC-256 条件；它们的时间只能说明回退后的控制路径没有明显旁路
回归，不能归因于 scalar-LDS。该实现将 complex LDS exchange 拆成
REAL/IMAG 两个 scalar-LDS 访问，正确性保持，但新增地址/访存粒度并未
带来端到端收益。

决策：拒绝 SBRC-256 scalar-LDS 跨规模推广，源码 gate 已回退，不合并稳定
分支；保留实验分支、job 日志和八个 raw CSV 作为失败证据。后续从新的
EXP-074 编号开始，必须从稳定提交 e53d182b 建立独立分支。
### EXP-074：可推广 512K 优化的跨规模审计与 late-LDS gate 试验（计划）

日期：2026-09-04。实验分支：exp-074-cross-size-reglocal-late-lds。
起点稳定提交：7bababec；起点标签：pre-exp-074-cross-size-20260904。

目标：对此前 512K 路径中尚未完成跨规模验证的两类修改进行事实审计：
(1) SBCC-1024 [8,8,4,4]/TPT=64 的 register-local 4x4 exchange；
(2) SBCC-1024 的 late large-twiddle LDS reuse。只把能够由当前生成器的
索引公式和 LDS 生命周期证明的条件，建立为小规模的独立精确 gate；不改变
planner 分解、radix、WGS、TPT、Stockham layout 或 global handoff。

代码审计结果：

- stockham_gen_base.h::use_register_local_exchange() 当前要求
  half_lds && DP && length=1024 && factors=[8,8,4,4] && TPT=64 &&
  npass=2。其正确性证明是 pass 2 的 radix-4 store 与 pass 3 的 radix-4
  load 在同一线程内形成 4x4 转置。目标 64K/128K 的 SBCC-256
  [8,4,8] 和 256K 的 SBCC-512 [8,8,8] 不具备相同的相邻
  radix-4/radix-4 边界，因此本方向对这些尺寸目前是静态不可推广，不应
 只扩宽 length 条件。

- stockham_gen_cc.h::use_late_large_twiddle_lds() 当前要求
  direct_to_from_reg && half_lds && DP && length=1024 && WGS=256 &&
  TPT=64 && TPB=4 && factors=[8,8,4,4]。该 gate 复用 lds_complex 起始
  位置；large_twiddles_multiply() 在最终 pass 后协作上传，随后通过两次
  block barrier 读取。对小规模 gate，必须重新确认 direct_load_to_reg
  生成路径、row_data_end 不超过分配的 LDS、以及实际
  TW_NSteps 最大索引小于上传范围。由于 SBCC-256/512 的 LUT 参数和
  trans_local 范围不同，不能沿用 514 项上限。

- 本计划将后者作为一个跨规模候选族，但每个 gate 仍按实际 kernel 单独验证：
  SBCC-256 [8,4,8]、length=256、WGS=256、TPT=32、TPB=8；
  SBCC-512 [8,8,8]、length=512、WGS=256、TPT=64、TPB=4；
  以及已保留的 SBCC-1024 [8,8,4,4]、length=1024、WGS=256、
  TPT=64、TPB=4。三者均要求 DP、half-LDS、direct-register。
  其中现有 RTC/CSV 显示 64K 的 SBCC-256 为 base=8/steps=2，
  128K 的 SBCC-256 和 256K 的 SBCC-512 为 base=8/steps=3；
  runtime 条件必须同时覆盖 steps=2/3，不能把 512K 的 steps=3
  直接假定为所有长度。
  对每个 gate 先由 RTC/plan 取得 trans_local 和 TW_NSteps 的实际范围，
  计算最大 LUT 项并确认 row_data_end 后的原始 LDS 容量足以容纳 768 项；
  再检查最终 pass 后没有 direct-register 路径继续读取 row-data LDS。
  register-local 方向只做静态审计，不伪造性能结果。

验证顺序：先记录本计划，再做静态审计和 RTC 范围证明；若满足条件，提交
单一源码 gate，执行构建、四规模 correctness，最后对受影响长度至少两轮
标准 DP z2z、batch=1000、-N 10、hipprof --stats benchmark。canonical
时间严格使用 agents.me 的
(TotalDurationNs - generate_random_interleaved_data_kernel) / 11 / 1e6。
若 correctness、RTC 命中、LDS 范围或两轮端到端结果不满足退出条件，回退
runtime gate；保留分支、日志和 raw CSV，不合入稳定分支。
### EXP-074 实测收尾：late-LDS 跨规模推广与 register-local 可推广性审计

日期：2026-09-04。实验分支：exp-074-cross-size-reglocal-late-lds。
稳定起点为提交 7bababec（标签 pre-exp-074-cross-size-20260904）。

本轮实际修改了同一个生成器文件
rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/device/generator/stockham_gen_cc.h。
提交 5b4a99e1 将 late large-twiddle LDS 试验扩展到 SBCC-256
[8,4,8]、SBCC-512 [8,8,8] 和原有 SBCC-1024 [8,8,4,4]，并令
late_large_twiddle_lds_enabled 同时接受 large_twiddle_steps=2/3。
提交 e57d01b9 根据 256K 的实测回归移除 SBCC-512 gate，同时保留
SBCC-256 和 SBCC-1024。回退构建 805913 成功。

register-local 4x4 方向只完成了静态可推广性审计，没有扩宽源码条件。
stockham_gen_base.h::use_register_local_exchange() 仍要求 length=1024、
factors=[8,8,4,4]、TPT=64、npass=2、DP half-LDS。64K/128K 的
SBCC-256 [8,4,8] 和 256K 的 SBCC-512 [8,8,8] 没有相同的相邻
radix-4/radix-4 边界，因此不能只增加 length 条件来复用该 4x4
线程内交换。该结论来自生成器条件和实际 factor，不是性能推测。

late-LDS 的范围检查确认 SBCC-256/512 的 row-data LDS 可容纳 1024 个
complex 槽；base=8 时 2-step/3-step 的上传量分别为 512/768 槽，
因此本轮使用 large_twiddle_steps * 256 作为上传边界，没有沿用只适合
512K 三步表的固定上限。该 gate 仅要求 DP、direct-to/from-register、
half-LDS、WGS=256，并分别绑定实际 length、TPT、TPB 和 factors。

实验版 correctness（提交 5b4a99e1，构建 805862）全部通过：

| length | job | relative_l2 | relative_max | max_abs |
|---:|---:|---:|---:|---:|
| 64K | 805865 | 7.125347e-16 | 1.156407e-15 | 1.325805e-12 |
| 128K | 805866 | 6.799770e-16 | 9.776713e-16 | 1.792371e-12 |
| 256K | 805868 | 6.564081e-16 | 8.565374e-16 | 2.285077e-12 |
| 512K | 805869 | 6.604511e-16 | 8.405844e-16 | 3.158776e-12 |

所有性能任务均为 DP z2z、batch=1000、-N 10、hipprof --stats。
canonical 时间严格按
(TotalDurationNs - generate_random_interleaved_data_kernel) / 11 / 1e6
计算。实验版任务和原始 CSV 为：

| length | jobs | raw CSV |
|---:|---|---|
| 64K | 805870, 805871 | results/z2z_64k_b1000_exp074_late_64k_r1_20260904_182733.csv.hipkernel.csv；results/z2z_64k_b1000_exp074_late_64k_r2_20260904_182733.csv.hipkernel.csv |
| 128K | 805872, 805873 | results/z2z_128k_b1000_exp074_late_128k_r1_20260904_182733.csv.hipkernel.csv；results/z2z_128k_b1000_exp074_late_128k_r2_20260904_182933.csv.hipkernel.csv |
| 256K | 805874, 805893 | results/z2z_256k_b1000_exp074_late_256k_r1_20260904_182933.csv.hipkernel.csv；results/z2z_256k_b1000_exp074_late_256k_r2_20260904_182933.csv.hipkernel.csv |
| 512K | 805894, 805895 | results/z2z_512k_b1000_exp074_late_512k_r1_20260904_183134.csv.hipkernel.csv；results/z2z_512k_b1000_exp074_late_512k_r2_20260904_183334.csv.hipkernel.csv |

EXP-074 与 EXP-071 前一有效版本及固定官方 7.2.2 baseline 的结果如下。
speedup 定义为比较版本时间除以实验时间；括号内为按 agents.me 计算的
耗时下降百分比，即 (T_ref - T_exp) / T_ref * 100，不是 (speedup-1)*100。

| length | EXP-074 mean ms | EXP-071 mean ms | vs EXP-071 | official baseline ms | vs official |
|---:|---:|---:|---:|---:|---:|
| 64K | 3.568369091 | 3.616871818 | 1.013592408x (+1.341013%) | 3.732493091 | 1.045994121x (+4.397168%) |
| 128K | 7.804589091 | 7.925554136 | 1.015499220x (+1.526266%) | 8.954852000 | 1.147382892x (+12.845136%) |
| 256K | 17.925635182 | 17.729335136 | 0.989049200x (-1.107205%) | 19.360417545 | 1.080040810x (+7.410906%) |
| 512K | 38.820766818 | 38.852262364 | 1.000811307x (+0.081065%) | 70.509517909 | 1.816283492x (+44.942516%) |

EXP-074 的直接前一有效版本已包括 EXP-072 XOR，不能将相对 EXP-071 的
全部变化归因于 late-LDS。64K/128K 的直接比较时间分别为
3.605748682/7.889876773 ms；本轮对应加速比为 1.010475259x/1.010927889x，
耗时下降 1.036667%/1.080976%。256K/512K 前一有效路径没有 EXP-072 的修改。

64K 和 128K 的 SBCC-256 late-LDS 两轮均同向改善，因此该精确 gate
保留。256K 的 SBCC-512 late-LDS 两轮均回归，故拒绝该推广。512K 的
SBCC-1024 gate 在本轮没有实质改变，0.081% 属于基本持平，不能归因于
本轮新增修改。

为确认回退没有留下 256K 回归，提交 e57d01b9 的构建 805913 又执行了
四规模 correctness：805915/805916/805917/805918，结果分别为：

| length | job | relative_l2 | relative_max | max_abs |
|---:|---:|---:|---:|---:|
| 64K | 805915 | 7.125347e-16 | 1.156407e-15 | 1.325805e-12 |
| 128K | 805916 | 6.799770e-16 | 9.776713e-16 | 1.792371e-12 |
| 256K | 805917 | 6.565662e-16 | 8.565374e-16 | 2.285077e-12 |
| 512K | 805918 | 6.604511e-16 | 8.405844e-16 | 3.158776e-12 |

回退版 256K benchmark 为 805919/805920，原始 CSV 为
results/z2z_256k_b1000_exp074_late_256k_rollback_r1_20260904_184937.csv.hipkernel.csv
和
results/z2z_256k_b1000_exp074_late_256k_rollback_r2_20260904_184937.csv.hipkernel.csv。
两轮 canonical 时间为 17.734693455 ms 和 17.731536273 ms，平均
17.733114864 ms；相对 EXP-071 为 0.999786855x（-0.021315%），
处于测量噪声量级，说明回退恢复了稳定路径。

最终决策：本轮两个被审计的优化族中，能够推广且端到端两轮同向
改善的是 SBCC-256 [8,4,8] 的 late large-twiddle LDS reuse；
SBCC-512 gate 不保留，register-local 4x4 不扩展到其它规模。实验分支
保留 SBCC-256 gate 和全部证据；稳定分支仍不自动合并，后续实验从新的
EXP 编号开始。

#### EXP-074 记录修订与稳定收录（2026-09-05）

修复上一节被 Windows 终端写成 GB18030 的 85 行，恢复为 UTF-8；既有
正确性数值、CSV 和源码历史均保留。修正百分比口径，并补上相对 EXP-072
直接前版的比较。e57d01b9 的四规模 correctness 和 256K 回退基准已经完成，
因此将该 runtime 作为下一轮稳定起点，源代码树对应 ec946b42，稳定标签为
stable-exp074-cross-size-late-lds-20260905。合并仅包含 EXP-074 的有效
SBCC-256 gate、步骤相关上传数量和上述记录，不包含已拒绝的 SBCC-512 gate。
EXP-075 构建前会在同一个 GPU allocation 内重测前版四规模，随后测试候选，
消除旧文件不同节点或时间段造成的比较不确定性。

### EXP-075：按实际可达索引缩减 late large-twiddle 上传（计划）

日期：2026-09-05。实验分支：exp-075-compact-late-lut。
实验起点为稳定源码提交 e57d01b9，记录起点为 f9755e4f；起点标签为
pre-exp075-compact-lut-20260905。目标仍是 DP z2z、batch=1000、-N 10、
gfx936，长度为 64K、128K、256K、512K。

代码事实：large_twiddles.h::TW_NSteps() 对 base=8 的 large-twiddle
索引 u 只读取三段表中的位置
0..255、256..511 和 512 + ((u >> 16) & 255)，其余相位通过复数乘法
组合。当前 stockham_gen_cc.h 的 late-LDS 上传循环却统一上传
large_twiddle_steps * 256 项。large_twiddles_multiply_generator() 的
索引为 q * trans_local，其中 q 为最终 pass 的局部因子范围；因此可以
根据每个实际 kernel 的最大 trans_local 和 q，计算所需 LUT 前缀。

本轮只改变 late-LDS cooperative upload 的循环上限，不改变
TW_NSteps 的数学实现、LDS 起始地址、LDS 容量、barrier、Stockham layout、
radix、WGS、TPT、tile ownership 或 ordinary-twiddle recurrence。新增的
精确条件为：

| source length | SBCC factors | TPT | steps | trans_local cutoff | upload prefix |
|---:|---|---:|---:|---:|---:|
| 256 | [8,4,8] | 32 | 2 | <256 | 288 |
| 256 | [8,4,8] | 32 | 3 | <512 | 513 |
| 1024 | [8,8,4,4] | 64 | 3 | <512 | 514 |

对于 source length=256，普通 large-twiddle 递推的 q 最大值为 32；
对于 source length=1024，q 最大值为 256。上传前缀分别覆盖所有三段
TW_NSteps 索引，并保留超出 cutoff 的完整表上传路径，避免把局部证明
错误地推广到更大的 trans_local。cutoff 选择为 transforms-per-block
对齐的边界，保证一个 workgroup 的 cooperative upload 上限一致。

静态验证程序会枚举上述 q、trans_local 和每个 8-bit 表段的索引，证明
候选前缀覆盖全部访问；RTC 检查会确认生成代码使用 ltwd_count，且
64K/128K/512K 分别出现 288/513/514 的上限，256K 不命中本轮新增
compact gate。随后对前版和候选在同一作业中各运行四规模、两轮标准
benchmark，并执行四规模 correctness。

风险是 cooperative upload 线程在缩短的最后一段中出现更多空闲线程，且
额外的 trans_local 条件可能增加地址/控制指令；上传 global load 减少
本身不保证端到端收益。若 correctness、RTC 范围证明失败，或任一受影响
路径两轮均不快于对应前版，则回退源码并保留证据；只有目标路径有重复
收益且其它长度无回归时才考虑合入稳定分支。

#### EXP-075 实施和静态验证（2026-09-05）

本实验续接仅有计划而没有 runtime/benchmark 的 EXP-070，并根据 EXP-074
现有 gate 增加 64K/128K 的独立边界。源文件修改为
stockham_gen_cc.h::late_large_twiddle_upload_count() 和最终 pass 后的
ltwd_count 上限；其它 runtime 源码保持稳定版本。

exp075_checks.py 的 CPU 检查覆盖 trans_local=0..4095、每个实际 q 和
每一段 8-bit 表项，同时检查整个 workgroup 的上限一致。三种情形分别验证
270336/405504/3158016 个索引，最大已用 LUT 索引为 287/512/513，全部通过。
超出 cutoff 的 tile 使用完整表，静态检查同时覆盖这些 fallback tile。
相对原上传量，三个目标分别减少 224/255/254 次 complex copy/block；
这是逻辑复制次数，不能等同于 DRAM 字节减少比例或端到端加速比。

测试入口为 exp075_compact_lut.slurm，先核对前版已安装库与 bench 的
SHA-256，再在一个 allocation 内依次运行 previous、build.slurm、candidate。
correctness 使用既有 validate_rocfft_batch.cpp，在实验独立输出目录中对
四个长度分别测试 batch=1 和 3，对比 NumPy；不覆盖已有验证二进制或数据。
性能仍为 batch=1000、-N 10、hipprof --stats，两版四规模各两轮；两个阶段
均禁用 RTC cache read，以便保证所采源码版本，并保留所有 CSV、trace、DB、
plan 和 RTC。结果保存在 results/exp075_JOBID/，compare 子命令严格按
agents.me 公式生成 comparison.json。此时 GPU correctness/性能尚未运行。

历史参考的四规模保留时间为 3.568369091/7.804589091/17.733114864/
38.820766818 ms，其中 256K 使用 EXP-074 回退版；新结果优先与同 allocation
重测的 previous 比较，同时报告 agents.me 的四个固定官方 baseline。
256K 为无新 gate 的对照，只有 64K/128K/512K 才可归因于本轮候选。

#### 后续候选及依据（尚未实施）

1. SBRC-512 ordinary-twiddle recurrence。当前
   stockham_gen_base.h::use_ordinary_twiddle_recurrence() 要求 half_lds
   和 WGS=256，因而没有覆盖 SBRC-512 [8,8,8]/WGS=512/TPT=128；
   stockham_gen_rc.h::set_lds_is_real() 使用 scalar-LDS 不等于 half_lds。
   两个 radix-8 stage 的 7 次 ordinary LUT load 可以分别改为一次基础项
   加载和幂次递推，代价是各新增 6 次复乘及寄存器生命期。该 consumer 被
   128K/256K/512K 共用，必须三规模分别衡量，64K 用作对照。EXP-065/071
   的 SBCC 收益不能作为此方案已有效的证据。VkFFT 的
   vkFFT_RadixStage.h 根据 radix 决定 LUT 项数，radix-8 对应 3 项，证明
   它也用算术组合压缩 twiddle 数据，但不意味着照搬会在 gfx936 更快。
2. SBRC-512 的局部交换所有权。当前 scalar-LDS 仍按
   generate_device_function() 的 REAL/IMAG 循环在每个边界做两组 LDS
   store/load 和 barrier。应从 RC 的线程映射重新证明完整 wave-local
   边界或可直接放到目标寄存器的置换；只对整段通信都能消除的边界原型化。
   EXP-060 的否证针对 SBCC 的交错 transform 所有权，不能未经 RC 索引
   检查就套到 SBRC。VkFFT 的 vkFFT_RadixShuffle.h 同时依据当前和下阶段
   logicalStoragePerThread、stageSize 等决定寄存器重排和 shared exchange，
   这是本方向的借鉴点。若 RC 静态映射仍跨 wave，则记录否证，不重做只换
   barrier 的试验。
3. late-LDS 上传位置与最后两级算术的重叠。当前上传在最后 butterfly
   之后进行；SBCC-1024 的 register-local 4x4 已消除最后边界 LDS，因此
   row-data LDS 在更早处就结束使用。可审计将协作上传放到最后一次 LDS
   load 之后，并将消费 barrier 留到 large-twiddle 读取之前，尝试隐藏
   上传等待。必须保留防止覆盖仍在读取数据的 block barrier，并观察编译器
   是否实际重排及是否增加 VGPR；没有证据前不称为异步复制或已有加速。

执行顺序：先收尾 EXP-075，再独立测试 SBRC recurrence；wave-local 与
上传调度先完成静态所有权/生命期分析。上述三个候选未取得新性能结果。

#### EXP-075 result audit (2026-09-08)

Job 807356 completed with exit code 0:0 on a01r4n19, source commit
879c9c715475ecfaa7b7c431582cf8fcaccf3e91, branch exp-075-compact-late-lut.
Evidence: results/exp075_807356/{driver.log,comparison.json,
previous_correctness.json,candidate_correctness.json,source.patch,build.log}.
Raw profiles: previous_LENGTH_r{1,2}.csv.hipkernel.csv and
candidate_LENGTH_r{1,2}.csv.hipkernel.csv in that directory.
Both versions passed all four lengths at batches 1 and 3. Performance uses
batch=1000, -N 10, hipprof --stats and the AGENTS.md canonical metric.

| Length | Previous mean ms | Candidate mean ms | Speedup prev | Improvement prev | Official ms | Speedup official | Improvement official |
|---|---:|---:|---:|---:|---:|---:|---:|
| 64K | 3.567517045 | 3.570570273 | 0.999145 | -0.085584% | 3.732493091 | 1.045349 | 4.338195% |
| 128K | 7.802516636 | 7.844008318 | 0.994710 | -0.531773% | 8.954852000 | 1.141617 | 12.404936% |
| 256K | 17.729449636 | 17.729906773 | 0.999974 | -0.002578% | 19.360417545 | 1.091964 | 8.421878% |
| 512K | 38.809393227 | 39.102023909 | 0.992516 | -0.754020% | 70.509517909 | 1.803219 | 44.543623% |

Decision: reject compact upload for retention. No affected length improved
in either paired run. This does not establish a hardware root cause without
PMC/disassembly; fewer logical LUT copies did not improve measured runtime.
256K has no new gate and its tiny difference is not attributable to the patch.
Stable remains stable-exp074-cross-size-late-lds-20260905 (f9755e4f).
The main source/install have NOT been rolled back by this audit; do not use
the currently installed EXP-075 candidate as a stable-version measurement.

EXP-076 workspace audit: exp076-partial-pass/.git points to
/public/home/zhangkewei/zr/.git/worktrees/exp076-partial-pass, whose directory
was empty when inspected on zz-login01. git worktree list reports only the
main workspace. No implementation/build/performance result is established
for EXP-076. Preserve its files; do not infer an optimization outcome from
the incomplete checkout. Next implementation must start from the stable
commit in a valid isolated checkout, not from this unverified directory.

### EXP-077: early large-twiddle upload (implementation, pending GPU validation)

Branch exp-077-early-lut starts at stable commit
f9755e4f36706cf372f7b22c44470431263293d1, not EXP-075.
Full mechanism, synchronization proof, scope and test protocol are recorded
in exp077-early-lut/EXP077-record.txt (EXP077-record.txt within its branch).
Modified stockham_gen_base.h and stockham_gen_cc.h: add an empty pre-pass
hook and override it only for DP SBCC1024 [8,8,4,4], TPT64/WGS256/TPB4,
half-LDS/direct-register, with the existing final register-local exchange.
Upload the unchanged full LUT after the final row-data LDS read, before
pass-2 arithmetic. Preserve the overwrite-protection block barrier and move
only the consumption barrier to the original pre-large-twiddle location.
The last two radix-4 stages lie between upload and consumption. No change
to FFT decomposition, global traffic, LUT size, or arithmetic is claimed.
Potential benefit is scheduling room; actual hardware overlap is unproven.

Entry exp077.slurm builds immutable stable and candidate into independent
result-local directories, leaving main install and EXP-075 untouched.
Results: results/exp077_JOBID/, containing exact commit.txt, source.patch,
build logs, linked-library checks, correctness/RTC evidence, raw profiles,
comparison.json. Four lengths, correctness batches 1/3; benchmark batch1000
-N10 hipprof --stats, two alternating paired rounds, AGENTS.md canonical
metric and official baselines. Three smaller lengths are controls.
Job ID, correctness, times, speedups and retention: pending. Reject failures;
do not merge until repeatable target benefit and control checks complete.

EXP-077 submission: Slurm job 813229, implementation commit d46ffcf1,
branch exp-077-early-lut. bash -n, Python py_compile and git diff --check
passed before submission. Raw output directory: results/exp077_813229/.
GPU build/correctness/performance are pending; no measured benefit yet.

#### EXP-077 completed result audit (2026-09-08)

Job 813229: COMPLETED, exit 0:0, elapsed 00:52:59, node a01r3n07.
Recorded implementation commit: d46ffcf12b909bc5e90934b8274998bd3208b93a.
Both isolated builds succeeded. All four lengths at batches 1 and 3 passed
forward DP out-of-place correctness; generated-code marker/placement checks
also passed. Candidate 512K relative_l2: 6.60200637581743e-16 (batch1),
6.606076649329701e-16 (batch3). This is not inverse/in-place validation.

Times below are two-round means, batch1000, -N10, hipprof --stats,
AGENTS.md canonical TotalDurationNs metric, same GPU allocation.

| Length | Stable ms | Candidate ms | Speedup stable | Improvement stable | Official ms | Speedup official | Improvement official |
|---|---:|---:|---:|---:|---:|---:|---:|
| 64K | 3.565415182 | 3.566076545 | 0.999815 | -0.018549% | 3.732493091 | 1.046667 | 4.458590% |
| 128K | 7.802326636 | 7.803003864 | 0.999913 | -0.008680% | 8.954852000 | 1.147616 | 12.862838% |
| 256K | 17.730146045 | 17.728880955 | 1.000071 | 0.007135% | 19.360417545 | 1.092027 | 8.427177% |
| 512K | 38.798264182 | 39.476427136 | 0.982821 | -1.747921% | 70.509517909 | 1.786117 | 44.012627% |

512K stable rounds: 38.806170000, 38.790358364 ms; candidate rounds:
39.463104273, 39.489750000 ms. Both candidate rounds regress.
The first paired CSV attributes the increase primarily to SBCC1024:
TotalDurationNs/11/1e6 = 21.248623636 -> 21.912109364 ms;
SBRC512 = 17.554520909 -> 17.548289455 ms. These component times are
diagnostics, not a replacement for the canonical total including twiddle_gen.
Smaller lengths are unchanged-path controls; their tiny differences do not
establish optimizations or regressions caused by this patch.

Evidence directory: /public/home/zhangkewei/zr/results/exp077_813229/.
Files: commit.txt, source.patch, driver.log, comparison.json,
previous_correctness.json, candidate_correctness.json, ldd-candidate.log,
previous_LENGTH_r{1,2}.csv.hipkernel.csv,
candidate_LENGTH_r{1,2}.csv.hipkernel.csv, *_b1_rtc.log, build-*.log.
ldd-candidate.log resolves librocfft to the isolated install-candidate/lib.

Decision: reject EXP-077 for retention; keep its branch and all evidence.
Stable remains f9755e4f / stable-exp074-cross-size-late-lds-20260905.
No main install or stable source was modified by this isolated experiment.
Earlier upload was correct but did not improve performance. No PMC or ISA
evidence was collected here, so increased VGPR, waitcnt serialization or
occupancy changes are hypotheses, not demonstrated causes. Do not claim
actual memory/arithmetic overlap merely from the source scheduling change.
#### EXP-086：SBRC-512 首个 radix-8 load 完全静态特化（2026-09-20）

实验分支：`exp-086-sbrc-static-load`。基于 `9eb8f3b70e83a5f27bdf4b4c59ca713111d6586b`；精确稳定版由同一工作树干净源码独立构建（任务 `848330`，`install-stable`），候选版为任务 `848286`（`install`）。目标严格限定为 DP z2z、SBRC-512、length=512、WGS=512、TPT=128、TPB=4、factors `[8,8,8]`、2D `TILE_ALIGNED`；本轮性能只测 512K，其他规模只做 correctness 控制。

##### 实现

修改了 `stockham_gen.h`、`stockham_gen_base.h`、`stockham_gen_rc.h` 和 `rtc_stockham_kernel.cpp`。生成期 gate 只命中上述目标。首个 radix-8 pass 直接生成 global→register，输入映射为 `[tid, tid+64, ..., tid+448]`；因为 TPT=128 而该 pass 只需要 64 个 butterfly 线程，只有 `threadIdx.x % 128 < 64` 的线程执行 8 次 load。首个 pass 之后仍使用原有 Stockham Register→LDS 映射和后续两个 radix-8 pass，没有改变布局契约。非目标配置保留通用路径。

最初无条件修改 base layer 错误影响了非目标 SBCC，任务 `846364--846367`、`846376--846379` 仅为实现错误记录。恢复通用控制流后，候选任务 `848293--848296` 四规模 correctness 全部通过。无 active-lane guard 的版本任务 `848273` 导致 VMEM read `29.696M→37.888M` 并回退，因此舍弃；active-lane 版本修正了这次重复加载。

##### Correctness

| length | job | relative_l2 | relative_max | max_abs |
|---:|---:|---:|---:|---:|
| 64K | 848293 | 7.125347e-16 | 1.156407e-15 | 1.325805e-12 |
| 128K | 848294 | 6.799472e-16 | 9.776713e-16 | 1.792371e-12 |
| 256K | 848295 | 6.561126e-16 | 8.437206e-16 | 2.250885e-12 |
| 512K | 848296 | 6.602929e-16 | 8.405844e-16 | 3.158776e-12 |

##### 最终 512K 性能

任务 `849368` 使用 batch=1000、-N 10、hipprof --stats，在同一 allocation 内按稳定→候选→候选→稳定执行；canonical 时间为排除随机输入 kernel 后除以 11：

| round | stable (ms) | candidate (ms) | speedup |
|---:|---:|---:|---:|
| 1 | 38.818616273 | 38.581165182 | 1.006157x |
| 2 | 38.816666364 | 38.469762182 | 1.009019x |
| 平均 | 38.817641319 | 38.525463682 | **1.007583x** |

两轮同向改善，平均下降 0.292177637 ms（0.752%）。SBRC-512 两轮约为稳定 17.5610/17.5586 ms、候选 17.3160/17.3191 ms；SBCC-1024 未修改。

##### PMC 与 ISA

任务 `849379` 对精确稳定/候选安装各执行两次 SBRC-512：

| 指标 | stable | candidate | 变化 |
|---|---:|---:|---:|
| arch_vgpr | 64 | 60 | -6.25% |
| arch_sgpr | 48 | 48 | 0 |
| LDS allocation | 32768 | 32768 | 0 |
| SQ_INSTS_LDS | 73,728,000 | 49,152,000 | -33.33% |
| SQ_INSTS_VMEM_RD | 29,696,000 | 29,696,000 | 0 |
| SQ_INSTS_VMEM_WR | 8,192,000 | 8,192,000 | 0 |
| SQ_INSTS_VALU | 540,672,000 | 517,120,000 | -4.36% |
| SQ_LDS_BANK_CONFLICT | 458,752,000 | 458,752,000 | 0 |
| SQ_WAIT_INST_LDS | 529.249M | 255.767M | -51.68% |

global read 数量不变，减少的是首个 global→LDS→register 往返；active-lane 条件也避免了重复 global read。LDS 等待、LDS 指令和 VGPR 同时下降，支持性能收益来自初始 LDS 路径删除，而不是 bank-conflict 变化。

ISA 任务 `848314`：候选 `.text` 4052 bytes，稳定 3864 bytes，增加 188 bytes（4.87%）；无 spill。RTC 源码确认候选目标 kernel 为 `direct_load_to_reg = true`，直接生成 8 次 global load，并由 `thread < 64` 保护首个 butterfly/Register→LDS；稳定版为 false，先 global→LDS，再调用 `lds_to_reg_input_length512_device`。

##### 决策

这是严格限定到 512K z2z 目标路径的 SBRC-512 候选，不是跨规模通用优化。四规模 correctness 全部通过，最终两轮性能同向改善，PMC 能解释收益来源，因此保留在 `exp-086-sbrc-static-load` 分支；暂不合并稳定分支。若后续合并，必须保留精确 gate，不能推广到其他 SBRC 长度、factor 或不满足 `TILE_ALIGNED` 的配置。


#### EXP-089：SBRC 任意 2 的幂次首个 global→register load 泛化（2026-09-21）

实验分支：`exp-089-sbrc-pow2-static-load`。实验起点为提交 `088c9636`。
本实验将 EXP-086/088 按长度枚举的静态首个 global→register load 推广为
结构化生成期 gate：DP z2z、2D、TILE_ALIGNED、无 callback、SBRC、
direct-to/from-register；局部 length 和所有 factors 为 2 的幂，factor
乘积等于 length，且 workgroup size 可被 threads-per-transform 整除。

实现修改：
- `rtc_stockham_kernel.cpp` 删除 SBRC-64/128/256/512 长度白名单，增加
  任意 2 的幂次和 factor-product 约束；未来 SBRC-1024 满足条件时自动覆盖。
- `stockham_gen_rc.h` 将首个 load 生成器参数化为
  `width=factors.front()`、`height=length/(width*TPT)`，按已有首个
  Stockham LDS/register 映射生成 R 寄存器的 global load。
- 后续 Register→LDS、barrier、LDS→Register 和 Stockham pass 不变；不满足
  gate 的 kernel 保留通用 Global→LDS→Register 路径。
- 未修改 planner、FFT 分解、WGS、TPT、radix 或 twiddle 算法。

构建任务：851278。正确性任务：851279--851282（64K--512K）和
851825（32768 重跑）；RTC：851826；性能：851837；PMC：851838。
所有目标规模正确性通过。32768 重跑为
relative_l2=5.726651e-16、relative_max=1.037618e-15、
max_abs=8.658132e-13。

按 AGENTS.md canonical 公式，当前版本平均时间及相对上一稳定版本
EXP-074 的结果：

| length | EXP-089 T_compute_ms | EXP-074 stable ms | speedup |
|---:|---:|---:|---:|
| 64K | 3.456907136 | 3.568369091 | 1.032243x |
| 128K | 7.610478727 | 7.804589091 | 1.025506x |
| 256K | 17.366023955 | 17.925635182 | 1.032224x |
| 512K | 38.515949864 | 38.820766818 | 1.007914x |

原始结果位于 `results/exp089_*_new_r*.csv.hipkernel.csv`，日志为
`logs/bench_exp089_pair_851284.out` 和
`logs/bench_exp089r_small_retry_851837.out`。相对于直接前版 EXP-088，
64K/128K/256K/512K 分别为 0.99923x、0.99973x、0.99997x、0.99870x；
因此本实验的泛化本身没有可确认的额外稳态 GPU 加速。

SBRC-128 PMC（`results/exp089_pmc_small_retry/8k_{old,new}.csv.csv`）
old/new 的 arch VGPR=52、SGPR=48、SQ_INSTS_LDS=768000、
SQ_INSTS_VALU=4176000、SQ_INSTS_VMEM_RD=272000、
SQ_INSTS_VMEM_WR=128000、SQ_LDS_BANK_CONFLICT=10240000，最终机器代码
结构基本不变。主要成果是覆盖范围泛化和正确性，而非新增 GPU 指令级收益。

最终决策：保留结构化 gate，作为新的稳定版本。累计收益不得全部归因于
EXP-089；EXP-089 相对 EXP-088 的增量收益未证实。

#### 文档同步维护（2026-09-22）

将顶层实验记录中保留的 EXP-075/077 条目与仓库内较新的 EXP-086/089
条目合并，未修改任何既有实验结论、数值或证据路径。仓库内与顶层的
`VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md` 自本次维护起保持完全一致。
同时在 `AGENTS.md` 中明确：以后更新仓库内实验记录文档时，必须在同一
任务中同步顶层副本并验证两份文件一致。

### EXP-090：验证并修复 twiddle recurrence 的 inverse 语义（完成并推广）

日期：2026-09-22。实验分支：`exp-090-inverse-recurrence-fix`。实验前标签：
`pre-exp090-inverse-recurrence-20260922`。起始稳定记录提交为 `a0978f20`；
起始稳定 runtime 为 `a7a228cf7b851bb948f10910b6c12e3de7b0ad63`，其中
EXP-089 源码提交为 `f24222f0546df7cf5b19404cff0dc379a62c3f12`。

目标是在当前稳定源码和独立安装上验证 64K、128K、256K、512K DP z2z 的
forward/inverse、in-place/out-of-place、batch=1/3，共 32 个 correctness
组合。标准性能条件仍为四个目标长度、forward DP z2z、out-of-place、
batch=1000、`-N 10`、同一 GPU allocation、`hipprof --stats` 和 AGENTS.md
canonical 公式。

当前源码审计显示，保留的 ordinary-twiddle recurrence 使用
`TwiddleMultiply(W,W)` 和 `TwiddleMultiply(t,W)` 构造寄存器内 twiddle
幂；large-twiddle recurrence 使用 `TwiddleMultiply(W,t)` 更新递推状态。
`MakeInverseVisitor` 会将这些内部状态乘法和最终数据乘 twiddle 一并改写为
共轭乘法。历史 EXP-085 分支曾证明这会破坏 inverse，但其修复提交没有进入
当前稳定 HEAD。因此本实验必须先对当前稳定安装取得独立失败或通过证据，
不能仅引用旧分支结果。

若当前稳定 inverse 失败，最小修复只把 recurrence 内部状态更新改成由
`ComplexLiteral` 展开的普通复数乘法，使 inverse visitor 不改变 twiddle
幂/状态的数学递推；最终作用于 `R[ridx]` 的 `TwiddleMultiply` 保持不变，
继续由 visitor 对 inverse 使用共轭 twiddle。不修改 planner、分解、radix、
WGS/TPT、LDS layout、global handoff、EXP-089 SBRC 静态首载或 gate 范围。

验证顺序：记录计划；独立构建当前稳定 control；运行 32 组 correctness；
若失败则应用最小修复并先构建 `rocfft-rtc-gen`，再完整构建 candidate；检查
RTC 生成公式；运行 candidate 32 组 correctness；最后在同一 GPU allocation
完成 control/candidate 四规模两轮配对 benchmark。只有 candidate 32/32
通过、forward 结果保持正确、四规模无不可接受回归且原始日志/CSV 完整时，
才合入稳定分支，更新 AGENTS.md、本文档、顶层同步副本和新的 immutable
stable tag。若 control 已全部通过，则不修改 runtime，只记录验证结果。

#### EXP-090 实测结果与结论

Control 完整构建 job `854953` 成功，源码为
`b942259e13657f97644e54848ce288e4122f3f4e`，独立安装为
`/public/home/zhangkewei/zr/install-exp090-control`。Control correctness job
`855023` 的 32 个组合中 forward 16/16 通过，inverse 0/16 通过；四个长度、
in-place/out-of-place、batch=1/3 的 inverse relative L2 均约为 `1.42`。
原始记录为 `logs/exp090_correctness_855023.out` 和
`results/exp090_correctness_control_855023.json`。因此当前稳定 inverse 确认
不正确，而非容差边界或单一长度问题。

源码提交 `0473680e99b181e4660643425f53382f3a6afad7` 实施最小修复：ordinary
recurrence 的 `W*W`、`t*W` 以及 large-twiddle recurrence 的 `W*t` 改为
`ComplexLiteral` 展开的普通复乘；最终作用于数据的 `TwiddleMultiply` 未变。
RTC 生成器门禁 job `855044` 成功，完整 candidate 构建 job `855086` 成功，
候选独立安装为 `/public/home/zhangkewei/zr/install-exp090-candidate`。

Candidate correctness job `855145` 为 32/32 通过：forward 16/16、inverse
16/16；inverse relative L2 为约 `6.6e-16` 至 `7.1e-16`，与 forward 同量级。
原始记录为 `logs/exp090_correctness_855145.out` 和
`results/exp090_correctness_candidate_855145.json`。

同一 GPU allocation 的 ABBA 配对性能 job `855992` 使用 forward DP z2z、
out-of-place、batch=1000、`-N 10`。canonical 指标为
`(TotalDurationNs(Total)-generate_random_interleaved_data_kernel)/11/1e6`：

| 长度 | control (ms) | candidate (ms) | candidate 相对 control | 对官方 7.2.2 加速 |
|---:|---:|---:|---:|---:|
| 65536 | 3.455337 | 3.454254 | +0.031% | 1.080550x |
| 131072 | 7.608224 | 7.607957 | +0.004% | 1.177038x |
| 262144 | 17.365426 | 17.367240 | -0.010% | 1.114767x |
| 524288 | 38.475163 | 38.521134 | -0.119% | 1.830411x |

原始 CSV 位于 `results/exp090_paired_855992/`，汇总为
`results/exp090_paired_855992.json` 和 `results/exp090_paired_855992.txt`。
四规模最大回退为 512K 的 0.119%，属于两轮配对测量波动；没有可确认的性能
回退，也没有把 inverse 正确性修复误记为新的 forward 加速。

最终决策：推广该最小 inverse 修复。它是 ordinary 与 large-twiddle recurrence
共同使用的正确性修复，不是 512K 独有优化；保留 EXP-089 的 SBRC power-of-two
静态首载和此前所有已推广优化。稳定标签为
`stable-exp090-inverse-recurrence-fix-20260922`。

### EXP-091：batch=1 基线校准与 512K global-handoff/L2 诊断（完成）

日期：2026-09-22。实验分支：`exp-091-batch1-baseline`。实验前标签：
`pre-exp091-batch1-baseline-20260922`。起始稳定记录提交为 `c20d0a31`，
已验证 runtime 源码提交为 `0473680e99b181e4660643425f53382f3a6afad7`，
稳定标签为 `stable-exp090-inverse-recurrence-fix-20260922`。本实验不修改
planner、kernel、FFT 分解或数值语义。

用户明确说明：历史 `batch=1000` 只是为了降低性能测量误差而选择的参数，
实际应用或测试可能为 `batch=1`。因此不能把跨用户 batch 的 strip-mining、
重排或 cache reuse 当作主优化。本实验先把“工作负载 batch”和“重复测量次数
`-N`”分离：主工作负载固定为 batch=1，通过提高 `-N` 和独立重复轮次控制
误差；原 batch=1000、`-N 10` 只保留为不可与 batch=1 数值混用的吞吐量回归。

第一阶段只在 512K、DP z2z、forward、out-of-place、同一稳定安装上校准
`-N`。依次测量 `N=100/1000/10000`，每个 N 三轮，并采用平衡顺序减少温度和
时钟单调漂移。canonical 指标仍为：

```text
(TotalDurationNs(Total) - generate_random_interleaved_data_kernel) / (N + 1)
```

选择标准是：优先选取相对 `N=10000` 均值已收敛、三轮 CV 足够小且不会让
profiling 产生不必要长作业的最小 N。原始 CSV 保存在
`results/exp091_batch1_calibration_<jobid>/`，汇总为同名前缀的 JSON/TXT，
提交脚本为 `exp091_batch1_calibration.slurm`，分析器为
`exp091_analyze_batch1.py`。

首次校准提交 job `856156` 在进入任何 FFT/hipprof 调用前失败：脚本在
`source /public/home/zhangkewei/.bashrc` 之前启用了 `set -u`，而系统
`/etc/bashrc` 读取了尚未定义的 `BASHRCSOURCED`。该 job 没有产生性能数据，
不能作为有效样本；修复仅将 `set -u` 移到既有 `load_fft` 之后，不改变任何
测量参数。

校准解释还必须区分两种指标。`twiddle_gen_radices_dp` 和
`twiddle_gen_large_dp` 在一次 benchmark 进程中分别只调用固定次数，而两个
FFT kernel 和随机输入 kernel 调用 `N+1` 次；因此提高 `-N` 会同时降低随机
误差和摊薄固定 twiddle 生成成本。分析器同时输出保留历史定义的 canonical
值与只汇总 `fft_*`/`transpose_*` 的 transform-only 稳态值。不同 N 之间不把
canonical 均值差全部解释成噪声，也不把高 N 的 steady-state GPU kernel
时间描述成单次 cold-start 或 host wall-clock 延迟。

第二次有效提交 job `856160` 在节点 `f09r1n04` 完成，原始 CSV 位于
`results/exp091_batch1_calibration_856160/`。三轮 canonical 结果为：

| N | mean (ms) | median (ms) | CV | 相对 N=10000 mean |
|---:|---:|---:|---:|---:|
| 100 | 0.053513370 | 0.054284327 | 2.748% | +1.130% |
| 1000 | 0.053642534 | 0.051503024 | 7.391% | +1.374% |
| 10000 | 0.052915600 | 0.052143128 | 3.512% | 0% |

transform-only 的 mean/CV 分别为 0.053178584/2.787%、
0.053609607/7.397%、0.052912038/3.512%，说明主要波动来自 FFT kernel
本身，而不是约 33--36 us 的每进程固定 twiddle 生成。单纯增大 N 没有消除
跨进程的频率/系统漂移，因此后续候选必须继续采用同 allocation 的交错配对；
独立 batch=1 基线使用多进程中位数并同时保留均值、CV 和全部轮次。

后续四规模基线固定 `N=10000`、每个长度五轮。选择 N=10000 不是因为它在
三轮中表现出最低 CV，而是因为每个文件约 10001 次 transform，与旧
batch=1000、`N=10` 每文件约 11000 个 transform 的总样本量接近，并把固定
twiddle 生成的摊销影响降到最低。四规模使用平衡顺序，主汇总统计量为五个
独立进程的 median；这仍是 steady-state GPU-kernel 指标，不代表 cold start。

PMC 阶段必须按精确 kernel family 分开收集：SBCC 使用
`len_1024_factors_8_8_4_4` filter，SBRC 使用
`len_512_factors_8_8_8` filter。full counter 对 batch=1 各跑三进程，并保留
`N=1` 所产生的 warm-up/trial 两个 dispatch 行，用于检查跨 iteration cache
warming；同 allocation 再各跑一次 batch=1000，仅作为机制对照。focused
read 只测 SBRC，focused write 同时测 SBCC intermediate store 与 SBRC final
store。full/read/write 可能来自不同 profiler replay，不能把它们视为同一次
物理执行，也不能使用 PMC 中的时间做性能比较。

总体 `TCC_HIT/(TCC_HIT+TCC_MISS)` 混合了 intermediate、twiddle、常量与
store，并不等于 8 MiB handoff 的独立 L2 hit rate；`TCC_MISS` 也不自动等于
HBM bytes。若当前 hipprof 暴露的 focused/DRAM 请求计数仍不足以分离流量，
结论只能写成“与 L2 residency 一致/不一致”，并由静态 logical-byte 与
transaction 模型继续约束，不能声称已直接测得 intermediate 的 HBM 字节数。

第二阶段将在选定 N 下建立 64K/128K/256K/512K 的独立 batch=1 基线，并对
512K 当前 `SBCC-1024 [8,8,4,4] -> SBRC-512 [8,8,8]` 路径采集 PMC。重点
比较 SBRC consumer 的 TCC_HIT/TCC_MISS、VMEM read/write 和 LDS 指标，判断
单个 512K transform 的 8 MiB 中间结果是否已主要由 L2 承接。PMC 是整个
SBRC kernel 的计数，包含首载、twiddle/LUT 访问和最终 store，不能把总体
TCC hit rate 直接等同为中间数组首载 hit rate；结论必须结合 batch=1000
旧记录、静态地址模型及必要的受控对照。

只有完成上述基线和证据采集后，才进入 layout kernel 原型。若当前 store
的 64-byte 连续组存在明确 transaction 浪费，再测试 batch-independent 的
grouped-nearby 映射（候选为 SBRC WGS=1024、TPT=128、内部 TPB=8）；若该
映射因 64 KiB LDS/occupancy 抵消收益，则再评估显式 block layout。不得因
user batch=1 而混淆或删除内部 `transforms_per_block` 维度。

#### EXP-091 batch=1 四规模基线结果

基线 job `856749` 在节点 `f09r1n01` 完成，使用稳定 EXP-090 安装、forward
DP z2z、out-of-place、batch=1、`N=10000`，每长度五个独立进程。20 份原始
hipkernel CSV 均存在，错误日志为空。主统计量为五轮 canonical median：

| length | canonical median (ms) | canonical mean (ms) | CV | transform-only median (ms) |
|---:|---:|---:|---:|---:|
| 65536 | 0.017346298 | 0.017489193 | 1.396919% | 0.017343179 |
| 131072 | 0.019450103 | 0.019638673 | 1.459374% | 0.019446504 |
| 262144 | 0.023224602 | 0.023228576 | 0.198862% | 0.023222554 |
| 524288 | 0.051072366 | 0.051137676 | 0.299984% | 0.051069166 |

原始结果位于 `results/exp091_batch1_baseline_856749/`，汇总为
`results/exp091_batch1_baseline_856749.{json,txt}`。固定 twiddle 生成每进程
约为 20.736--36.160 us；在除以 10001 后 canonical 与 transform-only
只差约 2--4 ns。512K 的跨进程 CV 已降到 0.30%，但 64K/128K 仍约 1.4%，
所以后续小收益候选不能只与这个独立固定数做一次比较，仍必须在同 allocation
内与稳定版交错配对。该结果把 batch=1 正式设为主延迟工作负载；历史
batch=1000、`N=10` 仅保留为吞吐量回归，不与本表绝对值比较。

#### EXP-091 512K 分 kernel PMC 结果与方向裁决

PMC job `856758` 完成，耗时 2m30s，exit code 0，错误日志为空；原始 full、
focused-read、focused-write CSV/DB/hiptrace/hipkernel 文件全部位于
`results/exp091_batch1_pmc_856758/`，汇总为
`results/exp091_batch1_pmc_856758.{json,txt}`。PMC 时间不用于性能比较。

Full counter 的每 user FFT 结果如下。batch=1 为三进程、每进程两个
dispatch 的 aggregate；batch=1000 为同一稳定二进制和同 allocation 的机制
对照并按 1000 归一化：

| kernel/workload | TCC hit rate | hit/FFT | miss/FFT | VMEM read/write | LDS inst |
|---|---:|---:|---:|---:|---:|
| SBCC, batch=1 r1 | 11.8083% | 35164.5 | 262631.0 | 12800 / 8192 | 74752 |
| SBCC, batch=1 r2 | 11.9134% | 35520.0 | 262631.0 | 12800 / 8192 | 74752 |
| SBCC, batch=1 r3 | 11.5788% | 34391.5 | 262629.5 | 12800 / 8192 | 74752 |
| SBCC, batch=1000 | 5.0181% | 13849.9 | 262146.2 | 12800 / 8192 | 74752 |
| SBRC, batch=1 r1 | 11.1606% | 24732.0 | 196868.0 | 29696 / 8192 | 49152 |
| SBRC, batch=1 r2 | 11.1666% | 24748.0 | 196877.0 | 29696 / 8192 | 49152 |
| SBRC, batch=1 r3 | 11.2951% | 25068.5 | 196873.0 | 29696 / 8192 | 49152 |
| SBRC, batch=1000 | 12.2260% | 27385.7 | 196609.5 | 29696 / 8192 | 49152 |

SBRC 的 batch=1 TCC hit rate 没有高于 batch=1000，miss/FFT 也没有下降；
warm-up 与 trial 两行之间差异很小。这否定了“只要 user batch=1，当前 8 MiB
intermediate 就会主要由 L2 承接”的假设。因为 HIT/MISS 混合了 data、
twiddle、常量和 store，这里不把 11% 直接称为 intermediate hit rate。

Focused request-size counter 给出更强的边界形状证据：

- SBRC 四个 dispatch 的 `TCC_EA_RDREQ` 为 131337、131337、131344、
  131337，`TCC_EA_RDREQ_32B=0` 且 EA1 为 0；
- 8 MiB intermediate 恰好等于 `131072 * 64B`，实测只多 265--272 个
  64B request（约 0.20%，可由 twiddle/常量等其它读取解释）；
- SBCC 四个 dispatch 的 `TCC_EA_WRREQ=TCC_EA_WRREQ_64B=131072`，精确
  等于 8 MiB/64B，没有 32B request；
- SBRC final store 四个样本中三个同样为 131072 个 64B request，一个 replay
  为 204381；该单个异常不用于推导稳定 store 流量，若以后研究 final store
  需要单独复测。

AMD 的 counter 定义表明 `TCC_EA_RDREQ/WRREQ` 是经过 TCC/EA interface 到
efficiency arbiter 的 32B/64B 请求，而 HBM 有独立的 `_DRAM` counter。因此
这里可以直接确认的是：几乎完整的 8 MiB handoff 以 64B 粒度跨过 EA 接口；
在当前本地 buffer 条件下它与重新访问 HBM 的解释高度一致，但没有
`TCC_EA_RDREQ_DRAM` 时不把它写成直接测得的 HBM bytes。

方向裁决：当前 producer store 和 consumer load 已经达到无放大的完整 64B
transaction。把内部 TPB=4/WGS=512 改成 TPB=8/WGS=1024、把逻辑连续组从
64B 扩为 128B，仍会被分成两个 64B EA request，不能减少 131072 个请求，
而还会把 LDS/WG 从 32 KiB 增到 64 KiB。因此 grouped-nearby TPB=8 的原始
transaction-reduction 动机已被证伪，不进入 kernel 实现。单纯保持相同
8 MiB store+load 的 permutation/block-layout 也没有 transaction 数收益。

下一阶段静态模型仍有价值，但重点改为：精确计算 `O_P/O_C/A_P/A_C`、
`F1/F2/F3`、每条 producer-consumer 边的字节数，并寻找能减少 global
boundary bytes 或 fan-in 的 boundary movement/hierarchical ownership；不再
以“改善当前 coalescing”为目标。若以后专门研究 cache policy/residency，
再补采可用的 DRAM counter 或构造受控 cache-policy 对照。

#### EXP-091C 512K ownership/address/transaction 闭式模型

静态模型脚本为 `exp091_handoff_ownership_model.py`，机器可读和文本结果为
`results/exp091_handoff_ownership_model.{json,txt}`。它不是 WGS/TPT/radix
autotuner，也没有枚举任意数值参数；模型只从实测 kernel geometry 和
`SBRC [8,8,8]` 的三个合法 factor-prefix cut 推导必要条件。

对中间矩阵 `H[K=1024,M=512]`，物理地址为 `q*512+a`。当前 producer
tile 的 ownership 为全部 `q` 和 4 个相邻 `a`，共 128 个 producer；当前
consumer tile 为 4 个相邻 `q` 和全部 `a`，共 256 个 consumer。因此
ownership 依赖图是完整二部图 `K_{128,256}`，共有 32768 条边；每条边是
`4x4=16` 个 DP complex，即 256B。每个 consumer 的 fan-in 为 128，每个
producer 的 fan-out 为 256。batch 只复制互不相连的该图，不改变任何单
transform ownership、fan-in、edge bytes 或 transaction 下界。

只要 producer tile 宽 `P` 为 4 的倍数、consumer tile 高 `C` 整除 1024，
并保留“一次写出、一次读入全部 DP-complex intermediate”，64B EA request
数满足闭式恒等式：

```text
R = (M/P) * (K/C) * C * (P*16/64)
  = N*16/64
  = 131072 requests / direction
```

模型的逐地址枚举与该闭式结果一致：当前 `P=4,C=4`、仅把 consumer TPB
改成 8 的 `P=4,C=8`，以及 producer/consumer 都取 8 的 `P=8,C=8`，均为
131072 个 request。PMC 中 SBCC 四个样本也恰为 131072；SBRC 四个样本只
多 265、265、272、265 个 request，平均额外 0.2035%。因此 TPB=8、WGS=1024
和任何仍完整写读 8MiB 的纯 permutation/block layout 都已达到同一下界，
没有 transaction-count 优化空间。

三个合法 consumer prefix 的 ownership 必要条件为：

| cut | 当前 producer fan-in | 相对完整 consumer | 当前 TPT 下 owner WGS | half-LDS live state | 保持 4 个相邻 a 所需 WGS | cut 后 global boundary |
|---|---:|---:|---:|---:|---:|---:|
| F1 `[8]` | 8 | 16x 降低 | 512 | 64 KiB | 2048 | 8 MiB |
| F2 `[8,8]` | 64 | 2x 降低 | 4096 | 512 KiB | 16384 | 8 MiB |
| F3 `[8,8,8]` | 128 | 不变 | 32768 | 4 MiB | 32768 | 8 MiB |

F1 是唯一在单个 WG 的 WGS/half-LDS 硬上限内勉强成立的 hierarchical-owner
形状，并把 fan-in 从 128 降到 8；但一个 F1 group 使用
`a={0,64,...,448}`，失去当前相邻-a producer access。若同时保留当前 4-wide
连续性则需要 WGS=2048 和 256KiB scalar live state，均不可行。更重要的是，
64 个 F1 group 合计仍写出全部 `N` 个元素，所以 boundary 仍为 8MiB，并未
减少 global bytes。完整 same-WG continuation 则需要 WGS=32768、8MiB complex
live state（即使 half-LDS 也为 4MiB），直接排除。

因此静态模型的结论不是“枚举没有找到好参数”，而是：在保持当前完整中间
数组语义时，TPB 和纯 layout 参数被闭式下界统一排除；F2/F3 被资源下界
排除；F1 只保留为未来 cross-workgroup cluster/hierarchical ownership 的
结构线索，不能作为当前 gfx936 上减少 boundary bytes 的 kernel 原型。

当前 `hipprof` 只提供固定 `--pmc/--pmc-read/--pmc-write` 预设，现有 CSV 和
帮助信息均未暴露 `_DRAM` counter，也未安装可用的 `rocprof/rocprofv3`。
下一步先用最小设备能力程序查询 gfx936 的 `clusterLaunch`、cooperative launch、
LDS/WGS/L2 等属性：若 cluster 不存在，则 F1 的“8 producer 直接共享”路线在
本机结束；cooperative grid 只能提供同步而不能提供 remote LDS，不单独作为
fusion 理由。

EXP-091 最终决策：接受 batch=1 测量协议、四规模固定基线、PMC 诊断和上述
闭式模型，不产生或推广任何 kernel/planner 源码修改。稳定 runtime 源码仍为
EXP-090 的 `0473680e99b181e4660643425f53382f3a6afad7`；EXP-091 只将脚本、
分析器、原始结果索引和实验记录并入稳定记录。后续独立实验从该记录切出，
不得重新实现已被 64B transaction 下界否定的 TPB=8 grouped-nearby 候选。

### EXP-092：gfx936 workgroup-cluster 能力门禁（完成）

日期：2026-09-22。实验分支：`exp-092-gfx936-cluster-capability`。起始稳定
记录提交为 `d9129c654e9f4947ab1e2125c8bc06a556b90bae`，实验前标签为
`pre-exp092-gfx936-cluster-capability-20260922`，稳定 runtime 源码仍为
`0473680e99b181e4660643425f53382f3a6afad7`。本实验不修改 rocFFT runtime、
planner、kernel、分解或数值语义。

EXP-091C 证明唯一仍有结构意义的 consumer prefix 是 F1 `[8]`：它能把当前
consumer 对 producer tile 的 fan-in 从 128 降到 8，但在 gfx936 上只有存在
跨 workgroup shared-memory mapping/cluster barrier 时，8 个既有 producer
workgroup 才可能不经 global intermediate 直接交给 prefix owner。普通
cooperative launch 只提供 grid synchronization，不等价于 remote LDS。

因此本实验先做一票否决式设备查询，而不直接实现 fusion。程序
`exp092_query_device_capabilities.cpp` 通过 `hipGetDeviceProperties` 记录实际
分配 GPU 的 `gcnArchName`、HIP runtime/driver、`clusterLaunch`、
`cooperativeLaunch`、WGS、LDS、L2 和 CU 属性；对较旧头文件用编译期字段检测，
字段不存在也作为明确结果。提交脚本为
`exp092_query_device_capabilities.slurm`，结果写入
`results/exp092_device_caps_<jobid>.txt`。

停止条件：若 `clusterLaunch` 字段不存在或值为 0，则结束 gfx936 remote-LDS
cluster 路线；即使 `cooperativeLaunch=1` 也不继续做同义替换。若
`clusterLaunch=1`，也只允许下一步做最小 8-workgroup shared-memory mapping
microprobe，必须先验证可用 cluster size、同步和 remote-LDS 语义，不能直接
进入 rocFFT F1 fusion。该能力查询本身不产生性能数值，也不改变稳定版本。

能力查询 job `856857` 在节点 `f09r1n01` 完成，耗时 5 秒，exit code 0，
错误日志为空；提交记录 HEAD 为
`a2d56aa188a888a8858a0d84ee20c2de1140c731`。原始结果为
`results/exp092_device_caps_856857.txt`，日志为
`logs/exp092_device_caps_856857.{out,err}`。关键属性如下：

```text
device=BW
gcnArchName=gfx936:sramecc+:xnack-
warpSize=64
multiProcessorCount=80
maxThreadsPerBlock=1024
maxThreadsPerMultiProcessor=2560
sharedMemPerBlock=65536
maxSharedMemoryPerMultiProcessor=65536
l2CacheSize=8388608
cooperativeLaunch=1
cooperativeMultiDeviceLaunch=1
clusterLaunch_field=absent
```

`clusterLaunch` 字段在当前 DTK 26.04 的实际 `hipDeviceProp_t` 中不存在，满足
停止条件。虽然 cooperative launch 可用，但它不提供跨 workgroup shared
memory mapping，不能替代 cluster；因此不提交 cluster microprobe，也不在
gfx936 上实现依赖 remote LDS 的 F1 hierarchical-owner fusion。

另一个直接观测是 L2 恰为 8MiB，与 512K DP complex intermediate 的逻辑
大小完全相同；再计入 cache metadata、twiddle 和其它流量后，没有容量余量。
结合 EXP-091 的 512K SBRC 低 TCC hit 和接近完整 8MiB 的 EA read request，
下一项诊断应在不改 kernel 的前提下比较 64K/128K/256K/512K 对应的
1/2/4/8MiB intermediate，建立 batch=1 L2 容量曲线。只有较小工作集显示
明显更高 reuse、而 8MiB 出现容量断崖时，才继续研究 cache-local scheduling；
否则结束 cache-residency 路线。

EXP-092 最终决策：能力门禁通过执行但 cluster 路线被硬件/接口证据否决；
保留查询程序和结果作为负向证据，不修改或推广 rocFFT runtime。稳定 runtime
源码继续为 `0473680e99b181e4660643425f53382f3a6afad7`。

### EXP-093：batch=1 SBRC L2 容量曲线（完成）

日期：2026-09-23。实验分支：`exp-093-batch1-l2-capacity-curve`。起始稳定
记录提交为 `6a71d2223e50c8473a1ef10578fb2d3eb841a033`，实验前标签为
`pre-exp093-batch1-l2-capacity-curve-20260923`，稳定 runtime 源码仍为
`0473680e99b181e4660643425f53382f3a6afad7`。本实验只采集计数器，不修改
rocFFT runtime、planner、kernel、分解或数值语义。

EXP-092 实测 gfx936 L2 为 8MiB，正好等于 512K DP-complex SBCC→SBRC
中间数组的逻辑大小，尚不能区分 512K 的低 TCC hit 是容量边界，还是 SBRC
当前 ownership/调度使数据在所有规模上都没有可利用的 cache reuse。为避免把
batch=1000 的跨 transform cache 行为误当成算法性质，本实验固定 batch=1、
double、complex forward、out-of-place，并比较以下单 transform 工作集：

| FFT length | 中间数组逻辑大小 | SBRC kernel filter |
|---:|---:|---|
| 65536 | 1MiB | `len_256_factors_4_4_4_4` |
| 131072 | 2MiB | `len_512_factors_8_8_8` |
| 262144 | 4MiB | `len_512_factors_8_8_8` |
| 524288 | 8MiB | `len_512_factors_8_8_8` |

提交脚本 `exp093_batch1_l2_curve.slurm` 使用 EXP-090 已验证安装
`install-exp090-candidate`。每个规模采集三轮完整 TCC counter 和两轮独立
read-request counter；规模顺序在各轮中正序、逆序和交错，以降低温度与运行
顺序偏差。每次 `rocfft-bench` 使用 `-N 1`，保留 profiler 中 warm-up 与 trial
两个 dispatch 样本；PMC 时间不作为 latency。分析器
`exp093_analyze_l2_curve.py` 保存逐 dispatch 原始值，并汇总 TCC hit rate、
hit/miss 数和 `TCC_EA_RDREQ` 相对 `N*16/64` 个 64B request 下界的偏差。

解释边界必须严格：TCC hit/miss 同时混合 intermediate、twiddle、常量和 store
流量；EA request 是 EA 接口请求，不是直接 HBM byte counter；不同 preset 来自
独立 replay。因此这里只判断随工作集大小变化的结构趋势，不用 counter 反推
绝对 DRAM 带宽，也不与基准延迟混算。

决策条件：若 1/2/4MiB 的 hit/reuse 明显更高且接近 8MiB 时出现一致容量断崖，
则下一项只研究 batch=1 下缩短 SBCC→SBRC reuse distance 的 cache-local
scheduling；若四个规模均接近完整 EA read 下界且 hit/reuse 曲线基本平坦，或
小工作集也无可靠改善，则结束 cache-residency 路线，不实现 cache-aware planner
原型。任何结论都必须来自多轮一致趋势；本实验本身不产生可推广 kernel。

#### EXP-093 结果与裁决

脚本提交为 `7f7e2305f61fe80a5b8bb63132a5d0100b1b000b`；任务 `856930`
在 `f09r1n01` 上 `COMPLETED 0:0`，耗时 3 分 11 秒，stderr 为空。原始计数
文件为 `results/exp093_batch1_l2_curve_856930/{full,read}_n<L>_r<R>.csv`，
其中每个长度有 3 份 full、2 份 read 文件，每份有 warm-up 和 trial 两次
SBRC dispatch；作业日志为 `logs/exp093_batch1_l2_curve_856930.{out,err}`，
修正汇总为 `results/exp093_batch1_l2_curve_856930.{json,txt}`。

首次分析器将 256K 的 SBCC-512 和 SBRC-512 混算，因为它们都包含
`len_512_factors_8_8_8`。原始 CSV 中该长度每份有 4 行；其它长度每份 2 行。
修订后的分析器只选择 `unitstride_sbrc_aligned`，并要求每份 CSV 恰有两行
SBRC，否则报错。修订前 256K 的 12/8 个 full/read dispatch 计数及
0.123355/65770.5 汇总作废；修订后为 6/4 个，数据如下：

| N | 中间数组 | SBRC TCC hit 中位数 | SBRC EA read 中位数 | 完整数组 64B 下界 | 超出下界 |
|---:|---:|---:|---:|---:|---:|
| 65536 | 1MiB | 12.7975% | 16515 | 16384 | 0.7996% |
| 131072 | 2MiB | 18.6712% | 32972 | 32768 | 0.6226% |
| 262144 | 4MiB | 12.6303% | 65740.5 | 65536 | 0.3120% |
| 524288 | 8MiB | 11.1381% | 131330.5 | 131072 | 0.1972% |

各长度的完整计数均为三轮、每轮两行；read 计数均为两轮、每轮两行，且
`TCC_EA_RDREQ_32B` 和 EA1 read 均为零。256K 正确 SBRC 的 full
hit/miss 每 dispatch 平均为 14235.667/98508.333，read request 为
65740、65740、65741、65741；误混入的 SBCC 行已保留在原始 CSV 中供审计。
2MiB 的 TCC hit 局部较高，但 4MiB 和 8MiB 均较低，未出现“较小三个规模
保持高 reuse、仅在 8MiB 容量边界急降”的多轮曲线。所有规模的 EA read
都接近一次完整中间数组读取。TCC hit 混有 twiddle/常量/其它流量，EA
也不是直接 HBM byte 计数，因此这些数据不能证明具体 cache eviction 原因。

决策：预先规定的 cache-local scheduling 进入条件未满足，结束把 L2 容量
作为当前 SBCC→SBRC handoff 主要瓶颈的优化路线；不实现 cache-aware
planner。EXP-093 不修改 rocFFT runtime，correctness 沿用 EXP-090 已验证版，
没有候选性能差异。固定 batch=1 canonical latency 仍为 EXP-091 的
64K/128K/256K/512K `0.017346298/0.019450103/0.023224602/0.051072366`
ms；相同 runtime 身份下相对前版及该固定基线均为 1.000000x，这不是本任务
重新测得的加速。下一项从稳定版本独立分支开始，转向 SBRC-512 内部交换
所有权或 ordinary-twiddle 的可证伪候选，而不重试完整 intermediate 的
纯 layout/TPB 调整。

### EXP-094：SBRC-512 ordinary twiddle 递推（计划）

日期：2026-09-23。实验分支：`exp-094-sbrc512-twiddle-recurrence`。起点稳定
记录提交为 `7f07f687a884003b6187446e384357753be87168`，实验前标签为
`pre-exp094-sbrc512-twiddle-recurrence-20260923`。上一有效 runtime 为
EXP-090 `0473680e99b181e4660643425f53382f3a6afad7`，安装在
`/public/home/zhangkewei/zr/install-exp090-candidate`；EXP-093 的计数器诊断
没有改变它。固定 batch=1 延迟基线为 EXP-091 job `856749`。

候选只在 `stockham_gen_base.h::use_ordinary_twiddle_recurrence()` 增加
`CS_KERNEL_STOCKHAM_BLOCK_RC`、DP、length=512、factors `[8,8,8]`、
WGS=512、TPT=128、`direct_to_from_reg`、`static_initial_reg_load` 的精确
gate。现有 SBCC-256/512/1024 gate 不变。该 SBRC 使用 scalar-LDS 而不是
`half_lds`，所以先前 SBCC gate 没有覆盖它。候选在第二、第三个 radix-8
pass 中，每个 butterfly 从 ordinary twiddle 表读取一个基础相位，并在
寄存器内形成其余幂；每个 pass 原有 7 次查表变成 1 次查表，同时增加复数
乘法及寄存器生命期。是否净加速必须由实测决定。EXP-090 已修正 recurrence
内部状态在 inverse 下的语义，但本轮仍重新验证 inverse。

两个带 `afterok` 依赖的 Slurm 任务一次性提交：第一项在独立
`build/exp094_candidate` 和 `install-exp094-candidate` 构建候选，不覆盖稳定
安装；先编译 `rocfft-rtc-gen`，再完整构建，随后使用
既有 NumPy 对照脚本验证四个长度、forward/inverse、in/out-of-place、
batch=1/3 共 32 个 case。第二项只有在第一项成功且 32 个 case 全部通过时
才运行，并在同一 GPU allocation 内执行
batch=1、DP z2z forward out-of-place、`-N 10000` 的稳定/候选交错配对：
64K/128K/256K/512K 各三轮，64K 作为未命中 gate 的对照。时间严格按
`(TotalDurationNs - bench-only random-input kernel)/(10000+1)` 计算，同时
保留 transform-only 诊断值。最后对 512K SBRC 各采一份 PMC，检查
VMEM/VALU/VGPR 变化，不把 PMC 时间用于性能结论。

结果须保存 source commit、stable/candidate 库哈希、正确性 JSON、逐轮
hipkernel CSV、PMC 原始 CSV、汇总 JSON/TXT 和作业日志。若构建、32-case
正确性或配对基准不通过，候选留在实验分支且不合入稳定分支。若正确性通过，
也只有受影响的 128K/256K/512K 相对同节点稳定版跨轮一致改善，且 64K
无可归因回归，才考虑保留；否则记录失败证据并回到稳定 runtime。

EXP-094 result (2026-09-23): source commit `e5f327d381efbfdf4f2ff3e79381d87511cc0525`.
Build and 32-case correctness job `857327` passed; benchmark/512K PMC job
`857328` completed. Stable and candidate library SHA256 values were
`ad152877ba276dd70d6dbdac2e6fec454e348eb989431229f412a69f2da531a5`
and `fc46dc5ae8c1b66988ea903dfdce079e961749dc32e64e69770c6c9037335f98`.
Raw evidence is under `results/exp094_sbrc512_recurrence_857327/` and
`results/exp094_sbrc512_recurrence_857328/`, with the paired summary in
`results/exp094_sbrc512_recurrence_857328/paired.json` and `.txt`.
Same-allocation batch=1, DP z2z OOP, `-N 10000` median canonical times
(64K/128K/256K/512K) were stable
`0.017343244/0.019423012/0.023461434/0.050989232` ms and candidate
`0.017343279/0.019093283/0.024215722/0.052131887` ms. Speedups versus
the paired stable runtime were `0.999998/1.017269/0.968851/0.978081`;
speedups versus EXP-091 fixed baseline were
`1.000174/1.018688/0.959071/0.979676`. The 128K SBRC saved about
0.34-0.36 us in all three rounds. The 256K total regressed in all three
rounds; the 512K candidate CV was 6.44% and one round favored candidate.
512K SBRC PMC showed VMEM read instructions `29696 -> 11264`, VALU
`512000 -> 583680`, with LDS instructions `49152`, bank conflicts `458752`,
VGPR `60`, and SGPR `48` unchanged. PMC time is not the canonical metric.
This candidate fails the pre-registered cross-size acceptance rule and remains
unmerged; the stable runtime remains EXP-090.

EXP-094 supplemental crossover diagnostic, pre-registered before submission:
`exp094_crossover_diagnostics.slurm` compares the same validated installed
libraries, with no rocFFT source changes. One allocation first runs eight
ABBA-ordered stable/candidate process pairs per 64K/128K/256K/512K,
batch=1 and `-N 10000`, retaining all raw CSV and per-round values. Then
full PMC is collected for SBCC and SBRC at all four lengths, three paired
rounds each; a separate SBRC read-request PMC group covers 128K/256K/512K
twice. PMC uses batch=1 and `-N 10`; use counts only, not profiler time,
and normalize by grid workgroups/elements when comparing lengths. Compare
VMEM read/VALU/LDS/wait counts, TCC hits/misses, TA data stalls, register and
LDS resource use, and read request sizes. The 64K gate-off control and
unchanged SBCC distinguish run-state drift from the candidate SBRC mechanism.
The cache and scheduling explanation remains a hypothesis until these
per-length diagnostics are reviewed. Do not promote this candidate solely
from 128K gain or a counter reduction.

EXP-094 supplemental crossover result (2026-09-23): diagnostic job `857552`
completed. In eight paired batch=1, `-N 10000` rounds, stable/candidate
canonical medians in ms for 64K/128K/256K/512K were
`0.017389487/0.019480471/0.023265002/0.052853446` and
`0.017395566/0.019122356/0.023803352/0.053266044`, respectively.
The 128K candidate improved by 1.84% with all eight SBRC pairs faster;
256K regressed by 2.31% with seven of eight SBRC pairs slower. 512K
is noisy. At all affected sizes, SBRC VMEM read instructions per workgroup
fell from 116 to 44, while VALU rose from 2000 to 2280; LDS bank conflicts,
VGPR, SGPR, and LDS allocation were unchanged. Global read request counts
and TCC misses were nearly unchanged, so fewer twiddle-load instructions
did not materially reduce the global handoff traffic. The size-dependent
latency explanation remains a scheduling hypothesis, not a proven cause.

EXP-094 batch=1000 crosscheck (pre-registered before submission): use the
same installed stable/candidate libraries and correctness precondition, with
eight same-GPU, ABBA-ordered pairs for 64K/128K/256K/512K, DP z2z OOP,
`hipprof --stats`, `-N 10`, canonical divisor 11. Preserve every raw CSV.
Do not compare batch=1000 absolute time to batch=1. If 128K improves
consistently while 64K stays neutral and 256K/512K show no reliable gain,
then investigate restricting the recurrence to full FFT length 128K only;
otherwise report the disagreement without changing the optimization gate.

EXP-094 batch=1000 crosscheck result (2026-09-23): job `858035` completed
successfully on `f09r1n03`, with an empty error log. All 64 paired raw
hipkernel CSV files and their SHA256 list are in
`results/exp094_batch1000_858035/`. Stable/candidate libraries and bench
executables matched the pre-registered hashes. The canonical metric excludes
the random-input kernel and divides by 11; it is per batch of 1000 FFTs,
not a batch=1 latency measurement. Stable/candidate median times in ms:
64K `3.452476818/3.452738773` (flat, -0.008%, 3/8 pairs faster);
128K `7.607042727/6.957106318` (+8.54%, 8/8 faster);
256K `17.363624045/16.020065182` (+7.74%, 8/8 faster);
512K `38.479123682/37.759450545` (+1.87%, 8/8 faster).
The 256K and 512K batch=1000 directions disagree with the batch=1
diagnostic, where 256K regressed and 512K was noisy. Thus the user's
conditional criterion is not met: do not restrict the recurrence to 128K
on this evidence. Report the workload-dependent result; leave stable and
candidate optimization gates unchanged.

EXP-094 batch-dependence mechanism diagnostic (pre-registered before new
jobs, 2026-09-23): no rocFFT source, installed library, or optimization gate
changes. The existing eight-round raw CSVs localize the difference. For
128K/256K/512K, batch=1 SBRC stable/candidate medians (ms) were
`0.008537309/0.008186032`, `0.010792154/0.010999236`, and
`0.026148672/0.026450709`. At batch=1000 they were
`3.979473273/3.330361000`, `8.104954409/6.762321636`, and
`17.237266409/16.508618545` ms per batch. The corresponding unchanged
SBCC stage stayed essentially flat at batch=1000. At batch=1, 256K SBCC
also regressed (`0.012476403/0.012791461` ms), despite unchanged SBCC
source; do not assign this to the SBRC recurrence without further evidence.
All stage figures are from `TotalDurationNs/(N+1)` within each workload;
batch=1000 absolute times are not a batch=1 latency substitute.

Test competing explanations, without assuming any is proven: (1) more
independent workgroups change how VMEM issue versus added VALU affects
throughput; (2) batch-dependent cache/request traffic or cross-iteration
state changes; (3) repetition count, clocks, or run-order artifact. The
paired timing sweep covers lengths 128K/256K/512K and batches
1/2/4/8/16/32/64/128/256/1000, four rounds per exact condition on one
GPU allocation. Set N=max(10,floor(10000/batch)); compare versions only
within identical length, batch, N, and GPU. Add eight paired 256K controls
at batch=1,N=10 and batch=1000,N=100. Retain canonical and SBCC/SBRC
stage times separately; alternate version order and reverse size/batch
order across rounds. Do not compare absolute times across batches as
latencies. The PMC job uses one warm-up transform (`-N 0`) per process and
two stable/candidate rounds at 256K batches 1/4/32/1000 plus 128K/512K
batch=1000. Collect both full and read-request counter groups, recording
grid/workgroup size, register/LDS allocation, VMEM/VALU instructions,
TCC hits/misses/read requests, stalls and bank conflicts. Normalize counts
per workgroup; never use PMC replay durations as performance evidence.

EXP-095 (pre-registered, 2026-09-23): user requests retaining the EXP-094
ordinary-twiddle recurrence only for a complete 1D FFT of length 131072,
then promoting the validated result as a new stable version and measuring
the batch=1 baseline/new-version times and speedup. Work starts on branch
`exp-095-sbrc128k-only` from stable record commit
`7f07f687a884003b6187446e384357753be87168`; validated stable runtime
source is `0473680e99b181e4660643425f53382f3a6afad7`. The existing
EXP-094 experimental branch and installed library are not the baseline.

Change only the SBRC-512 DP `[8,8,8]`, WGS=512, TPT=128,
aligned/static-register-load ordinary-twiddle recurrence gate. Propagate
the complete plan-root shape into RTC generation: require one-dimensional
root length exactly 131072, not merely a local SBRC length of 512. Keep
the established SBCC recurrence gates unchanged. Give the specialized RTC
variant a distinct kernel name/cache key so other sizes cannot reuse it.
No change to global handoff, planner decomposition, or batch scheduling.

Build in isolated `build/exp095_candidate` and install to
`install-exp095-candidate`; do not overwrite validated EXP-090. First
compile `rocfft-rtc-gen`, then full library/bench, then run the 32-case
NumPy forward/inverse, in/out-of-place, batch=1/3 correctness matrix at
64K/128K/256K/512K. Benchmark only after correctness passes: eight
same-allocation stable/candidate process pairs per length, DP z2z forward
out-of-place, batch=1, `hipprof --stats`, `-N 10000`, canonical divisor
10001. Preserve raw CSV, logs, exact commits and binary hashes; report
paired stable and candidate medians plus the fixed EXP-091 batch=1 baseline.
Check the 128K RTC suffix and its absence at 64K/256K/512K. Only after
correctness, gate isolation, reproducible 128K gain and no cross-size
regression may the tested source be promoted to stable with an immutable
tag. Otherwise retain it as an experimental branch and report the failure.

EXP-094 follow-up results (2026-09-23; jobs 858088 and 858089, both
COMPLETED/0). The ten-batch paired sweep and two-round PMC files are in
`results/exp094_batch_dependence_sweep_858088/` and
`results/exp094_batch_dependence_pmc_858089/` in the EXP-078 worktree;
both raw SHA256 manifests verified. Four pairs per condition, with
N=max(10,floor(10000/batch)), show that the broad recurrence is
batch-sensitive. At 128K, batch=1 total 0.019443337 -> 0.019130104 ms
(+1.611%, 3/4) and SBRC 0.008534471 -> 0.008202327 ms (+3.892%, 4/4);
batch=1000 total 7.608264500 -> 6.958565045 ms (+8.539%, 4/4)
and SBRC 3.979868545 -> 3.330238227 ms (+16.323%, 4/4).
At 256K, batch=1 total 0.023409389 -> 0.024271945 ms (-3.685%,
0/4) and SBRC 0.010829619 -> 0.011469814 ms (-5.912%, 0/4);
batch=2/4/8/32/1000 total gains were +2.698/+3.472/+4.470/
6.813/+7.722%, respectively. Batch=1000 SBRC gained +16.560%.
The additional 256K N controls reproduce the sign: batch=1,N=10
SBRC -2.178% (0/8), batch=1000,N=100 SBRC +17.154% (8/8);
changing N alone does not explain the crossover. At 512K, batch=1
total -1.210% (2/4, high variance) versus batch=1000 +2.053%
(4/4); the broad candidate is not safe for unknown batch workloads.

PMC of the 256K SBRC kernel (two rounds, per-workgroup normalized)
shows unchanged 60 VGPR, 48 SGPR, 32768 B LDS, 512-thread blocks,
192 LDS instructions and 1792 bank-conflict counts. The recurrence
changes VALU 2000 -> 2280 (+14.0%) and VMEM reads 116 -> 44
(-62.1%) per workgroup at every sampled batch. L2 misses remain
about 768/workgroup and read requests about 512/workgroup; fewer
VMEM instructions do not imply proportionally less external traffic.
The unprofiled paired timings and profiled kernel durations both
reverse sign as batch grows: PMC 256K SBRC batch=1 ~19.04 -> 20.08
us (+5.5% duration), batch=1000 ~8.124 -> 7.289 ms (-10.3%
duration). Cache-hit and stall counters vary with batch; they do not
alone prove a unique causal bottleneck. The supported conclusion is
a throughput/latency crossover under unchanged resources and data
requests, not a universal batch=1000 benefit. Do not retain the
broad EXP-094 gate.

EXP-095 results (2026-09-23; source commit
`88b0322ecc623a2c9898ad740aa83e1d0f2e4b5b`; jobs 858371
build/correctness and 858372 paired batch=1, both COMPLETED/0).
The 64K/128K/256K/512K x forward/inverse x in/out-of-place x
batch=1/3 correctness matrix passed 32/32, tolerance 5e-12:
`exp-095-sbrc128k-only/results/exp095_build_validate_858371/correctness.json`.
Eight same-GPU, same-condition process pairs used DP z2z forward
out-of-place, batch=1, -N10000, canonical divisor 10001. Raw timing
CSV and SHA256 manifest are in
`exp-095-sbrc128k-only/results/exp095_paired_batch1_858372/`;
the manifest verified. Stable/candidate library SHA256 are
`ad152877ba276dd70d6dbdac2e6fec454e348eb989431229f412a69f2da531a5`
and `bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539`.
Analyzer verified the `_ordtwrec128k` RTC suffix at 128K only and
its absence at 64K/256K/512K. The measured paired medians (ms) are:

| N | stable | EXP-095 | paired gain | candidate vs fixed EXP-091 baseline |
|---:|---:|---:|---:|---:|
| 65536 | 0.017406229 | 0.017346378 | +0.344% (4/8) | 0.999995x |
| 131072 | 0.019433537 | 0.019087594 | +1.780% (8/8) | 1.018992x |
| 262144 | 0.023448049 | 0.023447142 | +0.004% (3/8) | 0.990509x |
| 524288 | 0.053039961 | 0.053175447 | -0.255% (4/8) | 0.960450x |

The fixed EXP-091 batch=1 baselines were 0.017346298,
0.019450103, 0.023224602, and 0.051072366 ms, respectively.
The 256K/512K fixed-baseline differences also occur for the stable
library within job 858372 (notably 512K stable 0.053039961 ms);
therefore cross-day fixed-baseline ratios are descriptive, not a
cross-size regression verdict. For 512K, stable/candidate CVs were
5.23/4.56% and only 4/8 pairs favored the candidate. The only
consistent changed-size signal is 128K (8/8 wins); unchanged sizes
show no consistent paired regression. Decision: accept only the
128K-scoped recurrence as the new stable version; reject the broad
EXP-094 gate. No global handoff or planner change was introduced.

EXP-096 (pre-registered 2026-09-23): remeasure the *original official*
ROCm 7.2.2 rocFFT baseline against the latest retained EXP-095 stable
version at batch=1. This answers the user's request left open by the
EXP-095 result: job 858372 compared the prior optimized EXP-090 stable
runtime, not the original official baseline. Historical official CSVs
are batch=1000 and must not be reused for a batch=1 speedup.

Official source: the user-provided original archive
`/public/home/zhangkewei/rocm-libraries-rocm-7.2.2.tar.gz`
(SHA256 `4dbdeb5241b12becb379f58dafce685028824fca191ad2a54c3d8d671ca38f63`).
Only its `projects/rocfft` tree was extracted under
`/public/home/zhangkewei/zr/exp096-official-archive/`.
A byte-for-byte tree comparison matched the upstream rocm-7.2.2 tag,
commit `dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef`.
Build the official rocFFT and bench in isolated
`/public/home/zhangkewei/zr/build/exp096_official` and install to
`/public/home/zhangkewei/zr/install-exp096-official`. Validate the
same 32-case NumPy matrix before timing. Latest stable source is
`88b0322ecc623a2c9898ad740aa83e1d0f2e4b5b`, tagged at record
commit `d5924f87207a6393cf818971211dd26d2c6cfd26`;
installed library SHA256 is
`bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539`.
No stable-source edit or new optimization is proposed.

Submit the build/correctness job
`exp096_official_build_validate.slurm` and, with afterok dependency,
the paired benchmark job `exp096_official_vs_stable_batch1.slurm`.
The latter runs eight interleaved official/latest process pairs per
64K/128K/256K/512K on one GPU allocation: DP z2z forward,
out-of-place, batch=1, `hipprof --stats`, -N10000, divisor 10001.
Alternate variant and length order; preserve all raw CSVs, logs, binary
hashes, per-size medians, CVs, paired wins, speedup and transform-only
diagnostics. Analyzer: `exp096_analyze_pair.py`. Do not interpret
results or submit follow-up work until the user asks to check.

EXP-096 results (2026-09-23): build/correctness job 858703 and
same-GPU paired timing job 858704 both COMPLETED/0 on f09r1n06.
The original user archive SHA256
`4dbdeb5241b12becb379f58dafce685028824fca191ad2a54c3d8d671ca38f63`
was checked at build and benchmark time; its extracted rocFFT source
matched upstream rocm-7.2.2 commit
`dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef` byte-for-byte.
The isolated official build passed the 32/32 NumPy correctness matrix
(tolerance 5e-12) in
`results/exp096_official_build_858703/correctness.json`.
Official/latest librocfft SHA256:
`3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5`
and `bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539`.
The benchmark executables were hashed in
`logs/exp096_official_pair_858704.out`.

Eight interleaved pairs per length used batch=1, -N10000 and the
canonical (TotalDurationNs minus random-input kernel)/10001/1e6
metric. The analyzer verified the 128K-only RTC suffix in the latest
version. The 64 raw hipkernel CSV SHA256 checks passed; full
per-round data are in
`results/exp096_official_pair_858704/paired.json`, concise results
in `paired.txt`, and the manifest in `raw_sha256.txt`.
Build and timing logs are
`logs/exp096_official_build_858703.{out,err}` and
`logs/exp096_official_pair_858704.{out,err}`.

| N | original official baseline ms | latest EXP-095 stable ms | baseline/latest speedup | time reduction | latest wins | baseline/latest CV |
|---:|---:|---:|---:|---:|---:|---:|
| 65536 | 0.017998436 | 0.017343149 | 1.037784x | 3.640797% | 8/8 | 0.564/0.053% |
| 131072 | 0.020949760 | 0.019103228 | 1.096661x | 8.814099% | 8/8 | 0.592/0.358% |
| 262144 | 0.028916669 | 0.023305366 | 1.240773x | 19.405082% | 8/8 | 0.189/3.036% |
| 524288 | 0.087667321 | 0.054067399 | 1.621445x | 38.326621% | 8/8 | 0.425/5.992% |

The latest 512K absolute time fluctuated (52.0-60.1 us), so retain
the CV and raw rounds; even its slowest pair was 1.456x faster than
the official baseline. Transform-only medians closely track the
canonical medians, so fixed twiddle-generation amortization does
not explain these speedups. This is a batch=1 comparison against
the *original official* rocFFT, distinct from EXP-095's comparison
against the previously optimized EXP-090 installation. Decision:
original-baseline comparison complete; no source change or further
stable promotion. The latest stable tag remains
`stable-exp095-sbrc128k-only-20260923`.

EXP-097 (pre-registered 2026-09-23): diagnose the EXP-096 batch=1
512K latest-stable process-to-process latency variation, without changing
the stable source, plan, metric, or 128K-only optimization gate.
EXP-096 has eight latest 512K canonical rounds from 0.051994856 to
0.060143834 ms (CV 5.992%), while the official baseline CV is 0.425%.
Per-kernel CSVs place the variation mainly in the first SBCC-1024
kernel (26.260-33.188 us per transform, CV about 10.28%); the second
SBRC-512 kernel varies only 25.681-26.952 us (CV about 1.73%). The
random-input initialization kernel is excluded from the canonical metric.
Read-only analysis of the hipprof databases finds 10001 SBCC calls per
process, with narrow within-process durations and persistent fast/slow
process modes. This localizes the variation but does not yet prove a
clock, cache, memory-placement, or other physical cause.

Submit both diagnostic jobs at once, with the PMC job dependent on the
timing job so they cannot share the GPU. `exp097_512k_process_modes.slurm`
runs 16 interleaved official/latest pairs for 512K, DP z2z forward,
out-of-place, batch=1, `hipprof --stats`, -N10000 (divisor 10001), with
both process orders balanced. Eight latest processes have timestamped
active `rocm-smi` clock, power, temperature, and utilization sampling;
the other eight serve as unmonitored controls. Preserve all per-call
hipprof databases and CSVs. `exp097_512k_sbcc_pmc.slurm` collects 12
independent SBCC and four SBRC full PMC profiles on the same validated
latest binary, batch=1, -N10, separately from normal latency timing.
PMC replay durations are not canonical timing observations. Compare
frequency/power telemetry, per-process kernel modes, baseline controls,
and PMC counters; report any residual causal uncertainty. Correctness
remains the EXP-096 32/32 result because binaries and source are unchanged.
Raw outputs will be under `results/exp097_512k_modes_<jobid>/` and
`results/exp097_sbcc_pmc_<jobid>/`; logs under `logs/exp097_*_<jobid>.*`.
Job IDs and results are pending; wait for the user to ask to check them.

EXP-097 interim result (2026-09-23): normal timing job 859120
COMPLETED/0 on f09r1n01. Its 16 official/latest 512K pairs all favored
the latest binary. Canonical batch=1, -N10000 medians were
0.087534780 ms official and 0.053104567 ms latest (1.648348x);
process CVs were 0.611% and 4.602%, respectively. Latest rounds
spanned 0.052730624-0.060307721 ms. The latest SBCC-1024 stage
spanned 26.786-33.035 us (CV 7.5536%), while SBRC-512 spanned
25.932-27.269 us (CV 1.7201%). Per-call databases again show 10001
SBCC dispatches per process with persistent fast/slow modes rather
than isolated long calls or a within-process thermal ramp.
Eight latest processes were monitored; their 199 rocm-smi samples
all reported 0% HCU use and 600 MHz sclk, including timestamps
inside the recorded GPU-dispatch interval. Thus those SMI readings
cannot establish the active kernel clock or rule out clock effects.
Monitored and unmonitored runs both contained slow modes. Raw timing,
telemetry, and per-call data: results/exp097_512k_modes_859120/;
logs: logs/exp097_512k_modes_859120.{out,err}.
The dependent PMC job 859121 FAILED/1 on f09r1n03 after one second:
Bash set -u rejected a same-line local declaration that expanded
output using family before family was assigned. It collected no PMC
counters. Fix only this shell-script defect and submit a fresh PMC
retry; do not use the failed run as hardware evidence. No library,
planner, stable branch, or correctness change was made.

EXP-097 counter retry 859154 COMPLETED/0 on f09r1n03, same
EXP-095 installed librocfft SHA256
bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539.
Twelve SBCC and four SBRC independent processes used batch=1, -N10,
full PMC type 3; all 48 CSV hashes verified. For SBCC, post-warm-up
per-dispatch medians across processes had 262630-262633 aggregate
TCC misses, 34910-35470 aggregate TCC hits, exactly 635904 VALU,
12800 VMEM read and 8192 VMEM write instructions, and exactly
241876 LDS bank conflicts. This counter workload showed no large
hit/miss-count bifurcation. Its profiled SBCC duration was
43.447-45.295 us (CV 1.209%), unlike normal -N10000 timing at
26.786-33.035 us (CV 7.554%). Because PMC replays kernels, changes
N, and ran on another node, it neither captures nor rules out the
physical cause of the normal fast/slow modes. Raw counter files:
results/exp097_sbcc_pmc_859154/; logs:
logs/exp097_sbcc_pmc_859154.{out,err}. Independently, bench's own
GPU-event medians in EXP-097 timing log repeat the same mode (latest
rounds 2/4: 61.92/68.96 us), so it is not an artifact of reconstructing
hipprof's TotalDurationNs. No stable-source change or promotion.

EXP-098 (pre-registered 2026-09-23): test whether persistent 512K
batch=1 SBCC process modes track GPU allocation placement. Read-only
source audit shows rocfft-bench allocates its work, input and output
buffers once per process, then reuses them for 10000 transforms.
Existing hipprof databases omit buffer pointer arguments, so address
correlation cannot be tested from EXP-097 artifacts. Use an isolated
LD_PRELOAD hipMalloc interposer that logs returned pointer and size;
its optional 8 or 16 MiB dummy allocation happens before the first
ordinary allocation and is never accessed. Preserve a no-interposer
control and a logging-only pad=0 control. Run eight Latin-square
rounds of all four conditions on one DCU (32 independent processes),
512K DP z2z forward out-of-place, batch=1, hipprof --stats, -N10000,
canonical divisor 10001. Compare each condition's process-mode
frequency and canonical timing with allocation addresses; a virtual
address association or pad effect is mechanism evidence, not proof
of physical page placement. The dummy allocation changes allocator
state and VRAM footprint, so interpret causality cautiously. Abort if
logging is absent or a pad hipMalloc fails. Scripts:
exp098_log_hipmalloc.c and exp098_allocator_modes.slurm; only diagnostic
code changes, no rocFFT library, planner or stable-tag edit. Raw output
will be results/exp098_allocator_modes_<jobid>/ and
logs/exp098_alloc_modes_<jobid>.{out,err}. Job ID/results pending;
stop after submission and wait for the user to request a check.

EXP-098 result (2026-09-23): job 859182 COMPLETED/0 on f09r1n03.
All 32 independent 512K batch=1 processes used the same stable library
SHA256 bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539;
all 88 raw timing and allocation files passed SHA256 verification.
The 24 interposed allocation logs each had one PID matching its
corresponding HIPOPS database, and all dummy hipMalloc calls succeeded.
The slow mode was defined descriptively by SBCC mean >28 us/call;
the observed fast maximum was 27.085 us and slow minimum 28.221 us.

| condition (8 processes each) | slow SBCC processes | canonical median us | range us | CV |
|---|---:|---:|---:|---:|
| no interposer | 4/8 | 54.275 | 52.043-60.341 | 5.18% |
| logging only | 2/8 | 52.368 | 52.198-59.681 | 5.50% |
| 8 MiB untouched pad | 0/8 | 52.442 | 52.305-52.888 | 0.36% |
| 16 MiB untouched pad | 1/8 | 52.351 | 52.147-60.054 | 5.11% |

In round 6 the control measured 60.341 us (SBCC 32.625 us)
versus pad8 52.344 us (SBCC 26.521 us); SBCC explained 6.104
of the 7.997 us difference. The control's slow process had 10001
SBCC calls with p10/p50/p90 31.20/32.64/33.92 us; pad8's same-round
fast process had 25.28/26.72/27.52 us. The benchmark's independent
HIP-event medians were 69.28 and 61.60 us, confirming a sustained
process mode rather than a few outliers or CSV arithmetic. However,
pad16 was slow in round 5 and logging-only slow in rounds 5 and 7.
Logging-only rounds 3 (fast) and 5 (slow) had identical low 4-bit
MiB offsets (6,6,12) for the three 8 MiB virtual buffers, so a
simple virtual-address alignment rule is not supported. The pad
changes allocator state and footprint; 0/8 slow with pad8 is not
proof of physical placement or a dependable benchmark fix. Do not
add a hidden pad to the official metric. No source change, stable
promotion, or new performance contract. Raw data:
results/exp098_allocator_modes_859182/; log:
logs/exp098_alloc_modes_859182.{out,err}.

EXP-099 (pre-registered 2026-09-23): build an independent C++ rocFFT
benchmark to test whether the persistent 512K batch=1 process modes
survive a different client and whether input refresh or hipprof
affects them. Branch exp-099-standalone-benchmark starts from
EXP-098 record commit 3de58754240c34831232e2c64719f2ffdf7451ea;
the stable rocFFT source and installed library are unchanged.
Source exp099_standalone_bench.cpp creates the same DP z2z forward,
out-of-place, length-524288, batch-1 plan, allocates explicit work,
input, and output buffers in rocfft-bench order, executes one warm-up,
then uses one HIP event pair with synchronization around each of
10000 transforms. It records every event sample, per-process
summary, buffer virtual addresses, and whether fixed input changed.
A separate impulse-DFT check must pass before timing.
The refresh mode runs hipMemsetAsync before each timed transform
on the same default stream; the fixed mode does not refresh.
These modes intentionally have different input/cache conditions.
HIP-event and host times are diagnostic only; they must not replace
the AGENTS.md canonical hipprof GPU-kernel metric.

The single Slurm job exp099_standalone_bench.slurm will compile the
client and run eight Latin-square rounds of four independent-process
conditions on one GPU: fixed without profiler, refresh without
profiler, fixed under hipprof --stats, and unchanged rocfft-bench
under hipprof --stats. Both profiled arms have one warm-up and
10000 measured transforms; only the unchanged rocfft-bench arm is
the official canonical anchor. Compare only like-for-like metrics;
custom profiled kernel totals can diagnose SBCC/SBRC behavior but
are not a replacement baseline. If fixed input changes, report it
as a diagnostic workload, not a faithful repeated-input FFT.
Preserve stdout, 10000-event sample CSVs, profiler CSV/DB,
binary hashes, and all raw files. Preflight C++ syntax and link
checks passed; correctness and GPU timing remain pending.
Expected results: results/exp099_standalone_bench_<jobid>/ and
logs/exp099_standalone_bench_<jobid>.{out,err}.
Submit one job containing all conditions, then stop and wait for
the user to request a result check.

EXP-100 (pre-registered 2026-09-24): test whether the user's one-shot hipFFT
client provides a useful diagnostic for the batch=1 512K DP z2z workload,
without changing rocFFT source, stable install, or measurement contract.
Preparation branch is `exp-099-standalone-benchmark`, starting commit
`d7f1bce8b7f5b47bb1e0c0fc4b8032dcbb75fa69`; stable runtime is
`install-exp095-candidate`, whose `librocfft.so.0.1` SHA256 is
`bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539`.

The user attachment SHA256 is
`28134F74B9A8EAFD8E47C5407EC87FC7A448A0CA3D1CEA4DA3EE01148DE0483B`.
Archive it as `fft_test_1d_original.cpp`; `fft_test_1d_exp100.cpp` is an
adapted copy whose only source diff changes `OUTPUT_PATH` to the EXP-100 CSV
directory under this repo. The adapted source SHA256 is
`48D4B6C2CE93ACF2C0929283546B1ECBC35F4C2B3850FC26AE7768CE82C0F5A1`.

One Slurm allocation requests one DCU. In eight blocks, execute four
adjacent pairs of independent processes for each client condition
(`524288 1 z2z_1d` and `524288 0 z2z_1d`), 32 processes per condition.
Each block has two pairs in each order. The unmodified client keeps its
input generation, buffer setup, 3 separate-buffer warmups (when enabled),
`test_times=1`, HIP-event placement and synchronization unchanged.
After every block, run one unchanged stable `rocfft-bench` reference with
512K, DP z2z forward out-of-place, batch=1, `hipprof --stats`, `-N10000`.
Thus eight standard profiled anchors are distributed through the sequence.

The client results are single HIP-event durations in its CSV and per-process
stdout; summarize only their own repeated-process distribution. Keep these
values separate from `rocfft-bench` canonical hipprof time, reconstructed
with divisor 10001 after excluding only the verified benchmark input-gen
kernel. Record the allocated node/GPU, compiler and binary hashes, `ldd`
resolution and SHA256 for the actually resolved hipFFT/rocFFT libraries,
all per-run stdout, per-run CSV snapshots, full CSV, hipprof CSV/DB and logs.
The app itself has no numerical output check and ignores the `hipfftExecZ2Z`
return code, so a successful process and positive recorded event time attest
to invocation viability, not numerical FFT correctness. One event per fresh
process cannot establish a steady-state API latency.

Sources/scripts are `fft_test_1d_original.cpp`, `fft_test_1d_exp100.cpp`, and
`exp100_user_hipfft.slurm`; record this entry in both synchronized copies.
Expected artifacts are `results/exp100_user_hipfft_<jobid>/`,
`results/exp100_user_hipfft_csv/fft_test_1d_exp100.csv`, and
`logs/exp100_user_hipfft_<jobid>.{out,err}`. The first attempt, job `860032`,
failed after 7 seconds (exit 1) during linking, before any FFT execution:
`ld.lld` reported undefined `std::filesystem` symbols (`create_directories`,
`_M_split_cmpts`, `_M_find_extension`) because the client link command omitted
`-lstdc++fs`. No FFT measurements were produced. Preserve the failure output at
`results/exp100_user_hipfft_860032/stdout/build.log` and
`logs/exp100_user_hipfft_860032.{out,err}`.

The earlier login-node preflight used link parameters different from the
submitted script and was insufficient. The retry changes only the client
link command by appending `-lstdc++fs`; source, stable rocFFT install,
measurement contract, and sample sequence remain unchanged. Preflight the
exact revised script command, verify `ldd` resolves stable rocFFT, `bash -n`
passes, and the CSV target is absent; then submit one corrected job. Wait for
the user to ask before inspecting its result.
Follow-up: retry job `860170` also failed after 9 seconds (exit 1) on the
first `is_warmup=1` client run: `open comgr lib:libamd_comgr.so error`,
`load comgr library error`, `load library error`, `HIP error`. It produced no
valid client timing sample. Preserve its output in
`results/exp100_user_hipfft_860170/` and
`logs/exp100_user_hipfft_860170.{out,err}`.

A read-only toolchain check found `/public/software/compiler/dtk-26.04/lib64/libamd_comgr.so`
resolves to `/public/software/compiler/dtk-26.04/dcc/comgr/lib64/libamd_comgr.so.2.6.0`
(SHA256 `3e62d2545564a05b334635be2ed98d2c9fbef2c8927d0d9ec23783431267eaba`).
No system toolchain files are modified.

Next retry: keep `${LATEST}/lib` first and add `${TOOLCHAIN}/lib64` before
`${TOOLCHAIN}/lib` in `LD_LIBRARY_PATH`, including each benchmark invocation.
Before client execution, load `libamd_comgr.so` with `ctypes.CDLL`; record the
actually loaded real path and SHA256 in the job output. Validate this exact
environment, script syntax, stable rocFFT hash, and absent CSV target, then
submit one corrected job retaining the 32+32 client runs and eight references.
Preserve all prior failures and wait for the user before inspecting new results.

Follow-up: retry job `860366` failed after about 9 seconds (exit 127) on the
first `is_warmup=1` client invocation, before producing a valid timing sample:
`/public/software/compiler/dtk-26.04/lib/libhipfft.so.0: undefined symbol:
`rocfft_plan_description_set_NotIsRocTop`. No FFT measurements were produced.
Preserve `results/exp100_user_hipfft_860366/` and
`logs/exp100_user_hipfft_860366.{out,err}`.

The prior link selected hipFFT from the toolchain while runtime resolution
selected the stable candidate rocFFT; this library pair is ABI-incompatible
for the required rocFFT plan-description symbol. A read-only check confirmed
`/zr/install/include/hipfft/hipfft.h` exists and
`/zr/install/lib/libhipfft.so.0.1` has SHA256
`d90867c5f9728bd59f32ef79c3a6b9b5636c9ea3892d1620719bbd3572da37c8`.
Under candidate-first runtime lookup, `ldd -r` on that hipFFT resolves
rocFFT from `install-exp095-candidate` with no unresolved symbols. The system
toolchain remains read-only.

Next retry: prioritize `${ZR_INSTALL}/include`; link with
`-L${LATEST}/lib -L${ZR_INSTALL}/lib -L${TOOLCHAIN}/lib` and
`-lhipfft -lrocfft -lstdc++fs`. The candidate lib directory was verified
not to contain `libhipfft`, so hipFFT comes from `${ZR_INSTALL}/lib` and
rocFFT from `${LATEST}/lib`. Use the same runtime path order for client and
reference: candidate rocFFT, `${ZR_INSTALL}/lib`, toolchain `lib64`, then
toolchain `lib`. Keep the COMGR load check; record and verify the resolved
hipFFT/rocFFT paths and hashes, and require `ldd -r` to show no missing or
undefined symbols. The exact link command passed a login-node-only preflight
with `ldd -r`; no GPU workload was run during preflight. Preserve the original
source, measurement contract, 32+32 client invocations, and eight references.
Submit one corrected job only after final script, source/library hash, CSV
absence, syntax, and Slurm dry-run checks pass; preserve all previous failures.

EXP-100 result (job 860543, 2026-09-24): completed on f09r2n05 with exit 0;
the error log is empty. All 64 client invocations (32 independent processes
with is_warmup=1 and 32 with is_warmup=0) and eight interleaved stable
rocfft-bench references completed. Each client process recorded one HIP-event
sample for 512K double-precision forward out-of-place Z2Z, batch=1. The warm
condition performs three transforms on separate buffers before the timed
transform. The 168 raw files passed SHA256 verification. Evidence is in
results/exp100_user_hipfft_860543/ and logs/exp100_user_hipfft_860543.{out,err}.

Client event durations, in microseconds (population SD/CV):

| condition | n | median | mean | SD | CV | min-max |
|---|---:|---:|---:|---:|---:|---:|
| is_warmup=1 | 32 | 72.80 | 72.605 | 2.623 | 3.613% | 67.68-77.92 |
| is_warmup=0 | 32 | 104.00 | 124.320 | 77.663 | 62.471% | 98.24-446.718 |

All 32 adjacent cold/warm pairs had a slower cold sample; the median paired
difference (cold minus warm) was 32.00 us. The cold mean/CV include two
outliers of 401.118 and 446.718 us; do not silently discard them. Warmup
reduces the observed one-shot spread, but even warm samples range over
10.24 us, so one sample is inadequate to judge a 1-2% optimization.

The eight reference canonical hipprof GPU-kernel times, using the Total-row
minus verified input-generation kernel and divisor 10001, were 52.650828,
55.180342, 51.832440, 52.203783, 52.982836, 52.155647, 52.024939,
and 56.486712 us (median 52.4273055 us). This is a different timing
metric/protocol from the client's event interval; their absolute values must
not be divided to claim a speedup. Only the stable installation was tested;
there is no baseline/candidate comparison or optimization speedup result.

The 64 client processes consumed 1742.31 s in aggregate (27.224 s/process
on average), and the eight reference processes consumed 130.081 s. These
process runtimes explain the roughly 31-minute job despite microsecond event
samples. Per-process startup, plan creation, and RTC preparation are outside
the timed event; with RTC cache reads/writes disabled, repeated preparation
is a plausible contributor, but no phase-by-phase wall-clock breakdown was
collected. The event does not measure end-to-end request latency. The client
does not check numerical output or hipfftExec/HIP-event return codes, so
successful execution does not establish FFT correctness. The result supports
this client only as a diagnostic of defined one-shot event latency, not as a
replacement for the official canonical rocfft-bench measurement.

For a future comparison, keep the same workload, libraries, warmup policy,
event protocol, and GPU allocation for both versions; interleave paired
independent processes, collect multiple samples, report the full distribution,
and add numerical and API-return-code checks. Retain the canonical profiled
rocfft-bench metric as the acceptance criterion. No further job was submitted
as part of this result inspection.

## EXP-101 (pre-registered 2026-09-24): user HIP-event client, official baseline vs latest stable

Preparation branch: `exp-099-standalone-benchmark`, starting commit `d7f1bce8b7f5b47bb1e0c0fc4b8032dcbb75fa69`. This is a measurement-only experiment; rocFFT source, both installed rocFFT libraries, and the original user source/archive are not changed.

Compare the official baseline installation `/public/home/zhangkewei/zr/install-exp096-official/lib/librocfft.so.0.1` (SHA256 `3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5`) with the latest validated stable installation `/public/home/zhangkewei/zr/install-exp095-candidate/lib/librocfft.so.0.1` (stable source commit `88b0322ecc623a2c9898ad740aa83e1d0f2e4b5b`, tag `stable-exp095-sbrc128k-only-20260923`, library SHA256 `bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539`). Both arms use the same installed hipFFT `/public/home/zhangkewei/zr/install/lib/libhipfft.so.0.1` (SHA256 `d90867c5f9728bd59f32ef79c3a6b9b5636c9ea3892d1620719bbd3572da37c8`).

The source `fft_test_1d_exp101.cpp` is copied from `fft_test_1d_exp100.cpp`; its only source change is a dedicated EXP-101 CSV output directory. Build one executable against the official baseline and the fixed hipFFT installation. Run that same binary in both arms, setting the selected rocFFT installation first in `LD_LIBRARY_PATH`. Before any measurements, require separate `ldd -r` checks to resolve hipFFT to `/zr/install/lib/libhipfft.so.0.1`, resolve rocFFT to the selected arm, and report no missing libraries or undefined symbols. Record both linkage outputs and the real paths and hashes of the loaded rocFFT and hipFFT files.

One Slurm allocation uses one DCU. Compare DP z2z, forward, out-of-place, batch=1 at lengths 65536, 131072, 262144, and 524288. Collect 16 adjacent baseline/stable pairs per length, for 128 independent client processes total. Rotate length order across rounds and balance arm order to eight baseline-first and eight stable-first pairs per length. Every process uses only `is_warmup=1`: the existing program performs three warm-up transforms on separate buffers, then records one HIP-event duration for one timed transform.

Retain each process stdout, one-row CSV snapshot, full CSV, per-sample length/round/arm/order/time/timestamps TSV, executable and source hashes, compiler/toolchain and COMGR hashes, selected GPU/environment details, and raw checksums. Require exactly one CSV row per process (128 data rows plus header), one sample in each arm for every length/round pair, and positive event durations.

Report each arm's median event time per length, `median_baseline / median_stable`, the median of the 16 paired baseline/stable speedup ratios, and the number of pairs won by each arm. Keep every observation; do not drop outliers. This is the user's one-shot HIP-event interval and must not be combined with or divided by EXP-096's canonical `hipprof --stats` GPU-kernel times. The client does not validate numerical output or check every HIP/HIPFFT return code, so successful execution and a positive event duration establish invocation viability, not numerical correctness.

Expected artifacts: `results/exp101_user_hipfft_<jobid>/`, `results/exp101_user_hipfft_csv/fft_test_1d_exp101.csv`, and `logs/exp101_user_hipfft_<jobid>.{out,err}`. No EXP-101 job has been submitted.

EXP-101 result (job 860936, 2026-09-24): the 128 paired client processes
completed, with 16 pairs at each of the four lengths. The event-time medians
for official baseline / EXP-095 stable were 26.88 / 27.12 us (64K),
31.20 / 29.04 us (128K), 42.40 / 37.76 us (256K), and 95.76 / 72.16 us
(512K); the corresponding ratio of medians was 0.9912x, 1.0744x,
1.1229x, and 1.3271x. These are warm one-shot hipFFT event intervals,
not EXP-096's profiled rocfft-bench kernel times; they must not be mixed.
All raw samples and checksums remain in results/exp101_user_hipfft_860936/.
The client lacks a numerical output check, so this is a performance
diagnostic only. No stable-source change followed EXP-101.

## EXP-102 (pre-registered 2026-09-24): research-derived FFT workload matrix

Reason: the actual semantic batch and external evaluator are unknown, and
the independent-process effect seen at 512K means a single batch=1 or
batch=1000 score cannot stand for the entire intended use. This is a
measurement-only experiment. It does not modify the official baseline or
EXP-095 stable library, planner, kernels, or original archive. Starting
experimental branch is exp-099-standalone-benchmark at
d7f1bce8b7f5b47bb1e0c0fc4b8032dcbb75fa69; the stable source remains
88b0322ecc623a2c9898ad740aa83e1d0f2e4b5b. The official baseline
librocfft.so.0.1 SHA256 is
3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5;
the stable library SHA256 is
bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539.

Use 1D double-precision packed interleaved complex FFT lengths
65536/131072/262144/524288, semantic batches 1/2/4/8/16/32/64,
forward/inverse, and in-place/out-of-place: 112 initial workloads. Each
array task uses one DCU and one length. For a fixed length/direction/
placement, compare batch throughput from B32 to B64 in Stage B; extend
to B128, and conditionally B256, if either library still gains >5% per
doubling and allocation succeeds. Keep per-workload output; no cross-batch
combined score. Additional batches use the same validation and timing
protocol. Any memory-limited extension is recorded as skipped, not as a
successful measurement.

Run correctness before timing for every workload. The independent client
checks full output for a nontrivial deterministic input against the official
baseline and checks both libraries against an analytic two-point signal.
The source's default double epsilon (1e-15), output L-infinity component
norm and log(length) scaling guide the threshold; the baseline-output norm
is a proxy for the CPU/FFTW norm used by rocfft-test, not a claim of full
rocfft-test equivalence. An API failure, library-image mismatch, nonfinite
output, or failed correctness check stops that workload before timing.

Stage A: both installed versions' unchanged rocfft-bench, -N30 without
profiling, with plan creation and input preparation outside each HIP event.
Stage B: one separate benchmark executable dynamically loads both absolute
library paths and verifies their API images; both plans query workspace
requirements, share a preallocated buffer of the maximum size, and each
receives at least one untimed warm-up. Every event interval contains exactly
one rocfft_execute. Host-to-device input restoration and correctness are
outside the interval. Each of five independent process blocks starts with
six randomly ordered adjacent AB/BA pairs (30 pairs total). If CV exceeds
1% or the process-aware paired-bootstrap 95% speedup CI relative half-width
exceeds 1%, add 10 pairs at a time to a maximum of 100. Retain all samples
and outliers; label persistent instability inconclusive. Report per-workload
medians, means, SD, CV, paired speedup/CI, transforms/s, time per transform,
and each library's workspace bytes. Record device temperature/clocks when
available, but do not assume a particular temperature is automatically
steady. GPU profiler output is not part of this experimental metric.

This HIP-event execute-only lane is not numerically comparable with prior
hipprof canonical results, nor with the EXP-100/101 hipFFT one-shot client.
For workloads where either Stage B arm has a median below 100 us, Stage C
runs five adjacent randomly ordered AB/BA pairs. Each Stage C measurement
uses one HIP event pair around K rocfft_execute calls on K independently
initialized input slots, preserving the same semantic batch. K is chosen
so every retained aggregate event interval lasts at least 10 ms; an
under-target attempt is discarded and K increased. For in-place calls,
every slot has its own input buffer. Stage C reports total/K timing and
speedup separately from Stage B. If device capacity cannot support the
independent slots, record CAPACITY_SKIP; do not replace or silently merge
the Stage B result. No cold-plan or host end-to-end claims follow.

Preparation files: exp102_paired_bench.cpp, exp102_aggregate_bench.cpp,
exp102_orchestrate.py, exp102_preflight.sh, and exp102.slurm. The static
and build preflight checks syntax, linkage, and pinned library hashes but
does not run GPU work. Expected raw output: results/exp102_workload_matrix_<jobid>/
and logs/exp102_workload_matrix_<jobid>_<arrayid>.{out,err}; actual job IDs,
correctness, counts, paths, timing, speedups, and decision are pending.
Submit the complete array once after static/build preflight; stop after
submission and wait for the user to request result inspection.

EXP-102 result (job 861601, inspected 2026-09-24): array tasks 0 and 1
completed with 36 workloads each (64K, 128K); tasks 2 and 3 ended
OUT_OF_MEMORY after 8 and 7 completed workloads (256K, 512K). Thus 87
workloads passed the full baseline/stable plus analytic correctness gate,
but only 70 of 112 required base workloads completed. The 256K B256 and
512K B128 forward in-place correctness subprocesses were SIGKILL -9. Each
has 1 GiB of transform data; the check retained multiple 1 GiB host
vectors while the Slurm task had 3888 MiB host memory. The kill happened
after CHECK_PAIR and before the analytic checks. This is a harness memory
failure, not evidence of a numerical failure in rocFFT.

All 87 completed workloads have Stage A and Stage B artifacts under
results/exp102_workload_matrix_861601/ and array logs under
logs/exp102_workload_matrix_861601_<arrayid>.{out,err}. Stage A used the
intended installed libraries (verified by loader resolution). Its forward,
in-place B1 medians, official baseline/stable in us, were 23.36/22.56
(64K), 25.60/25.04 (128K), 34.24/29.28 (256K), and 92.48/56.64
(512K); these are preliminary within-process 30-trial results, not a
converged multi-process comparison. Stage B instead measured about
231.52/231.44 us at 64K B1, versus Stage A's 23.36/22.56 us for the
same workload. Across 87 workloads the median Stage B minus Stage A
median was about 260.0 us (baseline) and 256.2 us (stable), showing a
large near-fixed measurement artifact whose mechanism is not yet proven.
Eighty-five workloads reached the 100-pair limit without satisfying the
CV criterion. All 87 Stage C lanes were NOT_REQUIRED because the trigger
looked only at inflated Stage B medians, although 40 workloads had a
Stage A median below 100 us. Decision: EXP-102 does not validate the
proposed measurement protocol or a definitive speedup. Do not promote its
Stage B speedups as canonical or change the stable rocFFT version from it.

## EXP-103 (pre-registered 2026-09-24): repair the independent-process timing protocol

Measurement-only branch exp-103-single-arm-benchmark starts from commit
d7f1bce8b7f5b47bb1e0c0fc4b8032dcbb75fa69. Keep the official
baseline and EXP-095 stable library images unchanged with SHA256
3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5
and bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539.
Use the same 112 base workloads and conditional B128/B256 extensions,
correctness oracle limits, unchanged Stage A rocfft-bench -N30, and
unprofiled HIP-event definition as EXP-102. Do not compare these with the
historical hipprof canonical metric. Raise each Slurm task's host memory
request to 16 GiB, and scope large host correctness vectors so the full
pair-output check is released before analytic checks.

Stage B uses one rocFFT library image per timed process. Five independent
adjacent A/B PROCESS pairs each run six single-execute event trials per arm
(30 matched samples initially); new process pairs add ten matched samples
at a time to a maximum of 100, with the same CV and hierarchical-bootstrap
CI stopping criteria. Randomize A/B process order; retain each process's
raw trials and match by trial index. This changes EXP-102's individual-event
adjacency to process-level adjacency to test whether simultaneously loaded
library images caused the 200-260 us offset. This is an explicit protocol
change, not a silent claim of exact EXP-102 equivalence. Before adaptive
collection, compare the initial 30-trial Stage B medians against same-
workload Stage A medians; a B/A ratio outside [0.5, 1.5] in either arm is
TIMING_SCOPE_MISMATCH and aborts further matrix testing rather than
publishing a contaminated score. This gate is diagnostic; passing it does
not by itself prove all noise has been removed.

Stage C triggers when either Stage A or Stage B has a median below 100 us.
For each short workload, use separate single-library processes for five
randomized adjacent A/B process pairs, one aggregate trial per process.
A common K is selected from the shorter median; K independent initialized
input slots are required, including in-place calls. Every retained HIP
event interval must cover at least 10 ms around K rocfft_execute calls.
On BELOW_TARGET, discard both arms and retry with larger common K; on
capacity failure record CAPACITY_SKIP separately. Report total/K and
speedup separately from Stage B.

Preparation files: modified exp102_paired_bench.cpp for scoped correctness,
plus exp103_single_arm_bench.cpp, exp103_single_arm_aggregate.cpp,
exp103_orchestrate.py, exp103_preflight.sh, and exp103.slurm. Preflight
compiles/links both clients and the correctness gate, checks syntax and
pinned library identities but runs no GPU work. Expected raw output:
results/exp103_workload_matrix_<jobid>/ and
logs/exp103_workload_matrix_<jobid>_<arrayid>.{out,err}; job IDs,
correctness, completed-workload counts, raw times, speedups and decision
are pending. Submit one complete four-length array after preflight, then
stop and wait for the user to request result inspection.

Pre-submit preparation commit: b3f808c9cefbe001b2bd7f0416fcfde85b263afc.
The compile/link/syntax/hash preflight passed without GPU work; Slurm
--test-only accepted the four-task array at 6 CPUs and 16 GiB per task.

EXP-103 result (job 861766, inspected 2026-09-25): all four array tasks
stopped at the first forward out-of-place workload because Stage B's parser
checked `data_bytes` against one FFT buffer, while its single-arm client
reports two allocated buffers for out-of-place transforms. Thus the reported
value was exactly twice the parser expectation; the observed failure is a
metadata-contract mismatch, not a demonstrated transform correctness or
performance failure. Across the partial run, 37 workloads passed correctness
and Stage A, 33 forward in-place workloads completed Stage B, and 13 short
workloads completed Stage C (130 aggregate rows). These are incomplete
diagnostic data, not a full 112-workload result. The Stage B/Stage A median
ratio was 1.003--1.424, so the large fixed EXP-102 timing offset was not
reproduced in those completed cases. Stage C retained intervals of at least
10 ms. Twenty-five of the 33 Stage B workloads hit the 100-pair limit;
do not label these converged. Raw outputs remain under
results/exp103_workload_matrix_861766/ and
logs/exp103_workload_matrix_861766_<arrayid>.{out,err}. No stable-version
decision follows from this incomplete matrix.

## EXP-104 (pre-registered 2026-09-25): correct out-of-place byte contract

Measurement-only branch exp-104-outofplace-contract starts from EXP-103
commit b5191e889b68f091125b9660396cf1bcb76eb463. Preserve the EXP-103
112 base workloads and adaptive B128/B256 extensions, correctness gate,
Stage A/B/C timing definitions, process pairing, stopping criteria, pinned
EXP-096 baseline and EXP-095 stable libraries, four target lengths, and
one-DCU-per-task allocation. Do not modify rocFFT kernels or the installed
library images. New EXP-104-owned runner/Slurm/preflight/test files are
used so EXP-103 evidence remains immutable.

The sole measurement-contract repair is for Stage B single-arm metadata:
`data_bytes` denotes total allocated data buffers, so expect N*batch*16
bytes in-place and 2*N*batch*16 bytes out-of-place. Stage C's
`per_execute_data_bytes` continues to denote one logical FFT buffer for
both placements. Before GPU submission, run synthetic no-GPU parser tests
for both valid placements and invalid sizes, Stage C out-of-place metadata,
and relevant early-status handling; compile/link/syntax/hash preflight and
Slurm --test-only must also pass. Reject any timing-scope mismatch rather
than interpreting it as an optimization result. Expected raw paths are
results/exp104_workload_matrix_<jobid>/ and
logs/exp104_workload_matrix_<jobid>_<arrayid>.{out,err}.

The EXP-104 no-GPU preflight passed: all six synthetic parser/status tests,
Python and Bash syntax, compilation and linkage of the unchanged EXP-102/103
C++ clients into EXP-104-owned binaries, pinned-library SHA checks, and
Slurm --test-only with six CPUs and 16 GiB per array task. The four local
source/script hashes matched their transferred copies before this check.

Pre-submit preparation commit: 9d113d42537973d080d692327b95ae8d07007161.
Job ID, correctness, completed-workload counts, timings, speedups, and final
decision are pending. Submit the complete
four-length array once; immediately stop and wait for the user to request
result inspection.

EXP-104 result (job 862765, inspected 2026-09-25): array tasks for 64K and
512K completed with 36 and 28 workloads respectively; 128K completed 21
workloads and 256K completed 2 before each task deliberately stopped at the
pre-registered Stage-B/Stage-A ratio guard. All 89 attempted workloads
passed the analytic correctness gate. In total 87 workloads, including
75 of the 112 required base workloads and 41 out-of-place workloads,
completed. The EXP-103 out-of-place metadata bug did not recur.

The guard fired at 128K batch8 inverse in-place (stable Stage A 82.24 us,
Stage B 124.08 us, ratio 1.50875485) and 256K batch4 forward in-place
(stable 85.52 us versus 129.84 us, ratio 1.51824136). These are policy
threshold crossings, not demonstrated numerical failures or proof that
HIP events included extra work. The two inputs are each 16 MiB. In the
completed rows, 64K Stage B met the adaptive convergence criterion in
0/36 workloads and 512K in 9/28; incomplete/nonconverged rows must not
be promoted as definitive speedups. Batch1 forward in-place Stage C
baseline/stable us and ratios were 18.715151/18.107689/1.033547 at 64K,
23.930640/21.728218/1.101362 at 128K, 37.026020/31.418584/1.178475
at 256K, and 90.971973/60.914349/1.493441 at 512K. The middle two
are from partial matrices. Raw evidence is preserved under
results/exp104_workload_matrix_862765/ and
logs/exp104_workload_matrix_862765_<arrayid>.{out,err}. This exploratory
HIP-event result does not replace the historical hipprof canonical metric;
no stable rocFFT version change is justified by this incomplete matrix.

## EXP-105 (pre-registered 2026-09-25): isolate input-restoration effects

Measurement-only branch exp-105-input-restore-diagnostic starts from
EXP-104 record commit c233e6b24a60f933c7aa2d1530a9f099990b5003.
The official rocfft-bench source restores input before each event using
device generation when built with hipRAND, while the EXP-103/104 single-arm
client uses a synchronous host-to-device copy before the event. Both
installed rocfft-bench images link hipRAND, and the CLI provides -g 0 for
device PRNG and -g 1 for host PRNG. Different preceding GPU activity may
change cache state; this is a hypothesis, not an established cause.

Run nine targeted 1D double-complex, forward/inverse as specified,
in-place, packed workloads on one DCU per array task. Submit all four
lengths as one Slurm array, with a concurrency limit of one to avoid
shared-node resource interference. For each length
64K/128K/256K/512K include forward batch1 as a control and forward batch
16/8/4/2 respectively (16 MiB of input). Also include 128K batch8 inverse,
the exact EXP-104 guard failure. Run correctness before timing. Within each
of five independent process blocks per workload, compare both pinned
library arms under three modes: official rocfft-bench -g 0 -N 30,
official rocfft-bench -g 1 -N 30, and the existing isolated host-copy
single-arm client with six single-execute event trials. Randomize mode
order by block and baseline/stable order within each adjacent arm pair.
Record every raw trial, command, process order, library identity and
workspace allocation. Report per-block and across-block medians,
Stage-A-host/Stage-A-device and Stage-B-host/Stage-A-host ratios for each
arm, plus uncertainty across process blocks. Do not pool lengths, batches,
or metric definitions. This is a mechanism diagnostic, not a full
optimization score: retain values outside [0.5,1.5] instead of aborting;
do not silently relax EXP-104's full-matrix gate. Do not run Stage C or
change rocFFT kernels/installed libraries. If host-input official bench
closes the gap, validate that interpretation before defining a revised
full-matrix protocol; otherwise investigate remaining plan/workspace or
cache differences.

Use new EXP-105-owned scripts and outputs. No-GPU preflight must validate
parser/trial contracts, syntax, linkage and pinned hashes, then Slurm
--test-only. Submit the entire four-task array once, stop immediately, and
wait for the user to request result inspection. Preparation commit, job
ID, raw paths, measurements and decision are pending.

## EXP-105 result (job 863229, inspected 2026-09-25)

All four serialized array tasks completed with exit code 0 and empty error
logs.  The nine preregistered workloads all passed correctness, and all five
process blocks were retained.  Device generation (-g0), host generation (-g1)
and custom host-copy produced the same optimization direction, but different
absolute execute times.  For 16 MiB inputs, official host/device medians were
roughly 1.18--1.35 depending on workload and library, and custom host/device
medians were roughly 1.22--1.38.  The custom and official host paths were
usually much closer to one another than either was to the device path.

The exact 128K batch8 inverse EXP-104 guard case gave stable official
host/device 1.292124 (95% block-bootstrap interval 1.242014--1.420363) and
custom-host/device 1.366466 (1.333011--1.462702).  The exact 256K batch4
forward case gave 1.302804 (1.283210--1.418207) and 1.377570
(1.304228--1.449806).  Thus EXP-104's 1.508755 and 1.518241 crossings were not
reproduced.  The supported conclusion is a systematic pre-execute-state effect
plus residual process variation; cache is plausible but not uniquely proven.
This diagnostic does not select -g0 or -g1 as universally representative and
does not replace the historical canonical metric.  Raw data are under
results/exp105_input_restore_863229/ and logs under
logs/exp105_input_restore_863229_*.{out,err}.  Preparation commit was
7670f67a1579df9205f92a95e6c518b23bf98515.

## EXP-106 (pre-registered 2026-09-25): qualify a fixed batch-1 streaming protocol

EXP-106 is measurement-only on branch exp-106-ring-qualification.  It keeps
the original EXP-096 library SHA256
3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5 and
the EXP-095 stable library SHA256
bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539.
No rocFFT kernel, planner, installed image or historical metric is changed.

The candidate canonical workload is 1D double-complex forward, out-of-place,
packed, semantic batch=1, one default stream, at 64K/128K/256K/512K.  Every
timed process dynamically loads exactly one pinned rocFFT image, creates one
plan and explicit workspace, and preloads deterministic independent input and
output rings.  BW reported 8 MiB L2 in EXP-092; require at least 32 MiB of
input ring, giving 32/16/8/4 slots respectively, plus an independent equal-size
output ring.  Baseline and stable use identical seeds and slot order.

Correctness, input upload, plan creation and one full-ring warm-up occur before
timing.  Calibration doubles a common K from one ring traversal until both
arms' event intervals are at least 10 ms; K must remain an integer multiple of
slots.  A retained HIP-event interval contains only K rocfft_execute calls
rotating through the ring.  Report total/K as batch-1 streaming steady-state
GPU execute time.  It is not one-shot latency and does not include planning,
allocation, host transfer or correctness.

Use two independent replicas per length (array 0-7%1, one DCU, serialized).
Each replica has ten adjacent independent-process pairs, exactly five AB and
five BA in randomized order.  Each process retains ten >=10 ms event windows.
Do not treat windows within a process as independent pair samples: form one
process median and one baseline/stable ratio per pair, then bootstrap the ten
pair ratios.  A replica passes only if every process CV <=1% and the paired
speedup 95% interval relative half-width <=1%.  A length passes only if both
replicas pass and their median speedups differ by <=1%.  All four lengths must
pass for the protocol to qualify.  Retain all observations; a failure is a
protocol qualification failure, not permission to delete outliers or extend
after seeing results.

Owned files are work/exp106/exp106_ring_bench.cpp,
exp106_orchestrate.py, exp106_analyze.py, exp106_contract_test.py,
exp106_preflight.sh and exp106.slurm.  Before submission, 12 no-GPU contract
tests, Python/Bash syntax, C++ compile/link, single-image loader check, pinned
hash checks, file transfer hashes and Slurm --test-only must pass.  Submit the
complete serialized array once, then stop and wait for result inspection.
Preparation commit, job ID and decision are pending.
## EXP-107 (pre-registered 2026-09-26): select a stable batch-1 streaming window target

EXP-107 is a measurement-only qualification on branch exp-107-window-stability,
starting from 7bd29db8a7d29b47eefc938ca35828861aab039d. Reuse the EXP-106 ring
client and process runner; do not change rocFFT source or either installed image.
Pin the EXP-096 baseline SHA256
3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5 and the
EXP-095 stable SHA256
bf2fc1555ac04208fc8e966db0d36aa96f077b6342c0c3f039cd7d3338ad5539.

The only workload is 1D double-complex forward, out-of-place, semantic batch=1,
length 524288, default stream, explicit workspace. Four 8 MiB slots form equal
32 MiB input and output rings. Baseline and stable run in separate processes
with the same deterministic seed within each adjacent pair. Correctness must
pass for both library images before that replica's calibration or timing.

Test minimum HIP-event window targets of 10, 20, and 50 ms. For each target and
each of two independent replicas, use ten adjacent independent-process pairs,
exactly five baseline/stable (AB) and five stable/baseline (BA) in randomized
order. Each process retains exactly ten event windows. Calibrate one common K
for both arms by doubling from one four-slot traversal until both calibration
windows reach that target; K must remain a multiple of four. Each retained
window consists only of K rotating-ring rocfft_execute calls. Every retained
window in both arms must meet its target.

For each process, take the median of its ten per-execute window times. Form one
baseline/stable speedup per adjacent process pair; do not treat windows as
independent pairs. Per replica, bootstrap the ten pair speedups with 20,000
paired resamples and percentile 95% interval. Require relative CI half-width
((upper-lower)/2)/median <= 1%. Require the two replica median speedups at a
target to differ by <= 1%, using the symmetric relative difference
abs(a-b)/((a+b)/2). The prior per-process CV <= 1% rule is diagnostic only:
report CV for every process, but do not gate qualification on CV.

A target is individually eligible only if both replicas pass correctness,
metadata, K/slot, process isolation, every-window duration and paired-CI gates,
and the replica speedup agreement gate. Define its combined speedup as the
median of all 20 process-pair speedups across its two replicas. Among eligible
targets, select the shortest target only if its combined speedup differs by at
most 1% from every longer eligible target's combined speedup, using the same
symmetric relative-difference formula. If this drift gate fails, select no
target. Retain every observation; do not delete outliers, extend collection
after seeing results, or change thresholds.

The serialized Slurm array has six tasks (target x replica, concurrency 1).
Raw outputs are under results/exp107_window_stability_<jobid>/ and task logs
under logs/exp107_window_<jobid>_<arrayid>.{out,err}. The no-GPU preflight,
six contract tests, syntax, C++ compile/link, pinned hashes and Slurm --test-only
must pass before one complete array submission. After submission, stop without
inspecting queue state or results. Preparation commit and job ID are pending.

## EXP-108 (pre-registered 2026-09-27): final fixed-protocol qualification

EXP-108 is measurement-only on branch `exp-108-final-protocol`, starting from
EXP-107 preparation commit `8e887cd6fc39d49401ad585de5406bbf7e2fabab`.
It changes no rocFFT planner, kernel, installed image or historical metric.  It
pins the same EXP-096 baseline and EXP-095 stable librocfft SHA256 values used
by EXP-106/107.

The workload is 1D double-complex forward, out-of-place, packed, semantic
batch=1 at lengths 65536/131072/262144/524288.  Each single-library process
uses one explicit non-default HIP stream; rocFFT execution info and both timing
events are bound to that same stream.  Workspace is explicit.  Independent
input and output rings are each at least 32 MiB, with different deterministic
input per slot.  This is a specified rotating working set, not a cold-cache or
complete non-residency claim.  Correctness evaluates every slot against a
scaled two-sparse-tone analytic oracle.  Upload, planning, correctness,
whole-ring warm-up, calibration and device conditioning remain outside retained
timing.

For every retained window, save both HIP-event total/K and CPU steady-clock
wall total/K.  The primary metric name is exactly `single-stream K-execute GPU
event interval / K`; CPU wall time is diagnostic.  Test 10, 20 and 50 ms event
targets for every length.  K is a slot-count multiple, shared by both arms in a
condition and fixed after calibration; all retained event intervals must meet
their target.  Every process retains ten windows and all observations remain in
the record; CV is diagnostic and no outlier may be deleted.

Each target/length has three replicas and every replica has 20 adjacent
independent-process pairs, with ten randomized AB and ten BA orders.  A process
contributes its ten-window median; a pair contributes baseline/stable process
medians.  The primary estimate is the median of 20 pair ratios.  Compute a
fixed-seed 20,000-draw percentile bootstrap 95% interval by resampling complete
pairs.  The 20 real pairs, not bootstrap draws, are the independent sample size.
Measurement qualification requires all correctness, metadata, stream,
workspace, library, K/window and device-state contracts; CI relative half-width
at most 1%; and first-ten versus last-ten pair-ratio median symmetric relative
difference at most 1%.  Effect is separate: lower CI >1 is optimization, upper
CI <1 is regression, otherwise inconclusive.  The three replica estimates must
have maximum pairwise symmetric relative difference at most 1%.

`rocm-smi` is required at job start and around every child process, outside the
event interval.  Record identity, edge temperature, sclk/mclk, utilization and
KFD compute PIDs.  Telemetry command failure or missing required fields, device
identity change, any competing compute PID, temperature outside 50--60 C, or a
different available idle sclk/mclk state before versus after a retained process
invalidates it.  The 50--60 C band is the documented ROCm primbench default;
conditioning uses unretained calibration work for at most 60 seconds.  Idle SMI
clocks do not prove active kernel clock and are reported with that limitation.

A target is globally eligible only when all four lengths and all three replicas
qualify.  Select the shortest eligible target only when, separately for every
length, its combined 60-pair median speedup differs by at most 1% from each
longer eligible target.  Effect is reported per length without claiming a
simultaneous project-wide 95% family interval.  Scope is this GPU/software,
specified working set and batch-1 steady-state throughput; it excludes one-shot
latency, plan creation, transfers, in-place, batch>1, other GPUs, cross-date and
cross-machine reproducibility.

The cluster QOS rejects arrays with more than ten elements even at `%1`.
Therefore the full 36-condition matrix is encoded as nine serialized array
allocations (`0-8%1`): target x replica.  Each allocation runs all four lengths
in a preregistered counterbalanced order, with separate correctness, calibration,
20-pair process sequence, telemetry and raw record for every length.  Thus the
three replicas for each target/length remain three different Slurm allocations.
Preflight must pass 13 no-GPU contract tests, syntax, compile/link, single-image
loader, hashes and Slurm `--test-only`.  Submit once and do not inspect state or
results until requested.  Preparation commit, job ID and result are pending.

## EXP-109 (pre-registered 2026-09-27): KFD PID-to-current-GPU attribution repair

EXP-108 job 865241 completed its nine serialized allocations and its statistical
summary selected 10 ms, but manual evidence review invalidated the device-state
qualification.  The installed `rocm-smi` prints legacy blocks beginning with
`PIDs for KFD processes:`, followed by `PID:` and `GPUID:` lines.  EXP-108's
case-sensitive/table-oriented parser did not recognize that form and returned
an empty PID set for all snapshots, so `no_competing_compute_process` could
false-pass.  EXP-108 timing data remain diagnostic but are not the final
qualification result.

EXP-109 changes measurement infrastructure only.  The HIP client records the
current device PCI BDF.  The orchestrator reads KFD topology nodes, maps that
BDF to exactly one KFD `gpu_id`, parses every legacy PID/GPUID block, and counts
as a competitor only a PID whose GPUID list contains the current device's
`gpu_id`.  PIDs mapped to another topology GPU are not competitors.  Missing
GPUIDs, unknown GPUIDs, incomplete parsing, zero/multiple BDF mappings, topology
change, or a PID on the current GPU are hard failures; none may default to no
competition.  Raw SMI output, parsed PID-to-GPUID records, topology, selected
current GPU and attribution result are retained.

The workload, libraries, hashes, explicit stream, ring, all-slot correctness,
10/20/50 ms targets, four lengths, 20 balanced pairs, ten windows, three
replicas, CPU-wall diagnostic, CI/effect/drift gates and global window-selection
rules are unchanged from EXP-108.  The same nine-task `0-8%1` matrix will be
rerun.  Seventeen no-GPU contract tests include the real legacy output shape,
missing/unknown GPUIDs and ambiguous PCI mappings.  Preparation commit
`b3701298` passed the no-GPU contracts, compile/link and Slurm test-only checks.

### EXP-109 result: infrastructure failure, no performance result

Job 865775 was inspected at the user's request.  All nine array allocations
failed with exit 1 after approximately one second, before correctness or FFT
timing.  The traceback is `PermissionError: [Errno 1] Operation not permitted`
while reading a KFD topology node's `gpu_id`.  This is not evidence of a
numerical, performance or statistical failure.  A complete-matrix retry is
not justified until current-device PID attribution is known to be accessible.

## EXP-110 (pre-registered 2026-09-27): device attribution interface diagnostic

This diagnostic starts from EXP-109 preparation commit `b3701298` and changes
no rocFFT source, installed library, benchmark estimator or acceptance gate.
Use one five-minute, one-DCU allocation, not an array.  No FFT or performance
measurement is run.  A HIP metadata probe enumerates visible device PCI BDFs
and creates a 4096-byte allocation on visible device zero, holding its known
PID live while read-only device/process metadata are collected.  Release it
after collection.  It is the only deliberately introduced GPU process.

Collect visibility/allocation environment fields, `rocm-smi --help`, supported
bus/unique-ID/device-ID/process/PID-to-GPU commands, and before/during/after
process snapshots.  Read each KFD node's `gpu_id` and `properties` separately;
preserve permission failures per file instead of aborting on the first node.
Also collect DRM card/render-device PCI identity metadata where accessible.
Every invoked command retains arguments, status, stdout and stderr, with a
ten-second timeout.  Unsupported commands and failed reads remain explicit
evidence; they must never imply an empty PID set or qualified isolation.

The purpose is to identify an accessible, unambiguous link from the actual
HIP PCI device to the GPUID used in process records and verify that the known
probe PID appears on that device.  Mapping/permission evidence will determine
the next repair; this diagnostic itself grants no qualification.  No privilege
escalation, permission changes or arbitrary process inspection is attempted.
Record sources under `work/exp110`, raw diagnostic JSON under
`results/exp110_device_attribution_<jobid>`, and logs under
`logs/exp110_attribution_<jobid>.{out,err}`.  Before submission check Python and
shell syntax, compile/link the probe, verify targeted file changes and Slurm
test-only.  Submit once, then stop until the user requests results.

### EXP-110 result: current-device attribution is readable, foreign topology is restricted

Job 865828 on `f09r1n01` completed its one-allocation diagnostic in about one
second.  The HIP probe reported device 0 at PCI BDF `0000:55:00.0`.  `rocm-smi --showbus`
reported the same BDF.  The readable KFD node 10 had `gpu_id` 20902,
`location_id` 21760 (`0x5500`), domain 0 and DRM render minor 130, uniquely
matching that HIP/SMI device.  The known probe PID 3770378 appeared while the
probe was live with `GPUID ['20902']`, HCU node 10 and index 0, then disappeared
after release.

Seven other KFD GPU nodes denied reads of `gpu_id` or `properties` with
`EPERM`.  Five other listed PIDs had complete GPUID values different from
20902, while their `PCI BUS` fields were `None`.  Thus the current allocation's
device mapping and current-device process membership can be checked without
reading every GPU node.  The foreign PIDs are not mapped to PCI devices by
this evidence; their devices are neither claimed known nor claimed absent.
No permission or privilege changes were made.

EXP-109 job 865775 remains an infrastructure failure: all nine tasks stopped
before FFT work on the denied KFD-node read.  Code review also found that the
EXP-109 wrapper indexed `pci_bus_id` in the dictionary returned by the shared
EXP-106 measurement helper, although that helper omits that field.  EXP-111
reads and validates PCI identity from each client's `META` record before
applying telemetry state.

## EXP-111 (pre-registered 2026-09-27): partial-topology attribution repair and small GPU smoke

EXP-111 adds new orchestration, smoke and contract files under `work/exp111`;
it reuses the EXP-109 client and analyzer and the EXP-106 measurement helper.
It changes no FFT C++ source, installed library, workload definition or final
qualification rule.  KFD permission denials are retained per node and file;
only `EPERM`/`EACCES` for an individual node are skippable.  Root enumeration,
malformed readable metadata, duplicate IDs and a missing or ambiguous mapping
for the current HIP BDF remain hard failures.  The current BDF must also match
one unique `rocm-smi --showbus` identity before and after each process.

Every KFD PID must have a complete nonempty list of positive decimal GPUIDs.
A PID is a current-device competitor exactly when that list contains the
uniquely resolved current HIP device `gpu_id`; this includes multi-GPU lists.
Other reported GPUIDs are diagnostic.  EXP-111 does not require access to
foreign topology or infer the PCI identity of a foreign PID.  Raw process and
SMI output, parser errors, readable topology, and denied-node details are
retained.

One 15-minute single-DCU allocation first holds the HIP probe PID and verifies
that its GPUID matches the HIP BDF mapping, that the isolation gate rejects
that known PID, and that the PID disappears after release.  Probe checks test
attribution only; they do not claim a temperature pass.  The same allocation
then checks all ring slots for both pinned libraries at N=65536, 131072,
262144 and 524288.  At N=524288 only, it chooses common K for a 10 ms target
and runs one adjacent baseline/stable pair with ten windows per process.
Retain the existing 50–60 C temperature and stable idle-clock gates and require
every timed window to be at least 10 ms.  Record GPU-event/K and CPU-wall/K;
the single pair is a plumbing smoke and makes no speedup, precision, or
qualification claim.  Do not invoke the 36-condition matrix or promote a
median ratio from this run.

No-GPU contracts cover permission-denied foreign nodes, strict PID/GPUID
parsing, current-device membership, bus identity, topology changes, retained
temperature/clock gates and PCI propagation from `META`.  Result output is
under `results/exp111_attribution_smoke_<jobid>`, logs under
`logs/exp111_attribution_smoke_<jobid>.{out,err}`, and sources under
`work/exp111`.  The preparation commit, Slurm job ID and smoke result are
pending.  Submit once, then stop until the user requests results.

### EXP-111 result: smoke passed, no statistical qualification claimed

Preparation commit `65a1b63ebabdc970ef07ce6a52cb7f3f2a371291`, branch
`exp-111-partial-topology-smoke`, job 865996 on f09r1n06 completed with exit 0
in 53 seconds.  Raw record: `results/exp111_attribution_smoke_865996/exp111_smoke_summary.json`;
logs: `logs/exp111_attribution_smoke_865996.{out,err}`.  Known PID 2350973 was
mapped to PCI 0000:85:00.0 / KFD node 12 / GPUID 60191 and correctly rejected
while alive; it was absent before and after, and ordinary isolation passed.
Seven denied foreign nodes remained diagnostic.  All 32/16/8/4 ring slots at
64K/128K/256K/512K passed for both pinned libraries (eight checks).
The single 512K AB pair used common K=256 and ten windows per arm, all >=10 ms.
Baseline/stable event/K medians were 90.81746265295/56.9661818445 us; within-process
CV was 0.08916617%/0.54000368%.  Before/after telemetry showed temperatures
52--53 C, sclk 1500 MHz and mclk 1800 MHz, with no current-device competitor.
These are diagnostic times, not a retained speedup or a stability qualification.
The next step is the complete preregistered matrix, not a changed estimator.

## EXP-112 (pre-registered 2026-09-27): full qualification with validated attribution

Start from EXP-111 commit 65a1b63ebabdc970ef07ce6a52cb7f3f2a371291.  Add only
packaging under `work/exp112`, reusing the unchanged EXP-111 pipeline, EXP-109
client/analyzer and EXP-106 base.  No rocFFT source, installed library, FFT
workload, acceptance threshold or statistical estimator is changed.  Record
the actual client source/binary and infrastructure hashes in each allocation
and result, keeping legacy base provenance explicitly separate.

The matrix remains DP complex forward, OOP, packed, semantic batch 1, explicit
single non-default stream/workspace, separate >=32 MiB rings, and all-slot
correctness at N=65536/131072/262144/524288.  Targets 10/20/50 ms each have three
independent allocations, 20 balanced randomized adjacent AB/BA process pairs
per length and ten windows per process; K is common to the arms and a slot
multiple.  Retain complete-pair 20000-draw percentile bootstrap, CI relative
half-width <=1%, first/last ten-pair median drift <=1%, all three replica
pairwise agreement <=1%, and <=1% comparison against longer eligible targets.
Effect classification remains separate, CV remains diagnostic, and no outlier
may be removed.  Temperature 50--60 C, stable available idle clocks and strict
current-device identity/process gates remain mandatory.

Submit one nine-task array `0-8%1` (target x replica), with the same three
counterbalanced length orders.  Each allocation first repeats only the known-PID
attribution probe, then runs its four complete length conditions.  This probe
is outside retained timing and grants no statistical qualification.  Use the
unchanged analyzer with explicit output `exp112_final_protocol_summary.json`.
Raw root: `results/exp112_final_protocol_<jobid>`; logs:
`logs/exp112_final_<jobid>_<arrayid>.{out,err}`.  Preflight checks all 18 EXP-111
contracts, two no-GPU matrix-packaging contracts, Python/shell syntax, pinned
libraries/client, loader dependencies, documentation synchronization and Slurm
test-only.  All nine tasks are submitted once; stop without checking queue or
results until requested.  Preparation commit, job ID and result are pending.

## EXP-112 inspection and paused EXP-113 (2026-09-27)

EXP112 preparation a1ea2eefb64b3515e77b1fea42e5afd8d37d3145, job866037:
eight tasks failed and one completed; only five of 36 condition-replicas
completed, so qualification is INCOMPLETE with no selected target window.
PID4029659 temporarily had blank GPUID; later it reported foreign GPUID45786
versus current60191. Unknown attribution conservatively invalidated samples;
later foreign attribution does not retroactively prove earlier isolation.
Completed groups passed their local CI/drift gates, not full reproducibility.
The user paused EXP113 readiness work before any GPU job was submitted.

## EXP-114 pre-registration: unmodified official dyna benchmark diagnostic

New user-authorized measurement-only lane on exp-114-official-dyna-diagnostic,
starting at a1ea2eefb64b3515e77b1fea42e5afd8d37d3145. Pinned EXP096 baseline
and EXP095 stable libraries remain unchanged. Full design and limitations:
work/exp114/exp114_record.md. DP forward OOP packed batch1 at64K/128K/256K/512K,
host PRNG -g1, 100 single-execute event samples per library, sequence0/1
separately, five independent process blocks:40 dyna calls plus8 ordinary
rocfft-bench reference calls. Eight existing all-slot correctness checks gate
timing. Raw temperatures/clocks/attribution retained; unknown attribution is
diagnostic-invalid, confirmed current-card competition blocks timing. No
profiling, long-window samples, outlier removal, qualification or promotion.
One30minute GPU allocation, raw results/exp114_dyna_<jobid>, logs/exp114_dyna

## EXP-119 pre-registration (2026-09-28): LDS-aware block-compute helper (Stage 1)

Starting stable commit: `d5924f87207a6393cf818971211dd26d2c6cfd26` on
`rocfft-opt-pre-tile-lifetime` (tag
`stable-exp095-sbrc128k-only-20260923`). The isolated implementation branch
is `exp-119-lds-aware-block-planner`, created from that commit. The
pre-registration is made before any source edit.

Documentation audit: the exp-114 worktree contains raw EXP-115, EXP-116,
EXP-117, and EXP-118 result/log directories, but neither the repository nor
top-level `VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md` contains tracked records
for those identifiers, and no EXP-115--118 branches or commits were found.
Those results are not reconstructed or interpreted here. This record therefore
preserves the audit outcome without inventing missing experiment results.

Scope is Stage 1 only: refactor the TODO in
`projects/rocfft/library/src/node_factory.cpp` into a private
LDS-aware block-compute selection helper, with any declaration kept private to
the existing NodeFactory implementation/header as required by local style.
For half/single use the single-length map and for double use the double-length
map; require a map entry, exact factorization, an available SBCC kernel, and
an available SBRC kernel for the complementary length. The existing function
pool LDS filter remains authoritative. Preserve the gfx906 262144 CRT
exception, all fallback semantics, public API/ABI, maps, and kernel configs.

This Stage 1 change is explicitly behavior-preserving. It must not add a
1048576 map entry, add SBRC-1024 or any other kernel configuration, or change
the 1024K TRTRT/fused three-kernel plan. Therefore Stage 1 cannot optimize
1024K by itself; any 1024K two-kernel experiment is out of scope and requires
a separate pre-registered stage.

Validation plan: build `rocfft-rtc-gen` first and then rocFFT in an isolated
build root; compare before/after scheme, factorization, and RTC/kernel
sequence for DP z2z 64K, 128K, 256K, 512K, and 1024K; verify insufficient-LDS
function-pool rejection before leaf grid setup when an existing non-invasive
path permits it; run proportionate correctness checks; preserve all raw logs
and results under EXP-119 names. Record exact commands, build/test outcomes,
plan comparisons, failures, and unverified items before finalizing this
record.

### EXP-119 Stage 1 validation and compatibility correction (2026-09-28)

The isolated candidate worktree is
`/public/home/zhangkewei/zr/exp-119-lds-aware-block-planner` on branch
`exp-119-lds-aware-block-planner`. The clean refreshed build root is
`/public/home/zhangkewei/zr/build/exp119_stage1_clean`, with install root
`/public/home/zhangkewei/zr/exp119-stage1-install-clean`.

The first fresh CMake configure attempt was blocked by the host HIP package's
missing `/opt/rocm/hip/lib/libgalaxyhip.so...` imported target (after the
available HIP, AMDDeviceLibs, and amd_comgr package paths were supplied). No
source or existing build tree was changed by that failed configure. Validation
then used an isolated copy of the configured EXP-095 build metadata, corrected
all generated paths inside that new root, cleaned it, and refreshed all objects.
The initial successful build sequence was:

```
cmake --build /public/home/zhangkewei/zr/build/exp119_stage1_clean \
  --target rocfft-rtc-gen/fast -- -j8
cmake --build /public/home/zhangkewei/zr/build/exp119_stage1_clean \
  --target rocfft/fast -- -j8
cmake --build /public/home/zhangkewei/zr/build/exp119_stage1_clean \
  --target rocfft-bench/fast -- -j8
cmake --build /public/home/zhangkewei/zr/build/exp119_stage1_clean \
  --target install/fast -- -j8
```

The copied build graph required explicit prerequisite targets while being
refreshed (`rocfft-rtc-cache`, `rocfft-rtc-compile`, `rocfft-rtc-subprocess`,
`rocfft-rtc-common`, `generator`, `stockham_gen`, `rocfft-function-pool`,
`rocfft-rtc-launch`, `rocfft-solution-map`, `rocfft-tuning-helper`,
`rocfft_rtc_helper`, and `dyna-rocfft-bench`). Those were built only inside
the new EXP-119 root. Build and install logs are retained under `logs/` with
`exp119_clean_` names. The build completed with existing upstream warnings and
no compile/link errors. The correction was then rebuilt with
`rocfft-rtc-gen/fast`, `rocfft/fast`, and `install/fast`; its logs are
`logs/exp119_correction_build_rtc_gen.log`,
`logs/exp119_correction_build_rocfft.log`, and
`logs/exp119_correction_install.log`.

The first edge audit found a real compatibility defect in the initial helper
extraction. Job 868936 tested every power of two from 1 through 524K for
single and half precision, batch 1, out of place. The stable library rejected
the absent single-map entry at 524K with `CS_L1D_CC`, while the initial
candidate returned successfully through TRTRT. The single map has no 524K
entry (the double map does), so this was an expansion of the single/half
reachable behavior rather than a harmless refactor. The other tested powers
through 256K matched.

The correction keeps the LDS-aware helper but distinguishes a missing map
entry from a mapped pair rejected by the LDS-aware SBCC/SBRC checks. A named
`legacy_block_compute_map_threshold` retains the old missing-map failure for
lengths through 524K; a mapped-but-LDS-ineligible pair still takes the new
TRTRT fallback. This preserves the old single/half 524K behavior without
silently expanding its plan. Corrected edge audit job 868963 emitted the same
`CS_L1D_CC` failure for stable and candidate at single/half 524K (wrapper exit
status 139 under `--ignore_runtime_failures`); all other tested powers matched
with status 0. Raw edge logs are retained under
`results/exp119_edge_compare_868963/`.

GPU plan comparison job 868991 (`f09r1n01`) reran DP complex forward, out of
place, batch 1 for both the pinned stable install and the corrected candidate
at 64K, 128K, 256K, 512K, and 1024K. All ten runs returned status 0. After
normalizing only runtime user-buffer addresses, each stable/candidate plan log
was byte-identical at all five lengths; the raw plans also had no unexpected
scheme differences. The 64K through 512K plans used `CS_L1D_CC` with
`CS_KERNEL_STOCKHAM_BLOCK_CC` and `CS_KERNEL_STOCKHAM_BLOCK_RC`; the 1024K
plan remained `CS_L1D_TRTRT` with stockham/transpose/stockham. Raw plans,
bench logs, and status are retained in
`results/exp119_plan_compare_clean_868991/`. The earlier 868887 comparison is
also retained as pre-correction evidence.

An earlier partial object reuse in `build/exp119_stage1_buildreuse` produced
candidate bench segfaults; those logs/results are retained and are not treated
as a source failure. The clean all-object refresh above removed that stale
generated-object condition and passed all ten GPU runs.

No direct non-invasive test seam was available for observing the
insufficient-LDS rejection immediately before leaf-grid setup, and the clean
build had `BUILD_CLIENTS_TESTS=OFF` with no configured gtest target. A separate
test-enabled configure was attempted in
`build/exp119_stage1_tests`; it reached the same missing HIP imported target
and is recorded in `logs/exp119_tests_configure.log`. The existing
`function_pool` SBCC/SBRC LDS filters remain the helper's gate, but the
dedicated pre-leaf rejection observation remains unverified.

For numerical-reference correctness, the existing C API/sample path was used
through a temporary isolated EXP-119 driver (not committed production code).
Job 868989 ran out-of-place DP z2z forward and inverse against an independent
radix-2 CPU reference at every required length. All ten checks passed:

| length | forward max error | inverse max error | tolerance |
| ---: | ---: | ---: | ---: |
| 64K | 2.58e-8 | 2.61e-8 | 1.02e-3 |
| 128K | 1.17e-7 | 1.17e-7 | 2.10e-3 |
| 256K | 3.15e-7 | 3.16e-7 | 3.69e-3 |
| 512K | 1.50e-6 | 1.50e-6 | 9.96e-3 |
| 1024K | 6.10e-6 | 6.10e-6 | 2.09e-2 |

The raw reference log and plan log are retained under
`results/exp119_dp_z2z_reference_868989/`. The source and Slurm wrapper are
untracked validation artifacts under the EXP-119 worktree and are not part of
the production diff.

The EXP-115--118 audit remains unchanged: raw directories exist in the
exp-114 worktree, but no tracked records, branches, or commits were found, so
no results were fabricated. The repository copy and the pre-existing
top-level copy of this document were compared with `cmp` after the correction;
they are byte-identical and retain the imported history through EXP-114 plus
the EXP-119 record. No map, kernel configuration, public API/ABI, or Stage-2
change was made.

## EXP-120 pre-registration (2026-09-28): SBRC-1024 candidate screening

Starting commit: `ed9343e510bf4b9f199fa748609311b879f65c3e`, the reviewed
EXP-119 Stage-1 correction on `exp-119-lds-aware-block-planner`. The isolated
worktree is `/public/home/zhangkewei/zr/exp-120-sbrc1024-cc` and the branch is
`exp-120-sbrc1024-cc`. This record is written before EXP-120 source edits.

Stage 2 evaluates the first 1048576 double-precision complex-interleaved
out-of-place block-compute candidate only for the exact 1D z2z gate. The
candidate adds the double map entry `1048576 -> 1024` and one SBRC-1024 RTC
configuration using factors `[8,8,4,4]`. All other lengths, precisions,
placements, array layouts, callbacks, strides, and transforms retain the
EXP-119 path; in-place 1024K is explicitly a control and must remain TRTRT.
If `NodeMetaData` cannot express this gate safely at scheme-decision time,
the experiment stops without widening the planner condition.

The three candidate configurations are evaluated independently, with exactly
one default FMKey variant in each build:

| candidate | WGS | TPT | block width | DP LDS |
| --- | ---: | ---: | ---: | ---: |
| A | 256 | 128 | 2 | 32 KiB |
| B | 512 | 128 | 4 | 64 KiB |
| C | 512 | 256 | 2 | 32 KiB |

The EXP-089 static initial-load gate remains unchanged and must be shown to
accept the new SBRC-1024 kernel. No generator semantic workaround is allowed.
For every candidate, build `rocfft-rtc-gen` first and then a clean isolated
rocFFT/bench/install root. Confirm generated metadata, WGS/TPT/block width,
LDS usage at or below 65536 bytes, and an exact 1024K OOP DP CI plan of
`SBCC-1024 + SBRC-1024` with no transpose or SBRR fallback.

Before timing, run numerical-reference correctness for 1024K forward/inverse,
OOP and IP, batch 1 and 3; run 64K/128K/256K/512K correctness/control plans;
and cover planar, callback, and non-unit-stride controls when existing tools
permit non-invasive checks. IP must retain the EXP-119 TRTRT plan. Reject a
candidate immediately on generator, build, resource, plan, or correctness
failure and preserve its evidence.

For surviving candidates, screen DP z2z OOP batch 1 at 1024K with `-N 10000`
in the same allocation as the Stage-1 stable install, retaining raw CSV and
canonical metrics. Select a winner only after comparable screens. Qualify the
winner with eight interleaved ABBA pairs, retaining every raw process value,
and use exactly
`(TotalDurationNs - generate_random_interleaved_data_kernel TotalDurationNs)
/(10000+1)` once. Run 64K/128K/256K/512K controls under the same conditions
and collect PMC diagnostics only for the winner.

Acceptance requires all correctness/resource/plan checks, at least 7 of 8
1024K pairs faster, median canonical improvement of at least 2%, and no
consistent control regression above 1%. Otherwise record rejection and leave
the stable branch unchanged. EXP-115--118 remain unaudited/unfabricated;
EXP-120 must not start Stage 3 or merge into stable.

## EXP-120 outcome (2026-09-28): stopped before source edits

EXP-120 stopped at the explicit gate-audit condition before any source edit,
candidate configuration, build, install, GPU job, timing run, correctness run,
or PMC collection. The branch remains at the pre-registration commit
`19f407ad` on `exp-120-sbrc1024-cc`, based on the reviewed Stage-1 commit
`ed9343e510bf4b9f199fa748609311b879f65c3e`; the stable branch and stable
install were not modified.

The exact callback exclusion cannot be represented safely by the current
`NodeMetaData` at scheme-decision time. `NodeMetaData` carries dimension,
length, strides, placement, precision, and array types, but no callback
presence. `BuildSingleDevicePlan` calls `NodeFactory::CreateExplicitNode` and
`ApplySolution` before it copies plan load/store operations to the root node.
User callbacks are supplied later through execution-info, converted by
`DeviceCallbackMap`, and assigned during `TransformPowX`; the plan may also
precompile callback variants based only on planar array capability. Therefore
the same 1D double CI OOP 1048576 plan metadata can be used once with runtime
callbacks and once without them. A metadata-only gate would either allow the
candidate for callbacks (violating this registration) or conservatively reject
all candidate-capable CI plans (making the requested candidate unreachable).
The pre-registered stop rule therefore applies; no condition was widened and
no workaround was added.

Candidates A, B, and C were not evaluated, so no candidate was selected and
there are no build, generated-kernel resource, plan, numerical-correctness,
screening, control, or PMC results to report. The EXP-115--118 audit remains
unchanged and no results were fabricated. The repository and top-level copies
of this document were synchronized after this outcome record.

## EXP-121 pre-registration (2026-09-28): callback-aware SBRC-1024

Starting commit: `1642eb6383e0a4615dee46ac3cef4cec8e1f425c`, the EXP-120
callback-gate blocker record. The isolated worktree is
`/public/home/zhangkewei/zr/exp-121-sbrc1024-callback-aware` and the branch
is `exp-121-sbrc1024-callback-aware`. This record is written before source
edits. EXP-120 remains unchanged and is not rewritten.

This experiment carries internal callback/load-store-operation state from the
`BuildSingleDevicePlan` optionals into `NodeMetaData` before every root
scheme decision and recreated root. The gate requires a root 1D node, target
length 1048576, double precision, C2C complex-interleaved input and output,
out-of-place placement, fastest input/output strides equal to one, and no
engaged callback-capable load/store optionals. The state is internal only; no public API or
ABI field is added. All `BuildSingleDevicePlan` call sites and callback
assignment paths must be shown to receive these optionals; if a callback can
bypass them, EXP-121 stops without widening the condition.

Only the double block map entry `1048576 -> 1024` and one SBRC-1024 RTC
configuration are added in each candidate source state. Other lengths,
precisions, placements, planar layouts, callback/load-store-op cases,
non-unit strides, non-root nodes, and in-place 1048576 remain on the EXP-119
path. The EXP-089 static initial-load gate and generator semantics remain
unchanged.

Candidates are built independently, with one default FMKey configuration per
build:

| candidate | WGS | TPT | block width | DP LDS |
| --- | ---: | ---: | ---: | ---: |
| A | 256 | 128 | 2 | 32 KiB |
| B | 512 | 128 | 4 | 64 KiB |
| C | 512 | 256 | 2 | 32 KiB |

For each candidate, build `rocfft-rtc-gen` first, then clean rocFFT/bench/
install roots. Confirm generated WGS/TPT/block width/resource metadata, LDS
at or below 65536 bytes, static initial load, and exact 1024K OOP DP CI plan
`SBCC-1024 + SBRC-1024` without transpose or SBRR fallback. Run correctness
before timing: target OOP forward/inverse batch 1/3, IP and callback/
load-store-op/planar/non-unit-stride fallback controls, and 64K/128K/256K/
512K controls. Reject immediately on generator, build, resource, plan, or
correctness failure without semantic workarounds.

For surviving candidates, retain raw same-allocation 1024K DP z2z OOP batch-1
screens with `-N 10000`. Qualify a winner with eight interleaved ABBA pairs,
the canonical metric
`(TotalDurationNs - generate_random_interleaved_data_kernel TotalDurationNs)
/(10000+1)`, and 64K/128K/256K/512K controls. Collect VMEM/LDS/VALU/
VGPR/SGPR/occupancy/cache PMC diagnostics only for the winner. Acceptance
requires all checks, at least 7/8 faster target pairs, median improvement at
least 2%, and no consistent control regression above 1%; otherwise reject
and leave stable unmodified. No Stage 3 or merge is allowed, and EXP-115--118
records remain unaudited/unfabricated.

## EXP-121 callback-path blocker record (2026-09-28)

The callback-path audit stopped this experiment before candidate qualification.
The initial implementation used `loadOps && loadOps->enabled()` and
`storeOps && storeOps->enabled()` when populating the internal metadata. That
is insufficient: `LoadOps::enabled()` is always false and default
`StoreOps::enabled()` is false, but runtime user callbacks are supplied later
through `rocfft_execution_info` at `Execute()`.

The source evidence is direct. `callback_map.cpp` constructs the callback map
from `info->load_cb_fns` and `info->store_cb_fns`; `transform.cpp` calls it at
execution; and `powX.cpp` assigns those callbacks to the load/store nodes when
the root plan's `loadOps`/`storeOps` optionals are engaged. The ordinary no-field
plan path passes the non-optional `plan->desc.loadOps` and `plan->desc.storeOps`
objects into `BuildSingleDevicePlan`, which therefore receives engaged
optionals even when the operations are disabled. Consequently, the original
`.enabled()` gate could admit the 1024K candidate while a user callback was
still attachable after planning, violating the exact callback exclusion.

Correction commit `2fae589c` uses `optional::has_value()` for the internal
presence flags, conservatively treating an engaged optional as callback-capable.
This preserves Stage-1 behavior and prevents the 1024K candidate from being
selected on the ordinary path; it does not manufacture a safe no-callback
state. Candidate-A build job `869224` was already running from source commit
`24474d47` before this correction. `rocfft-rtc-gen` completed, but the clean
build reached 93% before Slurm reported `OUT_OF_MEMORY` (`0:125`) compiling
`plan.cpp`; it is not a qualification
build and no plan, correctness, timing, or PMC result is claimed. Candidates B
and C were not started. EXP-121 therefore stops under its preregistered rule;
no source is merged into stable, and no EXP-115--118 result is fabricated.

## EXP-122 pre-registration (2026-09-29): simple SBRC-1024 decomposition

Starting source commit: `ed9343e510bf4b9f199fa748609311b879f65c3e`, the
reviewed EXP-119 Stage-1 commit. The isolated worktree is
`/public/home/zhangkewei/zr/exp-122-simple-sbrc1024` and the branch is
`exp-122-simple-sbrc1024`. The current top-level optimization document,
including the EXP-120 and EXP-121 history, was synchronized into this repo
copy before this record; its pre-registration hash was
`357d0bed3fd700cc172b4d6a926c1a8eb0da653d40f32e15a03ba5cfbeabdca6`.

This is a deliberately simple technical experiment. It adds only the double
map decomposition `1048576 -> 1024` (ordinary `CC`: `1024cc + 1024rc`) and
registers ordinary SBRC-1024 with factors `[8,8,4,4]`,
`CS_KERNEL_STOCKHAM_BLOCK_RC`, and `runtime_compile=True`. It does not change
`NodeMetaData`, callback handling, planner API/ABI, stockham generator
semantics, or the EXP-089 static-initial-load logic. The ordinary SBRC path
must retain its existing callback behavior.

Candidate order, with one configuration per isolated binary/build, is:

| candidate | WGS | TPT | block width | DP LDS |
| --- | ---: | ---: | ---: | ---: |
| A | 512 | 128 | 4 | 65536 bytes |
| B | 256 | 128 | 2 | 32768 bytes |
| C | 512 | 256 | 2 | 32768 bytes |

Each candidate receives a clean build root and install root. Build
`rocfft-rtc-gen` first, then rocFFT/bench/install with sufficient Slurm host
memory and conservative parallelism (for example `-j4`) to avoid the prior
OOM. Confirm function-pool registration, generated factors/WGS/TPT/block
width/LDS, EXP-089 static initial load, and an actual 1048576 DP z2z plan
with exactly `SBCC-1024` followed by `SBRC-1024`, without TRTRT, SBRR, or a
transpose. If A fails build/resource/correctness, record it and evaluate B;
if B fails, evaluate C. Do not combine default configurations in one binary.

Correctness precedes timing: run DP z2z 1048576 forward/inverse, OOP/IP,
batch 1/3 against numerical reference; run existing callback correctness if
available without new architecture; and run 64K/128K/256K/512K controls.
Preserve all raw logs/results. For each correctness survivor, run a short
same-allocation stable/candidate screen at 1048576 DP z2z OOP batch 1,
`-N 10000`, then qualify the best survivor with eight interleaved ABBA pairs.
The canonical time is exactly
`(TotalDurationNs - generate_random_interleaved_data_kernel TotalDurationNs)
/(10000+1)`. Run 64K/128K/256K/512K controls and collect PMC diagnostics
only for the winner; PMC timing is diagnostic, not acceptance timing.

Acceptance requires correctness, the exact two-kernel target plan, at least
7/8 faster target pairs, median canonical improvement of at least 2%, and no
consistent control regression above 1%. Otherwise record rejection and leave
stable unchanged. Do not merge or start a later stage. EXP-115--118 remain
unfabricated, and EXP-120/121 source experiments are not carried into this
branch.

## EXP-122 result (2026-09-29): retained SBRC-1024 two-kernel 1024K plan

The retained source change is commit
`ed06208f30706f63126078a5c51af07fa0439fe7` on branch
`exp-122-simple-sbrc1024`, based on the reviewed EXP-119 planner commits
`7d3bbc3580fd9cda06fc4f8fa387839e408de1d3` and
`ed9343e510bf4b9f199fa748609311b879f65c3e`. It adds only
`map1DLengthDouble[1048576] = 1024` and the ordinary runtime-compiled
SBRC-1024 configuration with factors `[8,8,4,4]`. There is no public API or
ABI change and no callback/metadata/generator semantic change.

The requested configuration line contains `WGS=512`, `TPT=128`, but the
existing ordinary Stockham generator applies its 32-KiB DP occupancy limit
and derives the actual SBRC kernel as `WGS=256`, `TPT=128`, two transforms per
block, with 32768 bytes of launch LDS. This is the tested and retained kernel;
the configuration comment was corrected to describe the generated result.
The matching SBCC-1024 uses four transforms per block. Diagnostic job
`870956` proved `mapEntryFound=1`, `hasSBCC=1`, `hasSBRC=1`, and
`maxLDS=65536`; the resulting 1048576 plan is exactly
`CS_L1D_CC -> CS_KERNEL_STOCKHAM_BLOCK_CC +
CS_KERNEL_STOCKHAM_BLOCK_RC`. Earlier TRTRT observations were caused by
loading the wrong installed library, not by planner rejection.

Build job `870840` completed successfully and installed candidate A at
`/public/home/zhangkewei/zr/exp122-A-install`. Correctness job `871126`
explicitly loaded candidate library SHA256
`1824f2ac8b978fe456edd28b31940ed26fe6d4d0af9f4c1bcefac1bd8c9c8dfe`
and passed all 40 DP z2z cases:

- lengths 65536, 131072, 262144, 524288, and 1048576;
- forward and inverse;
- in-place and out-of-place;
- batch 1 and batch 3.

The maximum relative L2 error was `7.133677e-16`, the maximum relative-max
error was `1.249925e-15`, and the maximum absolute error was `5.823608e-12`.
The correctness JSON is
`logs/exp122_correctness_retry_871126.json`, SHA256
`8fc40900e55eedc4f95b122168f5ae3340e37f548c76bfb8ba3ea36694114b63`.

Formal performance job `871397` ran on `f09r1n01` in one allocation. It used
eight `stable -> candidate -> candidate -> stable` rounds for 1048576, DP
complex-interleaved z2z, out-of-place, batch 1, `N=10000`, and retained 64
raw hipprof kernel CSV files including the control lengths. The canonical
metric is strictly

`(TotalDurationNs from the Total row - TotalDurationNs of
generate_random_interleaved_data_kernel) / 10001`.

An initial analyzer incorrectly added the per-kernel rows to the already
aggregated `Total` row and reported `16.657%`; that number is invalid and is
preserved only as diagnostic history. The corrected analyzer is
`logs/exp122_perf_formal_analyze_corrected.py`. Its result
`logs/exp122_perf_formal_retry_871397/paired_corrected.json` has SHA256
`1fa9f17a1d6caa77afde8f416a89f8a1616016b4220e186663ac3ff305781296`.
The corrected formal target result is:

| metric | stable | EXP-122 candidate |
| --- | ---: | ---: |
| median canonical time | 176.164568 us | 109.942273 us |
| candidate-faster rounds | - | 8/8 |
| median improvement | - | 37.451301% |

The eight paired improvements were `37.340197%`, `37.217891%`,
`37.317642%`, `38.437242%`, `38.046030%`, `38.010485%`, `36.424714%`, and
`37.562405%`.

The corrected two-round controls from job `871397` showed median changes of
`+0.519622%` at 64K, `+0.804441%` at 128K, `+0.035845%` at 256K, and a noisy
`-5.522388%` at 512K. Because stable and candidate 512K plans were identical
apart from allocation addresses, job `871410` repeated 512K for eight ABBA
rounds at `N=10000`. Its corrected result had stable/candidate medians of
`52.365034/52.023568 us`, median improvement `+1.139704%`, and 5/8
candidate-faster rounds. The individual 512K changes ranged from
`-10.633906%` to `+6.603189%`, demonstrating measurement variance rather
than a consistent regression above 1%. The corrected control JSON is
`logs/exp122_ctrl512_871410/paired_corrected.json`, SHA256
`6e1cf1632ee71cd6e803d4238194ab4601403abd5b3f48173b0f9b84ad1f389d`.

PMC is not required for the retention decision. Job `871420` failed before
producing useful evidence and is excluded from all conclusions. The user
subsequently waived PMC explanation.

EXP-122 therefore passes its preregistered acceptance criteria: correctness
passes, the target is the exact two-kernel CC plan, 8/8 target rounds are
faster, median target improvement is well above 2%, and the expanded controls
do not show a consistent regression above 1%. Decision: retain EXP-119 plus
EXP-122, fast-forward `rocfft-opt-pre-tile-lifetime`, and tag the resulting
recorded state `stable-exp122-sbrc1024-20260929`.

## EXP-123 pre-registration (2026-09-29): cuFFT-format rocFFT comparison harness

Starting stable marker commit:
`5bc13e58901201b25884b9e602782345bbe7782f` on
`rocfft-opt-pre-tile-lifetime`; validated rocFFT source commit:
`ed06208f30706f63126078a5c51af07fa0439fe7`.  The isolated worktree is
`/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark` and the branch is
`exp-123-cufft-format-benchmark`.  This record is written before the GPU test.

EXP-123 is a benchmark-harness experiment and does not alter rocFFT library
source, planner behavior, kernels, public API, or ABI.  It ports the supplied
CUDA/cuFFT `fft_test_1d` harness to HIP/rocFFT while preserving the command-line
shape, double precision, out-of-place layouts, batch-1 default, correctness
tests, unconditional warm-up, three unrecorded timing warm-ups, 50 individually
HIP-event-timed iterations, row order, units, and 14-column CSV schema.  The
matrix is exactly lengths 32768, 65536, 131072, 262144, 524288, and 1048576,
with functions `z2z_1d`, `d2z_1d`, and `z2d_1d`, yielding 18 rows.

The supplied reference CSV has a provenance ambiguity: its external filename
uses `A100`, while the supplied archive stores byte-identical content under a
`results_A800` path.  EXP-123 will not infer the NVIDIA device from either
filename.  Its output filename records the measured AMD architecture
(`gfx936`), and the Slurm provenance records the actual hostname, library path
and SHA256, source commit/status, compiler version, device report, and linked
libraries.

For rocFFT, `plan_ms` covers creation of a ready-to-execute plan: plan
description, plan, execution info, work-buffer query/allocation, and work-buffer
binding.  This is the operational counterpart of `cufftPlan1d`, which manages
its work area internally, but cross-library plan-time differences must still be
described as API-dependent.  rocFFT requires a separate inverse plan for the
z2z round-trip check.  It is created only after the recorded forward first
execution and is excluded from `plan_ms` and steady-state transform timing.

Acceptance for this first run requires successful compilation against the
retained EXP-122 install, all 18 checks reporting `PASS`, exactly one row per
requested function/length pair in the prescribed order, the exact reference
CSV header, and preserved raw CSV/log/provenance files.  Any build, execution,
schema, matrix, or correctness failure rejects the run; do not publish partial
rows as a comparison result.  Timing values are descriptive cross-vendor data,
not evidence that the two libraries use identical planning internals.

### EXP-123 baseline extension (2026-09-29)

At the user's request, repeat the identical 18-case harness on the rocFFT
baseline install `/public/home/zhangkewei/zr/exp119-stage1-install-clean`.
Keep the same pinned gfx936 node `f09r1n01`, batch 1, 50 individually timed
iterations, correctness threshold, cold RTC-cache settings, CSV schema, row
order, and driver.  The retained EXP-122 run is Slurm job `871496`, source
commit `d6c50e6bd9f050410e31818daac832203946666e`, and library SHA256
`1824f2ac8b978fe456edd28b31940ed26fe6d4d0af9f4c1bcefac1bd8c9c8dfe`.
The baseline library SHA256 is
`2db62527b0530cd9cb351349f345199dfd7d8a9544cc4e20e24784b78f19488d`.

The requested comparison uses each CSV row's `mean_ms`.  Report
`latest_mean / A100_mean` and `baseline_mean / A100_mean`, plus latest-version
speedup over baseline as `baseline_mean / latest_mean`; values above 1 in the
speedup column favor the retained latest version.  Preserve the baseline CSV,
stdout, stderr, and provenance.  All 18 correctness checks and schema/matrix
validation must pass before adding baseline values to the comparison table.

### EXP-123 official-baseline correction (2026-09-29)

The baseline extension above used EXP-119, which is the direct predecessor of
EXP-122 but already contains the retained 64K--512K optimization history.  It
is therefore a previous-stable control, not the original rocFFT baseline, and
cannot measure cumulative 512K speedup.  Preserve job `871530` and its results
under that corrected interpretation; do not delete or relabel its raw data.

At the user's request, repeat the identical 18-case harness with the original
official ROCm 7.2.2 installation
`/public/home/zhangkewei/zr/install-exp096-official`, whose rocFFT source was
previously verified byte-for-byte against tag commit
`dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef` and whose library SHA256 is
`3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5`.
Keep the same pinned gfx936 node, batch, iteration count, correctness checks,
cold RTC-cache settings, schema, row order, and driver as jobs `871496` and
`871530`.

The corrected table must call this official installation `rocFFT baseline`.
For each row report A100 `mean_ms`, official-baseline `mean_ms`, retained-latest
`mean_ms`, retained-latest/A100 time ratio, and latest cumulative speedup
`official_baseline_mean / latest_mean`.  Do not use EXP-119 values for that
cumulative speedup.  Require all 18 checks plus schema/matrix validation before
publishing the corrected table.

### EXP-123 paired outlier retest (2026-09-30)

Official-baseline job `871543` and retained-latest job `871496` both completed
18/18 correctness checks on the same gfx936 UUID.  Three arithmetic-mean rows
nevertheless reported speedup below one: 128K d2z, 256K z2d, and 512K d2z.
Each retained-latest row contained a long-tail maximum of 0.340639, 0.277920,
and 0.360960 ms respectively, roughly 8--11 times its normal minimum.  A
single 50-event process cannot determine whether those means are measurement
noise or persistent regressions.

Rerun only these three cases in one pinned gfx936 allocation.  For each case,
run eight order-balanced ABBA rounds, yielding 16 independent official and 16
independent latest processes.  Every process keeps the original three warmups,
50 individually event-timed transforms, batch 1, correctness check, cold RTC
settings, and CSV schema.  Preserve all 96 process outputs and CSV rows.
Define each arm's aggregate average as the mean of its 16 `mean_ms` values,
equivalent to the mean of 800 equally weighted event samples.  Also retain the
median process mean, minimum event, maximum event, every process mean, and
`official_mean/latest_mean`.  Do not discard outliers.  Treat a repeatable
ratio below one as a possible real regression; treat isolated maxima that do
not persist across paired processes as measurement noise.  No source or stable
promotion change is part of this diagnostic.

## Worktree organization record (2026-09-30; administrative, no new experiment)

The user approved retaining the root repository, official baseline checkout,
active stable branch, and EXP-123 benchmark worktree. Eight old worktrees were
unregistered after saving their original Git administrative state and binary
patches. All original directories/files remain in place as historical snapshots;
all historical branch/tag refs and fixed EXP-091 baseline SHA256 hashes remained
unchanged during the operation. EXP-079's two uncommitted generator edits remain
unmerged in their original files and have separate recovery patches/hashes.

No rocFFT source, kernel, planner, numerical behavior, measurement definition,
installation or experimental outcome changed. No source branch was merged.
There are three registered optimization worktrees and one separate official
checkout. The archived `.git` pointers are retained as inactive historical markers;
use the stable/EXP-123 paths for active development.

At the user's explicit decision, the complete latest record is synchronized with
EXP-123 instead of the archived EXP-078 worktree. The stable branch retains its
validated-version experiment record. `WORKTREE_ARCHIVES.md` lists exact paths,
original HEADs and the recovery batch `/public/home/zhangkewei/zr/.worktree-archives/20260930-113952`.

## Top-level material organization (2026-09-30; administrative)

The user approved moving 135 historical entries (92 files, 43 directories) into
`experiments/EXP-NNN/` and `archives/worktrees/`, retaining original names and
file content. Historical script bodies are unchanged and will be adapted on
demand. The old EXP-078 path is retained as one compatibility link for the fixed
EXP-091 baseline; all 22 baseline hashes match. The 22 build/install/cache
directories and active stable/EXP-123/official paths are unchanged.

Preflight discovered three additional independent Git repositories and one
linked EXP-083 worktree. EXP-082 shares metadata with that linked worktree, and
the v2 directory lacks an index and reports 35,124 deletions. The user explicitly
deferred all four, and their refs, status and directory identities were preserved.
No reset, repair, deletion, experiment-source merge or performance claim follows.

The approved path map, snapshots and audit records are under
`/public/home/zhangkewei/zr/.worktree-archives/layout-20260930`.
`EXPERIMENT_LAYOUT.md` and `WORKTREE_ARCHIVES.md` describe current locations.
Stable validated-version experiment history remains unchanged.

## Persistent top-level organization (2026-09-30, round 3; administrative)

User-confirmed Q1-Q8 moved 183 more entries (169 files, 14 directories) into
tools/jobs/docs and numbered/purpose-based history folders. Eight old experimental
build trees are archived for rebuild on reproduction; four EXP-082/083 Git trees
are archived with linked paths corrected and original refs/status/index conditions
preserved. Two EXP-083 alternate-object paths were corrected after pausing and
obtaining separate user confirmation; original paths were backed up. The v2
missing index and deletion-status anomaly are not repaired.

Current tool/job paths and output locations are adapted without changing FFT
conditions, accuracy thresholds or timing calculations. Historical entry originals,
evidence, prior references and existing user modifications are preserved. Main
build/install, source/runtime, stable/EXP123/official paths, fixed baselines and
the explicit solution-map exception remain. No GPU experiment was run or source
optimization merged. Future storage rules and read-only top-level checking are
documented in AGENTS.md and EXPERIMENT_LAYOUT.md. Audit and migration map:
`/public/home/zhangkewei/zr/.worktree-archives/top-level-20260930`.
Stable validated-version experiment history remains unchanged.


## 2026-09-30 — Primary measurement policy fixed from EXP-123

User-approved administrative update; no new GPU run or optimization source change.
The exact EXP-123 fft_test_1d.cpp is frozen (SHA256
849d011336601e6cffb1959e89590847e26160f7b3e256482a5eb37289e333da).
Future primary matrix is five sizes 64K–1M × z2z/d2z/z2d, DP, batch=1,
out-of-place, original correctness, 3 timing warmups and 50 event measurements.
Formal acceptance uses 8 mirror-balanced three-arm rounds, all 16 process
means/arm/case, with official and preceding stable controls on one GPU UUID and
allocation. No outlier trimming; criteria preregistered per experiment.
Report both previous/official speedups and A100 Performance (A100 mean/candidate
mean ×100%). User confirmed NVIDIA hardware A100. The authorized raw 18-case
reference is preserved at results/reference/a100/, SHA256
3b376eb69a77318ace8fbe537acfc7b3e82cdff1ea847f6177ed7ea82b27603b; reports select
15 cases without 32K. Old mixed single/retest table remains historical.
See docs/technical/FFT_MEASUREMENT_PROTOCOL.md and shared tools/fft_measurement/.
Old hipprof contracts, raw baselines and original EXP-123 programs remain intact.
No source/tag promotion results from this policy update.


### Workspace management implementation (2026-10-03; source unchanged)

User-approved management plan resumed explicitly and implemented: 1,589 loose
files and 29 directories grouped; 10 invalid build payloads cleared only after
source/configuration provenance retention; 7 other build snapshots retained;
tune_all.py retired. Main build/install, 4 install compatibility paths, fixed
baselines/A100, validated source/tag and user changes retained. New manage.py
provides preview-first parameterized build, quick validation, formal measurement
and report, with independent configurations and immutable per-run evidence.

No source merge/promotion, compiler execution or GPU job was performed. Frozen
EXP-123 measurement definitions and original CPP remain unchanged. Source/version
integration is a separate task. First new experiment requires actual compilation,
loaded-library/GPU/runtime verification and correctness. Audit and mappings are
.worktree-archives/artifact-management-20261003/. See WORKSPACE_MANAGEMENT.md.


### EXP-123 designated latest stable (2026-10-03; explicit user decision)

The current stable branch is exp-123-cufft-format-benchmark, worktree
/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark. Its retained source
anchor is 344fbb5970f533db838fcb8c85e0eaa025cbc419; immutable release tag:
stable-exp123-cufft-format-20261003. Start all subsequent EXP branches from this
tag/current explicitly approved stable successor, never from the old root EXP-075.

Compared with validated EXP-122 source ed06208f30706f63126078a5c51af07fa0439fe7,
rocFFT has only a config_sbrc.py comment change; executable source semantics
are unchanged. This is an explicitly user-approved source/workflow promotion,
not evidence of a new optimization or a new formal GPU measurement. EXP-123's
historical measurements retain their original definitions. The unchanged EXP-122
installed library remains the approved previous-arm binary until an identity-
verified equivalent EXP-123 rebuild is explicitly registered; record its real
build source ed06208f30706f63126078a5c51af07fa0439fe7, not a fabricated new build.

The old rocfft-opt-pre-tile-lifetime branch/worktree and stable-exp122 tag remain
prior-stable history. Keep operational documents synchronized across root,
prior-stable and EXP-123 current-stable paths. Complete latest records remain
root/EXP-123; preserve the prior-stable full historical record. Do not auto-merge
new experiment results or move the immutable release tag. Measurement contract,
official/A100 references and all user modifications remain unchanged.


### Prior-stable worktree consolidation (2026-10-03)

User requested consolidation after EXP-123 became stable. Only two primary
worktrees remain: root (exp-075-compact-late-lut) and
exp-123-cufft-format-benchmark (current stable). The prior-stable
exp-095-sbrc128k-only directory was moved intact to
archives/worktrees/exp-095-sbrc128k-only; its .git marker is now .git.inactive.
The original Git administration, inventory and recovery mapping are preserved
in .worktree-archives/retire-exp122-worktree-20261003/. Do not run Git in this
historical snapshot; restore registration explicitly when needed.

The rocfft-opt-pre-tile-lifetime branch and all immutable tags remain. Its
tracked source has no unique code requiring integration into EXP-123. Six
untracked historical log/result entries and all ignored files are preserved
in the snapshot. No installed library, baseline, source or existing user change
was deleted. Current previous-arm source_repo references the active EXP-123
repository, retaining the real EXP-122 binary build commit and checksum.
Operational documents now synchronize only root/EXP-123; the prior-stable
snapshot and its complete historical record are immutable archive material.
Top-level worktree count: 3 to 2; top-level entries: 43 to 42. This is worktree
consolidation, not an EXP-123 merge into the old top-level source checkout.


### EXP-125 新局部实数分解：正式性能复核（任务889083）

2026年10月6日。沿用 EXP125；候选来自稳定 EXP123 的干净基线，提交 `d79a74bc24f85bdedabefd3dbcb56e5085853764`，分支 `exp-125-local-real-f`。本轮新构建库校验值 `e1bf9b2b903611635624db88a3f2fa2af558ec73558e45efbf31af6860e73759`。源码只有一个本轮实现提交，此前 EXP125 的实现和安装未被当作本轮候选。

前置构建及验证任务 888825 已通过二十项原始程序检查、六十项特殊频点及边界检查，两种加载路径、五个尺寸均证实每次执行只有两个融合核函数。

正式性能任务 889083 正常完成，用时34分44秒。本轮测量默认寄存器加载路径。双精度、单批、非原位，十五种情形、八轮同卡交错对照，共七百二十个进程。全部正确性检查通过，最大误差约 `3.55×10^-15`；顺序、设备、库和原始记录校验值均通过复核，重新汇总与原报告一致。

复数转实数相对稳定基线的耗时下降：64K为11.70%，128K为11.32%，256K为8.28%，512K为2.02%，1M为0.64%。前三个尺寸八轮全部更快。512K四轮更快、四轮更慢，中位数慢0.31%；1M五轮更快、三轮更慢。按已登记的算术平均规则五个尺寸均获益，但512K与1M尚不能认定稳定提升。全部慢样本原样保留。

稳定对照使用批准的 EXP122 原始库，真实构建提交 `ed06208f30706f63126078a5c51af07fa0439fe7`；其变换源码语义与稳定 EXP123 一致。官方、稳定对照、候选及固定 A100 参考的全表见原始测量目录 `/public/home/zhangkewei/zr/experiments/EXP-125/runs/EXP-125-performance-20261006-f`。

完整复核与说明：`experiments/EXP-125/records/local-real-f/performance-889083/`。构建凭据：`experiments/EXP-125/runs/EXP-125-build-20261006-f/build-provenance.json`。正式配置：`configs/experiments/EXP-125-performance-f.json`。

决定：保留本轮源码与证据；64K～256K有较明确收益，512K和1M有待进一步确认。不自动合并或晋升稳定版本，本次检查没有提交新的任务。


### EXP-125 实数转复数末段后处理融合：实施与验证登记（2026年10月6日）

沿用分支 `exp-125-local-real-f`，从已通过前处理验证及正式性能复核的提交
`d79a74bc24f85bdedabefd3dbcb56e5085853764` 修改。此前失败的 EXP125 实现没有被复制。
本轮源码提交与逐文件校验、完整源码归档固定在
`experiments/EXP-125/source/paired-post-g/manifest.json`；实验编号仍为 EXP125。

范围：64K、128K、256K、512K、1M，双精度，单批，非原位，单位步长，零偏移，
实数输入与交错半谱输出，当前 gfx936 的已核对配置。显式指定方案和其他条件沿用原路径。
保留半长复数变换及第一段列变换；末段把镜像行放进同一线程块，以已有完整输出共享存储
完成后处理，删除独立后处理核函数。原有前处理实现及普通生成代码保持一致。

代码修改十个文件：`real_block_io.h` 增加独立角色；`tree_node_real.h` 与
`tree_node_real.cpp` 接入已有半长分解、限定条件及两种加载方式，并在分配子节点参数前
设定输出距离；`tree_node.h` 描述多出一个频点的实际输出与独立旋转因子资源；
`tree_node.cpp` 申请和释放原全局后处理旋转因子表；`assignment_policy.cpp` 按实际输出
检查容量；`rtc_stockham_kernel.cpp` 传递资源及加载参数；`rtc_stockham_gen.cpp` 接入独立
生成器和缓存名称；`stockham_gen_real_post.h` 分离镜像地址、数值组合与常规加载/写出节点；
`CMakeLists.txt` 登记新头文件。末段不增加变换、矩阵、共享存储容量或同步屏障。

首版使用原始完整后处理表。仍有镜像地址运算、频点组合、寄存器存活区间、写出连续段
缩短和并行度变化等开销；不能据此认定性能获益。理论去掉一次半长复数矩阵读写，
逻辑数据访问节省约 16N 字节（旋转因子及实际缓存事务另计）。

离线前置要求：独立目录构建代码生成器；四个改动的主机源文件语法检查；
120 份既有生成代码逐字一致（其中40份已有前处理）；20份新后处理代码离线编译通过，
覆盖五个尺寸、寄存器/共享存储加载及回调开关；两个正确性程序编译通过。
证据保存在 `experiments/EXP-125/artifacts/preflight/paired-post-g/generated-proof-*/`。
无回调的十个核函数资源检查没有发现私有存储溢出；256点行变换使用58个向量寄存器，
512点寄存器加载使用60个，共享存储加载使用61个。此为离线编译记录，设备构建可能不同。

本轮只提交构建和设备正确性/实际融合验证，不提交正式性能。独立构建安装标识为
`EXP-125-paired-post-g`，配置为 `configs/experiments/EXP-125-build-g.json` 和
`configs/experiments/EXP-125-diagnostic-g.json`。原始程序检查25项；新增完整长度复数
参考检查70项，覆盖冲激、直流、奈奎斯特、四分之一频点、混合频率和随机输入，检查全部
半谱点、输入不变及边界；已有前处理回归60项。两种加载方式及五个尺寸均须每次只执行
两段变换，且不再出现独立前/后处理核函数。所有误差严格小于十的负九次方。

设备检查结果及任务编号以同目录提交记录和
`experiments/EXP-125/runs/EXP-125-diagnostic-20261006-g/` 为准，当前待执行。
性能结论、相对基线及官方提速、A100 对照均待用户后续授权的正式性能测试。
提交设备任务后立即停止，等用户要求检查；不自动晋升稳定版本。


### 2026-10-07：EXP125后处理旋转因子连续表与提前读取实现

继续 EXP125，当前分支 `exp-125-local-real-f`，起点为已验证后处理版本
`dc254562cb023dcf63b7d2b3e4451eb4aa433bfb`。按此前访存分析方案直接生成
四分之一长度的连续旋转因子表，普通路径在后处理开始前提前读取，回调路径逐轮读取。
缓存增加布局字段，保留现有设备隔离和引用计数。未改变傅里叶计算、后处理公式、共享存储、
中间矩阵及输出位置；已有前处理保持原样。源码九文件清单、开销及验证范围见
`experiments/EXP-125/records/post-memory-h/实施记录.md`。

提交前已完成独立代码生成器构建、三份主机集成语法检查、两份生成器源文件编译。
既有一百二十份生成代码（包括四十份已有前处理代码）和十五份普通建表代码逐字一致。
二十份新后处理代码的计算、数据读取和输出写入经对照保持一致；实际生成的新表
在五个尺寸的主机模拟中覆盖完整并与原表对应值一致。二十份后处理代码及三份新表
代码离线编译均通过，未发现私有存储溢出。证据位于
`experiments/EXP-125/artifacts/preflight/post-memory-h/`。

独立构建安装标识 `EXP-125-post-memory-h`。构建和验证配置分别为
`configs/experiments/EXP-125-build-h.json` 和 `configs/experiments/EXP-125-diagnostic-h.json`。
单个设备任务先构建，再进行原始程序二十五项、完整半谱一百四十项（包含回调）、
已有前处理回归六十项，以及普通表与新表共存、共享和释放的一百二十项检查。
适用范围保持双精度、单批次、输入输出分离、六万四千至一百万点、两种加载方式。
共存检查的普通双批次计划仅用于验证缓存隔离，不纳入性能范围。
所有数值误差要求严格小于十的负九次方。融合路径每次必须实际执行两段核函数。

精确源码提交、归档、脚本与证据摘要由
`experiments/EXP-125/source/post-memory-h/manifest.json` 及同目录独立配置登记。
保留官方原版和此前批准的 EXP122 安装身份，已验证后处理安装也保持原样。
本轮不提交正式性能测试，性能及相对官方、稳定版本和 A100 的结果均待后续授权测试。
提交构建与正确性验证后立即停止，等用户要求检查，不自动晋升稳定版本。


### 2026-10-07：EXP125前处理系数读取调度实施与恢复点

用户授权按已完成评估的方案实施，并要求保存当前代码以便发生负收益时恢复。继续EXP125，基底为已测提交7fc5daeadd170b36fe19850f0977d87b61dc1718，分支exp-125-local-real-f。修改前建立标签exp-125-before-pre-memory-i-20261007，完整计算源码356份文件逐一对照版本内容，两个源文件另存原件，旧库副本与原库校验值一致。恢复目录/public/home/zhangkewei/zr/experiments/EXP-125/artifacts/rollback/pre-memory-i-before-20261007，原安装保持原样。

仅修改stockham_gen_local_real.h和rtc_stockham_gen.cpp两个计算文件，复用已通过离线检查的原型原件。64K/128K默认寄存器路径保持原实现、共享存储路径逐对提前；256K至1M两条普通路径一次声明四个系数。回调和后处理生成代码保持原样。策略与名称共用选择函数，不改变数据布局、算术及同步。八份目标代码离线编译通过，另外132份生成代码逐字一致；实际设备验证仍待新任务。

独立构建、安装标识EXP-125-pre-memory-i，配置configs/experiments/EXP-125-build-i.json与configs/experiments/EXP-125-diagnostic-i.json，源码归档experiments/EXP-125/source/pre-memory-i/。验证沿用已通过的数值程序，包括原始程序25项、前处理边界与特殊频点60项、后处理参考及回调140项、表共存与释放120项，并检查30组严格两段执行记录及新读取策略实际进入即时编译源码。前处理回调代码以静态逐字一致保护，本轮没有新增其设备用例。

完整机制、范围、冻结凭据及恢复说明见experiments/EXP-125/records/pre-memory-i/实施与恢复记录.md。若测得负收益，可直接回用原安装；源码仅恢复两个计算文件并新建恢复提交，保留本轮历史和证据。正式性能尚未提交，也不自动晋升稳定版本。构建与正确性验证提交后立即停止，等待用户检查指令。
