# Current worktree paths and historical snapshots

Updated 2026-09-30 after the user-approved top-level material migration.

The optimization repository has three registered worktrees: root,
`exp-095-sbrc128k-only` (stable), and `exp-123-cufft-format-benchmark`.
`official-rocm722-source` is the separate official checkout. Four additional
EXP-082/083 Git directories discovered later remain untouched, pending review;
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
