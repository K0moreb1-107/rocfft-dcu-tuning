#!/usr/bin/env python3
"""Summarize EXP-095 batch=1 pairs and verify the 128K-only RTC gate."""

import argparse
import csv
import json
import statistics as stats
from pathlib import Path

from exp091_analyze_batch1 import sample_metrics

LENGTHS = (65536, 131072, 262144, 524288)
FIXED_BASELINE_MS = {
    65536: 0.017346298,
    131072: 0.019450103,
    262144: 0.023224602,
    524288: 0.051072366,
}
REPETITIONS = 10000
ROUNDS = 8
SUFFIX = "_ordtwrec128k"


def read_sample(path, length, variant):
    metrics = sample_metrics(str(path), REPETITIONS)
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    sbrc = [row for row in rows if "unitstride_sbrc_aligned" in row["Name"]]
    if len(sbrc) != 1:
        raise ValueError(f"expected one aligned SBRC kernel in {path}, found {len(sbrc)}")
    name = sbrc[0]["Name"]
    expected_specialization = variant == "candidate" and length == 131072
    if (SUFFIX in name) != expected_specialization:
        raise ValueError(f"incorrect 128K-only RTC gate in {path}: {name}")
    metrics["sbrc_ms"] = int(sbrc[0]["TotalDurationNs"]) / (REPETITIONS + 1) / 1e6
    metrics["sbrc_kernel"] = name
    metrics["file"] = str(path.resolve())
    return metrics


def cv(values):
    return stats.stdev(values) / stats.mean(values) * 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--text", required=True, type=Path)
    args = parser.parse_args()
    report = {
        "experiment": "EXP-095",
        "batch": 1,
        "repetitions_N": REPETITIONS,
        "divisor": REPETITIONS + 1,
        "rounds": ROUNDS,
        "metric": "(TotalDurationNs - bench-only random-input kernel)/10001/1e6",
        "input_dir": str(args.input_dir.resolve()),
        "lengths": {},
    }
    lines = [
        "length stable_median_ms candidate_median_ms speedup_paired "
        "improvement_paired_pct fixed_baseline_ms speedup_fixed "
        "stable_sbrc_ms candidate_sbrc_ms faster_pairs/8 "
        "stable_cv_pct candidate_cv_pct round_speedups"
    ]
    for length in LENGTHS:
        rounds = []
        for round_number in range(1, ROUNDS + 1):
            suffix = f"{length}_r{round_number}.hipkernel.csv"
            stable_path = args.input_dir / f"stable_{suffix}"
            candidate_path = args.input_dir / f"candidate_{suffix}"
            if not stable_path.is_file() or not candidate_path.is_file():
                raise ValueError(f"missing pair: {stable_path} or {candidate_path}")
            stable = read_sample(stable_path, length, "stable")
            candidate = read_sample(candidate_path, length, "candidate")
            rounds.append({
                "round": round_number,
                "stable": stable,
                "candidate": candidate,
                "speedup": stable["canonical_ms"] / candidate["canonical_ms"],
            })
        old = [item["stable"]["canonical_ms"] for item in rounds]
        new = [item["candidate"]["canonical_ms"] for item in rounds]
        stable_median = stats.median(old)
        candidate_median = stats.median(new)
        stable_sbrc = stats.median(item["stable"]["sbrc_ms"] for item in rounds)
        candidate_sbrc = stats.median(item["candidate"]["sbrc_ms"] for item in rounds)
        fixed = FIXED_BASELINE_MS[length]
        faster_pairs = sum(item["speedup"] > 1 for item in rounds)
        summary = {
            "rounds": rounds,
            "stable_median_ms": stable_median,
            "candidate_median_ms": candidate_median,
            "speedup_vs_paired_stable": stable_median / candidate_median,
            "improvement_vs_paired_stable_percent": (1 - candidate_median / stable_median) * 100,
            "fixed_baseline_ms": fixed,
            "speedup_vs_fixed_baseline": fixed / candidate_median,
            "stable_sbrc_median_ms": stable_sbrc,
            "candidate_sbrc_median_ms": candidate_sbrc,
            "faster_pairs": faster_pairs,
            "stable_cv_percent": cv(old),
            "candidate_cv_percent": cv(new),
        }
        report["lengths"][str(length)] = summary
        lines.append(
            f"{length} {stable_median:.9f} {candidate_median:.9f} "
            f"{summary['speedup_vs_paired_stable']:.6f} "
            f"{summary['improvement_vs_paired_stable_percent']:+.6f} "
            f"{fixed:.9f} {summary['speedup_vs_fixed_baseline']:.6f} "
            f"{stable_sbrc:.9f} {candidate_sbrc:.9f} {faster_pairs}/8 "
            f"{summary['stable_cv_percent']:.6f} {summary['candidate_cv_percent']:.6f} "
            + ",".join(f"{item['speedup']:.6f}" for item in rounds)
        )
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    result = "\n".join(lines) + "\n"
    args.text.write_text(result)
    print(result, end="")


if __name__ == "__main__":
    main()
