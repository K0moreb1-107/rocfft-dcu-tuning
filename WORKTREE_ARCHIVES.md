# Current worktree paths and historical snapshots

Updated 2026-09-30 after the user-approved top-level material migration.

The optimization repository has three registered worktrees: root,
`exp-095-sbrc128k-only` (prior stable), and `exp-123-cufft-format-benchmark` (current stable).
`official-rocm722-source` is the separate official checkout. Four additional
EXP-082/083 Git directories are now historical archives under `archives/repositories/`;
this count describes the primary optimization repository, not all nested repositories.

## Retired snapshot locations

| Original top-level name | Current physical location |
| --- | --- |
| `exp-078-sbrc-two-tier` | `archives/worktrees/exp-078-sbrc-two-tier` |
| `exp-079-sbrc-stage-aware` | `archives/worktrees/exp-079-sbrc-stage-aware` |
| `exp-085-auto-communication-classification` | `archives/worktrees/exp-085-auto-communication-classification` |
| `exp-119-lds-aware-block-planner` | `archives/worktrees/exp-119-lds-aware-block-planner` |
| `exp-120-sbrc1024-cc` | `archives/worktrees/exp-120-sbrc1024-cc` |
| `exp-121-sbrc1024-callback-aware` | `archives/worktrees/exp-121-sbrc1024-callback-aware` |
| `exp-122-simple-sbrc1024` | `archives/worktrees/exp-122-simple-sbrc1024` |
| `exp077-early-lut` | `archives/worktrees/exp077-early-lut` |

Original snapshot files, inactive `.git` pointers and archive notes are unchanged.
Do not run Git in those retired snapshots. The EXP-078 compatibility link keeps
fixed baseline paths accessible. EXP-079's uncommitted generator files and patches
remain preserved; its files now reside in the corresponding archived snapshot.

Recovery batch for original Git administration/patches:
`/public/home/zhangkewei/zr/.worktree-archives/20260930-113952`.

New physical-path migration map and original documentation snapshots:
`/public/home/zhangkewei/zr/.worktree-archives/layout-20260930`.

See `EXPERIMENT_LAYOUT.md` for layout, exceptions, necessary compatibility and
restoration cautions. Prior archive records remain historical evidence, while
this index describes current physical locations. Source changes were not merged.


## Additional historical Git directories (round 3)

| Original top-level name | Current path |
| --- | --- |
| `exp-082-sbcc1024-mixed-digit` | `archives/repositories/exp-082-sbcc1024-mixed-digit` |
| `exp-083-p2-precomputed-mix89` | `archives/repositories/exp-083-p2-precomputed-mix89` |
| `exp-083-p2-precomputed-mix89-v2` | `archives/repositories/exp-083-p2-precomputed-mix89-v2` |
| `exp-083-p2-precomputed-mix89-worktree` | `archives/repositories/exp-083-p2-precomputed-mix89-worktree` |

The EXP-082 repository and linked EXP-083 worktree retain corrected administrative
links. Two EXP-083 object-store alternate references were backed up and corrected
after separate user confirmation. References, original indices and tracked-status
conditions are preserved.
The v2 missing index is intentionally unchanged. No experimental source was
merged or index repaired. The primary repository still has its same three
registered worktree paths; official remains separate at its original location.
Round 3 audit and old/new path map: `.worktree-archives/top-level-20260930/`.
See `EXPERIMENT_LAYOUT.md` for tool/job locations and protected exceptions.


## 2026-10-03 artifacts and output organization

Approved plan executed after the user's explicit resume instruction. Active Git
worktree/source paths and validated tags were not moved or merged. 1,589 loose
files and 29 directories were grouped. Main build/install and four necessary
install compatibility links remain. Ten invalid build payloads were cleared
after preserving their metadata/generated text source records; seven other
build/helper snapshots are retained. tune_all.py is retired.

Audit: .worktree-archives/artifact-management-20261003/ (actions.json,
move-before.json, move-journal.jsonl, migration-complete.json, cleanup-journal.jsonl,
cleanup-complete.json, originals and git-before). Original source/data names and
checksums remain recorded. Cleaned build provenance archives are under the
corresponding experiments/EXP-NNN/records/builds/<old-name>/.

Earlier dated archives, repository relationships, missing-index v2 state and
eight archived build trees remain unchanged. Eight stale FFTW links remain as
original historical state. See docs/technical/WORKSPACE_MANAGEMENT.md.


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
