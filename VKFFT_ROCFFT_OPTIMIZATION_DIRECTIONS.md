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
### EXP-006：stage-aware read-to-register（已完成，回滚）

Date: 2026-08-21.

Goal: test whether VkFFT setReadToRegisters can remove an LDS round trip for the 512K z2z SBCC-1024 kernel.
Only the DP length=1024 factors=[8,8,4,4] SBCC entry was changed by setting direct_to_from_reg=False; WGS, TPT, radix, LDS addressing, and twiddles were unchanged.

Result: build 759721 and correctness task 759711 produced relative_l2=1.382328e+00, relative_max=1.439529e+00, max_abs=5.409508e+03. Correctness failed.

The option was removed and the default direct-reg path was restored; the restored path passed correctness.

Decision: revert. rocFFT direct_to_from_reg is a global path switch, not a stage-local read policy. Disabling it without a matching Stockham LDS layout breaks pass-to-pass data placement.

### EXP-007: limited registerBoost (completed, retained)

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

### EXP-008: stage-aware XOR LDS mapping (completed, reverted)

Date: 2026-08-21.

Hypothesis: VkFFT changes LDS conflict handling by stage. The existing rocFFT XOR mapping was applied to every DP half-LDS access for length 512/1024. This experiment added a generated-pass state and enabled XOR only for early passes (stage <= 1); later passes used the linear LDS address. No WGS, TPT, radix, twiddle, or synchronization change was made.

Build 759796 and 512K correctness 759798 passed: relative_l2=6.644698e-16, relative_max=9.451432e-16, max_abs=3.551690e-12.

Benchmark results: 512K jobs 759800/759799 gave SBCC+SBRC=40.687127 ms versus EXP-007 40.682627 ms; 256K=18.137063 ms versus 18.135222 ms; 128K=7.926573 ms versus 7.921375 ms; 64K=3.632477 ms versus 3.633847 ms. The changes are neutral within noise and show no consistent gain.

Decision: revert. The stable source was restored and installed by build 759803; 512K correctness 759805 passed. The existing all-stage XOR mapping remains retained because it is the better measured configuration.

### EXP-009: small-radix register permutation (feasibility completed)

Date: 2026-08-21.

Generated-source inspection was used to test the VkFFT RadixShuffle idea. In the actual 1024-point SBCC [8,8,4,4] kernel, pass 0 stores R to LDS with tid/cumheight and tid%cumheight; the next pass reloads a different layout. Pass 1 and pass 2 repeat this cross-thread layout change before the radix-4 butterflies. The data needed by a later butterfly is therefore not confined to one thread's R array.

Conclusion: there is no safe local register-only permutation candidate in this kernel. Removing one LDS load/store without changing the ownership map would read a different transform element and fails the Stockham contract. This direction is not implemented as a fake bypass; a valid version would require a new cross-wave ownership layout and a correctness proof. No code change was retained.

### EXP-010: extend tile lifetime across large-twiddle and next FFT (mechanism completed)

Date: 2026-08-21.

The RTC source for the stable 1024-point SBCC kernel was inspected. It performs global load -> Stockham LDS/register passes -> final large-twiddle multiplication in registers -> global store. The following SBRC-512 kernel starts from the global buffer and has a separate launch. The source confirms the current CC kernel already fuses its local FFT and large-twiddle operation, but it does not keep the tile alive into the next SBRC kernel.

At 512K the current retained CC route is SBCC-1024 23.126766 ms plus SBRC-512 about 17.55 ms (EXP-007 total 40.682627 ms). Extending the tile across these kernels cannot be enabled in stockham_gen_cc.h alone: it needs a planner-level fused SBCC/SBRC kernel, shared LDS ownership, and a new launch interface. No unsafe partial fusion was retained.

Decision: the VkFFT mechanism is already partially present inside SBCC; the missing cross-kernel lifetime is a high-risk architectural change, not a parameter switch. The experiment is complete as a boundary/feasibility result.

### EXP-011: stage-local/coalesced ordinary LUT (completed via EXP-002, reverted)

Date: 2026-08-21.

