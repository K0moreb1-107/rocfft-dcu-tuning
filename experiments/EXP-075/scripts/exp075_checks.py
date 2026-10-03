"""Reachability proof and existing DP z2z validation/measurement conventions."""

import csv
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys


LENGTHS = (65536, 131072, 262144, 524288)


def prove_prefixes():
    for length, steps, tpb, qmax, cutoff, prefix in (
        (256, 2, 8, 32, 256, 288),
        (256, 3, 8, 32, 512, 513),
        (1024, 3, 4, 256, 512, 514),
    ):
        max_index = 0
        checks = 0
        for tile in range(0, 4096, tpb):
            counts = {prefix if p < cutoff else 256 * steps
                      for p in range(tile, tile + tpb)}
            assert len(counts) == 1, "nonuniform cooperative upload bound"
            upload_count = counts.pop()
            for p in range(tile, tile + tpb):
                for q in range(qmax + 1):
                    u = p * q
                    for digit in range(steps):
                        index = digit * 256 + ((u >> (8 * digit)) & 255)
                        assert index < upload_count, (length, steps, p, q, index)
                        if p < cutoff:
                            max_index = max(max_index, index)
                        checks += 1
        assert max_index + 1 == prefix
        print(json.dumps(dict(length=length, steps=steps, tpb=tpb,
                              cutoff=cutoff, prefix=prefix, max_index=max_index,
                              index_checks=checks, uniform=True, passed=True)))


def validate(root, out, phase):
    import numpy as np

    records = []
    for length in LENGTHS:
        for batch in (1, 3):
            stem = out / f"{phase}_{length}_b{batch}"
            rng = np.random.default_rng(20260730 + batch)
            data = (rng.standard_normal((batch, length))
                    + 1j * rng.standard_normal((batch, length))).astype(np.complex128)
            input_file = Path(str(stem) + "_input.bin")
            output_file = Path(str(stem) + "_output.bin")
            data.tofile(input_file)
            env = os.environ.copy()
            if batch == 1:
                env.update(ROCFFT_LAYER="40",
                           ROCFFT_LOG_RTC_PATH=str(stem) + "_rtc.log",
                           ROCFFT_LOG_PLAN_PATH=str(stem) + "_plan.log")
            subprocess.run([str(out / "validate_batch"), str(length), str(batch),
                            str(input_file), str(output_file)], env=env, check=True)
            actual = np.fromfile(output_file, dtype=np.complex128).reshape(batch, length)
            expected = np.fft.fft(data, axis=1)
            error = actual - expected
            relative_l2 = float(np.linalg.norm(error) / np.linalg.norm(expected))
            max_abs = float(np.max(np.abs(error)))
            relative_max = max_abs / float(np.max(np.abs(expected)))
            passed = (np.isfinite(relative_l2) and np.isfinite(relative_max)
                      and relative_l2 < 5e-12 and relative_max < 5e-12)
            row = dict(phase=phase, length=length, batch=batch,
                       relative_l2=relative_l2, relative_max=relative_max,
                       max_abs=max_abs, passed=bool(passed))
            records.append(row)
            print(json.dumps(row), flush=True)
            if not passed:
                raise RuntimeError("DP z2z correctness failed")
        rtc = Path(str(out / f"{phase}_{length}_b1") + "_rtc.log").read_text()
        expected_cc = {65536: 256, 131072: 256, 262144: 512, 524288: 1024}[length]
        assert f"forward_length{expected_cc}_SBCC_device" in rtc
        if phase == "candidate" and length != 262144:
            assert "ltwd_count" in rtc and "while(ltwd_id < ltwd_count)" in rtc
            assert str({65536: 288, 131072: 513, 524288: 514}[length]) in rtc
        else:
            assert "ltwd_count" not in rtc
    (out / f"{phase}_correctness.json").write_text(json.dumps(records, indent=2) + "\n")


def canonical(path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    totals = [int(r["TotalDurationNs"]) for r in rows if r["Name"] == "Total"]
    extra = [r for r in rows if "generate_random_interleaved_data_kernel" in r["Name"]]
    assert len(totals) == 1 and len(extra) == 1 and int(extra[0]["Calls"]) == 11
    return (totals[0] - sum(int(r["TotalDurationNs"]) for r in extra)) / 11 / 1e6


def compare(root, out):
    records = []
    for length in LENGTHS:
        base_path = root / "results" / f"z2z_{length // 1024}k_official_7.2.2_20260831_172537.csv.hipkernel.csv"
        base = canonical(base_path)
        phases = {}
        for phase in ("previous", "candidate"):
            paths = [out / f"{phase}_{length}_r{run}.csv.hipkernel.csv" for run in (1, 2)]
            times = [canonical(path) for path in paths]
            phases[phase] = dict(paths=[str(p) for p in paths], times_ms=times,
                                 mean_ms=statistics.mean(times))
        previous, candidate = (phases[x]["mean_ms"] for x in ("previous", "candidate"))
        row = dict(length=length, previous=phases["previous"], candidate=phases["candidate"],
                   baseline_ms=base, speedup_prev=previous / candidate,
                   improvement_prev_percent=(previous - candidate) / previous * 100,
                   speedup_baseline=base / candidate,
                   improvement_baseline_percent=(base - candidate) / base * 100,
                   both_runs_faster=all(t < previous for t in phases["candidate"]["times_ms"]))
        records.append(row)
        print(json.dumps(row), flush=True)
    (out / "comparison.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "prove":
        prove_prefixes()
    elif command == "validate":
        validate(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    elif command == "compare":
        compare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit("expected prove, validate, or compare")
