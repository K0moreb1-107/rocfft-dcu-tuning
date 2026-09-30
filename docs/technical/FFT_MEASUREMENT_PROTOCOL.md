# FFT measurement protocol (approved 2026-09-30)

This is the primary contract for future rocFFT optimization measurements in
`/public/home/zhangkewei/zr`. Source: the user's specified conversation
`codex://threads/01a0e6cd-9ded-7570-93df-5a5a0ca88255`, EXP-123's final event table.
The user confirmed the NVIDIA reference is **A100**. This policy does not relabel
the mixed historical single-run/outlier-retest table as a new formal baseline.

## Fixed program and timing

The shared source is `tools/fft_measurement/fft_test_1d.cpp`, an exact original
copy, SHA256 `849d011336601e6cffb1959e89590847e26160f7b3e256482a5eb37289e333da`.
Original EXP-123 source, 18-case driver, retest scripts and data stay unchanged.
Double precision, batch=1, out-of-place, correctness enabled; select 65536,
131072, 262144, 524288 and 1048576 for z2z_1d, d2z_1d and z2d_1d: 15 cases.
No 32K in new default reports.

Each fresh process uses the original setup, correctness and input pattern,
three unrecorded warmup executions, and 50 separately synchronized HIP-event
measurements enclosing rocfft_execute. FFT_TEST_ITERS is explicitly 50, not an
inherited default; CLI `N 1 func 1` never supplies nocheck. is_warmup=1 is a
recorded flag; original code always warms up three times. Correctness retains
the original strict error <1e-9 checks, with -1 err_b sentinel on real transforms.

The steady mean excludes allocation, input copies, correctness and host plan
setup outside the event windows. No kernel subtraction or hipprof N+1 division
applies. Twiddle inclusion is not independently instrumented, so do not claim
equivalence to old hipprof totals. plan_ms and first_ms are diagnostics;
first_ms occurs before correctness-input initialization in the frozen source.
per_tf_ms is original min_ms/batch, not the mean. Original code does not save
each of the 50 event samples: save each process's original 14-column CSV,
min/mean/max and logs; all 50 events participate in its mean.

## Formal ordering and aggregation

ABBA means run A, B, B, A to reduce bias from time drift. The approved formal
protocol uses three arms in one GPU allocation, on one HIP-visible GPU UUID:

- Odd rounds: official, previous, candidate, candidate, previous, official.
- Even rounds: candidate, previous, official, official, previous, candidate.

Run eight rounds for each of 15 cases, sequentially, with fresh processes.
Each arm has 16 process means / 800 events per case; total **720 processes**.
Every pair projects to ABBA or BAAB. Use the arithmetic mean of all 16 mean_ms
values, without outlier removal. Median, standard deviation, minimum and maximum
are diagnostics. A single process with 50 measurements is a quick check only;
it cannot be used as formal promotion evidence.

The runtime records and checks allocation, node, HIP UUID/architecture/runtime,
source commits and tracked status, compiler command/version, executable hash,
actual loaded rocFFT path/hash, condition flags and chronological schedule.
The device identity helper is separate from the unchanged timing program and
queries HIP device 0 under the same visibility environment. It refuses missing
UUID or multiple visible GPUs. API reference: [HIP initialization/device UUID](https://rocm.docs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/initialization_and_version.html),
[ROCm 7.2.2 header](https://github.com/ROCm/HIP/blob/rocm-7.2.2/include/hip/hip_runtime_api.h).
This task validates scheduling/aggregation without compiling or executing HIP;
helper and frozen harness compilation remain checks in the first authorized GPU run.

Like the original retest, compile one harness against the official ABI and
preload each arm's exact library, checking loader resolution and hashes.
Disable RTC cache reads/writes and use separate process TMPDIRs. This is not
proof that every event sees a cold GPU cache. Do not run profiling concurrently.
Any new dependency, conflict or unexplained state must be raised to the user.

## Three comparisons

Official is original ROCm 7.2.2 source
`dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef`, installation
`/public/home/zhangkewei/zr/install-exp096-official`, library SHA256
`3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5`.
Previous is the immediately preceding valid stable source/install, preregistered
per experiment; it advances with stable promotion. Current validated source is
EXP-122 `ed06208f30706f63126078a5c51af07fa0439fe7`; do not hardcode EXP-119.
Candidate also needs explicit source/build provenance and exact library hash.
Git commit existence and library hash do not themselves prove build origin;
preserve the build record connecting them and disclose dirty-source status.

Report official_mean_ms, previous_mean_ms and candidate_mean_ms, plus:

```
speedup_previous = previous_mean_ms / candidate_mean_ms
speedup_official = official_mean_ms / candidate_mean_ms
A100 Performance (%) = a100_mean_ms / candidate_mean_ms * 100
```

One candidate mean underlies all three ratios. Performance >100% means the
candidate is faster than this A100 reference. This is a fixed cross-hardware
reference, not a same-allocation control. Conditions/case matching must be exact.
No fabricated zero or rounded-table reconstruction for missing references.

The full authorized original 18-row CSV is versioned at
`results/reference/a100/A100_1d_32768_65536_131072_262144_524288_1048576.csv`,
1835 bytes, SHA256
`3b376eb69a77318ace8fbe537acfc7b3e82cdff1ea847f6177ed7ea82b27603b`.
Only its matching 15 rows are selected in future reports. Provenance is alongside
the raw file. The original local file is unchanged.

## Entry points and preregistration

Shared root entries are used from all active worktrees:

```
python3 tools/fft_measurement/run.py experiments/EXP-NNN/measurement.json
# Default: validate preregistration and print 720-process plan; no GPU calls.
mkdir -p logs/fft_measurement
sbatch jobs/measure_fft.slurm /public/home/zhangkewei/zr/experiments/EXP-NNN/measurement.json
# Submit only when the experiment and GPU execution have been authorized.
python3 tools/fft_measurement/summarize.py results/fft_measurement/<run_id>
```

Copy `tools/fft_measurement/manifest.example.json` to the experiment directory,
replace placeholders, and preregister acceptance criteria before any run. Record
an experiment-specific minimum improvement/cross-size regression rule or other
explicit criteria; this policy imposes no new universal 2%/1% thresholds and
does not transfer old hipprof thresholds. An example intentionally cannot run
until candidate and criteria are filled in. Previous/candidate source_state and
build_provenance must be explicit. A report does not automatically promote code.

Outputs: results/fft_measurement/<run_id> holds preregistration, plan, provenance,
all process CSV/log hashes and comparison.csv/md/summary.json; compilation logs
go to logs/fft_measurement/<run_id>, binaries/private temporary directories to
build/fft_measurement/<run_id>. Duplicate run IDs refuse overwrites. Partial
failures retain evidence, but cannot aggregate as formal results.

The old hipprof batch=1 and batch=1000 definitions/files remain historical or
diagnostic, interpreted with their original divisors and exclusions. Keep all
26 fixed baseline evidence files unchanged. Do not mix them with event means
in the same numerator/denominator or silently revise historical percentages.
