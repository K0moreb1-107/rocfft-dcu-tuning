#!/usr/bin/env python3
"""EXP-091C algebraic model of the 512K SBCC -> SBRC handoff.

This is deliberately not an autotuner.  It derives transaction and ownership
lower bounds from the measured kernel geometry, then enumerates only the three
factor-aligned consumer-prefix cuts that exist in SBRC [8, 8, 8].
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Geometry:
    n: int = 524288
    k: int = 1024
    m: int = 512
    complex_bytes: int = 16
    ea_request_bytes: int = 64
    producer_tpb: int = 4
    consumer_tpb: int = 4
    producer_wgs: int = 256
    producer_tpt: int = 64
    consumer_wgs: int = 512
    consumer_tpt: int = 128
    lds_limit_bytes: int = 64 * 1024
    wgs_limit: int = 1024
    producer_factors: tuple[int, ...] = (8, 8, 4, 4)
    consumer_factors: tuple[int, ...] = (8, 8, 8)


def product(values: Iterable[int]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def exact_edge_request_histogram(g: Geometry, p_width: int, c_height: int) -> dict[int, int]:
    """Count aligned EA lines touched by every producer/consumer edge.

    H[q,a] is stored at byte address (q*M+a)*sizeof(complex).  One edge is the
    intersection of a producer a-strip and a consumer q-strip.
    """
    if g.m % p_width or g.k % c_height:
        raise ValueError("tile extents must divide M and K")
    histogram: dict[int, int] = {}
    for producer in range(g.m // p_width):
        a0 = producer * p_width
        for consumer in range(g.k // c_height):
            q0 = consumer * c_height
            requests: set[int] = set()
            for q in range(q0, q0 + c_height):
                begin = (q * g.m + a0) * g.complex_bytes
                end = begin + p_width * g.complex_bytes
                first = begin // g.ea_request_bytes
                last = (end - 1) // g.ea_request_bytes
                requests.update(range(first, last + 1))
            count = len(requests)
            histogram[count] = histogram.get(count, 0) + 1
    return dict(sorted(histogram.items()))


def tile_case(g: Geometry, p_width: int, c_height: int, label: str) -> dict[str, object]:
    producer_tiles = g.m // p_width
    consumer_tiles = g.k // c_height
    edges = producer_tiles * consumer_tiles
    edge_elements = p_width * c_height
    edge_bytes = edge_elements * g.complex_bytes
    histogram = exact_edge_request_histogram(g, p_width, c_height)
    enumerated_requests = sum(requests * count for requests, count in histogram.items())
    return {
        "label": label,
        "producer_tile_width": p_width,
        "consumer_tile_height": c_height,
        "producer_tiles": producer_tiles,
        "consumer_tiles": consumer_tiles,
        "graph": f"K_{{{producer_tiles},{consumer_tiles}}}",
        "edges": edges,
        "producer_degree": consumer_tiles,
        "consumer_degree": producer_tiles,
        "edge_elements": edge_elements,
        "edge_bytes": edge_bytes,
        "edge_request_histogram": {str(key): value for key, value in histogram.items()},
        "enumerated_ea_requests": enumerated_requests,
        "global_boundary_bytes": g.n * g.complex_bytes,
        "request_lower_bound": math.ceil(g.n * g.complex_bytes / g.ea_request_bytes),
    }


def prefix_cases(g: Geometry) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    span = 1
    for prefix_count, factor in enumerate(g.consumer_factors, start=1):
        span *= factor
        group_count = g.m // span
        sample_columns = [lane * group_count for lane in range(span)]
        producer_tiles = sorted({column // g.producer_tpb for column in sample_columns})
        owner_wgs = span * g.producer_tpt
        live_complex = g.k * span * g.complex_bytes
        live_scalar = live_complex // 2

        # Adjacent prefix groups recover the current producer's contiguous-a
        # width.  This is a lower-bound resource check, not a proposed mapping.
        coalesced_groups = min(g.producer_tpb, group_count)
        coalesced_owner_wgs = owner_wgs * coalesced_groups
        completes_consumer = prefix_count == len(g.consumer_factors)
        resource_fit = owner_wgs <= g.wgs_limit and live_scalar <= g.lds_limit_bytes
        coalesced_resource_fit = (
            coalesced_owner_wgs <= g.wgs_limit
            and live_scalar * coalesced_groups <= g.lds_limit_bytes
        )
        cases.append(
            {
                "name": f"F{prefix_count}",
                "factors": list(g.consumer_factors[:prefix_count]),
                "span": span,
                "remaining_factors": list(g.consumer_factors[prefix_count:]),
                "group_count": group_count,
                "sample_columns": sample_columns,
                "producer_tiles_touched": len(producer_tiles),
                "fan_in_from_current_producer_tiles": len(producer_tiles),
                "fan_in_reduction_vs_full_consumer": g.m // g.producer_tpb / len(producer_tiles),
                "producer_tile_indices": producer_tiles,
                "owner_producer_transforms": span,
                "owner_wgs_at_current_tpt": owner_wgs,
                "owner_live_complex_bytes": live_complex,
                "owner_live_scalar_bytes": live_scalar,
                "resource_fit_with_half_lds": resource_fit,
                "groups_needed_for_current_contiguous_width": coalesced_groups,
                "coalesced_owner_wgs_at_current_tpt": coalesced_owner_wgs,
                "coalesced_live_scalar_bytes": live_scalar * coalesced_groups,
                "coalesced_resource_fit": coalesced_resource_fit,
                "completes_consumer_fft": completes_consumer,
                "post_prefix_boundary_bytes": g.n * g.complex_bytes,
                "can_elide_global_boundary": completes_consumer and resource_fit,
            }
        )
    return cases


def build_report(g: Geometry) -> dict[str, object]:
    if g.n != g.k * g.m:
        raise ValueError("N must equal K*M")
    if product(g.producer_factors) != g.k:
        raise ValueError("producer factors must multiply to K")
    if product(g.consumer_factors) != g.m:
        raise ValueError("consumer factors must multiply to M")
    if g.producer_wgs // g.producer_tpb != g.producer_tpt:
        raise ValueError("producer WGS/TPB must equal TPT")
    if g.consumer_wgs // g.consumer_tpb != g.consumer_tpt:
        raise ValueError("consumer WGS/TPB must equal TPT")

    current = tile_case(g, g.producer_tpb, g.consumer_tpb, "current_tpb4_tpb4")
    controls = [
        current,
        tile_case(g, 4, 8, "consumer_tpb8_only"),
        tile_case(g, 8, 8, "producer_and_consumer_tpb8"),
    ]
    lower_bound = math.ceil(g.n * g.complex_bytes / g.ea_request_bytes)
    observed_reads = [131337, 131337, 131344, 131337]
    observed_writes = [131072, 131072, 131072, 131072]
    read_excess = [value - lower_bound for value in observed_reads]
    prefixes = prefix_cases(g)
    full_owner_wgs = g.m * g.producer_tpt
    full_owner_live_complex = g.n * g.complex_bytes
    full_owner_live_scalar = full_owner_live_complex // 2

    return {
        "experiment": "EXP-091C",
        "model_kind": "closed-form lower bound plus exact structural cuts",
        "not_an_autotuner": True,
        "geometry": asdict(g),
        "coordinate_contract": {
            "logical_matrix": "H[K=1024,M=512]",
            "physical_index": "q*M+a",
            "producer_owner": "all q for producer_tpb adjacent a columns",
            "consumer_owner": "consumer_tpb adjacent q rows for all a",
        },
        "ownership_sets": {
            "O_P(p)": "{(q,a): 0<=q<K, 4p<=a<4p+4}",
            "A_P(p)": "O_P(p), written once at the global boundary",
            "O_C(c)": "{(q,a): 4c<=q<4c+4, 0<=a<M}",
            "A_C(c)": "O_C(c), read once at the global boundary",
            "intersection": "O_P(p) intersect O_C(c) is 4x4 complex values = 256 B",
            "batch_independence": (
                "batch adds disconnected copies of this graph; it does not change "
                "per-transform ownership, edge bytes, degrees, or lower bounds"
            ),
        },
        "current_graph": current,
        "tile_controls": controls,
        "algebraic_invariant": {
            "statement": (
                "For aligned P divisible by 4 and C dividing K, "
                "R=(M/P)*(K/C)*C*(P*16/64)=N*16/64."
            ),
            "bytes_per_direction": g.n * g.complex_bytes,
            "minimum_64B_requests_per_direction": lower_bound,
            "consequence": (
                "Changing TPB/WGS or applying a bijective permutation while retaining "
                "one full DP-complex store and load cannot reduce transaction count."
            ),
        },
        "pmc_cross_check": {
            "counter_scope": (
                "TCC_EA requests at the EA interface, not a direct HBM-byte measurement"
            ),
            "observed_sbcc_write_requests": observed_writes,
            "observed_sbrc_read_requests": observed_reads,
            "read_request_excess": read_excess,
            "mean_read_request_excess": sum(read_excess) / len(read_excess),
            "mean_read_excess_percent": (
                sum(read_excess) / len(read_excess) / lower_bound * 100.0
            ),
            "write_matches_lower_bound": all(value == lower_bound for value in observed_writes),
        },
        "consumer_prefixes": prefixes,
        "full_same_workgroup_owner": {
            "producer_transforms": g.m,
            "wgs_at_current_producer_tpt": full_owner_wgs,
            "live_complex_bytes": full_owner_live_complex,
            "live_scalar_bytes": full_owner_live_scalar,
            "wgs_fits": full_owner_wgs <= g.wgs_limit,
            "scalar_lds_fits": full_owner_live_scalar <= g.lds_limit_bytes,
        },
        "decisions": {
            "tpb8_transaction_reduction": "rejected_by_lower_bound",
            "permutation_only_transaction_reduction": "rejected_by_lower_bound",
            "first_consumer_prefix_as_boundary_reduction": (
                "rejected: it still exports all N elements; the one-group form loses "
                "the current adjacent-a width, while preserving width exceeds WGS/LDS limits"
            ),
            "first_consumer_prefix_as_hierarchical_owner": (
                "structurally interesting only: F1 reduces fan-in 128->8, but on the "
                "current hardware it either needs cross-workgroup shared state or fuses "
                "eight spaced producer transforms into one max-resource workgroup; neither "
                "case has yet removed the N-element boundary"
            ),
            "full_same_workgroup_continuation": "rejected_by_WGS_and_live_state",
            "kernel_source_prototype": "not_justified",
            "next_measurement": (
                "the installed hipprof presets expose EA requests but not the DRAM "
                "variants, so first query gfx936 clusterLaunch/cooperative capability. "
                "If cluster sharing is absent, use a controlled cache-disruption test "
                "only if further residency evidence is needed; any algorithmic candidate "
                "must eliminate boundary elements, not merely permute them"
            ),
        },
    }


def render_text(report: dict[str, object]) -> str:
    g = report["geometry"]
    current = report["current_graph"]
    invariant = report["algebraic_invariant"]
    pmc = report["pmc_cross_check"]
    lines = [
        "EXP-091C 512K SBCC -> SBRC handoff ownership model",
        "",
        "Method: closed-form lower bound plus exact factor-aligned cuts; no free-parameter search.",
        f"Geometry: N={g['n']}=K{g['k']}*M{g['m']}, DP complex={g['complex_bytes']} B, EA request={g['ea_request_bytes']} B.",
        (
            f"Current ownership graph: {current['graph']}, {current['edges']} edges; "
            f"each edge={current['edge_elements']} elements/{current['edge_bytes']} B, "
            f"producer degree={current['producer_degree']}, consumer degree={current['consumer_degree']}."
        ),
        "O_P(p)={all q, four adjacent a}; O_C(c)={four adjacent q, all a}; every pair intersects in 4x4 values.",
        "Batch adds disconnected copies of this graph and does not change any per-transform bound.",
        (
            f"Boundary: {invariant['bytes_per_direction']} B per direction; "
            f"minimum={invariant['minimum_64B_requests_per_direction']} 64B requests."
        ),
        f"Identity: {invariant['statement']}",
        (
            "PMC cross-check: SBCC writes="
            f"{pmc['observed_sbcc_write_requests']} (all exactly at lower bound); "
            f"SBRC reads={pmc['observed_sbrc_read_requests']}, mean excess="
            f"{pmc['mean_read_request_excess']:.2f} ({pmc['mean_read_excess_percent']:.4f}%)."
        ),
        "",
        "Tile controls:",
    ]
    for case in report["tile_controls"]:
        lines.append(
            f"  {case['label']}: P={case['producer_tile_width']} C={case['consumer_tile_height']} "
            f"edges={case['edges']} requests={case['enumerated_ea_requests']} "
            f"lower_bound={case['request_lower_bound']}"
        )
    lines.extend(["", "Consumer-prefix ownership:"])
    for prefix in report["consumer_prefixes"]:
        lines.append(
            f"  {prefix['name']} factors={prefix['factors']} span={prefix['span']} "
            f"groups={prefix['group_count']} sample={prefix['sample_columns'][:8]} "
            f"fan_in={prefix['fan_in_from_current_producer_tiles']} "
            f"reduction={prefix['fan_in_reduction_vs_full_consumer']:.1f}x owner_wgs="
            f"{prefix['owner_wgs_at_current_tpt']} scalar_live="
            f"{prefix['owner_live_scalar_bytes']} B fit={prefix['resource_fit_with_half_lds']}"
        )
        lines.append(
            f"    preserve adjacent width: groups={prefix['groups_needed_for_current_contiguous_width']} "
            f"wgs={prefix['coalesced_owner_wgs_at_current_tpt']} scalar_live="
            f"{prefix['coalesced_live_scalar_bytes']} B fit={prefix['coalesced_resource_fit']}; "
            f"post-prefix boundary={prefix['post_prefix_boundary_bytes']} B"
        )
    full = report["full_same_workgroup_owner"]
    lines.extend(
        [
            "",
            (
                "Full same-WG continuation: "
                f"WGS={full['wgs_at_current_producer_tpt']}, complex_live="
                f"{full['live_complex_bytes']} B, scalar_live={full['live_scalar_bytes']} B; "
                f"fits WGS={full['wgs_fits']} LDS={full['scalar_lds_fits']}."
            ),
            "",
            "Decision:",
            "  Reject TPB=8 and permutation-only candidates as transaction-count optimizations.",
            "  Reject F1 as a boundary-byte optimization: it still exports the full 8 MiB array.",
            "  Retain F1 only as a hierarchical-owner lead: fan-in falls 128->8, subject to a cluster-capability check.",
            "  Do not submit a kernel prototype from this model.",
            f"  Next: {report['decisions']['next_measurement']}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--text", type=Path)
    args = parser.parse_args()
    report = build_report(Geometry())
    text = render_text(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.text:
        args.text.parent.mkdir(parents=True, exist_ok=True)
        args.text.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
