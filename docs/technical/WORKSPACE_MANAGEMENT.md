# Managed rocFFT experiment tasks

Current path status (2026-10-03): the five former top-level aliases are retired;
their real directories remain. Top-level entries: 36. Adaptation guide:
[LEGACY_PATH_ADAPTATION.md](LEGACY_PATH_ADAPTATION.md); old program adaptation is deferred.

Current status after integration (2026-10-03): the sole primary checkout is
`/public/home/zhangkewei/zr`, on `main`; stable tag
`stable-main-exp123-20261003`. Use serial EXP-NNN branches in this checkout.
Temporary worktrees require explicit user agreement. Earlier dated sections
record prior states and are superseded by the final main/branch section.


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
source from top-level main in an EXP branch, record its exact
commit, and set `build.source_repo`, `build.source_dir`, `build.source_commit`,
`build.build_id` and a unique `run_id`. The manager never changes the checkout.
Use an EXP-NNN branch in the top-level checkout by default. A temporary
worktree requires explicit user agreement for concurrent source development. A build
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
