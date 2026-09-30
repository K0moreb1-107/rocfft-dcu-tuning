# Experiment material layout (2026-09-30)

135 approved historical entries (92 files, 43 directories) were moved with original
names and content preserved. Four additional independent/linked Git directories
were discovered during preflight and explicitly deferred by the user.

## Current paths

| Location | Contents |
| --- | --- |
| `experiments/EXP-NNN/scripts/` | Historical Slurm, validation and analysis scripts; adapt paths when needed |
| `experiments/EXP-NNN/patches/` | Original patches |
| `experiments/EXP-NNN/records/` | Historical notes, hashes and operation logs |
| `experiments/EXP-NNN/source/` | Historical source files or source archive |
| `experiments/EXP-NNN/evidence/` | Original validation input/output |
| `experiments/EXP-NNN/artifacts/` | Historical experiment directories, kept whole |
| `archives/worktrees/<original-name>/` | Eight retired worktree snapshots |

Create only needed category directories. Historical script contents are not
rewritten. No historical experiment is promoted into stable by moving its files.

## Paths retained

Root Git metadata, official repository, active stable and EXP-123 paths are
unchanged. All 22 build/install/cache directories remain where they were.
In particular, current EXP-123 uses `exp122-A-install` and
`exp119-stage1-install-clean`; these paths are unchanged.

The four deferred Git directories are:

- `exp-082-sbcc1024-mixed-digit`;
- `exp-083-p2-precomputed-mix89`;
- `exp-083-p2-precomputed-mix89-v2`;
- `exp-083-p2-precomputed-mix89-worktree`.

EXP-082 and the EXP-083 linked worktree share Git administrative data. The v2
directory lacks a Git index and reports 35,124 deletion entries. Their original
Git states are preserved; investigate separately and ask the user before changes.

## Necessary compatibility

`exp-078-sbrc-two-tier` is one top-level compatibility link to
`archives/worktrees/exp-078-sbrc-two-tier`. This preserves the fixed EXP-091 raw
baseline and summaries at their known paths. All 22 baseline SHA256 values match.
Other migrated historical top-level paths are intentionally not recreated.

## Audit and recovery

Migration batch: `/public/home/zhangkewei/zr/.worktree-archives/layout-20260930`

`approved-exp-moves.csv` maps every old relative path to its new relative path.
`inventory.before.json`, `moves.jsonl`, preserved documentation/patches/index,
baseline checksums and the final completion record support review and restoration.
Original Git recovery material from the first archive phase remains at
`/public/home/zhangkewei/zr/.worktree-archives/20260930-113952`.

The first phase preserved original paths at that time; this second phase explicitly
migrates their physical locations with the user's approval. Preserve old dated
records and use this migration mapping to translate earlier recovery references.
Before restoring or moving anything further, check source/destination state and
confirm unclear dependencies with the user.
