#!/usr/bin/env python3
"""Summarize EXP-093 batch=1 SBRC PMC capacity-curve captures."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import statistics


NAME_RE = re.compile(r"^(?P<mode>full|read)_n(?P<length>[0-9]+)_r(?P<round>[0-9]+)\.csv$")
EXPECTED_LENGTHS = (65536, 131072, 262144, 524288)
COMPLEX_BYTES = 16
EA_REQUEST_BYTES = 64
SBRC_KERNEL_MARKER = "unitstride_sbrc_aligned"


def numeric(value):
    if value is None or value == "":
        return 0
    return int(float(value))


def sum_columns(row, prefix):
    return sum(numeric(value) for key, value in row.items() if key.startswith(prefix))


def summarize_dispatch(row):
    hits = sum_columns(row, "TCC_HIT[")
    misses = sum_columns(row, "TCC_MISS[")
    lookups = hits + misses
    return {
        "kernel": row.get("KernelName", ""),
        "grid": numeric(row.get("grd")),
        "workgroup": numeric(row.get("wgr")),
        "lds_bytes": numeric(row.get("lds")),
        "tcc_hit": hits,
        "tcc_miss": misses,
        "tcc_hit_rate": hits / lookups if lookups else None,
        "tcc_ea_rdreq": sum_columns(row, "TCC_EA_RDREQ["),
        "tcc_ea_rdreq_32b": sum_columns(row, "TCC_EA_RDREQ_32B["),
        "tcc_ea1_rdreq": sum_columns(row, "TCC_EA1_RDREQ["),
        "tcc_ea1_rdreq_32b": sum_columns(row, "TCC_EA1_RDREQ_32B["),
        "ta_flat_read_wavefronts": sum_columns(row, "TA_FLAT_READ_WAVEFRONTS["),
    }


def analyze_file(path):
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("empty PMC CSV: {}".format(path))
    selected_rows = [
        row for row in rows if SBRC_KERNEL_MARKER in row.get("KernelName", "")
    ]
    if len(selected_rows) != 2:
        raise ValueError(
            "{} expected exactly two SBRC dispatches, found {} out of {}: {}".format(
                path,
                len(selected_rows),
                len(rows),
                sorted({row.get("KernelName", "") for row in rows}),
            )
        )
    return {
        "path": os.path.abspath(path),
        "raw_dispatch_count": len(rows),
        "selected_dispatch_count": len(selected_rows),
        "excluded_kernel_names": sorted(
            {
                row.get("KernelName", "")
                for row in rows
                if row not in selected_rows
            }
        ),
        "dispatches": [summarize_dispatch(row) for row in selected_rows],
    }


def available(values):
    return [value for value in values if value is not None]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    report = {
        "experiment": "EXP-093",
        "phase": "batch1-sbrc-l2-capacity-curve",
        "warning": (
            "PMC is structural evidence, not latency. TCC hit/miss mixes intermediate, "
            "twiddle, constants, and stores. TCC_EA_RDREQ is an EA-interface request, "
            "not a direct HBM-byte counter. Different counter presets use separate replays."
        ),
        "input_dir": os.path.abspath(args.input_dir),
        "files": {},
        "lengths": {},
    }

    by_length = {length: {"full": [], "read": []} for length in EXPECTED_LENGTHS}
    for path in sorted(glob.glob(os.path.join(args.input_dir, "*.csv"))):
        name = os.path.basename(path)
        match = NAME_RE.match(name)
        if not match:
            continue
        metadata = match.groupdict()
        length = int(metadata["length"])
        if length not in by_length:
            raise ValueError("unexpected FFT length in {}".format(name))
        item = analyze_file(path)
        item.update(
            {
                "mode": metadata["mode"],
                "length": length,
                "round": int(metadata["round"]),
            }
        )
        report["files"][name] = item
        by_length[length][metadata["mode"]].append(item)

    lines = [
        "length intermediate_bytes expected_64B_requests full_dispatches "
        "median_hit_rate mean_hit_per_dispatch mean_miss_per_dispatch read_dispatches "
        "median_ea_rdreq excess_requests excess_percent all_read_requests_64B"
    ]
    for length in EXPECTED_LENGTHS:
        full_files = by_length[length]["full"]
        read_files = by_length[length]["read"]
        if len(full_files) != 3 or len(read_files) != 2:
            raise ValueError(
                "length {} expected 3 full and 2 read files, got {} and {}".format(
                    length, len(full_files), len(read_files)
                )
            )
        full_dispatches = [
            dispatch for item in full_files for dispatch in item["dispatches"]
        ]
        read_dispatches = [
            dispatch for item in read_files for dispatch in item["dispatches"]
        ]
        hit_rates = available(dispatch["tcc_hit_rate"] for dispatch in full_dispatches)
        ea_requests = [dispatch["tcc_ea_rdreq"] for dispatch in read_dispatches]
        ea_32b = [dispatch["tcc_ea_rdreq_32b"] for dispatch in read_dispatches]
        ea1 = [dispatch["tcc_ea1_rdreq"] for dispatch in read_dispatches]
        expected = length * COMPLEX_BYTES // EA_REQUEST_BYTES
        median_requests = statistics.median(ea_requests)
        excess = median_requests - expected
        summary = {
            "intermediate_bytes": length * COMPLEX_BYTES,
            "expected_64B_requests": expected,
            "full_dispatch_count": len(full_dispatches),
            "full_tcc_hit_rate_median": statistics.median(hit_rates),
            "full_tcc_hit_rate_values": hit_rates,
            "full_tcc_hit_per_dispatch_mean": statistics.mean(
                dispatch["tcc_hit"] for dispatch in full_dispatches
            ),
            "full_tcc_miss_per_dispatch_mean": statistics.mean(
                dispatch["tcc_miss"] for dispatch in full_dispatches
            ),
            "read_dispatch_count": len(read_dispatches),
            "ea_rdreq_values": ea_requests,
            "ea_rdreq_median": median_requests,
            "ea_rdreq_excess": excess,
            "ea_rdreq_excess_percent": excess / expected * 100.0,
            "ea_rdreq_32b_values": ea_32b,
            "ea1_rdreq_values": ea1,
            "all_read_requests_64B": all(value == 0 for value in ea_32b + ea1),
            "kernel_names": sorted({dispatch["kernel"] for dispatch in full_dispatches}),
        }
        report["lengths"][str(length)] = summary
        lines.append(
            "{} {} {} {} {:.6f} {:.3f} {:.3f} {} {:.1f} {:.1f} {:.6f} {}".format(
                length,
                summary["intermediate_bytes"],
                expected,
                summary["full_dispatch_count"],
                summary["full_tcc_hit_rate_median"],
                summary["full_tcc_hit_per_dispatch_mean"],
                summary["full_tcc_miss_per_dispatch_mean"],
                summary["read_dispatch_count"],
                median_requests,
                excess,
                summary["ea_rdreq_excess_percent"],
                summary["all_read_requests_64B"],
            )
        )

    if not report["files"]:
        raise ValueError("no recognized PMC CSV files in {}".format(args.input_dir))

    with open(args.json, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    text_output = "\n".join(lines) + "\n"
    with open(args.text, "w") as handle:
        handle.write(text_output)
    print(text_output, end="")


if __name__ == "__main__":
    main()
