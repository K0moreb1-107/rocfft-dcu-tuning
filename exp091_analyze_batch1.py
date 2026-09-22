#!/usr/bin/env python3
"""Analyze EXP-091 batch=1 timing and PMC evidence."""

import argparse
import csv
import glob
import json
import os
import statistics


BENCH_ONLY = ("generate_random_interleaved_data_kernel",)


def sample_metrics(path, repetitions):
    total_ns = None
    excluded_ns = 0
    transform_ns = 0
    twiddle_ns = 0
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["Name"]
            duration = int(row["TotalDurationNs"])
            if name == "Total":
                total_ns = duration
            elif any(marker in name for marker in BENCH_ONLY):
                excluded_ns += duration
            elif name.startswith("fft_") or name.startswith("transpose_"):
                transform_ns += duration
            elif name.startswith("twiddle_gen_"):
                twiddle_ns += duration
    if total_ns is None:
        raise ValueError("missing Total row: {}".format(path))
    if excluded_ns <= 0:
        raise ValueError("missing bench-only kernel: {}".format(path))
    if transform_ns <= 0:
        raise ValueError("missing transform kernels: {}".format(path))
    divisor = repetitions + 1
    return {
        "canonical_ms": (total_ns - excluded_ns) / divisor / 1e6,
        "transform_only_ms": transform_ns / divisor / 1e6,
        "fixed_twiddle_total_us": twiddle_ns / 1e3,
        "amortized_twiddle_ms": twiddle_ns / divisor / 1e6,
    }


def summarize(values):
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "rounds_ms": values,
        "mean_ms": mean,
        "median_ms": statistics.median(values),
        "stdev_ms": stdev,
        "cv_percent": stdev / mean * 100.0 if mean else 0.0,
        "range_ms": max(values) - min(values),
    }


def analyze_calibration(args):
    report = {
        "experiment": "EXP-091",
        "phase": "batch1-N-calibration",
        "length": 524288,
        "batch": 1,
        "metric": "(TotalDurationNs - bench-only kernels) / (N + 1) / 1e6",
        "input_dir": os.path.abspath(args.input_dir),
        "samples": {},
    }
    lines = [
        "N canonical_mean_ms canonical_cv_pct transform_mean_ms "
        "transform_cv_pct fixed_twiddle_mean_us canonical_rounds_ms"
    ]
    for repetitions in (100, 1000, 10000):
        pattern = os.path.join(
            args.input_dir, "n{}_r*.hipkernel.csv".format(repetitions)
        )
        paths = sorted(glob.glob(pattern))
        if len(paths) != 3:
            raise ValueError(
                "expected 3 files for N={}, got {}: {}".format(
                    repetitions, len(paths), paths
                )
            )
        samples = [sample_metrics(path, repetitions) for path in paths]
        canonical_values = [sample["canonical_ms"] for sample in samples]
        transform_values = [sample["transform_only_ms"] for sample in samples]
        twiddle_values = [sample["fixed_twiddle_total_us"] for sample in samples]
        twiddle_summary = summarize(twiddle_values)
        item = {
            "canonical": summarize(canonical_values),
            "transform_only": summarize(transform_values),
            "fixed_twiddle_total_us": {
                "rounds_us": twiddle_summary["rounds_ms"],
                "mean_us": twiddle_summary["mean_ms"],
                "median_us": twiddle_summary["median_ms"],
                "stdev_us": twiddle_summary["stdev_ms"],
                "cv_percent": twiddle_summary["cv_percent"],
                "range_us": twiddle_summary["range_ms"],
            },
            "files": paths,
            "per_file_metrics": samples,
        }
        report["samples"][str(repetitions)] = item
        lines.append(
            "{} {:.9f} {:.6f} {:.9f} {:.6f} {:.6f} {}".format(
                repetitions,
                item["canonical"]["mean_ms"],
                item["canonical"]["cv_percent"],
                item["transform_only"]["mean_ms"],
                item["transform_only"]["cv_percent"],
                item["fixed_twiddle_total_us"]["mean_us"],
                ",".join(
                    "{:.9f}".format(value) for value in canonical_values
                ),
            )
        )

    reference = report["samples"]["10000"]["canonical"]["mean_ms"]
    report["mean_delta_vs_N10000_percent"] = {
        key: (item["canonical"]["mean_ms"] / reference - 1.0) * 100.0
        for key, item in report["samples"].items()
    }
    lines.append("mean_delta_vs_N10000_percent=" + json.dumps(
        report["mean_delta_vs_N10000_percent"], sort_keys=True
    ))
    return report, lines


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    calibration = subparsers.add_parser("calibration")
    calibration.add_argument("--input-dir", required=True)
    calibration.add_argument("--json", required=True)
    calibration.add_argument("--text", required=True)
    args = parser.parse_args()

    report, lines = analyze_calibration(args)
    with open(args.json, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    text_output = "\n".join(lines) + "\n"
    with open(args.text, "w") as handle:
        handle.write(text_output)
    print(text_output, end="")


if __name__ == "__main__":
    main()
