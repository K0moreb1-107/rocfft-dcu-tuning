# Remote rocFFT optimization measurement contract

This file is authoritative for all subsequent rocFFT optimization experiments
in /public/home/zhangkewei/zr. Do not change the measurement definition without
recording the reason and updating this file first.

## 任务提交（用户更新，2026-10-20）

后续提交任务不再冻结源码、工作区及构建／验证依赖，不检查构建期间或结束时的源码状态变化，也不据此阻断任务。
记录实际提交号、配置、所用库和结果用于追溯；既定正确性与性能验收要求保留。本条优先于下文冲突的冻结及源码状态一致性要求，历史任务与证据不改写。

## 设备验证时限（用户强制要求，2026-10-21）

后续每轮设备验证总时长禁止超过600秒；EXP128本轮仍以300秒为上限，不以拆分任务规避时限。
按变更选择能在预算内完成的检查，保留数值正确性、输入保护、越界及本次修改相关检查；失败用例先跑。
未受影响且已有通过证据的全量矩阵、内部组合及逐尺寸分析器追踪不重复作为提交门槛。
提交前核对清单并完成必要主机编译；逐项记录耗时，超时终止，不自动延长或盲目重提。
正式计时仍逐尺寸／类型在窗口外校验正确性；注明实际验证范围，未检查部分不宣称全面验收，历史证据保留。

## 性能测量（用户更新，2026-10-15）

统一入口：`python3 manage.py measure --config CONFIG.json` 预览，加 `--execute` 提交。
新测量默认 `FFT-event-cufft261012-single-v3`：双精度、一维、批量一、非原位、默认计划；
每个尺寸／类型／版本一个独立进程，十次预热、三十次正式计时。
沿用test_fft_261012原包事件循环：预热及正式变换共用计划、缓冲区与默认流，每次单独同步；
只读出后30次耗时，预分配样本空间，结束后写文件。输入为元素序号，复数虚部为零。
严格 `<1e-9` 正确性在窗口外完成，随后完整恢复测量输入；没有假N=1计划或未初始化首轮。
节点独占、单卡；对照与当前紧邻、交替先后，冻结源码／头文件／库／程序／参考与设备身份。
保留原包39列、未舍入逐次样本及独立正确性表；缺项、校验失败或身份不符即拒绝汇总。
性能分析及验收只用全部逐次样本的中位数，加速比＝对照中位数／当前中位数，不剔除慢点。
保留散点与测量序号图，仅标中位数及中间50%区间；重叠或漂移标注差异不明确，不自动重测或推广。
新A100参考在提交前冻结具体版本，只按精确N、类型及10／30条件匹配中位数；无匹配留空。
performance＝A100中位数／当前中位数×100%，仅作跨设备参考，原包构建凭据限制须注明。
旧v1／v2配置显式沿用原协议与程序，原始结果及920949的三次／50次记录不改写、不混表。
新程序固定10／30；需要调整次数时另行登记对应源码版本，不能只改配置冒用原身份。
诊断用 `manage.py diagnose`：冻结脚本、输入及库，独占单卡；分析器耗时单列，不替代正式事件结果。
对照可指定已有的已验证稳定安装，无需重建；候选构建与验证独立，提前排队性能只依赖实际待完成版本的验证成功。双方仍在同一独占单卡分配内紧邻、交替计时，注明对照含义。
细则及版本差异见 `docs/technical/FFT_MEASUREMENT_PROTOCOL.md`。提交任务后停止，待用户要求检查。

## Historical hipprof scope and matching conditions

For historical batch=1 hipprof comparisons, match FFT length, transform type,
precision, batch size, -N value, profiling command, GPU and runtime environment.
The EXP-091 workload was double-precision z2z, out-of-place, batch=1,
`-N 10000`, on the same DCU with `hipprof --stats`; five independent processes
per length, median canonical time, preserving rounds/mean/stdev/CV. Target
lengths: 64K, 128K, 256K, 512K, not 102400. Retain same-allocation interleaved
comparisons when interpreting that historical contract.
Legacy throughput was z2z, batch=1000, `-N 10`, same DCU and hipprof --stats;
do not mix absolute times with batch=1 or divide by 1000 as a substitute.