EXP-002 already tested the VkFFT coalesced-LUT idea on the second radix-8 stage of SBCC-1024. It cooperatively uploaded the 56-entry, 896-byte stage-local ordinary twiddle working set to LDS and redirected only that stage's twiddle reads. Correctness passed, VMEM reads dropped from 31.744M to 24.832M, but LDS instructions increased to 105.728M and the SBCC-1024 time regressed from 25.995145 ms to 26.085001 ms.

Decision: revert. The working set is small enough for the GPU cache; explicit LDS staging replaces cache hits with LDS traffic and a barrier. This completes the stage-local LUT direction without retaining a regression.

### EXP-012: final stable installation verification

Build 759803 restored the source after EXP-008. Correctness task 759805 passed. Final benchmark 759807 measured SBCC-1024=23.136096 ms and SBRC-512=17.566211 ms, total=40.702307 ms. The small difference from EXP-007 (40.682627 ms) is within run-to-run noise; the final kernel name confirms wgs_256_tpt_64_halfLds and no stage-aware code remains.

Final retained mechanisms: CC threshold selection, DP half-LDS, all-stage XOR LDS mapping for lengths 512/1024, single-thread large-twiddle recurrence, SBRC scalar-LDS, radix-8-oriented 1024 factorization, and the limited registerBoost configuration.

### EXP-013：planner 级 tile 生命周期契约扩展（已完成）

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


### EXP-014：SBCC→SBRC streaming 融合条件诊断

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


### EXP-015：解除 consumer direct-reg 的误拒绝条件

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

### EXP-016：修复 fused RTC 变量的二次前缀改写

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

### EXP-017：前缀修复后的 rocFFT 构建与安装验证

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


### EXP-018：融合 RTC 首次正确性验证

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


### EXP-019：RTC 生成结果与 handoff stride 核对

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


### EXP-020：stride scope 诊断变体

日期：2026-08-23。

#### 原理

fused generator 中 producer、consumer 和外层 launch 使用不同的 stride 参数命名空间。为了排除 lexical variable visitor 把 `stride_out` 重写到错误 stage 的可能性，需要单独检查生成源码中每个 stride 参数的声明、引用和 handoff 表达式，而不能只观察 planner 的 plan dump。

#### 做了什么

增加并运行 stride scope 诊断，追踪 `FusedStageRewriteVisitor`、`FusedGlobalVariableVisitor` 对 producer `stride_out`、consumer `stride_in` 以及 handoff 中 `stride0_out` 的绑定关系。检查生成的 RTC 源码是否残留 standalone `stride_out` 或错误的二次前缀。

#### 验证结果与效果

生成源码中的 stride 声明和 handoff scope 已能区分 producer 与 consumer，未发现把 fused 外层 `oStrides` 直接当作 producer stride 的证据；但 correctness 仍失败，故该诊断变体没有解决数据错误。

本轮只保留诊断和源码检查，不改变运行时判定。当前最可疑的剩余问题是 producer WGS=256、consumer WGS=512 时，所有 512 个线程重复执行折叠后的 producer lane，可能对 handoff LDS 产生重复写入竞态。


### EXP-021：handoff ABI 与线程映射诊断

日期：2026-08-23。

#### 原理

producer 的 RTC helper 含有多个 `__syncthreads()`。不能用 `if(threadIdx.x < producerWgs)` 包住整个 producer helper，因为只有部分线程进入 barrier 会死锁。当前可行的第一步是让 512 个线程都执行 producer 计算和 barrier，同时把 `threadIdx.x` 折叠到 256-thread producer lane 空间；随后必须确认 handoff LDS 写入是否需要单写者限制。

#### 做了什么

增加 handoff ABI 诊断，观察 producer/consumer WGS、TPB、tile fan-in、producer block remap、handoff store guard 和 barrier 所在 helper。对受 RTC cache 初始化、作业环境和设备资源影响的任务分别记录失败原因，不把环境失败误判为算法正确性结果。

#### 验证结果与效果

诊断确认目标配置为 producer WGS=256、consumer WGS=512，producer 线程被折叠后 256 个 lane 会被两组外层线程重复执行。部分任务受 RTC 或环境问题阻断，未形成新的 correctness 通过证据；现有随机输入错误仍保持 EXP-018 的量级。

由此形成 EXP-024 的可验证假设：保留所有线程参与 producer barrier，但只允许原始 256 个 producer lane 写 handoff LDS，从而消除重复写者竞态。


### EXP-022：fused resource debug 构建验证

