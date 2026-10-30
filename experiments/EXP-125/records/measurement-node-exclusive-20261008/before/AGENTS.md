# Remote rocFFT optimization measurement contract

This file is authoritative for all subsequent rocFFT optimization experiments
in /public/home/zhangkewei/zr. Do not change the measurement definition without
recording the reason and updating this file first.

## Primary event measurement (approved 2026-09-30)

Use the exact original EXP-123 fft_test_1d.cpp measurement program, frozen at
SHA256 849d011336601e6cffb1959e89590847e26160f7b3e256482a5eb37289e333da.
Full protocol: docs/technical/FFT_MEASUREMENT_PROTOCOL.md. Shared entry points:
/public/home/zhangkewei/zr/tools/fft_measurement/run.py and summarize.py;
formal submission: python3 manage.py measure --config CONFIG.json --execute.
Compatibility submission helper: bash jobs/measure_fft.slurm CONFIG.json.

Default matrix: double precision, batch=1, out-of-place, sizes 65536, 131072,
262144, 524288, 1048576, each z2z_1d/d2z_1d/z2d_1d (15 cases; no 32K).
Correctness remains enabled with the original strict <1e-9 checks. Preserve
initialization, inputs, 3 timing warmups, and 50 separately synchronized HIP
event measurements of rocfft_execute per process. Explicitly force 50 iterations.
Use original mean_ms; plan_ms, first_ms and per_tf_ms are diagnostics only.
No hipprof N+1 division or kernel subtraction applies to these event times.

Formal comparison: 8 rounds per case, one GPU UUID and one allocation;
odd official/previous/candidate/candidate/previous/official;
even candidate/previous/official/official/previous/candidate.
Each arm has 16 process means (800 events/case); full matrix 720 processes.
Arithmetic mean of all 16 mean_ms values is primary; no outlier removal.
Retain every process CSV/log, exact order, allocation/GPU/runtime identity,
source state, library path/hash, executable/compiler and build provenance.
Any missing/failed/mismatched case invalidates formal aggregation. Single
50-event processes are quick checks only, not formal promotion evidence.

Always report previous/candidate and official/candidate speedups plus
A100 Performance = fixed matching A100 mean_ms / candidate mean_ms *100%.
Official source/install are original ROCm 7.2.2; previous is the preregistered
immediately preceding valid stable version, not permanently EXP-119.
Candidate identity and experiment-specific acceptance criteria must be
preregistered before measurement. Do not impose new global percentage gates
or reuse old hipprof gates without preregistration. All correctness checks PASS
is required. No automatic source promotion from a report.

A100 raw reference is results/reference/a100/ beneath the workspace root,
SHA256 3b376eb69a77318ace8fbe537acfc7b3e82cdff1ea847f6177ed7ea82b27603b.
The user confirmed A100 provenance; retain all 18 original rows and select
the 15 matched cases. The historical mixed table is not a formal new baseline.

The following hipprof sections preserve historical/diagnostic definitions and
evidence. They do not govern new primary event measurements. Never mix event
and hipprof metrics in one ratio or rewrite old results with the new protocol.

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

Record the exact commit and source/build state, changed files, preregistered
acceptance criteria, job/allocation/GPU UUID, correctness, raw evidence,
official/previous/candidate arithmetic event mean_ms, previous and official
speedups, matched A100 Performance and final decision. Preserve all raw process
CSV/logs and hashes. Label any additional hipprof/PMC measurement as diagnostic
with its own original definition. Do not recompute old comparisons silently.

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
Management tools reference: 27d5c5e164c25975505d613e0109016e076bc346
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
Formal measurement retains the exact frozen CPP, 15 cases, 3 warmups/50 events,
8-round three-arm ordering, 720 processes and fixed A100 reference/formulas.
Queued configurations freeze concrete library/source identities, not mutable
aliases. No automatic source promotion. Quick validation is not formal evidence.

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
