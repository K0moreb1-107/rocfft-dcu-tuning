#!/usr/bin/env python3
import csv
import argparse
import datetime
import pathlib
import sys

import matplotlib.pyplot as plt
import numpy as np


TRANSFORMS = ("z2z", "d2z", "z2d")
SIZES = ("64k", "128k", "256k", "512k")
TRIALS = 11


def transform_time_ms(path: pathlib.Path) -> float:
    total_ns = 0
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            name = row["Name"]
            if (
                name == "Total"
                or "generate_random_interleaved_data_kernel" in name
                or name.startswith("twiddle_gen_")
            ):
                continue
            total_ns += int(row["TotalDurationNs"])
    return total_ns / TRIALS / 1_000_000


def result_path(root: pathlib.Path, transform: str, size: str, stamp: str) -> pathlib.Path:
    path = root / f"{transform}_{size}_tuning_{stamp}.csv.hipkernel.csv"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description='Historical hipprof diagnostic plot; retains its original metric.')
    parser.add_argument('results_dir', type=pathlib.Path)
    parser.add_argument('baseline_stamp')
    parser.add_argument('current_stamp')
    parser.add_argument('--output-dir', type=pathlib.Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    baseline_stamp, current_stamp = args.baseline_stamp, args.current_stamp
    workspace = pathlib.Path(__file__).resolve().parent.parent
    output = (args.output_dir or workspace / 'results/diagnostics/runall' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    if workspace.resolve() not in output.parents or root == output or root in output.parents:
        raise SystemExit('output must be inside workspace and separate from historical inputs')
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for transform in TRANSFORMS:
        for size in SIZES:
            baseline = transform_time_ms(result_path(root, transform, size, baseline_stamp))
            current = transform_time_ms(result_path(root, transform, size, current_stamp))
            records.append((transform, size, baseline, current, baseline / current))

    stem = f"runall_{baseline_stamp}_vs_{current_stamp}"
    csv_path = output / f"{stem}.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("transform", "size", "baseline_ms", "optimized_ms", "speedup"))
        writer.writerows(records)

    labels = [f"{transform.upper()}\n{size}" for transform, size, *_ in records]
    baseline = np.array([row[2] for row in records])
    current = np.array([row[3] for row in records])
    speedup = np.array([row[4] for row in records])
    x = np.arange(len(records))
    width = 0.36

    plt.rcParams.update({"font.size": 10, "axes.titleweight": "bold"})
    fig, (ax_time, ax_speedup) = plt.subplots(
        2,
        1,
        figsize=(16, 9),
        sharex=True,
        gridspec_kw={"height_ratios": (2.15, 1), "hspace": 0.08},
    )
    baseline_color = "#6b7280"
    optimized_color = "#07847c"
    speedup_color = "#d6871d"
    bars_base = ax_time.bar(x - width / 2, baseline, width, label="Baseline", color=baseline_color)
    bars_opt = ax_time.bar(x + width / 2, current, width, label="Optimized", color=optimized_color)
    ax_time.set_ylabel("Transform kernel time (ms)")
    ax_time.legend(frameon=False, ncols=2, loc="upper left")
    ax_time.grid(axis="y", color="#d1d5db", linewidth=0.7, alpha=0.75)
    ax_time.set_axisbelow(True)

    for bars in (bars_base, bars_opt):
        for bar in bars:
            value = bar.get_height()
            ax_time.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=90,
            )

    bars_speedup = ax_speedup.bar(x, speedup, width=0.58, color=speedup_color)
    ax_speedup.axhline(1.0, color="#374151", linewidth=1)
    ax_speedup.set_ylabel("Speedup (baseline / optimized)")
    ax_speedup.set_xticks(x, labels)
    ax_speedup.grid(axis="y", color="#d1d5db", linewidth=0.7, alpha=0.75)
    ax_speedup.set_axisbelow(True)
    lower = min(0.9, float(speedup.min()) - 0.05)
    upper = max(1.1, float(speedup.max()) + 0.12)
    ax_speedup.set_ylim(lower, upper)
    for bar, value in zip(bars_speedup, speedup):
        ax_speedup.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}x",
            ha="center",
            va="bottom" if value >= 1 else "top",
            fontsize=9,
            fontweight="bold",
        )

    for boundary in (3.5, 7.5):
        ax_time.axvline(boundary, color="#9ca3af", linewidth=0.8, linestyle="--")
        ax_speedup.axvline(boundary, color="#9ca3af", linewidth=0.8, linestyle="--")

    fig.text(
        0.01,
        0.01,
        "Time sums transform-related kernel durations per trial; random input and twiddle setup are excluded.",
        color="#4b5563",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.07, right=0.985, top=0.97, bottom=0.12)

    png_path = output / f"{stem}.png"
    pdf_path = output / f"{stem}.pdf"
    fig.savefig(png_path, dpi=180)
    fig.savefig(pdf_path)
    print(csv_path)
    print(png_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
