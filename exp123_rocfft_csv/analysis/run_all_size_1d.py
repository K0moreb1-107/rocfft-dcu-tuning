#!/usr/bin/env python3
"""Run the six-size rocFFT matrix and produce the same CSV schema as the CUDA harness."""

import argparse
import csv
import os
import pathlib
import subprocess


SIZES = [32768, 65536, 131072, 262144, 524288, 1048576]
FUNCS = ["z2z_1d", "d2z_1d", "z2d_1d"]
EXPECTED_HEADER = [
    "func", "N", "batch", "is_warmup", "iters", "plan_ms", "first_ms",
    "min_ms", "mean_ms", "max_ms", "per_tf_ms", "check", "err_a", "err_b",
]


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    root = here.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", default=str(root / "bin" / "fft_test_1d"))
    parser.add_argument("--out-dir", default=str(root / "data" / "results_gfx936"))
    parser.add_argument("--device-label", default="gfx936")
    parser.add_argument("--batch", type=int, default=1)
    args = parser.parse_args()

    binary = pathlib.Path(args.bin).resolve()
    out_dir = pathlib.Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    temporary = out_dir / "fft_test_1d.csv"
    if temporary.exists():
        temporary.unlink()

    env = os.environ.copy()
    env["FFT_TEST_OUT"] = str(out_dir)
    env.setdefault("FFT_TEST_ITERS", "50")

    for size in SIZES:
        for func in FUNCS:
            command = [str(binary), str(size), "1", func, str(args.batch)]
            print("RUN", " ".join(command), flush=True)
            subprocess.run(command, check=True, env=env)

    final = out_dir / (
        f"{args.device_label}_1d_" + "_".join(map(str, SIZES)) + ".csv"
    )
    if final.exists():
        final.unlink()
    temporary.rename(final)

    with final.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
        if stream.seekable():
            stream.seek(0)
        header = list(rows[0].keys()) if rows else []
    expected_pairs = [(func, str(size)) for size in SIZES for func in FUNCS]
    actual_pairs = [(row["func"], row["N"]) for row in rows]
    if header != EXPECTED_HEADER:
        raise RuntimeError(f"unexpected CSV header: {header}")
    if len(rows) != 18 or actual_pairs != expected_pairs:
        raise RuntimeError(f"unexpected row matrix: {len(rows)} rows")
    failed = [row for row in rows if row["check"] != "PASS"]
    if failed:
        raise RuntimeError(f"correctness failures: {failed}")
    print(f"RESULT={final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