## Historical batch=1 transition (EXP-091)

The user clarified on 2026-09-22 that batch=1000 was chosen only as a way to
reduce measurement noise; it is not an application requirement.  Actual use
and evaluation may use batch=1.  Therefore, do not design or promote an
optimization whose benefit depends on scheduling multiple user transforms in
one batch.  In particular, batch strip-mining is only a diagnostic and is not
a primary optimization direction.

EXP-091 calibrated the repetition count (`-N`) and established the separate
batch=1 baseline below. Every historical hipprof batch=1 result must record its own `-N` and use
exactly its own `N+1` divisor. Increasing `-N` also amortizes fixed per-process
twiddle-generation kernels, so report transform-only timing as a diagnostic
when explaining differences across N; keep the canonical metric for the
contract result.

rocFFT's internal `transforms_per_block` is not the user batch size.  A kernel
mapping change such as four versus eight internal transforms per workgroup can
still be batch-independent, but it must be validated with user batch=1.

## Historical hipprof: Fixed batch=1 baseline result files (EXP-091)

Runtime: validated EXP-090 installation at
`/public/home/zhangkewei/zr/experiments/EXP-090/artifacts/install/install-exp090-candidate`, source commit
`0473680e99b181e4660643425f53382f3a6afad7`. Measurement job: `856749`.
Raw files are the five `r1` through `r5` hipkernel CSVs for each length under:

    /public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749/

The machine-readable and text summaries are:

    /public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749.json
    /public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749.txt

Canonical median times are 0.017346298 ms (64K), 0.019450103 ms (128K),
0.023224602 ms (256K), and 0.051072366 ms (512K). The corresponding
five-process CVs are 1.396919%, 1.459374%, 0.198862%, and 0.299984%.
These are steady-state profiled GPU-kernel metrics, not host wall-clock or
cold-plan latency.

## Historical hipprof: Fixed legacy batch=1000 baseline result files

Unless a new baseline is explicitly declared and recorded, use these files
as the baseline for double-precision z2z, batch=1000, -N 10 comparisons:

    /public/home/zhangkewei/zr/results/z2z_64k_official_7.2.2_20260831_172537.csv.hipkernel.csv
    /public/home/zhangkewei/zr/results/z2z_128k_official_7.2.2_20260831_172537.csv.hipkernel.csv
    /public/home/zhangkewei/zr/results/z2z_256k_official_7.2.2_20260831_172537.csv.hipkernel.csv
    /public/home/zhangkewei/zr/results/z2z_512k_official_7.2.2_20260831_172537.csv.hipkernel.csv

Select the baseline matching the exact FFT length. Do not compare a result
against a baseline from another length or transform type.

## Historical hipprof: Canonical time extracted from hipprof CSV

Use the TotalDurationNs column. The canonical rocFFT computation time is:

    T_compute_ns = (TotalDurationNs(Total row)
                    - sum(TotalDurationNs for bench-only extra kernels))
                   / (N + 1)

Convert to milliseconds only after subtraction:

    T_compute_ms = T_compute_ns / 1,000,000

The Total row is the aggregate GPU-kernel duration reported by hipprof across
the benchmark's N warm-up/measurement repetitions. Divide the adjusted value
by N+1 exactly once. For the standard -N 10 command, N+1 is 11. Do not apply
another repetition factor elsewhere.
Do not use AverageNs for the canonical time, and do not reconstruct the
total by summing per-kernel AverageNs; those are different aggregation
operations and can produce a different value when kernel call counts differ.
For a nonstandard N, use that run's actual N+1 divisor and record it with the
result. The standard baseline files use N=10 and therefore divisor 11.

## Historical hipprof: Excluding rocfft-bench overhead

The currently verified bench-only kernel is:

    generate_random_interleaved_data_kernel

Its TotalDurationNs is excluded because it initializes random input for
rocfft-bench and is not part of the rocFFT transform. Match this kernel by its
stable name substring, including template-specialized names.

Keep fft_*, transpose_*, and twiddle_gen_* in T_compute_ns. The first two are
transform kernels; the twiddle-generation kernels are part of the rocFFT
execution path. Exclude any additional kernel only after proving from the
benchmark source and a controlled profile that it is bench-only, then add its
stable name pattern and evidence to this file.

