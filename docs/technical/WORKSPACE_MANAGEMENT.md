# Managed rocFFT experiment tasks

Implemented 2026-10-03. This entry manages paths and task provenance; it does not
change or promote optimization source. Source branches remain an explicit choice.

## Locations

All paths below are relative to `/public/home/zhangkewei/zr`.

- `manage.py`: build, validate, measure and report; preview by default.
- `configs/installations.json`: historical installations and the currently
  approved official/previous identities. Names alone never establish validity.
- `configs/experiments/EXP-124.example.json`: template; replace IDs, source
  locations/commit and acceptance before use. No EXP-124 branch was created.
- `experiments/EXP-NNN/artifacts/{build,install,cache}/`: independent artifacts.
- `experiments/EXP-NNN/runs/<run-id>/`: frozen configuration, raw process CSVs,
  logs, provenance, status and reports together.
- `results/historical/legacy-root/`, `logs/historical/legacy-root/`: historical
  loose originals, retaining their names, bytes and measurement definitions.

Keep original archived input immutable. New diagnostic plots use a separate
output directory. Main `build/{rocfft_build,hipfft_build,tools}` and `install`
remain paired legacy development paths; they are not the latest stable default.

## Workflow

First prepare an experiment configuration from the template. Start optimization
source from the current validated stable state in an EXP branch, record its exact
commit, and set `build.source_repo`, `build.source_dir`, `build.source_commit`,
`build.build_id` and a unique `run_id`. The manager never changes the checkout.
Source may be an explicit worktree or a branch in the existing checkout. A build
requires a committed clean source subtree at the configured HEAD.

```bash
python3 manage.py build --config configs/experiments/EXP-124.json
python3 manage.py build --config configs/experiments/EXP-124.json --execute
```

The first command previews. `--execute` submits a one-node Slurm task with logs
prepared beforehand, freezes the submitted configuration, and uses independent
build/install/cache paths. It does not overwrite an existing build or run.
rocFFT builds check the RTC generator target before the full build. Compiler,
resolved CMake cache including GPU_TARGETS/AMDGPU_TARGETS, Git state, compile
commands and final library hash are retained. Dependencies and compiler paths
are explicit; the worker does not source ambient shell initialization.

Successful builds write `build-provenance.json` and `candidate-arm.json` in their
run directory. In a new configuration for validation/measurement, point
`arms.candidate.build_record` at this completed record and choose a **new run_id**.
Do not use the build run identifier again. Official and previous registry entries
resolve to frozen identities; historical/unclassified entries cannot supply those
roles. Review the source/library correspondence before formal measurement.

```bash
python3 manage.py validate --config configs/experiments/EXP-124-check.json
python3 manage.py validate --config configs/experiments/EXP-124-check.json --execute
python3 manage.py measure --config configs/experiments/EXP-124-formal.json
python3 manage.py measure --config configs/experiments/EXP-124-formal.json --execute
python3 manage.py report --config configs/experiments/EXP-124-formal.json --execute
```

Validation is a 15-case candidate quick correctness check using the original
frozen program, strict original error checks and 50 events; it is not formal
promotion evidence. Formal measure calls the existing 720-process three-arm
8-round program. Report calls the existing strict aggregator, requires complete
evidence, and includes previous/official speedups and fixed A100 Performance.
Reporting can also be repeated directly with `tools/fft_measurement/summarize.py`
against the completed run directory. No task automatically promotes source.

`jobs/measure_fft.slurm` is now a compatibility **submission helper**, invoked as
`bash jobs/measure_fft.slurm CONFIG.json`, not `sbatch jobs/measure_fft.slurm`.
It forwards to the manager and submits `jobs/workspace_task.slurm`. Prefer the
manager commands above. Old hipprof/PMC and auxiliary tools retain their separate
diagnostic purposes; `tune_all.py` is retired. Enumeration helpers remain.

## Reuse and failures

Output paths are confined to zr. Preview performs read-only validation and does
not create output directories. Run/build IDs reject existing artifacts, including
incomplete failed runs. Submission failure, compiler failure and partial correctness
evidence remain available under that run; investigate and choose a fresh identifier
for a subsequent attempt. A submitted configuration is frozen before queueing.

Only the first matching worker may claim a run. Existing execution evidence or
a mismatched reservation causes rejection. Formal aggregation still requires all
15 cases, correct order, all 16 process means per arm/case, valid hashes and one
GPU/allocation identity. Do not delete failed evidence or substitute quick checks.

Actual compiler/runtime/GPU integration was **not run** during this organization
task. The first authorized new experiment must verify real compilation, linked
library identity, GPU/runtime identity and correctness. No outside-zr files were
read to infer compiler behavior during implementation; compiler configuration came
from existing build records. Do not enable old stale environment scripts casually.

## Historical recovery

Migration/deletion audit: `.worktree-archives/artifact-management-20261003/`.
The 10 cleaned build trees have preserved source/configuration records under
`experiments/EXP-NNN/records/builds/<old-name>/`; see their provenance archives
and pre-cleanup file manifests. Removed generated payload requires rebuilding.
The other 7 old build/helper directories remain original snapshots. No installed
library was deleted. Four old install links and the EXP-078 baseline link remain.
Eight preexisting EXP-081 FFTW stale links remain recorded, not silently repaired.
