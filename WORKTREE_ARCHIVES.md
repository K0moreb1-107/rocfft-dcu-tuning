# Worktree layout and historical archives

Approved by the user on 2026-09-30: reduce active worktrees, retain all historical
branches/tags, preserve original evidence/file paths, and use EXP-123 for the complete
latest experiment record while retaining the stable validated-version record.

## Active checkouts

| Path below `/public/home/zhangkewei/zr` | Role |
| --- | --- |
| `.` | Main repository, shared Git metadata, historical artifacts; preserve existing changes |
| `official-rocm722-source` | Separate official repository, detached upstream baseline `dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef` |
| `exp-095-sbrc128k-only` | Active stable branch `rocfft-opt-pre-tile-lifetime`; retained EXP-122 source |
| `exp-123-cufft-format-benchmark` | Active benchmark harness and paired outlier-retest branch |

There are three registered worktrees in the optimization repository plus the
separate official checkout. Installation directories, including `install-exp096-official`,
`exp122-A-install`, and `exp119-stage1-install-clean`, are preserved.

## In-place historical snapshots

The following eight directories remain at their original paths with **all original
tracked, untracked and ignored files**. Their active Git registrations have been
removed. Each has `WORKTREE_ARCHIVED.md` with its historical branch, HEAD and
recovery-material location. Original `.git` pointers are retained as inactive
historical markers; do not run Git commands in these directories.

| Directory | Historical branch | Historical HEAD |
| --- | --- | --- |
| `exp-078-sbrc-two-tier` | `exp-114-official-dyna-diagnostic` | `6f5ed9657823c3382243b83f4e0954d3afd8fcb5` |
| `exp-079-sbrc-stage-aware` | `exp-084-sbrc-scalar-lds-swizzle` | `f9755e4f36706cf372f7b22c44470431263293d1` |
| `exp-085-auto-communication-classification` | `exp-085-auto-communication-classification` | `4e1495d93a5c518f616f116b810fb3f298d64781` |
| `exp-119-lds-aware-block-planner` | `exp-119-lds-aware-block-planner` | `ed9343e510bf4b9f199fa748609311b879f65c3e` |
| `exp-120-sbrc1024-cc` | `exp-120-sbrc1024-cc` | `1642eb6383e0a4615dee46ac3cef4cec8e1f425c` |
| `exp-121-sbrc1024-callback-aware` | `exp-121-sbrc1024-callback-aware` | `6c1dcc149617a379b210db21a57b3eb4ace5abfe` |
| `exp-122-simple-sbrc1024` | `exp-122-simple-sbrc1024` | `5bc13e58901201b25884b9e602782345bbe7782f` |
| `exp077-early-lut` | `exp-077-early-lut` | `48c2f04208e8dba28dc0a3beee204c984dce84cc` |

No experimental source was merged and no branch or tag was deleted or rewritten.
EXP-079's two uncommitted generator changes remain in their original files, and
their binary patches and SHA256 hashes are also saved. Fixed EXP-091 baseline
files remain under the original EXP-078 results path with unchanged SHA256 hashes.

## Recovery materials

Batch: `/public/home/zhangkewei/zr/.worktree-archives/20260930-113952`

- `refs.before.txt` / `refs.after.txt`: refs unchanged during archiving;
- `worktrees.before.json` / `worktrees.after.json`: registration lists;
- `states.json`: original directories, administrative backups, modified-file hashes;
- `metadata/`: full original administrative directories, including indexes;
- `state/<directory>/`: original Git pointer, tracked state, staged/unstaged/HEAD binary patches;
- `state/root`, `state/stable`, `state/latest`: original documentation snapshots;
- `baseline.before.sha256.json` / `baseline.after.sha256.json`: baseline integrity;
- `operations.jsonl` / `result.json`: per-directory completion and validation.

Before restoring any snapshot, check current branch/worktree usage and agree on
the restore plan. The saved metadata, unchanged original files, refs and patches
support restoration; do not blindly run Git repair or recreate a worktree over
an existing archive. Space reclamation and moving evidence are separate tasks.

## Documentation ownership

Operational AGENTS copies: top-level, active stable, active EXP-123 (identical).
Complete latest experiment record: top-level and EXP-123 (identical).
Stable experiment record: retained validated-version history.
Archived documents: preserved historical snapshots, never overwrite current copies.
