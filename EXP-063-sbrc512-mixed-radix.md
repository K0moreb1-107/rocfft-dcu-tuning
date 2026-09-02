# EXP-063: SBRC-512 mixed-radix factorization

Date: 2026-09-02
Branch: `exp-062-large-twiddle-index-recurrence`
Starting commit: `110dc53c` (EXP-062 static result, based on stable
`585f309b72c28d7d27706ca58205c7d5438c28da`).
Target: DP z2z, batch=1000, `-N 10`, gfx936, primary 512K.

## Motivation from source

The active 512K plan uses SBRC length 512, WGS=512, TPT=128 and factors
`[8,8,8]` (`logs/exp057_plan_diag.log`, the SBRC configuration entry in
`device/kernels/configs/config_sbrc.py`). The same rocFFT tree contains an
SBrr length-512 entry using `[16,16,2]`. This is a single algorithmic
factorization test, not an enumeration of WGS/TPT/radix combinations.

The candidate keeps the same 512-point tile, workgroup size, threads per
transform, and number of Stockham passes. It changes only the radix grouping:
the first two passes use radix 16 and the last uses radix 2. The intended
benefit is fewer radix-stage groups and a different twiddle/permutation
balance. The known cost is the generator register footprint: its
`compute_nregisters()` takes the maximum `ceil(length / width / TPT) * width`,
so the candidate requires 16 complex registers per thread instead of 8 before
compiler allocation.

## Gate

Build and correctness must succeed and the plan must show SBRC-512 `[16,16,2]`.
Compare the canonical hipprof metric against the EXP-057 stable value
`39.087328909 ms` for the full 512K transform and the SBRC component against
the available baseline. Collect PMC only if the candidate is not an obvious
regression, checking `arch_vgpr`, occupancy, LDS and VALU. Do not extend this
candidate to other lengths unless the exact configuration is selected there.

A higher VGPR/resource class with no SBRC or total-time improvement rejects the
candidate. A correctness failure rejects it immediately. Preserve the branch
and raw logs/CSV if rejected; do not merge it into the stable branch.

## Status before implementation

This plan is recorded before changing the SBRC configuration. Runtime source
code and the stable branch remain unchanged.
