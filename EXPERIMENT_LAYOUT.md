# Current experiment and top-level layout

Updated 2026-10-03. Historical rounds 1-3 are retained below; current unified
management is specified in the dated section at the end.
The second material phase moved 135 entries; round 3 moved another 183 entries
(169 files, 14 directories), leaving 59 top-level entries including exceptions.

| Location | Contents |
| --- | --- |
| `tools/` | Common Python/shell tools and helper C++ source |
| `jobs/` | Current submission and Slurm entries |
| `build/tools/bin/` | Helper executable originals and future compiled helpers |
| `docs/technical/` | Technical notes, environment records and page originals |
| `experiments/EXP-NNN/{scripts,patches,source,records,evidence,artifacts}/` | Numbered historical material |
| `archives/unclassified/` | Unnumbered historical originals by purpose |
| `archives/worktrees/` | Eight retired worktree snapshots from the first phase |
| `archives/builds/` | Eight old experimental build trees, requiring rebuild before reuse |
| `archives/repositories/` | Four historical EXP-082/083 Git directories |

## Current entry paths

- Build submission: `bash jobs/submit_build.sh`; direct job: `sbatch jobs/build.slurm`.
- Benchmarks: `sbatch jobs/job.slurm`, `sbatch jobs/job_bank.slurm`, `sbatch jobs/run_bench.sh`.
- Enumeration: `python3 tools/enumerate_configs.py` or `sbatch jobs/submit_enum.sh`.
- Retired tuning: `tune_all.py` removed 2026-10-03; historical progress and profiles retained.
- Device information: `sbatch jobs/query_device.slurm`.
- Validation: `sbatch jobs/validate_cc512k.slurm`; or
  `sbatch jobs/validate_cc_length.slurm <length>`.
- Static analysis: `python3 tools/partial_pass_tile_ownership.py`.
- Read-only directory check: `python3 tools/check_top_level.py --json`.

These commands are documented entry locations, not a claim of new GPU runtime
validation. This organization task did not build, profile, run FFTs or submit jobs.
Existing external environment references in current jobs are unchanged.

## Output and progress

Validation data go under `results/validation/<task>/<run-id>/`.
Bench/runall/runbank output goes under its named results subdirectory and run ID.
Enumeration and tuning progress go under `results/enumeration/` and
`results/tuning/`. On first use, the tools can copy archived original progress
CSVs into the new active location without editing the historical original.
Tuning profiles go under `results/tuning/profiles/`.
Job logs go under `logs/jobs/<entry>/`; the directories are prepared before any
Slurm submission so stdout/stderr creation does not depend on the job body.

Future experiment worktrees use `worktrees/EXP-NNN/`. Future experiment-specific
build/install/cache trees use `experiments/EXP-NNN/artifacts/`. Existing protected
source, installation, runtime, baseline and active worktree paths remain unchanged.

## Historical exceptions

Environment-stale `run_tuning.slurm`, `rebuild_rocfft.sh`, `test_prof.slurm` and
associated old-log analysis entries are archived as originals. Adapt them only
after verifying the environment. Historical entry paths are translated through
the dated migration maps; they are not all restored through top-level symlinks.

`exp-078-sbrc-two-tier` remains the sole compatibility link for fixed EXP-091
evidence. Both batch=1 and legacy fixed-baseline raw file hashes were checked.
`validate_cc512k_output.bin` retains its original uncommitted modification.
`gfx926_rocfft_solution_map.dat` remains an explicit runtime configuration exception.

EXP-082's archived repository and EXP-083 linked worktree retain their relationship
at their new paths. After pausing and obtaining separate user confirmation, two
EXP-083 object-store alternate references were backed up and corrected to the
archived EXP-082 object store; original HEADs, refs, status and indices were checked.
The v2 repository's index remains missing and its 35,124
deletion-status entries remain unexplained; no index recovery or deletion commit
was performed. Moving preserves these histories, not a claim of complete source
or object-database validation. Do not develop in retired snapshots by accident.

