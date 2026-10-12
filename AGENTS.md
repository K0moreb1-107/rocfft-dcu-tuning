# Remote rocFFT optimization measurement contract

This file is authoritative for all subsequent rocFFT optimization experiments
in /public/home/zhangkewei/zr. Do not change the measurement definition without
recording the reason and updating this file first.

## 性能测量（2026-10-12）

统一入口：`python3 manage.py measure --config CONFIG.json` 预览，加 `--execute` 提交。
新测量使用 `FFT-event-samples-single-v2`：双精度、批量一、非原位、默认计划；
每个尺寸／类型／版本一个独立进程，三次预热，默认50次逐次同步的完整变换事件计时。
次数可在登记中调整，同一比较各版本相同；保留原输入、初始化和严格 `<1e-9` 正确性。
对照与当前紧邻执行，各尺寸／类型交替先后；默认两版本，需要时显式增加稳定对照。
节点独占、单卡执行，登记具体源码、库、程序校验值、设备、顺序和验收要求；缺项或失败不汇总。
逐次耗时先存入预分配数组，计时结束再写文件；保留全部样本，不删慢点。
以后性能分析和验收只用原始逐次耗时的中位数；加速比＝对照中位数／当前中位数。
均值可保留在原始记录或兼容输出，不参与性能结论、类型判断或验收。
保留两列散点和测量序号—耗时图；图形重叠或顺序漂移时标注差异不明确，不自动重测或推广。
A100只有历史均值时单列参考，不与当前中位数混算加速比或相对性能。
历史登记、原表和任务900813保留原口径；以后重新分析已有逐次样本时另存中位数报告。
缺少逐次样本不构造中位数，不用进程均值的中位数替代；用户要求重测时才执行。
细则、样本格式和旧版协议见 `docs/technical/FFT_MEASUREMENT_PROTOCOL.md`。

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
Retained source reference: EXP-125 1d745ec17f516fa3bf1100c2fbd63baffa7e6d1d
Management tools: measurement-samples-v2-20261010 (versioned measurement entry).
Valid tag: stable-main-exp125-20261007
Approved stable installation: experiments/EXP-125/artifacts/install/EXP-125-pre-memory-i
Promotion record: experiments/EXP-125/records/stable-promotion-20261007/promotion.json

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

Current installation registry: configs/installations.json. Current previous
is the approved EXP-125-pre-memory-i library (user promoted 2026-10-07).
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

A managed build may carry a frozen, committed post_build_validation script and
its explicit hashed inputs under that experiment. Preview verifies the identities
and shows its command. Run it only after saving the build's immutable identity;
record validation completion separately and require its success before formal
measurement from that build record. Validation failure never becomes a
formal acceptance or automatic promotion. All task submission uses manage.py.
