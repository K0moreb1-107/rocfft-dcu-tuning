#!/usr/bin/env python3
"""Validate and summarize the paired EXP-123 outlier retest."""

import argparse
import csv
import json
import pathlib
import statistics


CASES = [(131072, "d2z_1d"), (262144, "z2d_1d"), (524288, "d2z_1d")]
ARMS = ("official", "latest")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    args = parser.parse_args()

    result = {"definition": "aggregate mean is mean of 16 process mean_ms values (800 events)"}
    lines = []
    for n, func in CASES:
        key = f"{n}_{func}"
        result[key] = {}
        for arm in ARMS:
            path = args.root / "csv" / arm / key / "fft_test_1d.csv"
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) != 16:
                raise RuntimeError(f"{path}: expected 16 rows, got {len(rows)}")
            if any(row["check"] != "PASS" for row in rows):
                raise RuntimeError(f"{path}: correctness failure")
            if any(int(row["iters"]) != 50 for row in rows):
                raise RuntimeError(f"{path}: unexpected iteration count")
            means = [float(row["mean_ms"]) for row in rows]
            mins = [float(row["min_ms"]) for row in rows]
            maxs = [float(row["max_ms"]) for row in rows]
            result[key][arm] = {
                "processes": len(rows),
                "events": sum(int(row["iters"]) for row in rows),
                "aggregate_mean_ms": statistics.mean(means),
                "median_process_mean_ms": statistics.median(means),
                "min_event_ms": min(mins),
                "max_event_ms": max(maxs),
                "process_mean_ms": means,
            }
        official = result[key]["official"]["aggregate_mean_ms"]
        latest = result[key]["latest"]["aggregate_mean_ms"]
        speedup = official / latest
        result[key]["official_over_latest_speedup"] = speedup
        result[key]["latest_time_change_percent"] = (latest / official - 1.0) * 100.0
        lines.append(
            f"{key} official_mean_ms={official:.9f} latest_mean_ms={latest:.9f} "
            f"speedup={speedup:.6f}x latest_change={result[key]['latest_time_change_percent']:.6f}%"
        )

    (args.root / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.root / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