## Recovery and ongoing rules

Round 3 audit: `.worktree-archives/top-level-20260930/` with approved mapping,
original scripts/docs/index/patches, before-state hashes and completion record.
Prior audits remain `.worktree-archives/20260930-113952/` and
`.worktree-archives/layout-20260930/`. Their dated records are preserved.
Operational instructions/indexes are synchronized across root, stable and EXP123.
Latest full records remain synchronized root/EXP123; stable's validated record
stays intact. A read-only allowlist check reports newly scattered entries; it
never moves or deletes files automatically. Ask the user about new uncertainties.

## Primary measurement entry points (approved 2026-09-30)

- `tools/fft_measurement/run.py`: validate preregistration and show the 720-process
  plan by default; `--execute` is reserved for an authorized one-GPU Slurm job.
- `tools/fft_measurement/summarize.py`: strict formal 15-case report including
  previous/official speedups and fixed A100 Performance.
- `jobs/measure_fft.slurm`: formal three-arm, 8-round event-measurement entry.
- `docs/technical/FFT_MEASUREMENT_PROTOCOL.md`: full timing/correctness/report
  contract, synchronized with active stable and EXP-123 operational copies.
- `results/reference/a100/`: versioned original reference CSV and provenance.

Use the root shared tools from all active worktrees. Measurement output and logs belong together under
`experiments/EXP-NNN/runs/<run-id>/`; binaries and temporary directories use the
matching `artifacts/build/measurement/<run-id>` and `artifacts/cache/<run-id>`.
No top-level outputs. Prefer manage.py; jobs/measure_fft.slurm is a bash submission helper.
Existing runall/hipprof profiling entries retain their historical or diagnostic
purpose; their old metric is not the new primary event metric. Original EXP-123
18-case programs/data remain historical evidence. New defaults omit 32K.


## Unified artifacts and task management (approved 2026-10-02; implemented 2026-10-03)

This dated policy supersedes the previous installation-preservation and output
path exceptions only for the approved migration. Source worktrees, official
repository, validated optimization source/tag and measurement definitions stay
unchanged. See docs/technical/WORKSPACE_MANAGEMENT.md for commands and recovery.

Use manage.py with an explicit independent experiment configuration under
configs/experiments/. Default is read-only preview; --execute submits the task
or generates the requested report. The manager never changes source checkouts.
New optimization still starts from the current valid stable source in an EXP
branch. Source integration into the top checkout is a separate task.

New build/install/cache belong to experiments/EXP-NNN/artifacts/ with unique IDs.
Run CSVs, stdout/stderr, configuration, provenance and reports belong together
under experiments/EXP-NNN/runs/<run-id>/; helper binaries remain artifacts.
Formal measurement retains the exact frozen CPP, 15 cases, 3 warmups/50 events,
8-round three-arm ordering, 720 processes and fixed A100 reference/formulas.
Queued configurations freeze concrete library/source identities, not mutable
aliases. No automatic source promotion. Quick validation is not formal evidence.

Current installation registry: configs/installations.json. Current previous
is the approved EXP-122 library; EXP-119 remains historical. Directory names do
not prove source identity or acceptance. Historical/unknown installations cannot
silently become official/previous/candidate. Candidate builds retain exact source
state, CMake parameters, compiler and final library checksum.

Main build/rocfft_build, build/hipfft_build, build/tools and install remain paired
legacy development locations. Four compatibility links remain at
install-exp096-official, exp122-A-install, exp119-stage1-install-clean and
install-exp090-candidate. Keep the EXP-078 and fixed raw-baseline paths intact.
The top-level count is now 43, subject to the explicit allowlist.

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
user modifications and historical refs. Operational documents stay synchronized
across root, stable and EXP-123; latest full records stay root/EXP-123 synchronized.