This metric is profiled GPU-kernel execution time. It does not claim to be
host wall-clock time and does not include CPU launch, synchronization, or
unprofiled runtime overhead. Keep this limitation explicit in reports.

## Speedup and improvement

For an experiment (exp) versus the immediately preceding valid version
(prev):

    speedup_prev = T_prev / T_exp
    improvement_prev_percent = (T_prev - T_exp) / T_prev * 100

For the same experiment versus the fixed baseline (base):

    speedup_baseline = T_base / T_exp
    improvement_baseline_percent = (T_base - T_exp) / T_base * 100

Use the same time metric for both numerator and denominator. A value below
1.0x or a negative improvement is a regression. Report times with enough
precision to reproduce the ratios, and do not mix FFT-only sums, CSV Total,
and the canonical metric in one comparison table.

## Required record for every future experiment

记录源码／构建身份、修改文件、协议和验收、任务／设备、正确性及原始样本／日志／校验值。
各版本耗时及各对照加速比只用逐次样本中位数；A100缺少匹配中位数时只留历史参考。
诊断指标单列，历史原件保留登记时的统计定义；记录最终决定。

## Required experiment result record

Every optimization attempt must have a unique EXP-NNN identifier and must be recorded in VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md before the next experiment. Each record must include the exact commit, branch, previous valid result, target conditions, changed files and conditions, job IDs, correctness result, raw CSV/log/PMC paths, canonical time, speedups versus previous valid version and fixed baseline, and final decision. Detailed rationale and mechanism analysis belong in VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md. Preserve raw evidence until the record is complete.

## rocFFT generator AST value categories

- Check AST-node constructor signatures in `library/src/device/generator/generator.h` before composing generator expressions.
- `Ternary` takes three `Expression&&` arguments. Do not pass named `const Expression` objects or other lvalues directly.
- Materialize fresh wrappers: `Ternary{Expression{condition}, Expression{true_result}, Expression{false_result}}`.
- EXP-084 job 840562 failed with `no matching constructor for initialization of 'Ternary'` because an argument was a `const Expression` and would lose its const qualifier.
- Fix this diagnostic as a value-category/ownership issue; do not change the generated kernel's semantics to silence it.
- Before submitting a full experiment chain, run `cmake --build <build-root>/rocfft_build --target rocfft-rtc-gen -j16` in the isolated candidate build.

## Top-level documentation synchronization

The authoritative operational instructions and complete latest experiment record
live only in /public/home/zhangkewei/zr. Retired worktree snapshots are immutable
historical copies, not synchronization targets. Keep AGENTS.md concise: update
the current valid version and workflow rules; put experiment details in
VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md. See WORKTREE_ARCHIVES.md for recovery.

## Git version maintenance requirements

main is the stable branch; use the top-level checkout for daily development.
Start each new optimization from main in a separate EXP-NNN branch in this same
directory, record its starting commit and criteria, and preserve failed branches.
Default to serial experiments. Do not switch branches while a task is queued,
building or running, or before local changes have been saved. Build/install/cache
and run evidence remain independent per experiment and immutable per run.
Create a temporary worktree only after the user's explicit agreement when
parallel source checkouts are necessary; approved temporary worktrees belong in
worktrees/EXP-NNN and must be archived after use.

Commit source changes with the experiment record and relevant instruction changes.
Promote only after correctness, benchmark and required cross-size acceptance.
Keep immutable official, pre-experiment and retained-version tags. Never rewrite
history, force-push stable history, discard failed records or treat uncommitted
source changes as a validated retained version.

## Current valid version

Stable branch: main
Stable workspace: /public/home/zhangkewei/zr
Retained source reference: EXP-126 06baff81d85a7f24fd240cd32c849244b05ae3b9
Management tools: sample-v2, median analysis, explicit dependencies and deferred queue; retained with stable tag.
Valid tag: 完成CC路径前后处理融合
Approved stable installation: experiments/EXP-126/artifacts/install/EXP-126-heldout-complex-20261012 (ROCFFT_REAL_PAIR_SCALAR_CAPACITY=OFF)
Promotion record: experiments/EXP-126/records/stable-promotion-20261013/promotion.json
用户于2026-10-13保留CC融合功能版本；已记录的性能退化留待后续优化，转置／卷积融合尚未实现。

