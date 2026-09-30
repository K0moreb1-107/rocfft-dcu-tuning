# Remote rocFFT optimization measurement contract

This file is authoritative for all subsequent rocFFT optimization experiments
in /public/home/zhangkewei/zr. Do not change the measurement definition without
recording the reason and updating this file first.

## Primary event measurement (approved 2026-09-30)

Use the exact original EXP-123 fft_test_1d.cpp measurement program, frozen at
SHA256 849d011336601e6cffb1959e89590847e26160f7b3e256482a5eb37289e333da.
Full protocol: docs/technical/FFT_MEASUREMENT_PROTOCOL.md. Shared entry points:
/public/home/zhangkewei/zr/tools/fft_measurement/run.py and summarize.py;
formal job: /public/home/zhangkewei/zr/jobs/measure_fft.slurm.

Default matrix: double precision, batch=1, out-of-place, sizes 65536, 131072,
262144, 524288, 1048576, each z2z_1d/d2z_1d/z2d_1d (15 cases; no 32K).
Correctness remains enabled with the original strict <1e-9 checks. Preserve
initialization, inputs, 3 timing warmups, and 50 separately synchronized HIP
event measurements of rocfft_execute per process. Explicitly force 50 iterations.
Use original mean_ms; plan_ms, first_ms and per_tf_ms are diagnostics only.
No hipprof N+1 division or kernel subtraction applies to these event times.

Formal comparison: 8 rounds per case, one GPU UUID and one allocation;
odd official/previous/candidate/candidate/previous/official, even the reverse.
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
`/public/home/zhangkewei/zr/install-exp090-candidate`, source commit
`0473680e99b181e4660643425f53382f3a6afad7`. Measurement job: `856749`.
Raw files are the five `r1` through `r5` hipkernel CSVs for each length under:

    /public/home/zhangkewei/zr/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749/

The machine-readable and text summaries are:

    /public/home/zhangkewei/zr/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749.json
    /public/home/zhangkewei/zr/exp-078-sbrc-two-tier/results/exp091_batch1_baseline_856749.txt

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

The user approved this layout and synchronization policy on 2026-09-30 while
archiving historical worktrees. The old EXP-078 synchronization target is retired.

Keep the following operational instruction files identical:

- `/public/home/zhangkewei/zr/AGENTS.md`;
- `/public/home/zhangkewei/zr/exp-095-sbrc128k-only/AGENTS.md` (active stable worktree);
- `/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark/AGENTS.md` (active benchmark worktree).

The complete latest experiment record must remain synchronized between:

- `/public/home/zhangkewei/zr/VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md`;
- `/public/home/zhangkewei/zr/exp-123-cufft-format-benchmark/VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md`.

The active stable branch retains its validated-version experiment record. Do not
silently replace it with newer benchmark-only records or change its validated
source/tag when updating operational documentation. Historical archived copies,
including EXP-078, are immutable snapshots and are no longer synchronization targets.

Update the matching operational copies in the same task and verify they are
identical. See `WORKTREE_ARCHIVES.md` for active paths and archive recovery material.

## Git version maintenance requirements

Keep one stable branch containing only validated retained optimizations. Start each new optimization from it in a separate EXP-NNN branch, record the starting commit, and create a before-experiment tag when practical. Commit source changes together with VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md and AGENTS.md. Do not merge correctness failures or unaccepted regressions into the stable branch; retain their branch and record rollback. Merge only after correctness, benchmark, and required cross-size checks. Use immutable tags for the official baseline, pre-experiment stable states, and retained versions. Do not rewrite experiment history or delete failed records. Treat uncommitted changes as experimental, not a valid version.

## Current valid version

Stable branch: rocfft-opt-pre-tile-lifetime
Validated source commit: ed06208f30706f63126078a5c51af07fa0439fe7
Validated record commit: f5dc0ce6e0a759e4cbcdd60e02e14725f78f7cb1
Valid tag: stable-exp122-sbrc1024-20260929

## Agent Delegation and Token-Efficiency Policy

The user clarified that Info.md applies only when they explicitly request
sub-agents. Otherwise follow the applicable normal agent instructions. When
explicitly requested, read /public/home/zhangkewei/zr/Info.md.

## Historical experiment layout (approved 2026-09-30)

Historical scripts, patches, records, source and evidence are grouped under
`/public/home/zhangkewei/zr/experiments/EXP-NNN/`. Eight retired worktree snapshots
are under `/public/home/zhangkewei/zr/archives/worktrees/`, retaining their names.
Their original files and inactive Git markers are preserved; use the active
stable/EXP-123 paths for development. Historical scripts are not rewritten and
may require path adaptation before reuse. Consult `EXPERIMENT_LAYOUT.md` and the
approved migration map before restoring or rerunning historical work.

The EXP-078 top-level compatibility link preserves access to the fixed EXP-091
baseline. Do not remove it without checking current baseline users. Eight historical experimental build trees are now in `archives/builds/`;
their old absolute CMake paths are evidence, and reproduction requires rebuilding.
Four EXP-082/083 Git directories are now in `archives/repositories/`, retaining
their original names, refs and tracked states; known linked-worktree paths and,
with separate user confirmation, two object-store alternate paths were corrected.
The v2 repository's missing index is preserved and must not be repaired
automatically. Existing installation paths, the main build and runtime stay put.

Keep `EXPERIMENT_LAYOUT.md` and the current `WORKTREE_ARCHIVES.md` index identical
between top-level, active stable, and active EXP-123 copies. Preserve prior dated
archive records; append later migration/restore mappings rather than rewriting
historical evidence. This layout does not change measurement or source semantics.


## Persistent top-level organization (approved 2026-09-30, round 3)

The top level is a workspace containing nested source repositories, not the
rocFFT CMake source root. Keep source/configuration and the current stable,
EXP-123 and official paths intact. Common tools are in `tools/`; current job and
submission entries are in `jobs/`. Use `EXPERIMENT_LAYOUT.md` for entry paths.

Never write new validation data, tuning CSVs, profile output, helper executables
or job logs directly at the top level or next to a tool's source. Use results,
logs and build subdirectories, or an experiment's approved category directory.
New experiment worktrees belong under `worktrees/EXP-NNN`; build/install/cache
belong under `experiments/EXP-NNN/artifacts/`. These future rules do not move
existing protected source, installation, runtime, or baseline paths.

Run `python3 tools/check_top_level.py` to report unexpected top-level entries.
This check is read-only: it must never delete or move anything automatically.
Keep its allowlist consistent with user-approved exceptions and mappings.
The modified `validate_cc512k_output.bin` remains at its original path and state.
`gfx926_rocfft_solution_map.dat` remains as an explicit runtime configuration
exception. Ask the user about new dependencies, conflicts or unexplained states.

Historical scripts and evidence remain original. Environment-stale entry scripts
are archived rather than silently repaired. Do not enable them without verifying
their dependencies. Tool path adaptations do not change FFT parameters, accuracy
thresholds, canonical measurement rules or validated optimization source.