日期：2026-08-23。

#### 原理

融合路径同时改变 producer/consumer 的 LDS 声明、launch bounds、参数数量和 helper 资源。需要先确认 host 侧资源估算和生成代码调试信息可以构建，避免把运行时资源初始化问题误认为 planner 或 RTC 逻辑错误。

#### 做了什么

增加资源相关诊断与阶段信息，检查 streaming LDS 字节数、producer/consumer resident LDS、launch WGS 和 fused 参数 ABI；重新构建并安装 rocFFT。运行阶段同时保留环境错误原文。

#### 验证结果与效果

host 构建和安装成功，资源诊断能够输出目标 streaming LDS=32768 bytes 以及 producer/consumer WGS=256/512。部分 DCU 运行受 RTC cache 初始化、`std::bad_alloc` 或设备环境影响，不能据此宣称资源契约已经在设备上完全验证。

本轮保留诊断代码和构建结果，没有改变 fused correctness 判定，也没有删除额外的 global store/load。


### EXP-023：fused stage debug 与变量前缀根因定位

日期：2026-08-23。

#### 原理

融合生成经历多个 visitor：stage rewrite 先把 producer 的 `stride_out` 绑定为 `producer_stride_out`，随后 lexical variable visitor 又会给 stage 参数加 `producer_` 或 `consumer_` 前缀。若第二次 visitor 不具备幂等性，就会生成 `producer_producer_stride_out`，导致 RTC 编译错误。

#### 做了什么

增加 stage 级生成源码诊断并重新构建、安装。检查旧 RTC 日志和生成代码中 producer stride 的最终名字，同时确认 planner、launch 和 handoff 代码没有被该诊断改写。

#### 验证结果与效果

旧 RTC 日志出现 `producer_producer_stride_out`，定位到 `FusedGlobalVariableVisitor::visit_Variable()` 的无条件前缀逻辑。随后在该 visitor 中加入幂等条件：变量名已经以当前 stage 前缀开头时不再添加前缀，同时继续递归改写下标和尺寸表达式。

修复后 `git diff --check` 通过，host 构建和安装成功。该修复解决了 fused RTC 的明确编译根因，但在 EXP-018 的随机 correctness 失败之后仍需继续验证 handoff 数据竞争；因此本轮不能单独视为数值正确性完成。


### EXP-024：producer handoff LDS 单写者修复

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

### EXP-025：修复 owner 变量的错误 stage 前缀

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

### EXP-026：handoff 单写者变体的运行时正确性验证

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

### EXP-027：传递 producer 的 planner intrinsic 模式

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

### EXP-028：planner 级 global handoff 正确性闭环

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

### EXP-030：修正 LDS handoff 的转置后 LDS 线性布局

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

### EXP-031：恢复 LDS 基线并准备真实 RTC 地址审计

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
### EXP-032：将 streaming handoff 放到 producer scratch 之后

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

### EXP-033：隔离 global handoff 与 LDS handoff 的 RTC 变量绑定

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

### EXP-034：补偿 half_lds 对 fused streaming LDS 元素数的二次折半

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
### EXP-035：多尺寸 streaming contract 基线扫描

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

### EXP-036：放宽 producer 与 consumer 的独立 tile width 约束

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

### EXP-037：TILE_UNALIGNED SBRC 入口探测

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

### EXP-038：factorized root 的 planner 强制入口与 solution map 问题定位

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

### EXP-039：补齐 1024 SBRC kernel 并完成 1M 全路径融合

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

### EXP-040：将 1M 已验证形状纳入统一融合开关

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
### EXP-041：4704 非对齐 SBRC 基线

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

### EXP-042：4913 非对齐基线与 large-twiddle 限制

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

### EXP-043：实现最小 TILE_UNALIGNED streaming gate

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

### EXP-044：large-twiddle 合约筛选

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

### EXP-045：首个真实 TILE_UNALIGNED fused kernel

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

### EXP-046：放宽 batch 融合准入的初次探测

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

### EXP-047：batch 融合诊断入口与 handoff bug 定位

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

### EXP-048：batch-local handoff 修复与正式 opt-in

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

### EXP-049：batch 与自定义 distance 回归

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

### EXP-050：planner 级中间 buffer 生命周期 contract

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

### EXP-051：最终诊断输出与安装回归

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
