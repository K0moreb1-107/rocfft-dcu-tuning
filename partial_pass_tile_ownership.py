#!/usr/bin/env python3
"""Static ownership screen for the 1D CC producer/consumer handoff.

The input is the plan log emitted by rocFFT, not a kernel name.  The model
uses the two leaf plans to construct the physical intermediate matrix H and
partitions H into the actual producer and consumer workgroup tiles.  It also
enumerates factor-aligned producer-suffix and consumer-prefix stage cuts.

This is a necessary-condition screen for preserving the current workgroup
ownership.  It can reject a simple pairing of one existing producer tile with
one existing consumer tile.  It cannot reject a redesigned partial-state
protocol that changes ownership, grouping, layout, or the launch contract.
Stockham layout state, synchronization, twiddle ownership, traffic, and
resource use still have to be derived and tested separately.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TARGETS = (65536, 131072, 262144, 524288)
COMPLEX_BYTES = 16
SCALAR_BYTES = 8
DEFAULT_LDS_LIMIT_BYTES = 64 * 1024
EXCLUDED_BENCH_KERNEL = "generate_random_interleaved_data_kernel"


@dataclass(frozen=True)
class GridShape:
    blocks: int
    workgroup_size: int
    lds_bytes: int


@dataclass(frozen=True)
class LeafPlan:
    scheme: str
    length: Tuple[int, int]
    batch: int
    input_strides: Tuple[int, ...]
    output_strides: Tuple[int, ...]
    factors: Tuple[int, ...]
    workgroup_size: int
    transforms_per_block: int
    grid: GridShape
    direct_to_from_reg: str
    sbrc_transpose_type: str
    large_1d: int
    large_twd_base: int
    large_twd_steps: int

    @property
    def tpt(self) -> int:
        if self.transforms_per_block == 0:
            raise ValueError(f"{self.scheme}: planner trans_per_block is zero")
        if self.workgroup_size % self.transforms_per_block:
            raise ValueError(
                f"{self.scheme}: WGS {self.workgroup_size} is not divisible by "
                f"tpb {self.transforms_per_block}"
            )
        return self.workgroup_size // self.transforms_per_block

    @property
    def logical_lds_complex(self) -> int:
        # This is the same length[0] * bwd expression used by SBCC/SBRC
        # SetupGridParam_internal().
        return self.length[0] * self.transforms_per_block

    @property
    def full_lds_bytes(self) -> int:
        return self.logical_lds_complex * COMPLEX_BYTES

    @property
    def allocated_storage_mode(self) -> str:
        if self.grid.lds_bytes == self.full_lds_bytes:
            return "full-complex"
        if self.grid.lds_bytes * 2 == self.full_lds_bytes:
            return "half-lds-scalar"
        return "other-or-dynamic"


@dataclass(frozen=True)
class PlanCase:
    fft_length: int
    batch: int
    producer: LeafPlan
    consumer: LeafPlan
    path: Path
    repeated_plans: int


@dataclass(frozen=True)
class TileInterval:
    index: int
    begin: int
    end: int

    @property
    def extent(self) -> int:
        return self.end - self.begin


@dataclass(frozen=True)
class CutCandidate:
    producer_factors: Tuple[int, ...]
    consumer_factors: Tuple[int, ...]
    producer_span: int
    consumer_span: int
    producer_stage_groups: int
    consumer_stage_groups: int
    producer_payload_elements: int
    consumer_payload_elements: int
    full_complex_union_lower_bound: int
    full_complex_disjoint_upper_bound: int
    partial_piece_count: int
    producer_transform_complete: bool
    consumer_transform_complete: bool

    @property
    def both_transforms_complete(self) -> bool:
        return self.producer_transform_complete and self.consumer_transform_complete


@dataclass(frozen=True)
class ConsumerPrefixOwnership:
    factors: Tuple[int, ...]
    span: int
    remaining_factors: Tuple[int, ...]
    group_count: int
    group_input_spacing: int
    producer_tiles_touched_min: int
    producer_tiles_touched_max: int
    sample_columns: Tuple[int, ...]
    owner_producer_transforms: int
    owner_wgs_at_current_tpt: int
    owner_output_live_complex_bytes: int
    owner_output_live_scalar_bytes: int
    coalesced_group_width: int
    coalesced_owner_producer_transforms: int
    coalesced_owner_wgs_at_current_tpt: int

    @property
    def completes_consumer_fft(self) -> bool:
        return not self.remaining_factors


def product(values: Iterable[int]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def parse_ints(value: str) -> Tuple[int, ...]:
    return tuple(int(item) for item in re.findall(r"-?\d+", value))


def parse_field(block: str, name: str, indent: int = 4) -> str:
    prefix = " " * indent
    match = re.search(
        rf"(?m)^{re.escape(prefix)}{re.escape(name)}:\s*(.*?)\s*$", block
    )
    if match is None:
        return ""
    return match.group(1)


def parse_radices(block: str) -> Tuple[int, ...]:
    match = re.search(r"(?m)^        radices:\s*\[([^]]*)\]", block)
    if match is None:
        return ()
    return parse_ints(match.group(1))


def parse_leaf(block: str, grid: GridShape, root_batch: int) -> LeafPlan:
    scheme_match = re.search(r"(?m)^    scheme:\s*(\S+)", block)
    if scheme_match is None:
        raise ValueError("leaf block has no scheme")
    scheme = scheme_match.group(1)

    length = parse_ints(parse_field(block, "length"))
    if len(length) != 2:
        raise ValueError(f"{scheme}: expected two-dimensional leaf length")

    input_strides = parse_ints(parse_field(block, "iStrides"))
    output_strides = parse_ints(parse_field(block, "oStrides"))
    factors = parse_radices(block)
    wgs_values = parse_ints(parse_field(block, "workgroup_size", indent=8))
    tpb_values = parse_ints(parse_field(block, "trans_per_block", indent=8))
    if len(wgs_values) != 1 or len(tpb_values) != 1:
        raise ValueError(f"{scheme}: missing planner leaf configuration")

    return LeafPlan(
        scheme=scheme,
        length=(length[0], length[1]),
        batch=root_batch,
        input_strides=input_strides,
        output_strides=output_strides,
        factors=factors,
        workgroup_size=wgs_values[0],
        transforms_per_block=tpb_values[0],
        grid=grid,
        direct_to_from_reg=parse_field(block, "Direct_to_from_Reg"),
        sbrc_transpose_type=parse_field(block, "SBRC_Trans_Type"),
        large_1d=(parse_ints(parse_field(block, "large1D")) or (0,))[0],
        large_twd_base=(parse_ints(parse_field(block, "largeTwdBase")) or (0,))[0],
        large_twd_steps=(parse_ints(parse_field(block, "largeTwdSteps")) or (0,))[0],
    )


def parse_one_plan(segment: str, path: Path) -> PlanCase:
    # The root node is printed without indentation; leaf nodes use four
    # spaces.  Keep these parses separate so a leaf length cannot be mistaken
    # for the transform length or batch.
    root_length_match = re.search(r"(?m)^length:\s*(.*?)\s*$", segment)
    root_batch_match = re.search(r"(?m)^batch:\s*(.*?)\s*$", segment)
    root_length_values = parse_ints(root_length_match.group(1)) if root_length_match else ()
    root_batch_values = parse_ints(root_batch_match.group(1)) if root_batch_match else ()
    if len(root_length_values) != 1 or len(root_batch_values) != 1:
        raise ValueError(f"{path}: missing root length or batch")

    leaf_matches = list(
        re.finditer(r"(?m)^    scheme:\s*CS_KERNEL_STOCKHAM_BLOCK_(CC|RC)\s*$", segment)
    )
    if len(leaf_matches) < 2:
        raise ValueError(f"{path}: expected SBCC and SBRC leaf plans")

    grid_match = re.search(r"(?m)^GridParams\s*$", segment)
    if grid_match is None:
        raise ValueError(f"{path}: missing GridParams")
    grid_text = segment[grid_match.end() :]
    grid_matches = list(
        re.finditer(
            r"(?m)^  b\[(\d+),\d+,\d+\]\s+wgs\[(\d+),\d+,\d+\], "
            r"dy_lds bytes (\d+)\s*$",
            grid_text,
        )
    )
    if len(grid_matches) < 2:
        raise ValueError(f"{path}: expected two grid entries")
    grids = [
        GridShape(
            blocks=int(match.group(1)),
            workgroup_size=int(match.group(2)),
            lds_bytes=int(match.group(3)),
        )
        for match in grid_matches[:2]
    ]

    leaves: Dict[str, LeafPlan] = {}
    for ordinal, match in enumerate(leaf_matches[:2]):
        end = (
            leaf_matches[ordinal + 1].start()
            if ordinal + 1 < len(leaf_matches)
            else grid_match.start()
        )
        block = segment[match.start() : end]
        kind = match.group(1).lower()
        key = "sbcc" if kind == "cc" else "sbrc"
        if key in leaves:
            continue
        leaves[key] = parse_leaf(block, grids[ordinal], root_batch_values[0])

    if set(leaves) != {"sbcc", "sbrc"}:
        raise ValueError(f"{path}: failed to identify both leaf plans")
    return PlanCase(
        fft_length=root_length_values[0],
        batch=root_batch_values[0],
        producer=leaves["sbcc"],
        consumer=leaves["sbrc"],
        path=path,
        repeated_plans=1,
    )


def plan_signature(case: PlanCase) -> Tuple[object, ...]:
    def leaf_signature(leaf: LeafPlan) -> Tuple[object, ...]:
        return (
            leaf.scheme,
            leaf.length,
            leaf.batch,
            leaf.input_strides,
            leaf.output_strides,
            leaf.factors,
            leaf.workgroup_size,
            leaf.transforms_per_block,
            leaf.grid,
            leaf.direct_to_from_reg,
            leaf.sbrc_transpose_type,
            leaf.large_1d,
            leaf.large_twd_base,
            leaf.large_twd_steps,
        )

    return (case.fft_length, case.batch, leaf_signature(case.producer), leaf_signature(case.consumer))


def read_plan(path: Path) -> PlanCase:
    text = path.read_text(encoding="utf-8", errors="replace")
    segments = [segment for segment in text.split("ExecPlan:")[1:] if "GridParams" in segment]
    parsed: List[PlanCase] = []
    for segment in segments:
        try:
            parsed.append(parse_one_plan(segment, path))
        except ValueError:
            # A log may contain an incomplete trailing plan.  It is not used.
            continue
    if not parsed:
        raise RuntimeError(f"{path}: no complete CS_L1D_CC plan found")

    reference = plan_signature(parsed[0])
    inconsistent = [case for case in parsed[1:] if plan_signature(case) != reference]
    if inconsistent:
        raise RuntimeError(f"{path}: repeated plans are not identical")
    first = parsed[0]
    return PlanCase(
        fft_length=first.fft_length,
        batch=first.batch,
        producer=first.producer,
        consumer=first.consumer,
        path=path,
        repeated_plans=len(parsed),
    )


def resolve_plan(root: Path, length: int) -> Path:
    exact = root / "logs" / f"exp007_plan_{length}.log"
    if exact.is_file():
        return exact
    candidates = sorted(glob.glob(str(root / "logs" / f"*plan*{length}*.log")))
    if not candidates:
        raise FileNotFoundError(f"{length}: no plan log found")
    return Path(candidates[-1])


def resolve_benchmark(root: Path, length: int) -> Optional[Path]:
    label = {65536: "64k", 131072: "128k", 262144: "256k", 524288: "512k"}[length]
    pattern = root / "results" / f"z2z_{label}_b1000_exp007_plan_*.csv.hipkernel.csv"
    candidates = sorted(glob.glob(str(pattern)))
    return Path(candidates[-1]) if candidates else None


def canonical_time(path: Path, divisor: int = 11) -> Tuple[float, int, int]:
    total: Optional[int] = None
    excluded = 0
    with path.open("r", newline="") as stream:
        for row in csv.DictReader(stream):
            name = row.get("Name", "")
            try:
                duration = int(row.get("TotalDurationNs", "0"))
            except ValueError:
                continue
            if name == "Total":
                total = duration
            elif EXCLUDED_BENCH_KERNEL in name:
                excluded += duration
    if total is None:
        raise RuntimeError(f"{path}: missing Total row")
    adjusted = total - excluded
    return adjusted / divisor / 1_000_000.0, total, excluded


def baseline_path(root: Path, length: int) -> Path:
    label = {65536: "64k", 131072: "128k", 262144: "256k", 524288: "512k"}[length]
    return root / "results" / f"z2z_{label}_official_7.2.2_20260831_172537.csv.hipkernel.csv"


def git_value(root: Path, args: Sequence[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=str(root), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def fmt_bytes(value: int) -> str:
    if value % 1024 == 0:
        return f"{value} B ({value // 1024} KiB)"
    return f"{value} B"


def tile_intervals(extent: int, tile_extent: int) -> List[TileInterval]:
    if extent <= 0 or tile_extent <= 0:
        raise ValueError("tile extents must be positive")
    return [
        TileInterval(index, begin, min(begin + tile_extent, extent))
        for index, begin in enumerate(range(0, extent, tile_extent))
    ]


def factor_prefixes(factors: Sequence[int]) -> List[Tuple[Tuple[int, ...], int]]:
    result: List[Tuple[Tuple[int, ...], int]] = []
    running = 1
    for index, factor in enumerate(factors, start=1):
        running *= factor
        result.append((tuple(factors[:index]), running))
    return result


def factor_suffixes(factors: Sequence[int]) -> List[Tuple[Tuple[int, ...], int]]:
    result: List[Tuple[Tuple[int, ...], int]] = []
    for index in range(len(factors)):
        suffix = tuple(factors[index:])
        result.append((suffix, product(suffix)))
    return result


def make_cut_candidates(producer: LeafPlan, consumer: LeafPlan) -> List[CutCandidate]:
    # Include complete cuts as controls.  Without them, reporting that every
    # enumerated non-trivial cut is incomplete would be circular.
    producer_cuts = [
        item for item in factor_suffixes(producer.factors)
        if 1 < item[1] <= producer.length[0]
    ]
    consumer_cuts = [
        item for item in factor_prefixes(consumer.factors)
        if 1 < item[1] <= consumer.length[0]
    ]
    result: List[CutCandidate] = []
    for producer_factors, producer_span in producer_cuts:
        for consumer_factors, consumer_span in consumer_cuts:
            producer_groups = producer.length[0] // producer_span
            consumer_groups = consumer.length[0] // consumer_span
            producer_payload = producer.transforms_per_block * producer_span
            consumer_payload = consumer_span * consumer.transforms_per_block
            result.append(
                CutCandidate(
                    producer_factors=producer_factors,
                    consumer_factors=consumer_factors,
                    producer_span=producer_span,
                    consumer_span=consumer_span,
                    producer_stage_groups=producer_groups,
                    consumer_stage_groups=consumer_groups,
                    producer_payload_elements=producer_payload,
                    consumer_payload_elements=consumer_payload,
                    full_complex_union_lower_bound=max(
                        producer_payload, consumer_payload
                    ) * COMPLEX_BYTES,
                    full_complex_disjoint_upper_bound=(
                        producer_payload + consumer_payload
                    ) * COMPLEX_BYTES,
                    partial_piece_count=producer_groups * consumer_groups,
                    producer_transform_complete=(producer_groups == 1),
                    consumer_transform_complete=(consumer_groups == 1),
                )
            )
    return result


def consumer_prefix_ownership(
    producer: LeafPlan, consumer: LeafPlan
) -> List[ConsumerPrefixOwnership]:
    """Enumerate the exact input groups for consumer Stockham prefixes.

    For a prefix whose radix product is S, the generated Stockham passes join
    S input columns with spacing M/S.  Each of those columns is a complete
    producer transform, so this maps the prefix group back to the contiguous
    producer tiles selected by the current SBCC launch.
    """
    k = producer.length[0]
    m = consumer.length[0]
    producer_tile_width = producer.transforms_per_block
    result: List[ConsumerPrefixOwnership] = []
    for prefix_count, (factors, span) in enumerate(factor_prefixes(consumer.factors), start=1):
        if m % span:
            raise ValueError(f"consumer prefix {factors} does not divide length {m}")
        group_count = m // span
        touched_counts: List[int] = []
        sample_columns: Tuple[int, ...] = ()
        for group in range(group_count):
            columns = tuple(group + lane * group_count for lane in range(span))
            touched_counts.append(
                len({column // producer_tile_width for column in columns})
            )
            if group == 0:
                sample_columns = columns

        # Owning adjacent prefix groups recovers the producer's contiguous-a
        # access width.  This is only a resource screen; it does not prove that
        # the generator can implement the grouping.
        coalesced_group_width = min(producer_tile_width, group_count)
        owner_transforms = span
        coalesced_owner_transforms = span * coalesced_group_width
        result.append(
            ConsumerPrefixOwnership(
                factors=factors,
                span=span,
                remaining_factors=tuple(consumer.factors[prefix_count:]),
                group_count=group_count,
                group_input_spacing=group_count,
                producer_tiles_touched_min=min(touched_counts),
                producer_tiles_touched_max=max(touched_counts),
                sample_columns=sample_columns,
                owner_producer_transforms=owner_transforms,
                owner_wgs_at_current_tpt=owner_transforms * producer.tpt,
                owner_output_live_complex_bytes=k * owner_transforms * COMPLEX_BYTES,
                owner_output_live_scalar_bytes=k * owner_transforms * SCALAR_BYTES,
                coalesced_group_width=coalesced_group_width,
                coalesced_owner_producer_transforms=coalesced_owner_transforms,
                coalesced_owner_wgs_at_current_tpt=(
                    coalesced_owner_transforms * producer.tpt
                ),
            )
        )
    return result


def validate_case(case: PlanCase) -> List[str]:
    p = case.producer
    c = case.consumer
    warnings: List[str] = []
    if p.length[0] * p.length[1] != case.fft_length:
        warnings.append("producer dimensions do not multiply to root N")
    if c.length != (p.length[1], p.length[0]):
        warnings.append("consumer dimensions are not the producer transpose")
    if p.input_strides[:2] != (p.length[1], 1):
        warnings.append("producer input strides differ from [M,1]")
    if p.output_strides[:2] != (p.length[1], 1):
        warnings.append("producer output strides differ from [M,1]")
    if c.input_strides[:2] != (1, p.length[1]):
        warnings.append("consumer input strides differ from [1,M]")
    if product(p.factors) != p.length[0]:
        warnings.append("producer factors do not multiply to producer length[0]")
    if product(c.factors) != c.length[0]:
        warnings.append("consumer factors do not multiply to consumer length[0]")
    expected_p_grid = math.ceil(p.length[1] / p.transforms_per_block) * case.batch
    expected_c_grid = math.ceil(c.length[1] / c.transforms_per_block) * case.batch
    if p.grid.blocks != expected_p_grid:
        warnings.append(f"producer grid blocks {p.grid.blocks} != {expected_p_grid}")
    if c.grid.blocks != expected_c_grid:
        warnings.append(f"consumer grid blocks {c.grid.blocks} != {expected_c_grid}")
    if p.grid.workgroup_size != p.workgroup_size:
        warnings.append("producer grid WGS differs from plan WGS")
    if c.grid.workgroup_size != c.workgroup_size:
        warnings.append("consumer grid WGS differs from plan WGS")
    return warnings


def print_case(root: Path, case: PlanCase, lds_limit: int, wgs_limit: int) -> None:
    p = case.producer
    c = case.consumer
    warnings = validate_case(case)
    if p.length[0] * p.length[1] != case.fft_length:
        raise RuntimeError(f"{case.fft_length}: invalid producer dimensions")

    k = p.length[0]
    m = p.length[1]
    producer_tiles = tile_intervals(m, p.transforms_per_block)
    consumer_tiles = tile_intervals(k, c.transforms_per_block)
    edge_histogram = Counter(
        (producer_tile.extent, consumer_tile.extent)
        for producer_tile in producer_tiles
        for consumer_tile in consumer_tiles
    )

    print(f"N={case.fft_length} batch={case.batch}")
    print(f"  plan={case.path} repeated_identical_plans={case.repeated_plans}")
    print(
        f"  producer=SBCC length=[{k},{m}] factors={list(p.factors)} "
        f"wgs={p.workgroup_size} tpb={p.transforms_per_block} tpt={p.tpt} "
        f"grid_blocks={p.grid.blocks} grid_lds={fmt_bytes(p.grid.lds_bytes)} "
        f"lds_mode={p.allocated_storage_mode} logical_lds_complex={p.logical_lds_complex}"
    )
    print(
        f"  consumer=SBRC length=[{m},{k}] factors={list(c.factors)} "
        f"wgs={c.workgroup_size} tpb={c.transforms_per_block} tpt={c.tpt} "
        f"grid_blocks={c.grid.blocks} grid_lds={fmt_bytes(c.grid.lds_bytes)} "
        f"lds_mode={c.allocated_storage_mode} logical_lds_complex={c.logical_lds_complex}"
    )
    print(
        f"  producer_plan_large_twd={p.large_1d}/{p.large_twd_base}/{p.large_twd_steps} "
        f"consumer_transpose={c.sbrc_transpose_type or 'n/a'}"
    )
    print(f"  handoff_matrix=H[K={k},M={m}]")
    print(
        "  coordinate_contract=producer H_P[q,a], q in [0,K), a in [0,M); "
        "consumer H_C[a,q] is the transposed logical view of the same element"
    )
    print(
        f"  physical_intermediate_index=q*{m}+a; "
        f"producer_strides={list(p.output_strides[:2])} "
        f"consumer_input_strides={list(c.input_strides[:2])}"
    )
    print(
        f"  producer_tile_in_H=rows[{k}]xcols[{p.transforms_per_block}] "
        f"count_per_batch={len(producer_tiles)}"
    )
    print(
        f"  consumer_tile_in_H=rows[{c.transforms_per_block}]xcols[{m}] "
        f"count_per_batch={len(consumer_tiles)}"
    )
    print(
        f"  consumer_tiles_require_producer_tiles={len(producer_tiles)} "
        f"producer_tiles_feed_consumer_tiles={len(consumer_tiles)} "
        f"intersection_edges_per_batch={len(producer_tiles) * len(consumer_tiles)}"
    )
    print(
        f"  full_producer_tile_elements={p.transforms_per_block * k} "
        f"full_consumer_tile_elements={m * c.transforms_per_block} "
        f"global_handoff_elements_per_batch={case.fft_length}"
    )
    print(
        f"  full_consumer_cross_workgroup_reduction={len(producer_tiles) > 1} "
        f"full_producer_cross_consumer_reuse={len(consumer_tiles) > 1} "
        f"single_edge_complete_ownership={len(producer_tiles) == 1 and len(consumer_tiles) == 1}"
    )
    print(f"  edge_extent_histogram={dict(sorted(edge_histogram.items()))}")
    full_pair_union = (
        p.transforms_per_block * k
        + m * c.transforms_per_block
        - p.transforms_per_block * c.transforms_per_block
    ) * COMPLEX_BYTES
    print(
        f"  paired_full_strip_geometric_union={fmt_bytes(full_pair_union)} "
        f"lds_screen_limit={fmt_bytes(lds_limit)}"
    )
    print(
        "  note=geometric union is not a claim that a fused kernel must retain "
        "both full strips simultaneously; streaming/overwriting needs a new contract"
    )

    candidates = make_cut_candidates(p, c)
    fit_lower = sum(
        candidate.full_complex_union_lower_bound <= lds_limit
        for candidate in candidates
    )
    both_complete = sum(candidate.both_transforms_complete for candidate in candidates)
    both_partial = sum(
        not candidate.producer_transform_complete
        and not candidate.consumer_transform_complete
        for candidate in candidates
    )
    print(
        f"  partial_cut_candidates={len(candidates)} "
        f"full_complex_union_lower_bound_fits={fit_lower}/{len(candidates)} "
        f"both_partial_candidates={both_partial} "
        f"both_complete_control_candidates={both_complete}"
    )
    for candidate in candidates:
        print(
            f"    producer_suffix={list(candidate.producer_factors)} span={candidate.producer_span} "
            f"consumer_prefix={list(candidate.consumer_factors)} span={candidate.consumer_span} "
            f"stage_groups={candidate.producer_stage_groups}x{candidate.consumer_stage_groups} "
            f"payload_elements={candidate.producer_payload_elements}+{candidate.consumer_payload_elements} "
            f"union_lb={fmt_bytes(candidate.full_complex_union_lower_bound)} "
            f"disjoint_ub={fmt_bytes(candidate.full_complex_disjoint_upper_bound)} "
            f"partial_piece_count={candidate.partial_piece_count} "
            f"producer_transform_complete={candidate.producer_transform_complete} "
            f"consumer_transform_complete={candidate.consumer_transform_complete}"
        )

    print("  consumer_prefix_ownership_screens=")
    for prefix in consumer_prefix_ownership(p, c):
        sample = list(prefix.sample_columns[:16])
        sample_suffix = "..." if len(prefix.sample_columns) > len(sample) else ""
        print(
            f"    prefix={list(prefix.factors)} span={prefix.span} "
            f"remaining={list(prefix.remaining_factors)} groups={prefix.group_count} "
            f"input_spacing={prefix.group_input_spacing} "
            f"producer_tiles_touched={prefix.producer_tiles_touched_min}.."
            f"{prefix.producer_tiles_touched_max} sample_columns={sample}{sample_suffix}"
        )
        print(
            f"      one_group_owner_transforms={prefix.owner_producer_transforms} "
            f"wgs_at_current_tpt={prefix.owner_wgs_at_current_tpt} "
            f"wgs_fits={prefix.owner_wgs_at_current_tpt <= wgs_limit} "
            f"producer_output_live_set={fmt_bytes(prefix.owner_output_live_complex_bytes)} "
            f"scalar_component={fmt_bytes(prefix.owner_output_live_scalar_bytes)}"
        )
        print(
            f"      preserve_current_contiguous_width={prefix.coalesced_group_width} "
            f"owner_transforms={prefix.coalesced_owner_producer_transforms} "
            f"wgs_at_current_tpt={prefix.coalesced_owner_wgs_at_current_tpt} "
            f"wgs_fits={prefix.coalesced_owner_wgs_at_current_tpt <= wgs_limit} "
            f"completes_consumer_fft={prefix.completes_consumer_fft} "
            f"can_elide_interkernel_handoff={prefix.completes_consumer_fft}"
        )
    if warnings:
        for warning in warnings:
            print(f"  warning={warning}")

    benchmark = resolve_benchmark(root, case.fft_length)
    if benchmark is not None:
        time_ms, total, excluded = canonical_time(benchmark)
        print(
            f"  standard_capture_benchmark={benchmark} "
            f"T_compute_ms={time_ms:.9f} total_ns={total} "
            f"excluded_ns={excluded} divisor=11"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent,
        help="rocFFT experiment root"
    )
    parser.add_argument(
        "--lds-limit", type=int, default=DEFAULT_LDS_LIMIT_BYTES,
        help="screening limit in bytes; this is not a performance prediction"
    )
    parser.add_argument(
        "--wgs-limit", type=int, default=1024,
        help="workgroup-size screening limit; this is not an occupancy prediction"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root does not exist: {root}")

    print("EXP-007 corrected static partial-pass tile ownership model")
    print(f"root={root}")
    print(f"branch={git_value(root, ['branch', '--show-current'])}")
    print(f"commit={git_value(root, ['rev-parse', 'HEAD'])}")
    print(f"lds_screen_limit={fmt_bytes(args.lds_limit)}")
    print(f"wgs_screen_limit={args.wgs_limit}")
    print(
        "source_contract=planner tpb/WGS from plan log; SBCC lds=length[0]*tpb; "
        "handoff strides from CC1D AssignParams_internal"
    )
    print(
        "candidate_contract=producer factor suffix x consumer factor prefix, including "
        "complete cuts as controls; all byte values are necessary-condition screens only"
    )

    print("fixed_baseline_canonical_times=")
    for length in TARGETS:
        path = baseline_path(root, length)
        time_ms, total, excluded = canonical_time(path)
        print(
            f"  N={length} file={path} T_compute_ms={time_ms:.9f} "
            f"total_ns={total} excluded_ns={excluded} divisor=11"
        )

    print("cases=")
    cases = [read_plan(resolve_plan(root, length)) for length in TARGETS]
    for case in cases:
        print_case(root, case, args.lds_limit, args.wgs_limit)

    no_single_tile_pair = all(
        math.ceil(case.producer.length[1] / case.producer.transforms_per_block) > 1
        and math.ceil(case.consumer.length[1] / case.consumer.transforms_per_block) > 1
        for case in cases
    )
    if no_single_tile_pair:
        first_prefixes = [consumer_prefix_ownership(case.producer, case.consumer)[0]
                          for case in cases]
        first_prefix_wgs_fit = all(
            prefix.owner_wgs_at_current_tpt <= args.wgs_limit
            for prefix in first_prefixes
        )
        full_prefix_wgs_fit = all(
            consumer_prefix_ownership(case.producer, case.consumer)[-1]
            .owner_wgs_at_current_tpt <= args.wgs_limit
            for case in cases
        )
        print(
            "decision=static_screen_rejects_one_existing_producer_tile_to_one_existing_"
            "consumer_tile_pairing; every measured size has a many-to-many Cartesian "
            f"handoff; first_consumer_prefix_owner_wgs_fits={first_prefix_wgs_fit}; "
            f"full_consumer_prefix_owner_wgs_fits={full_prefix_wgs_fit}; moving only "
            "the first consumer pass may be a separate layout experiment but cannot "
            "elide the inter-kernel global handoff; no rocFFT source prototype submitted"
        )
    else:
        print(
            "decision=static_screen_does_not_prove_fusion; a source prototype "
            "requires an explicit ownership/layout contract and separate validation"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