## Agent Delegation and Token-Efficiency Policy

The user clarified that Info.md applies only when they explicitly request
sub-agents. Otherwise follow the applicable normal agent instructions. When
explicitly requested, read /public/home/zhangkewei/zr/Info.md.

## Historical experiment layout (approved 2026-09-30)

Historical scripts, patches, records, source and evidence are grouped under
`/public/home/zhangkewei/zr/experiments/EXP-NNN/`. Retired worktree snapshots
are under `/public/home/zhangkewei/zr/archives/worktrees/`, retaining their names.
Their original files and inactive Git markers are preserved; use the top-level stable checkout for development. Historical scripts are not rewritten and
may require path adaptation before reuse. Consult `EXPERIMENT_LAYOUT.md` and the
approved migration map before restoring or rerunning historical work.

Access the fixed EXP-091 baseline through its physical EXP-078 archive path.
The former top-level compatibility links are retired; preserve their actual
archive/install directories. Legacy reuse follows docs/technical/LEGACY_PATH_ADAPTATION.md. Eight historical experimental build trees are now in `archives/builds/`;
their old absolute CMake paths are evidence, and reproduction requires rebuilding.
Four EXP-082/083 Git directories are now in `archives/repositories/`, retaining
their original names, refs and tracked states; known linked-worktree paths and,
with separate user confirmation, two object-store alternate paths were corrected.
The v2 repository's missing index is preserved and must not be repaired
automatically. Existing installation paths, the main build and runtime stay put.

Keep `EXPERIMENT_LAYOUT.md` and the current `WORKTREE_ARCHIVES.md` index identical
in the top-level checkout; archived copies are historical. Preserve prior dated
archive records; append later migration/restore mappings rather than rewriting
historical evidence. This layout does not change measurement or source semantics.


## Persistent top-level organization (approved 2026-09-30, round 3)

The top level is a workspace containing nested source repositories, not the
rocFFT CMake source root. Keep source/configuration and the current stable,
top-level stable and official paths intact. Common tools are in `tools/`; current job and
submission entries are in `jobs/`. Use `EXPERIMENT_LAYOUT.md` for entry paths.

Never write new validation data, tuning CSVs, profile output, helper executables
or job logs directly at the top level or next to a tool's source. Use results,
logs and build subdirectories, or an experiment's approved category directory.
Only explicitly approved temporary worktrees belong under `worktrees/EXP-NNN`;
build/install/cache belong under `experiments/EXP-NNN/artifacts/`. These future rules do not move
existing protected source, installation, runtime, or baseline paths.

Run `python3 tools/check_top_level.py` to report unexpected top-level entries.
This check is read-only: it must never delete or move anything automatically.
Keep its allowlist consistent with user-approved exceptions and mappings.
Preserve historical validation evidence and VkFFT local file permissions.
New validation outputs belong in managed run directories.
`gfx926_rocfft_solution_map.dat` remains as an explicit runtime configuration
exception. Ask the user about new dependencies, conflicts or unexplained states.

Historical scripts and evidence remain original. Environment-stale entry scripts
are archived rather than silently repaired. Do not enable them without verifying
their dependencies. Tool path adaptations do not change FFT parameters, accuracy
thresholds, canonical measurement rules or validated optimization source.


## Unified artifacts and task management (approved 2026-10-02; implemented 2026-10-03)

This dated policy supersedes the previous installation-preservation and output
path exceptions only for the approved migration. Source worktrees, official
repository, validated optimization source/tag and measurement definitions stay
unchanged. See docs/technical/WORKSPACE_MANAGEMENT.md for commands and recovery.

Use manage.py with an explicit independent experiment configuration under
configs/experiments/. Default is read-only preview; --execute submits the task
or generates the requested report. The manager never changes source checkouts.
New optimization still starts from the current valid stable source in an EXP
branch. The stable source now lives in the top-level main checkout.

