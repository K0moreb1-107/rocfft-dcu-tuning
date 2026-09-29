# EXP-123 rocFFT CSV comparison harness

This is a HIP/rocFFT port of the supplied CUDA/cuFFT 1D harness.  It keeps the
CLI, correctness checks, warm-up policy, 50 individually event-timed
iterations, row order, and 14-column CSV schema.  The six-size driver produces
18 rows for z2z, d2z, and z2d at batch 1.

`plan_ms` is the wall time required to create a usable rocFFT plan: plan
description, plan, execution info, work-buffer query/allocation, and work-buffer
binding.  This is the closest rocFFT equivalent to `cufftPlan1d`, which manages
its work area internally.  For z2z correctness only, a separate inverse plan is
created after the recorded forward first execution; that inverse-plan creation
is not included in `plan_ms` or transform timings.

The numerical timing columns are directly comparable in shape and units, but
not all planning internals are identical between cuFFT and rocFFT.  The output
filename records the actual device label rather than copying the supplied
A100/A800 filename ambiguity.
