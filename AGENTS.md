# Remote rocFFT optimization measurement contract

This file is authoritative for all subsequent rocFFT optimization experiments
in /public/home/zhangkewei/zr. Do not change the measurement definition without
recording the reason and updating this file first.

## Scope and matching conditions

Compare only runs with the same FFT length, transform type, precision, batch
size, -N value, profiling command, GPU, and relevant runtime environment.
The primary latency workload is double-precision z2z, out-of-place,
batch=1, `-N 10000`, using the same DCU and `hipprof --stats`. Collect five
independent processes per length and use the median canonical time as the
fixed-baseline summary while retaining every round, mean, standard deviation,
and CV. Candidate acceptance still requires an interleaved stable/candidate
comparison in the same GPU allocation because independent-process drift is
measurable. The target lengths are 64K, 128K, 256K, and 512K. Do not
substitute 102400 for any of these sizes.

The legacy throughput comparison remains double-precision z2z, batch=1000,
`-N 10`, on the same DCU with `hipprof --stats`. Never compare its absolute
times with the batch=1 baseline or divide it by 1000 as a substitute.

## Batch=1 primary-workload transition (EXP-091)

The user clarified on 2026-09-22 that batch=1000 was chosen only as a way to
reduce measurement noise; it is not an application requirement.  Actual use
and evaluation may use batch=1.  Therefore, do not design or promote an
optimization whose benefit depends on scheduling multiple user transforms in
one batch.  In particular, batch strip-mining is only a diagnostic and is not
a primary optimization direction.

EXP-091 calibrated the repetition count (`-N`) and established the separate
batch=1 baseline below. Every batch=1 result must record its own `-N` and use
exactly its own `N+1` divisor. Increasing `-N` also amortizes fixed per-process
twiddle-generation kernels, so report transform-only timing as a diagnostic
when explaining differences across N; keep the canonical metric for the
contract result.

rocFFT's internal `transforms_per_block` is not the user batch size.  A kernel
mapping change such as four versus eight internal transforms per workgroup can
still be batch-independent, but it must be validated with user batch=1.

## Fixed batch=1 baseline result files (EXP-091)

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

## Fixed legacy batch=1000 baseline result files

Unless a new baseline is explicitly declared and recorded, use these files
as the baseline for double-precision z2z, batch=1000, -N 10 comparisons:

    /public/home/zhangkewei/zr/results/z2z_64k_official_7.2.2_20260831_172537.csv.hipkernel.csv
    /public/home/zhangkewei/zr/results/z2z_128k_official_7.2.2_20260831_172537.csv.hipkernel.csv
    /public/home/zhangkewei/zr/results/z2z_256k_official_7.2.2_20260831_172537.csv.hipkernel.csv
    /public/home/zhangkewei/zr/results/z2z_512k_official_7.2.2_20260831_172537.csv.hipkernel.csv

Select the baseline matching the exact FFT length. Do not compare a result
against a baseline from another length or transform type.

## Canonical time extracted from hipprof CSV

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

## Excluding rocfft-bench overhead

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

Record the exact current git commit, source change, job IDs, correctness
result, benchmark result file, canonical T_compute_ms, previous-version
time/speedup/improvement, and baseline time/speedup/improvement. Preserve the
raw CSV and logs. If a kernel is reclassified as bench-only, record the proof
and update the exclusion list before recalculating historical comparisons.

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

The following tracked repository documents and their top-level copies must remain
synchronized:

- `/public/home/zhangkewei/zr/exp-078-sbrc-two-tier/AGENTS.md` and
  `/public/home/zhangkewei/zr/AGENTS.md`;
- `/public/home/zhangkewei/zr/exp-078-sbrc-two-tier/VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md`
  and `/public/home/zhangkewei/zr/VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md`.

Whenever either repository document is updated, update its top-level copy in the
same task and verify that the corresponding files are identical before completing
the change. Do not leave either copy with newer experiment state, evidence, or
instructions than the other.

## Git version maintenance requirements

Keep one stable branch containing only validated retained optimizations. Start each new optimization from it in a separate EXP-NNN branch, record the starting commit, and create a before-experiment tag when practical. Commit source changes together with VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md and AGENTS.md. Do not merge correctness failures or unaccepted regressions into the stable branch; retain their branch and record rollback. Merge only after correctness, benchmark, and required cross-size checks. Use immutable tags for the official baseline, pre-experiment stable states, and retained versions. Do not rewrite experiment history or delete failed records. Treat uncommitted changes as experimental, not a valid version.

## Current valid version

Stable branch: rocfft-opt-pre-tile-lifetime
Validated source commit: 0473680e99b181e4660643425f53382f3a6afad7
Validated record commit: 1ab8786cbe63d2f50b7f73d7a519306aabc0c77a
Valid tag: stable-exp092-gfx936-capability-gate-20260923
