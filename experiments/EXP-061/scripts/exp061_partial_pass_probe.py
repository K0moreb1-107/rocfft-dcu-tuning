from pathlib import Path
import re


root = Path(__file__).resolve().parent
tree = root / "rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/tree_node_1D.cpp"
node = root / "rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/tree_node.cpp"
rtc = root / "rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/rtc_stockham_gen.cpp"
plan = root / "logs/exp007_plan_524288.log"

tree_text = tree.read_text()
node_text = node.read_text()
rtc_text = rtc.read_text()
plan_text = plan.read_text()

print("source_facts")
print("one_d_creates_sbcc=" + str(
    "CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_CC" in tree_text))
print("one_d_creates_sbrc=" + str(
    "CreateNodeFromScheme(CS_KERNEL_STOCKHAM_BLOCK_RC" in tree_text))
print("partial_pass_accepts_1d_scheme=" + str(
    "CS_KERNEL_STOCKHAM_PP_BLOCK_CC" in rtc_text and
    "CS_KERNEL_STOCKHAM_PP" in rtc_text))
print("partial_pass_off_dim_0_rejected=" + str(
    "partial-passes along x not currently supported" in node_text))
print("partial_pass_off_dim_2_rejected=" + str(
    "partial-passes along z not currently supported" in node_text))

cc = re.search(
    r"scheme: CS_KERNEL_STOCKHAM_BLOCK_CC.*?"
    r"workgroup_size: (\d+).*?trans_per_block: (\d+).*?"
    r"radices: \[([^]]+)\]",
    plan_text,
    re.S,
)
rc = re.search(
    r"scheme: CS_KERNEL_STOCKHAM_BLOCK_RC.*?"
    r"workgroup_size: (\d+).*?trans_per_block: (\d+).*?"
    r"radices: \[([^]]+)\]",
    plan_text,
    re.S,
)
if not cc or not rc:
    raise SystemExit("could not parse the recorded 512K plan")

cc_wgs, cc_tpb, cc_factors = int(cc.group(1)), int(cc.group(2)), cc.group(3)
rc_wgs, rc_tpb, rc_factors = int(rc.group(1)), int(rc.group(2)), rc.group(3)
producer_transforms = 512
consumer_input_length = 512
producer_tiles = (producer_transforms + cc_tpb - 1) // cc_tpb
consumer_transforms = 1024
consumer_tiles = (consumer_transforms + rc_tpb - 1) // rc_tpb
producer_tiles_per_consumer = (consumer_input_length + cc_tpb - 1) // cc_tpb
handoff_elements = producer_transforms * 1024
handoff_bytes = handoff_elements * 16

print("plan_facts")
print(f"producer_wgs={cc_wgs} producer_tpb={cc_tpb} producer_factors=[{cc_factors.strip()}]")
print(f"consumer_wgs={rc_wgs} consumer_tpb={rc_tpb} consumer_factors=[{rc_factors.strip()}]")
print(f"producer_tiles_per_batch={producer_tiles}")
print(f"consumer_tiles_per_batch={consumer_tiles}")
print(f"producer_tiles_required_per_consumer_tile={producer_tiles_per_consumer}")
print(f"intermediate_elements_per_batch={handoff_elements}")
print(f"intermediate_bytes_per_batch={handoff_bytes}")
print("nonredundant_same_workgroup_continuation=" + str(
    producer_tiles_per_consumer == 1))
print("conclusion=ordinary_1d_tree_has_separate_sbcc_sbrc_leaves_and_many_to_many_handoff")
