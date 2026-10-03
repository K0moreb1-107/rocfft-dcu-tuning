# EXP-062: large-twiddle index recurrence

Date: 2026-09-02
Branch: `exp-062-large-twiddle-index-recurrence`
Start commit: `585f309b72c28d7d27706ca58205c7d5438c28da`
Target: DP z2z, batch=1000, `-N 10`, gfx936, primary 512K.

## Question

Can the final SBCC-1024 pass reuse a twiddle across the `h` iterations, in the
same spirit as VkFFT's staged twiddle handling, instead of reconstructing the
starting twiddle with `TW_NSteps()` for every `h`?

## Source facts

In `device/generator/stockham_gen_cc.h`, the retained recurrence path applies
only when the local length is 256, 512, or 1024, the final factor is 4 or 8,
and the precision is DP. For the target `[8,8,4,4]` kernel the final pass is
`width=4`, `cumheight=256`, `height=4`, and `threads_per_transform=64`.
The generator emits one `TW_NSteps()` for each of the four `h` values. It emits
one additional `TW_NSteps(256 * trans_local)` as the recurrence step for the
four `w` values. Thus the current final pass uses five twiddle reconstructions
per thread, followed by recurrence multiplies for the remaining `w` values.

The index relation is mathematically valid:
`W(h+1,0) = W(h,0) * W(64 * trans_local)` modulo the twiddle period. However,
the existing `t` state is already occupied by `W(256 * trans_local)`, the
independent step in the `w` direction. A correct two-dimensional recurrence
needs both steps and must preserve the `h`-origin while advancing through the
four `w` values. Reusing the existing `W` after the `w` loop is incorrect because
it no longer denotes the h-origin.

## Static cost model

A correct implementation therefore needs at least one additional complex
state for the h-step/origin, plus an additional `TW_NSteps()` or equivalent
construction for `W(64 * trans_local)`. It reduces four per-h `TW_NSteps()`
calls to one base call plus one h-step call, but does not reduce the four
complex output multiplications. It adds state and VALU, while the current
final-pass path already uses the late LDS large-twiddle upload and the
thread-local w recurrence.

This is not a global-memory-load reduction that can be inferred from the
number of `TW_NSteps()` calls: on the retained target, the large-twiddle LUT is
already uploaded cooperatively into reused row-data LDS, and `TW_NSteps()` reads
the same small staged table. The candidate would mainly trade address/table
reconstruction for register state and arithmetic.

## Decision

No runtime source change and no build job were submitted. The candidate is
rejected at the static gate because it adds a complex live state and an
independent twiddle construction without a proven reduction in global memory
traffic. This is especially unfavorable given the retained target's high