New build/install/cache belong to experiments/EXP-NNN/artifacts/ with unique IDs.
Run CSVs, stdout/stderr, configuration, provenance and reports belong together
under experiments/EXP-NNN/runs/<run-id>/; helper binaries remain artifacts.
New formal measurements use the current versioned sample protocol above.
Previously submitted manifests select their registered legacy protocol unchanged.
Unified preview must show concrete library identities, process count and event count.
用户明确要求提前排队时，可用统一入口的延迟解析登记：固定已提交构建、输入校验值及成功依赖；
预览注明候选库校验值待生成，验证成功后核对并冻结实际库身份，再开始计时。

Current installation registry: configs/installations.json. Current previous
is the approved EXP-126-heldout-complex-20261012 library (user promoted 2026-10-13).
The EXP-125 library remains available by its original registry ID and frozen historical manifests.
The EXP-122 library remains the frozen previous arm of historical EXP-125 runs. Directory names do
not prove source identity or acceptance. Historical/unknown installations cannot
silently become official/previous/candidate. Candidate builds retain exact source
state, CMake parameters, compiler and final library checksum.

Main build/rocfft_build, build/hipfft_build, build/tools and install remain paired
legacy development locations. Use the physical installation paths in
configs/installations.json; the five former top-level aliases are retired.
Preserve the EXP-078 archive and fixed raw-baseline files. Do not restore aliases
automatically; adapt old programs only when requested.
The top-level count is now 36, subject to the explicit allowlist.

Historical loose results/logs moved to results/historical/legacy-root and
logs/historical/legacy-root. Keep them original; old diagnostic definitions do
not change. partial_pass_tile_ownership uses these historical inputs while
retaining original fixed baselines/Git root. Diagnostic plots write separately.
tune_all.py is retired and removed; retain enumeration helpers and historical
tuning data. Stale profiling/environment entries remain historical, not defaults.

Ten explicitly approved invalid build trees were cleared after preserving
configuration, compiler/install records and generated source records under
experiments/EXP-NNN/records/builds/. Seven other old build/helper snapshots
were grouped under corresponding artifacts/build/history. Installed libraries
were preserved. Eight existing EXP-081 FFTW stale links remain unchanged and
recorded; do not silently repair them. Existing archives/builds remains original.

Audit and mapping: .worktree-archives/artifact-management-20261003/. Refresh
identity/dependency checks before future restores. This implementation used only
static and synthetic validation; no actual compilation/GPU jobs were run. The
first new experiment must verify real compiler/runtime/GPU/library integration.
Ask about new conflicts, dependencies or unexplained states; preserve prior
user modifications and historical refs. Operational documents and the complete latest record are maintained
only at the top level; retired worktree snapshots remain immutable.


## Explicit experiment case matrices (user authorized 2026-10-09/10)

The default frozen 15-case matrix remains unchanged. An experiment may preregister
an explicit nonempty list of unique {N, func} cases and a case_scope explanation.
Use this for EXP-126 large-even CC coverage: real N >65536, multiple actual sizes
per parity and paired-tail family, larger N allowed when existing CC kernels and
resources permit. Validate actual fusion before formal timing. Do not force load
paths in measurement. Expanded matrices use the measurement protocol and repetition count registered
for that run. Default-path coverage and all correctness/evidence checks remain required.
实数融合验收须覆盖旧式折叠列与新增路径；回调逐元素恰好一次，复数回调覆盖共轭顺序。

A managed build may carry a frozen, committed post_build_validation script and
its explicit hashed inputs under that experiment. Preview verifies the identities
and shows its command. Run it only after saving the build's immutable identity;
record validation completion separately and require its success before formal
measurement from that build record. Validation failure never becomes a
formal acceptance or automatic promotion. All task submission uses manage.py.

最新A100资料见 `results/reference/a100/latest.json` 与 `docs/technical/A100_REFERENCE_DATA.md`。
新A100参考与v3均为10次预热、30次逐次计时；只按精确尺寸及类型匹配中位数，历史参考和旧协议原件保留。

## 存储与缓存

正确性参考数组为临时缓存，检查结果后按清单清理；保留生成代码、参数、校验值及原始测量／诊断证据。
提交前估算空间峰值并留足余量。归档源码和证据只读共享，恢复修改须复制为独立文件；见 `docs/technical/STORAGE_CLEANUP_20261020.md`。
可重建参考数组不另留整包备份，大体积备份不默认存本机。
