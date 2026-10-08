# FFT measurement protocol (approved 2026-09-30)

Current path status (2026-10-03): the five former top-level aliases are retired;
their real directories remain. Top-level entries: 36. Adaptation guide:
[LEGACY_PATH_ADAPTATION.md](LEGACY_PATH_ADAPTATION.md); old program adaptation is deferred.

Current status after integration (2026-10-03): the sole primary checkout is
`/public/home/zhangkewei/zr`, on `main`; stable tag
`stable-main-exp123-20261003`. Use serial EXP-NNN branches in this checkout.
Temporary worktrees require explicit user agreement. Earlier dated sections
record prior states and are superseded by the final main/branch section.


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
`/public/home/zhangkewei/zr/experiments/EXP-096/artifacts/install/install-exp096-official`, library SHA256
`3a8f9b03c069b3ff6c3a2ff93d4a90028ad1c248c01c6db34f99a4d84038cea5`.
Previous is the immediately preceding valid stable source/install, preregistered
per experiment; it advances with stable promotion. Current stable checkout is top-level main (stable-main-exp123-20261003),
retaining the exact EXP-123 source; the prior immutable EXP-123 tag remains.
Its retained kernel semantics match validated EXP-122
`ed06208f30706f63126078a5c51af07fa0439fe7`; the approved existing previous
library retains that actual build identity. Do not hardcode EXP-119.
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

Shared root entries are used from EXP branches in the sole top-level checkout:

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


## 2026-10-03 management integration (paths only)

Use `python3 manage.py measure --config CONFIG.json` to preview, and append
`--execute` to submit one frozen-config GPU task. Use `bash jobs/measure_fft.slurm
CONFIG.json` only as a compatibility submission helper, not an sbatch job body.
The manager creates the run/log directory before submission and reserves it for
that exact preregistration. Matching workers claim it once; reused IDs, changed
reservations and existing execution evidence are rejected.

All process evidence, compile/Slurm logs, preregistration, plan, provenance and
reports are grouped under `experiments/EXP-NNN/runs/<run-id>/`. Measurement
executables use `experiments/EXP-NNN/artifacts/build/measurement/<run-id>/`;
temporary files use its `artifacts/cache/<run-id>/`. Original historical runs
retain their old structure. The dated paths here supersede earlier output-location
examples only; timing, correctness, sample counts, order and A100 definitions
above remain unchanged. Shared run.py/summarize.py implement the same contract.

`manage.py validate` is a candidate-only 15-case quick correctness task, not the
three-arm formal comparison or promotion evidence. Actual compilation/GPU
integration was not exercised by the organization task and must be verified
in the first authorized experiment. See WORKSPACE_MANAGEMENT.md.


## EXP-123 stable promotion (user approved 2026-10-03)

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


## EXP-122 prior-stable worktree retired (2026-10-03)

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


## Top-level main and branch workflow (implemented 2026-10-03)

The sole active primary checkout is /public/home/zhangkewei/zr, on main. It retains the
exact EXP-123 rocFFT source (27b00f0ba82235b4331d24acc953989bb980da97) and the existing shared management tools.
Old main's fusion history is preserved in archive/main-before-exp123-20261003,
immutable archive tags and merge ancestry; its unaccepted code is not part of
the stable tree. The new stable tag is stable-main-exp123-20261003; prior tags never move.

Both former active worktrees are now historical snapshots in archives/worktrees/:
exp-095-sbrc128k-only and exp-123-cufft-format-benchmark. Their original files,
ignored measurement evidence and inactive .git markers are preserved. Do not
run Git in snapshots or treat their old build paths as current defaults.
Root/EXP-123 synchronization is retired; root documents are authoritative.

Start new experiments from main in an EXP-NNN branch in the same top-level
directory. Wait for queued/building/running tasks to finish and save changes
before switching branches. Temporary worktrees require explicit user agreement.
Artifacts and run evidence keep their independent per-experiment locations.
The existing installed previous library remains the actual EXP-122 build with
its original source commit/checksum; a source merge never rebuilds a library.

Imported historical scripts/results are grouped below experiments/EXP-NNN,
not restored to the top level. The original EXP-123 harness is preserved under
experiments/EXP-123/source/exp123_rocfft_csv; primary measurements still use
the unchanged frozen tools/fft_measurement/fft_test_1d.cpp.
The old-main experiment record is restored by number with explicit historical
source/old-number labels; EXP-029's missing independent record is disclosed.

Recovery/audit: .worktree-archives/top-level-main-integration-20261003/.
This integration performs static and synthetic checks only. Actual compilation
and GPU/runtime verification remain required at the first new experiment.


## Five top-level compatibility links retired (2026-10-03)

The user approved removal of the EXP-078, EXP-119, EXP-122, EXP-090 and official
EXP-096 top-level symbolic links. Their physical archive/install directories and
all original evidence remain intact. The current top-level entry count is 36.
Use the physical paths in configs/installations.json and the mapping below.
Earlier dated statements about preserving these aliases describe former states.

| Former absolute path | Current physical path |
| --- | --- |
| `/public/home/zhangkewei/zr/exp-078-sbrc-two-tier` | `/public/home/zhangkewei/zr/archives/worktrees/exp-078-sbrc-two-tier` |
| `/public/home/zhangkewei/zr/exp119-stage1-install-clean` | `/public/home/zhangkewei/zr/experiments/EXP-119/artifacts/install/exp119-stage1-install-clean` |
| `/public/home/zhangkewei/zr/exp122-A-install` | `/public/home/zhangkewei/zr/experiments/EXP-122/artifacts/install/exp122-A-install` |
| `/public/home/zhangkewei/zr/install-exp090-candidate` | `/public/home/zhangkewei/zr/experiments/EXP-090/artifacts/install/install-exp090-candidate` |
| `/public/home/zhangkewei/zr/install-exp096-official` | `/public/home/zhangkewei/zr/experiments/EXP-096/artifacts/install/install-exp096-official` |

Historical source, scripts, binaries, CSV/JSON metadata and experiment records
remain original; they may still contain the former paths. The known four old
EXP-123 binaries have absolute RUNPATH dependencies, and the old submission
scripts also set LD_PRELOAD/LD_LIBRARY_PATH to the former installations.
No old program was adapted, rebuilt or executed in this task. When reuse is
requested, follow docs/technical/LEGACY_PATH_ADAPTATION.md; do not recreate
top-level aliases automatically or treat historical times as new event results.

Current official/previous registry IDs remain unchanged and resolve directly
to physical installation directories. Measurement definitions and source are
unchanged. Audit: .worktree-archives/top-level-compatibility-retirement-20261003/.
