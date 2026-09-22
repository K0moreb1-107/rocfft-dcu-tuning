#!/usr/bin/env python3
"""Analyze EXP-091 batch=1 timing and PMC evidence."""

import argparse
import csv
import glob
import json
import os
import statistics


BENCH_ONLY = ("generate_random_interleaved_data_kernel",)


def canonical_ms(path, repetitions):
    total_ns = None
    excluded_ns = 0
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["Name"]
            duration = int(row["TotalDurationNs"])
            if name == "Total":
                total_ns = duration
            elif any(marker in name for marker in BENCH_ONLY):
                excluded_ns += duration
    if total_ns is None:
        raise ValueError("missing Total row: {}".format(path))
    if excluded_ns <= 0:
        raise ValueError("missing bench-only kernel: {}".format(path))
    return (total_ns - excluded_ns) / (repetitions + 1) / 1e6


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
    lines = ["N mean_ms median_ms stdev_ms cv_percent range_ms rounds_ms"]
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
        values = [canonical_ms(path, repetitions) for path in paths]
        item = summarize(values)
        item["files"] = paths
        report["samples"][str(repetitions)] = item
        lines.append(
            "{} {:.9f} {:.9f} {:.9f} {:.6f} {:.9f} {}".format(
                repetitions,
                item["mean_ms"],
                item["median_ms"],
                item["stdev_ms"],
                item["cv_percent"],
                item["range_ms"],
                ",".join("{:.9f}".format(value) for value in values),
            )
        )

    reference = report["samples"]["10000"]["mean_ms"]
    report["mean_delta_vs_N10000_percent"] = {
        key: (item["mean_ms"] / reference - 1.0) * 100.0
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
