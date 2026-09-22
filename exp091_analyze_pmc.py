#!/usr/bin/env python3
"""Summarize EXP-091 per-kernel PMC CSV files without using PMC time."""

import argparse
import csv
import glob
import json
import os
import re


NAME_RE = re.compile(
    r"^(?P<mode>full|read|write)_b(?P<batch>1|1000)_"
    r"(?P<family>sbcc|sbrc)_r(?P<round>[0-9]+)\.csv$"
)


def numeric(value):
    if value is None or value == "":
        return 0
    return int(float(value))


def sum_columns(row, prefix):
    return sum(numeric(value) for key, value in row.items() if key.startswith(prefix))


def row_summary(row):
    hits = sum_columns(row, "TCC_HIT[")
    misses = sum_columns(row, "TCC_MISS[")
    total = hits + misses
    item = {
        "kernel": row.get("KernelName", ""),
        "grid": numeric(row.get("grd")),
        "workgroup": numeric(row.get("wgr")),
        "lds_bytes": numeric(row.get("lds")),
        "arch_vgpr": numeric(row.get("arch_vgpr")),
        "sgpr": numeric(row.get("sgpr")),
        "tcc_hit": hits,
        "tcc_miss": misses,
        "tcc_hit_rate": hits / total if total else None,
    }
    scalar_columns = (
        "SQ_INSTS_VMEM_RD",
        "SQ_INSTS_VMEM_WR",
        "SQ_INSTS_LDS",
        "SQ_LDS_BANK_CONFLICT",
        "SQ_WAIT_INST_LDS",
    )
    for column in scalar_columns:
        if column in row:
            item[column.lower()] = numeric(row[column])
    focused_prefixes = (
        "TCC_EA_RDREQ[",
        "TCC_EA_RDREQ_32B[",
        "TCC_EA1_RDREQ[",
        "TCC_EA1_RDREQ_32B[",
        "TCC_EA_WRREQ[",
        "TCC_EA_WRREQ_64B[",
        "TCC_EA1_WRREQ[",
        "TCC_EA1_WRREQ_64B[",
        "TA_FLAT_READ_WAVEFRONTS[",
        "TA_FLAT_WRITE_WAVEFRONTS[",
    )
    for prefix in focused_prefixes:
        value = sum_columns(row, prefix)
        if value:
            item[prefix.rstrip("[").lower()] = value
    return item


def analyze_file(path):
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("empty PMC CSV: {}".format(path))
    dispatches = [row_summary(row) for row in rows]
    hits = sum(item["tcc_hit"] for item in dispatches)
    misses = sum(item["tcc_miss"] for item in dispatches)
    total = hits + misses
    return {
        "path": os.path.abspath(path),
        "dispatch_count": len(dispatches),
        "dispatches": dispatches,
        "aggregate_tcc_hit": hits,
        "aggregate_tcc_miss": misses,
        "aggregate_tcc_hit_rate": hits / total if total else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    report = {
        "experiment": "EXP-091",
        "phase": "batch1-512k-pmc",
        "warning": (
            "PMC counts are mechanism diagnostics, not latency. Full/read/write "
            "sets may come from different replays. TCC hit rate mixes data, "
            "twiddle, constants, and stores."
        ),
        "input_dir": os.path.abspath(args.input_dir),
        "files": {},
    }
    lines = [
        "file dispatches batch_norm aggregate_hit aggregate_miss hit_rate "
        "dispatch_hit_rates"
    ]
    focused_lines = [
        "focused_file dispatch rdreq rdreq_32b ea1_rdreq ea1_rdreq_32b "
        "wrreq wrreq_64b ea1_wrreq ea1_wrreq_64b ta_read ta_write"
    ]
    paths = sorted(glob.glob(os.path.join(args.input_dir, "*.csv")))
    for path in paths:
        name = os.path.basename(path)
        match = NAME_RE.match(name)
        if not match:
            continue
        metadata = match.groupdict()
        item = analyze_file(path)
        item.update(metadata)
        batch = int(metadata["batch"])
        transforms = batch * item["dispatch_count"]
        item["normalized_tcc_hit_per_user_transform"] = (
            item["aggregate_tcc_hit"] / transforms if transforms else None
        )
        item["normalized_tcc_miss_per_user_transform"] = (
            item["aggregate_tcc_miss"] / transforms if transforms else None
        )
        report["files"][name] = item
        hit_rate = item["aggregate_tcc_hit_rate"]
        dispatch_rates = [dispatch["tcc_hit_rate"] for dispatch in item["dispatches"]]
        lines.append(
            "{} {} {} {} {} {} {}".format(
                name,
                item["dispatch_count"],
                transforms,
                item["aggregate_tcc_hit"],
                item["aggregate_tcc_miss"],
                "n/a" if hit_rate is None else "{:.6f}".format(hit_rate),
                ",".join(
                    "n/a" if value is None else "{:.6f}".format(value)
                    for value in dispatch_rates
                ),
            )
        )
        if metadata["mode"] != "full":
            for dispatch_index, dispatch in enumerate(item["dispatches"]):
                focused_lines.append(
                    "{} {} {} {} {} {} {} {} {} {} {} {}".format(
                        name,
                        dispatch_index,
                        dispatch.get("tcc_ea_rdreq", 0),
                        dispatch.get("tcc_ea_rdreq_32b", 0),
                        dispatch.get("tcc_ea1_rdreq", 0),
                        dispatch.get("tcc_ea1_rdreq_32b", 0),
                        dispatch.get("tcc_ea_wrreq", 0),
                        dispatch.get("tcc_ea_wrreq_64b", 0),
                        dispatch.get("tcc_ea1_wrreq", 0),
                        dispatch.get("tcc_ea1_wrreq_64b", 0),
                        dispatch.get("ta_flat_read_wavefronts", 0),
                        dispatch.get("ta_flat_write_wavefronts", 0),
                    )
                )
    if not report["files"]:
        raise ValueError("no recognized PMC CSV files in {}".format(args.input_dir))

    with open(args.json, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    text_output = "\n".join(lines + [""] + focused_lines) + "\n"
    with open(args.text, "w") as handle:
        handle.write(text_output)
    print(text_output, end="")


if __name__ == "__main__":
    main()
