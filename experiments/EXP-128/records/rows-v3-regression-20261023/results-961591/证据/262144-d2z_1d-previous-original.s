	.text
	.amdgcn_target "amdgcn-amd-amdhsa--gfx936:sramecc+"
	.protected	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg ; -- Begin function fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg
	.globl	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg
	.p2align	8
	.type	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg,@function
fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg: ; @fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg
; %bb.0:
	s_load_dwordx2 s[0:1], s[4:5], 0x10
	s_load_dwordx2 s[2:3], s[4:5], 0x60
	s_load_dwordx2 s[8:9], s[4:5], 0x0
	v_and_b32_e32 v1, 64, v0
	v_cmp_eq_u32_e32 vcc, 0, v1
	s_waitcnt lgkmcnt(0)
	s_load_dword s0, s[0:1], 0x8
	v_mov_b64_e32 v[3:4], 0
	v_mov_b64_e32 v[21:22], v[3:4]
	v_mov_b64_e32 v[25:26], v[3:4]
	v_mov_b64_e32 v[29:30], v[3:4]
	s_waitcnt lgkmcnt(0)
	s_add_i32 s0, s0, -1
	s_lshr_b32 s0, s0, 2
	s_add_i32 s1, s0, 1
	v_cvt_f32_u32_e32 v1, s1
	s_not_b32 s0, s0
	v_mov_b64_e32 v[27:28], v[3:4]
	v_mov_b64_e32 v[31:32], v[3:4]
	v_rcp_iflag_f32_e32 v1, v1
	v_mov_b64_e32 v[23:24], v[3:4]
	v_mov_b64_e32 v[17:18], v[3:4]
	v_mov_b64_e32 v[19:20], v[3:4]
	v_mul_f32_e32 v1, 0x4f7ffffe, v1
	v_cvt_u32_f32_e32 v1, v1
	v_mov_b64_e32 v[15:16], v[3:4]
	v_mov_b64_e32 v[13:14], v[3:4]
	v_mov_b64_e32 v[11:12], v[3:4]
	v_readfirstlane_b32 s7, v1
	s_mul_i32 s0, s0, s7
	s_mul_hi_u32 s0, s7, s0
	s_add_i32 s7, s7, s0
	s_mul_hi_u32 s0, s6, s7
	s_mul_i32 s0, s0, s1
	s_sub_i32 s0, s6, s0
	s_sub_i32 s6, s0, s1
	s_cmp_ge_u32 s0, s1
	s_cselect_b32 s0, s6, s0
	s_sub_i32 s6, s0, s1
	s_cmp_ge_u32 s0, s1
	s_cselect_b32 s18, s6, s0
	s_lshl_b32 s19, s18, 2
	v_mov_b64_e32 v[9:10], v[3:4]
	v_mov_b64_e32 v[1:2], v[3:4]
	v_mov_b64_e32 v[7:8], v[3:4]
	v_mov_b64_e32 v[5:6], v[3:4]
	v_lshlrev_b32_e32 v33, 2, v0
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_50
; %bb.1:
	s_load_dwordx2 s[12:13], s[4:5], 0x70
	s_load_dwordx2 s[10:11], s[4:5], 0x58
	v_lshrrev_b32_e32 v35, 7, v0
	v_add_u32_e32 v34, s19, v35
	s_movk_i32 s0, 0x100
	v_mov_b64_e32 v[7:8], 0
	v_cmp_gt_u32_e32 vcc, s0, v34
	v_sub_u32_e32 v9, 0, v35
	v_mov_b64_e32 v[5:6], v[7:8]
	v_mov_b64_e32 v[1:2], v[7:8]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_7
; %bb.2:
	v_cmp_ne_u32_e64 s[0:1], s19, v9
                                        ; implicit-def: $vgpr1_vgpr2
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_4
; %bb.3:
	v_and_b32_e32 v5, 0x7f, v0
	v_mul_lo_u32 v6, v34, v5
	s_mov_b32 s0, 0
	v_mov_b32_e32 v1, 4
	v_mov_b32_e32 v2, 0x1000
	v_lshlrev_b32_sdwa v14, v1, v6 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v1, s0, v6, 8
	v_lshl_or_b32 v15, v1, 4, v2
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[1:4], v14, s[12:13]
	global_load_dwordx4 v[10:13], v15, s[12:13]
	v_mov_b32_e32 v14, 0x2000
	v_alignbit_b32 v6, s0, v6, 16
	v_lshl_or_b32 v6, v6, 4, v14
	global_load_dwordx4 v[14:17], v6, s[12:13]
	v_mov_b32_e32 v6, 0
	v_lshl_or_b32 v5, v34, 9, v5
	v_lshlrev_b64 v[5:6], 4, v[5:6]
	v_mov_b32_e32 v18, s11
	v_add_co_u32_e64 v5, s[0:1], s10, v5
	v_addc_co_u32_e64 v6, s[0:1], v18, v6, s[0:1]
	global_load_dwordx4 v[18:21], v[5:6], off
	s_waitcnt vmcnt(2)
	v_mul_f64 v[5:6], v[3:4], v[12:13]
	v_mul_f64 v[12:13], v[1:2], v[12:13]
	v_fma_f64 v[1:2], v[1:2], v[10:11], -v[5:6]
	v_fmac_f64_e32 v[12:13], v[3:4], v[10:11]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[3:4], v[1:2], v[16:17]
	v_mul_f64 v[5:6], v[12:13], v[16:17]
	v_fmac_f64_e32 v[3:4], v[14:15], v[12:13]
	v_fma_f64 v[10:11], v[14:15], v[1:2], -v[5:6]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[5:6], v[20:21], v[3:4]
	v_mul_f64 v[1:2], v[18:19], v[3:4]
	v_fma_f64 v[5:6], v[18:19], v[10:11], -v[5:6]
	v_fmac_f64_e32 v[1:2], v[20:21], v[10:11]
.LBB0_4:
	s_andn2_saveexec_b64 s[0:1], s[16:17]
	s_cbranch_execz .LBB0_6
; %bb.5:
	v_and_b32_e32 v1, 0x1fc, v33
	v_lshlrev_b32_e32 v3, 3, v1
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[5:6], v3, s[10:11]
	global_load_dwordx2 v[1:2], v3, s[10:11] offset:16
.LBB0_6:
	s_or_b64 exec, exec, s[0:1]
.LBB0_7:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[3:4], v[7:8]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_13
; %bb.8:
	v_cmp_ne_u32_e64 s[0:1], s19, v9
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_10
; %bb.9:
	v_and_b32_e32 v3, 0x7f, v0
	v_add_u32_e32 v4, 64, v3
	v_mul_lo_u32 v4, v34, v4
	s_mov_b32 s0, 0
	v_mov_b32_e32 v7, 4
	v_mov_b32_e32 v8, 0x1000
	v_lshlrev_b32_sdwa v15, v7, v4 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v7, s0, v4, 8
	v_lshl_or_b32 v16, v7, 4, v8
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[7:10], v15, s[12:13]
	global_load_dwordx4 v[11:14], v16, s[12:13]
	v_mov_b32_e32 v15, 0x2000
	v_alignbit_b32 v4, s0, v4, 16
	v_lshl_or_b32 v4, v4, 4, v15
	global_load_dwordx4 v[15:18], v4, s[12:13]
	v_mov_b32_e32 v4, 0
	v_lshl_or_b32 v3, v34, 9, v3
	v_lshlrev_b64 v[3:4], 4, v[3:4]
	v_mov_b32_e32 v19, s11
	v_add_co_u32_e64 v3, s[0:1], s10, v3
	v_addc_co_u32_e64 v4, s[0:1], v19, v4, s[0:1]
	global_load_dwordx4 v[19:22], v[3:4], off offset:1024
	s_waitcnt vmcnt(2)
	v_mul_f64 v[3:4], v[9:10], v[13:14]
	v_mul_f64 v[13:14], v[7:8], v[13:14]
	v_fma_f64 v[3:4], v[7:8], v[11:12], -v[3:4]
	v_fmac_f64_e32 v[13:14], v[9:10], v[11:12]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[7:8], v[3:4], v[17:18]
	v_mul_f64 v[9:10], v[13:14], v[17:18]
	v_fmac_f64_e32 v[7:8], v[15:16], v[13:14]
	v_fma_f64 v[9:10], v[15:16], v[3:4], -v[9:10]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[11:12], v[21:22], v[7:8]
	v_mul_f64 v[3:4], v[19:20], v[7:8]
	v_fma_f64 v[7:8], v[19:20], v[9:10], -v[11:12]
	v_fmac_f64_e32 v[3:4], v[21:22], v[9:10]
.LBB0_10:
	s_andn2_saveexec_b64 s[0:1], s[16:17]
	s_cbranch_execz .LBB0_12
; %bb.11:
	v_and_b32_e32 v3, 0x1fc, v33
	v_lshlrev_b32_e32 v9, 3, v3
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[7:8], v9, s[10:11] offset:2048
	global_load_dwordx2 v[3:4], v9, s[10:11] offset:2064
.LBB0_12:
	s_or_b64 exec, exec, s[0:1]
.LBB0_13:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[11:12], 0
	v_mov_b64_e32 v[9:10], v[11:12]
	v_mov_b64_e32 v[13:14], v[11:12]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_19
; %bb.14:
	v_sub_u32_e32 v13, 0, v35
	v_cmp_ne_u32_e64 s[0:1], s19, v13
                                        ; implicit-def: $vgpr13_vgpr14
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_16
; %bb.15:
	v_and_b32_e32 v9, 0x7f, v0
	v_or_b32_e32 v10, 0x80, v9
	v_mul_lo_u32 v10, v34, v10
	s_mov_b32 s0, 0
	v_mov_b32_e32 v13, 4
	v_mov_b32_e32 v14, 0x1000
	v_lshlrev_b32_sdwa v21, v13, v10 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v13, s0, v10, 8
	v_lshl_or_b32 v22, v13, 4, v14
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[13:16], v21, s[12:13]
	global_load_dwordx4 v[17:20], v22, s[12:13]
	v_mov_b32_e32 v21, 0x2000
	v_alignbit_b32 v10, s0, v10, 16
	v_lshl_or_b32 v10, v10, 4, v21
	global_load_dwordx4 v[21:24], v10, s[12:13]
	v_mov_b32_e32 v10, 0
	v_lshl_or_b32 v9, v34, 9, v9
	v_lshlrev_b64 v[9:10], 4, v[9:10]
	v_mov_b32_e32 v25, s11
	v_add_co_u32_e64 v9, s[0:1], s10, v9
	v_addc_co_u32_e64 v10, s[0:1], v25, v10, s[0:1]
	global_load_dwordx4 v[25:28], v[9:10], off offset:2048
	s_waitcnt vmcnt(2)
	v_mul_f64 v[9:10], v[15:16], v[19:20]
	v_mul_f64 v[19:20], v[13:14], v[19:20]
	v_fma_f64 v[9:10], v[13:14], v[17:18], -v[9:10]
	v_fmac_f64_e32 v[19:20], v[15:16], v[17:18]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[13:14], v[9:10], v[23:24]
	v_mul_f64 v[15:16], v[19:20], v[23:24]
	v_fmac_f64_e32 v[13:14], v[21:22], v[19:20]
	v_fma_f64 v[15:16], v[21:22], v[9:10], -v[15:16]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[9:10], v[27:28], v[13:14]
	v_mul_f64 v[13:14], v[25:26], v[13:14]
	v_fma_f64 v[9:10], v[25:26], v[15:16], -v[9:10]
	v_fmac_f64_e32 v[13:14], v[27:28], v[15:16]
.LBB0_16:
	s_andn2_saveexec_b64 s[0:1], s[16:17]
	s_cbranch_execz .LBB0_18
; %bb.17:
	v_and_b32_e32 v9, 0x1fc, v33
	v_lshlrev_b32_e32 v9, 3, v9
	v_or_b32_e32 v15, 0x1000, v9
	v_or_b32_e32 v16, 0x1010, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[9:10], v15, s[10:11]
	global_load_dwordx2 v[13:14], v16, s[10:11]
.LBB0_18:
	s_or_b64 exec, exec, s[0:1]
.LBB0_19:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[15:16], v[11:12]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_25
; %bb.20:
	v_sub_u32_e32 v17, 0, v35
	v_cmp_ne_u32_e64 s[0:1], s19, v17
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_22
; %bb.21:
	v_and_b32_e32 v11, 0x7f, v0
	v_add_u32_e32 v12, 0xc0, v11
	v_mul_lo_u32 v12, v34, v12
	v_mov_b32_e32 v15, 4
	v_mov_b32_e32 v16, 0x1000
	s_mov_b32 s0, 0
	v_lshlrev_b32_sdwa v23, v15, v12 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v15, v12, 8, 8
	v_lshl_or_b32 v24, v15, 4, v16
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[15:18], v23, s[12:13]
	global_load_dwordx4 v[19:22], v24, s[12:13]
	v_mov_b32_e32 v23, 0x2000
	v_alignbit_b32 v12, s0, v12, 16
	v_lshl_or_b32 v12, v12, 4, v23
	global_load_dwordx4 v[23:26], v12, s[12:13]
	v_mov_b32_e32 v12, 0
	v_lshl_or_b32 v11, v34, 9, v11
	v_lshlrev_b64 v[11:12], 4, v[11:12]
	v_mov_b32_e32 v27, s11
	v_add_co_u32_e64 v11, s[0:1], s10, v11
	v_addc_co_u32_e64 v12, s[0:1], v27, v12, s[0:1]
	global_load_dwordx4 v[27:30], v[11:12], off offset:3072
	s_waitcnt vmcnt(2)
	v_mul_f64 v[11:12], v[17:18], v[21:22]
	v_mul_f64 v[21:22], v[15:16], v[21:22]
	v_fma_f64 v[11:12], v[15:16], v[19:20], -v[11:12]
	v_fmac_f64_e32 v[21:22], v[17:18], v[19:20]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[15:16], v[11:12], v[25:26]
	v_mul_f64 v[17:18], v[21:22], v[25:26]
	v_fmac_f64_e32 v[15:16], v[23:24], v[21:22]
	v_fma_f64 v[17:18], v[23:24], v[11:12], -v[17:18]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[11:12], v[29:30], v[15:16]
	v_mul_f64 v[15:16], v[27:28], v[15:16]
	v_fma_f64 v[11:12], v[27:28], v[17:18], -v[11:12]
	v_fmac_f64_e32 v[15:16], v[29:30], v[17:18]
.LBB0_22:
	s_andn2_saveexec_b64 s[16:17], s[16:17]
	s_cbranch_execz .LBB0_24
; %bb.23:
	v_lshlrev_b32_e32 v11, 1, v0
	v_lshlrev_b32_e32 v12, 3, v0
	v_and_b32_e32 v11, 0xfe, v11
	v_and_b32_e32 v12, 0x200, v12
	v_sub_u32_e32 v11, v11, v12
	v_bfe_u32 v12, v0, 6, 1
	v_lshl_or_b32 v19, v11, 1, v12
	v_add_u32_e32 v11, 0x300, v19
	v_mov_b32_e32 v12, 0
	v_lshlrev_b64 v[15:16], 3, v[11:12]
	v_add_u32_e32 v11, 0x302, v19
	s_waitcnt lgkmcnt(0)
	v_mov_b32_e32 v20, s11
	v_add_co_u32_e64 v17, s[0:1], s10, v15
	v_lshlrev_b64 v[11:12], 3, v[11:12]
	v_addc_co_u32_e64 v18, s[0:1], v20, v16, s[0:1]
	v_add_co_u32_e64 v19, s[0:1], s10, v11
	v_addc_co_u32_e64 v20, s[0:1], v20, v12, s[0:1]
	global_load_dwordx2 v[11:12], v[17:18], off
	global_load_dwordx2 v[15:16], v[19:20], off
.LBB0_24:
	s_or_b64 exec, exec, s[16:17]
.LBB0_25:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[19:20], 0
	v_mov_b64_e32 v[17:18], v[19:20]
	v_mov_b64_e32 v[21:22], v[19:20]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_31
; %bb.26:
	v_sub_u32_e32 v21, 0, v35
	v_cmp_ne_u32_e64 s[0:1], s19, v21
                                        ; implicit-def: $vgpr21_vgpr22
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_28
; %bb.27:
	v_and_b32_e32 v17, 0x7f, v0
	v_or_b32_e32 v17, 0x100, v17
	v_mul_lo_u32 v18, v34, v17
	v_mov_b32_e32 v21, 4
	v_mov_b32_e32 v22, 0x1000
	s_mov_b32 s0, 0
	v_lshlrev_b32_sdwa v29, v21, v18 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v21, v18, 8, 8
	v_lshl_or_b32 v30, v21, 4, v22
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[21:24], v29, s[12:13]
	global_load_dwordx4 v[25:28], v30, s[12:13]
	v_mov_b32_e32 v29, 0x2000
	v_alignbit_b32 v18, s0, v18, 16
	v_lshl_or_b32 v18, v18, 4, v29
	global_load_dwordx4 v[29:32], v18, s[12:13]
	v_mov_b32_e32 v18, 0
	v_lshl_or_b32 v17, v34, 9, v17
	v_lshlrev_b64 v[17:18], 4, v[17:18]
	v_mov_b32_e32 v36, s11
	v_add_co_u32_e64 v17, s[0:1], s10, v17
	v_addc_co_u32_e64 v18, s[0:1], v36, v18, s[0:1]
	global_load_dwordx4 v[36:39], v[17:18], off
	s_waitcnt vmcnt(2)
	v_mul_f64 v[17:18], v[23:24], v[27:28]
	v_mul_f64 v[27:28], v[21:22], v[27:28]
	v_fma_f64 v[17:18], v[21:22], v[25:26], -v[17:18]
	v_fmac_f64_e32 v[27:28], v[23:24], v[25:26]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[21:22], v[17:18], v[31:32]
	v_mul_f64 v[23:24], v[27:28], v[31:32]
	v_fmac_f64_e32 v[21:22], v[29:30], v[27:28]
	v_fma_f64 v[23:24], v[29:30], v[17:18], -v[23:24]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[17:18], v[38:39], v[21:22]
	v_mul_f64 v[21:22], v[36:37], v[21:22]
	v_fma_f64 v[17:18], v[36:37], v[23:24], -v[17:18]
	v_fmac_f64_e32 v[21:22], v[38:39], v[23:24]
.LBB0_28:
	s_andn2_saveexec_b64 s[0:1], s[16:17]
	s_cbranch_execz .LBB0_30
; %bb.29:
	v_and_b32_e32 v17, 0x1fc, v33
	v_lshlrev_b32_e32 v23, 3, v17
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[17:18], v23, s[10:11] offset:8
	global_load_dwordx2 v[21:22], v23, s[10:11] offset:24
.LBB0_30:
	s_or_b64 exec, exec, s[0:1]
.LBB0_31:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[23:24], v[19:20]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_37
; %bb.32:
	v_sub_u32_e32 v25, 0, v35
	v_cmp_ne_u32_e64 s[0:1], s19, v25
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_34
; %bb.33:
	v_and_b32_e32 v19, 0x7f, v0
	v_add_u32_e32 v19, 0x140, v19
	v_mul_lo_u32 v20, v34, v19
	v_mov_b32_e32 v23, 4
	v_mov_b32_e32 v24, 0x1000
	s_mov_b32 s0, 0
	v_lshlrev_b32_sdwa v31, v23, v20 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v23, v20, 8, 8
	v_lshl_or_b32 v32, v23, 4, v24
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[23:26], v31, s[12:13]
	global_load_dwordx4 v[27:30], v32, s[12:13]
	v_mov_b32_e32 v31, 0x2000
	v_alignbit_b32 v20, s0, v20, 16
	v_lshl_or_b32 v20, v20, 4, v31
	global_load_dwordx4 v[36:39], v20, s[12:13]
	v_mov_b32_e32 v20, 0
	v_lshl_or_b32 v19, v34, 9, v19
	v_lshlrev_b64 v[19:20], 4, v[19:20]
	v_mov_b32_e32 v31, s11
	v_add_co_u32_e64 v19, s[0:1], s10, v19
	v_addc_co_u32_e64 v20, s[0:1], v31, v20, s[0:1]
	global_load_dwordx4 v[40:43], v[19:20], off
	s_waitcnt vmcnt(2)
	v_mul_f64 v[19:20], v[25:26], v[29:30]
	v_mul_f64 v[29:30], v[23:24], v[29:30]
	v_fma_f64 v[19:20], v[23:24], v[27:28], -v[19:20]
	v_fmac_f64_e32 v[29:30], v[25:26], v[27:28]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[23:24], v[19:20], v[38:39]
	v_mul_f64 v[25:26], v[29:30], v[38:39]
	v_fmac_f64_e32 v[23:24], v[36:37], v[29:30]
	v_fma_f64 v[25:26], v[36:37], v[19:20], -v[25:26]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[19:20], v[42:43], v[23:24]
	v_mul_f64 v[23:24], v[40:41], v[23:24]
	v_fma_f64 v[19:20], v[40:41], v[25:26], -v[19:20]
	v_fmac_f64_e32 v[23:24], v[42:43], v[25:26]
.LBB0_34:
	s_andn2_saveexec_b64 s[0:1], s[16:17]
	s_cbranch_execz .LBB0_36
; %bb.35:
	v_and_b32_e32 v19, 0x1fc, v33
	v_lshlrev_b32_e32 v25, 3, v19
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[19:20], v25, s[10:11] offset:2056
	global_load_dwordx2 v[23:24], v25, s[10:11] offset:2072
.LBB0_36:
	s_or_b64 exec, exec, s[0:1]
.LBB0_37:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[27:28], 0
	v_mov_b64_e32 v[29:30], v[27:28]
	v_mov_b64_e32 v[25:26], v[27:28]
	s_and_saveexec_b64 s[14:15], vcc
	s_cbranch_execz .LBB0_43
; %bb.38:
	v_sub_u32_e32 v29, 0, v35
	v_cmp_ne_u32_e64 s[0:1], s19, v29
                                        ; implicit-def: $vgpr29_vgpr30
	s_and_saveexec_b64 s[16:17], s[0:1]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_40
; %bb.39:
	v_or_b32_e32 v25, 0x180, v0
	v_mul_lo_u32 v26, v34, v25
	v_mov_b32_e32 v29, 4
	v_mov_b32_e32 v30, 0x1000
	s_mov_b32 s0, 0
	v_lshlrev_b32_sdwa v40, v29, v26 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v29, v26, 8, 8
	v_lshl_or_b32 v41, v29, 4, v30
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[29:32], v40, s[12:13]
	global_load_dwordx4 v[36:39], v41, s[12:13]
	v_mov_b32_e32 v40, 0x2000
	v_alignbit_b32 v26, s0, v26, 16
	v_lshl_or_b32 v26, v26, 4, v40
	global_load_dwordx4 v[40:43], v26, s[12:13]
	v_mov_b32_e32 v26, 0
	v_lshl_or_b32 v25, v34, 9, v25
	v_lshlrev_b64 v[25:26], 4, v[25:26]
	v_mov_b32_e32 v44, s11
	v_add_co_u32_e64 v25, s[0:1], s10, v25
	v_addc_co_u32_e64 v26, s[0:1], v44, v26, s[0:1]
	global_load_dwordx4 v[44:47], v[25:26], off
	s_waitcnt vmcnt(2)
	v_mul_f64 v[25:26], v[31:32], v[38:39]
	v_mul_f64 v[38:39], v[29:30], v[38:39]
	v_fma_f64 v[25:26], v[29:30], v[36:37], -v[25:26]
	v_fmac_f64_e32 v[38:39], v[31:32], v[36:37]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[29:30], v[25:26], v[42:43]
	v_mul_f64 v[31:32], v[38:39], v[42:43]
	v_fmac_f64_e32 v[29:30], v[40:41], v[38:39]
	v_fma_f64 v[31:32], v[40:41], v[25:26], -v[31:32]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[36:37], v[46:47], v[29:30]
	v_mul_f64 v[25:26], v[44:45], v[29:30]
	v_fma_f64 v[29:30], v[44:45], v[31:32], -v[36:37]
	v_fmac_f64_e32 v[25:26], v[46:47], v[31:32]
.LBB0_40:
	s_andn2_saveexec_b64 s[0:1], s[16:17]
	s_cbranch_execz .LBB0_42
; %bb.41:
	v_and_b32_e32 v25, 0x1fc, v33
	v_lshlrev_b32_e32 v25, 3, v25
	v_or_b32_e32 v31, 0x1008, v25
	v_or_b32_e32 v32, 0x1018, v25
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[29:30], v31, s[10:11]
	global_load_dwordx2 v[25:26], v32, s[10:11]
.LBB0_42:
	s_or_b64 exec, exec, s[0:1]
.LBB0_43:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[31:32], v[27:28]
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_49
; %bb.44:
	v_sub_u32_e32 v35, 0, v35
	v_cmp_ne_u32_e32 vcc, s19, v35
	s_and_saveexec_b64 s[14:15], vcc
	s_xor_b64 s[14:15], exec, s[14:15]
	s_cbranch_execz .LBB0_46
; %bb.45:
	v_and_b32_e32 v27, 0x7f, v0
	v_add_u32_e32 v27, 0x1c0, v27
	v_mul_lo_u32 v28, v34, v27
	v_mov_b32_e32 v31, 4
	v_mov_b32_e32 v32, 0x1000
	s_mov_b32 s16, 0
	v_lshlrev_b32_sdwa v31, v31, v28 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v35, v28, 8, 8
	v_lshl_or_b32 v32, v35, 4, v32
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[35:38], v31, s[12:13]
	global_load_dwordx4 v[39:42], v32, s[12:13]
	v_mov_b32_e32 v31, 0x2000
	v_alignbit_b32 v28, s16, v28, 16
	v_lshl_or_b32 v28, v28, 4, v31
	global_load_dwordx4 v[43:46], v28, s[12:13]
	v_mov_b32_e32 v28, 0
	v_lshl_add_u32 v27, v34, 9, v27
	v_lshlrev_b64 v[27:28], 4, v[27:28]
	v_mov_b32_e32 v31, s11
	v_add_co_u32_e32 v27, vcc, s10, v27
	v_addc_co_u32_e32 v28, vcc, v31, v28, vcc
	global_load_dwordx4 v[47:50], v[27:28], off
	s_waitcnt vmcnt(2)
	v_mul_f64 v[27:28], v[37:38], v[41:42]
	v_mul_f64 v[31:32], v[35:36], v[41:42]
	v_fma_f64 v[27:28], v[35:36], v[39:40], -v[27:28]
	v_fmac_f64_e32 v[31:32], v[37:38], v[39:40]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[34:35], v[27:28], v[45:46]
	v_mul_f64 v[36:37], v[31:32], v[45:46]
	v_fmac_f64_e32 v[34:35], v[43:44], v[31:32]
	v_fma_f64 v[36:37], v[43:44], v[27:28], -v[36:37]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[31:32], v[49:50], v[34:35]
	v_mul_f64 v[27:28], v[47:48], v[34:35]
	v_fma_f64 v[31:32], v[47:48], v[36:37], -v[31:32]
	v_fmac_f64_e32 v[27:28], v[49:50], v[36:37]
.LBB0_46:
	s_waitcnt lgkmcnt(0)
	s_andn2_saveexec_b64 s[12:13], s[14:15]
	s_cbranch_execz .LBB0_48
; %bb.47:
	v_and_b32_e32 v27, 0x1fc, v33
	v_lshlrev_b32_e32 v27, 3, v27
	v_add_u32_e32 v34, 0x1808, v27
	v_add_u32_e32 v35, 0x1818, v27
	global_load_dwordx2 v[31:32], v34, s[10:11]
	global_load_dwordx2 v[27:28], v35, s[10:11]
.LBB0_48:
	s_or_b64 exec, exec, s[12:13]
.LBB0_49:
	s_or_b64 exec, exec, s[0:1]
.LBB0_50:
	s_or_b64 exec, exec, s[6:7]
	s_load_dwordx2 s[4:5], s[4:5], 0x68
	v_and_b32_e32 v47, 0x600, v33
	v_and_b32_e32 v48, 0x7f, v0
	v_cmp_gt_u32_e32 vcc, 64, v48
	v_lshl_add_u32 v33, v48, 3, v47
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_52
; %bb.51:
	s_waitcnt vmcnt(1)
	v_add_f64 v[17:18], v[5:6], -v[17:18]
	v_add_f64 v[29:30], v[9:10], -v[29:30]
	s_waitcnt vmcnt(0)
	v_add_f64 v[21:22], v[1:2], -v[21:22]
	v_add_f64 v[25:26], v[13:14], -v[25:26]
	v_add_f64 v[19:20], v[7:8], -v[19:20]
	v_add_f64 v[23:24], v[3:4], -v[23:24]
	v_add_f64 v[31:32], v[11:12], -v[31:32]
	v_add_f64 v[27:28], v[15:16], -v[27:28]
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[17:18]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[29:30]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[21:22]
	v_fma_f64 v[13:14], v[13:14], 2.0, -v[25:26]
	v_fma_f64 v[7:8], v[7:8], 2.0, -v[19:20]
	v_fma_f64 v[3:4], v[3:4], 2.0, -v[23:24]
	v_fma_f64 v[11:12], v[11:12], 2.0, -v[31:32]
	v_fma_f64 v[15:16], v[15:16], 2.0, -v[27:28]
	v_add_f64 v[34:35], v[17:18], -v[25:26]
	v_add_f64 v[36:37], v[19:20], -v[27:28]
	v_add_f64 v[38:39], v[29:30], v[21:22]
	v_add_f64 v[25:26], v[31:32], v[23:24]
	v_add_f64 v[9:10], v[5:6], -v[9:10]
	v_add_f64 v[13:14], v[1:2], -v[13:14]
	v_add_f64 v[11:12], v[7:8], -v[11:12]
	v_add_f64 v[15:16], v[3:4], -v[15:16]
	v_fma_f64 v[40:41], v[17:18], 2.0, -v[34:35]
	v_fma_f64 v[42:43], v[19:20], 2.0, -v[36:37]
	v_fma_f64 v[44:45], v[21:22], 2.0, -v[38:39]
	v_fma_f64 v[29:30], v[23:24], 2.0, -v[25:26]
	s_mov_b32 s6, 0x667f3bcd
	s_mov_b32 s7, 0xbfe6a09e
	s_waitcnt lgkmcnt(0)
	s_mov_b32 s11, 0x3fe6a09e
	s_mov_b32 s10, s6
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[9:10]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[13:14]
	v_fma_f64 v[7:8], v[7:8], 2.0, -v[11:12]
	v_fma_f64 v[3:4], v[3:4], 2.0, -v[15:16]
	v_fma_f64 v[19:20], s[6:7], v[42:43], v[40:41]
	v_fma_f64 v[31:32], s[10:11], v[36:37], v[34:35]
	v_fma_f64 v[23:24], s[6:7], v[29:30], v[44:45]
	v_fma_f64 v[27:28], s[10:11], v[25:26], v[38:39]
	v_lshl_add_u32 v33, v33, 3, 0
	v_add_f64 v[17:18], v[5:6], -v[7:8]
	v_add_f64 v[21:22], v[1:2], -v[3:4]
	v_fmac_f64_e32 v[19:20], s[6:7], v[29:30]
	v_add_f64 v[29:30], v[9:10], -v[15:16]
	v_fmac_f64_e32 v[31:32], s[6:7], v[25:26]
	v_fmac_f64_e32 v[23:24], s[10:11], v[42:43]
	v_add_f64 v[25:26], v[13:14], v[11:12]
	v_fmac_f64_e32 v[27:28], s[10:11], v[36:37]
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[17:18]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[21:22]
	v_fma_f64 v[7:8], v[40:41], 2.0, -v[19:20]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[29:30]
	v_fma_f64 v[11:12], v[34:35], 2.0, -v[31:32]
	v_fma_f64 v[3:4], v[44:45], 2.0, -v[23:24]
	v_fma_f64 v[13:14], v[13:14], 2.0, -v[25:26]
	v_fma_f64 v[15:16], v[38:39], 2.0, -v[27:28]
	ds_write_b128 v33, v[5:8]
	ds_write_b128 v33, v[9:12] offset:16
	ds_write_b128 v33, v[17:20] offset:32
	ds_write_b128 v33, v[29:32] offset:48
.LBB0_52:
	s_or_b64 exec, exec, s[0:1]
	v_or_b32_e32 v33, v47, v48
	s_waitcnt vmcnt(0) lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_54
; %bb.53:
	v_lshl_add_u32 v29, v33, 3, 0
	ds_read2st64_b64 v[5:8], v29 offset1:1
	ds_read2st64_b64 v[9:12], v29 offset0:2 offset1:3
	ds_read2st64_b64 v[17:20], v29 offset0:4 offset1:5
	ds_read2st64_b64 v[29:32], v29 offset0:6 offset1:7
.LBB0_54:
	s_or_b64 exec, exec, s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_56
; %bb.55:
	v_lshl_add_u32 v33, v48, 3, v47
	v_lshl_add_u32 v33, v33, 3, 0
	ds_write_b128 v33, v[1:4]
	ds_write_b128 v33, v[13:16] offset:16
	ds_write_b128 v33, v[21:24] offset:32
	ds_write_b128 v33, v[25:28] offset:48
.LBB0_56:
	s_or_b64 exec, exec, s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_58
; %bb.57:
	v_or_b32_e32 v1, v47, v48
	v_lshl_add_u32 v25, v1, 3, 0
	ds_read2st64_b64 v[1:4], v25 offset1:1
	ds_read2st64_b64 v[13:16], v25 offset0:2 offset1:3
	ds_read2st64_b64 v[21:24], v25 offset0:4 offset1:5
	ds_read2st64_b64 v[25:28], v25 offset0:6 offset1:7
.LBB0_58:
	s_or_b64 exec, exec, s[0:1]
	v_and_b32_e32 v49, 7, v0
	v_mul_u32_u24_e32 v33, 7, v49
	v_lshlrev_b32_e32 v58, 4, v33
	global_load_dwordx4 v[39:42], v58, s[8:9] offset:16
	global_load_dwordx4 v[43:46], v58, s[8:9] offset:32
	global_load_dwordx4 v[50:53], v58, s[8:9]
	global_load_dwordx4 v[33:36], v58, s[8:9] offset:48
	s_mov_b32 s0, 0x667f3bcd
	s_mov_b32 s1, 0x3fe6a09e
	s_mov_b32 s7, 0xbfe6a09e
	s_mov_b32 s6, s0
	s_waitcnt vmcnt(3) lgkmcnt(2)
	v_mul_f64 v[54:55], v[13:14], v[41:42]
	v_mul_f64 v[37:38], v[9:10], v[41:42]
	s_waitcnt vmcnt(2)
	v_mul_f64 v[56:57], v[15:16], v[45:46]
	v_mul_f64 v[45:46], v[11:12], v[45:46]
	v_fma_f64 v[54:55], v[9:10], v[39:40], -v[54:55]
	v_fmac_f64_e32 v[37:38], v[13:14], v[39:40]
	global_load_dwordx4 v[39:42], v58, s[8:9] offset:80
	v_fma_f64 v[56:57], v[11:12], v[43:44], -v[56:57]
	global_load_dwordx4 v[9:12], v58, s[8:9] offset:96
	v_fmac_f64_e32 v[45:46], v[15:16], v[43:44]
	global_load_dwordx4 v[13:16], v58, s[8:9] offset:64
	s_waitcnt vmcnt(2) lgkmcnt(0)
	v_mul_f64 v[43:44], v[25:26], v[41:42]
	v_mul_f64 v[41:42], v[29:30], v[41:42]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[58:59], v[27:28], v[11:12]
	v_fma_f64 v[29:30], v[29:30], v[39:40], -v[43:44]
	v_fmac_f64_e32 v[41:42], v[25:26], v[39:40]
	v_mul_f64 v[25:26], v[31:32], v[11:12]
	v_mul_f64 v[11:12], v[21:22], v[35:36]
	v_mul_f64 v[39:40], v[3:4], v[52:53]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[43:44], v[23:24], v[15:16]
	v_fma_f64 v[31:32], v[31:32], v[9:10], -v[58:59]
	v_mul_f64 v[15:16], v[19:20], v[15:16]
	v_fmac_f64_e32 v[25:26], v[27:28], v[9:10]
	v_mul_f64 v[9:10], v[7:8], v[52:53]
	v_fma_f64 v[11:12], v[17:18], v[33:34], -v[11:12]
	v_fma_f64 v[7:8], v[7:8], v[50:51], -v[39:40]
	v_fma_f64 v[19:20], v[19:20], v[13:14], -v[43:44]
	v_fmac_f64_e32 v[15:16], v[23:24], v[13:14]
	v_add_f64 v[13:14], v[37:38], -v[41:42]
	v_add_f64 v[27:28], v[56:57], -v[31:32]
	v_add_f64 v[25:26], v[45:46], -v[25:26]
	v_fmac_f64_e32 v[9:10], v[3:4], v[50:51]
	v_add_f64 v[3:4], v[5:6], -v[11:12]
	v_add_f64 v[11:12], v[54:55], -v[29:30]
	v_add_f64 v[23:24], v[7:8], -v[19:20]
	v_fma_f64 v[31:32], v[56:57], 2.0, -v[27:28]
	v_add_f64 v[29:30], v[9:10], -v[15:16]
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[3:4]
	v_fma_f64 v[15:16], v[54:55], 2.0, -v[11:12]
	v_fma_f64 v[7:8], v[7:8], 2.0, -v[23:24]
	v_add_f64 v[50:51], v[3:4], -v[13:14]
	v_add_f64 v[41:42], v[23:24], -v[25:26]
	v_fma_f64 v[19:20], v[9:10], 2.0, -v[29:30]
	v_fma_f64 v[9:10], v[45:46], 2.0, -v[25:26]
	v_add_f64 v[43:44], v[29:30], v[27:28]
	v_add_f64 v[27:28], v[5:6], -v[15:16]
	v_fma_f64 v[52:53], v[3:4], 2.0, -v[50:51]
	v_add_f64 v[15:16], v[7:8], -v[31:32]
	v_fma_f64 v[39:40], v[23:24], 2.0, -v[41:42]
	v_add_f64 v[31:32], v[19:20], -v[9:10]
	v_fma_f64 v[45:46], v[29:30], 2.0, -v[43:44]
	v_fma_f64 v[3:4], v[5:6], 2.0, -v[27:28]
	v_fma_f64 v[9:10], s[0:1], v[41:42], v[50:51]
	v_fma_f64 v[5:6], v[7:8], 2.0, -v[15:16]
	v_fma_f64 v[25:26], s[6:7], v[39:40], v[52:53]
	s_waitcnt lgkmcnt(0)
	s_barrier
	v_add_f64 v[7:8], v[27:28], -v[31:32]
	s_waitcnt lgkmcnt(0)
	v_fmac_f64_e32 v[9:10], s[6:7], v[43:44]
	v_add_f64 v[23:24], v[3:4], -v[5:6]
	v_fmac_f64_e32 v[25:26], s[6:7], v[45:46]
	v_fma_f64 v[27:28], v[27:28], 2.0, -v[7:8]
	v_fma_f64 v[29:30], v[50:51], 2.0, -v[9:10]
	v_fma_f64 v[3:4], v[3:4], 2.0, -v[23:24]
	v_fma_f64 v[5:6], v[52:53], 2.0, -v[25:26]
	v_lshlrev_b32_e32 v50, 3, v0
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_60
; %bb.59:
	s_movk_i32 s10, 0x3c0
	v_and_or_b32 v50, v50, s10, v49
	v_add_u32_e32 v50, v50, v47
	v_lshl_add_u32 v50, v50, 3, 0
	ds_write2_b64 v50, v[3:4], v[5:6] offset1:8
	ds_write2_b64 v50, v[27:28], v[29:30] offset0:16 offset1:24
	ds_write2_b64 v50, v[23:24], v[25:26] offset0:32 offset1:40
	ds_write2_b64 v50, v[7:8], v[9:10] offset0:48 offset1:56
.LBB0_60:
	s_or_b64 exec, exec, s[6:7]
	v_mul_f64 v[39:40], v[39:40], s[0:1]
	v_mul_f64 v[45:46], v[45:46], s[0:1]
	v_mul_f64 v[41:42], v[41:42], s[0:1]
	v_mul_f64 v[43:44], v[43:44], s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_62
; %bb.61:
	v_or_b32_e32 v3, v47, v48
	v_lshl_add_u32 v7, v3, 3, 0
	ds_read2st64_b64 v[3:6], v7 offset1:1
	ds_read2st64_b64 v[27:30], v7 offset0:2 offset1:3
	ds_read2st64_b64 v[23:26], v7 offset0:4 offset1:5
	ds_read2st64_b64 v[7:10], v7 offset0:6 offset1:7
.LBB0_62:
	s_or_b64 exec, exec, s[0:1]
	v_mul_f64 v[17:18], v[17:18], v[35:36]
	v_fma_f64 v[13:14], v[37:38], 2.0, -v[13:14]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	v_fmac_f64_e32 v[17:18], v[21:22], v[33:34]
	v_add_f64 v[17:18], v[1:2], -v[17:18]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[17:18]
	v_add_f64 v[33:34], v[17:18], v[11:12]
	v_add_f64 v[11:12], v[1:2], -v[13:14]
	v_fma_f64 v[13:14], v[17:18], 2.0, -v[33:34]
	v_fma_f64 v[17:18], v[19:20], 2.0, -v[31:32]
	v_add_f64 v[31:32], v[33:34], v[43:44]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[11:12]
	v_add_f64 v[21:22], v[13:14], -v[45:46]
	v_add_f64 v[19:20], v[11:12], v[15:16]
	v_add_f64 v[15:16], v[1:2], -v[17:18]
	v_add_f64 v[17:18], v[39:40], v[21:22]
	v_add_f64 v[21:22], v[41:42], v[31:32]
	v_fma_f64 v[31:32], v[11:12], 2.0, -v[19:20]
	v_fma_f64 v[11:12], v[1:2], 2.0, -v[15:16]
	v_fma_f64 v[13:14], v[13:14], 2.0, -v[17:18]
	v_fma_f64 v[33:34], v[33:34], 2.0, -v[21:22]
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_64
; %bb.63:
	v_lshlrev_b32_e32 v1, 3, v0
	s_movk_i32 s6, 0x3c0
	v_and_or_b32 v1, v1, s6, v49
	v_add_u32_e32 v1, v1, v47
	v_lshl_add_u32 v1, v1, 3, 0
	ds_write2_b64 v1, v[11:12], v[13:14] offset1:8
	ds_write2_b64 v1, v[31:32], v[33:34] offset0:16 offset1:24
	ds_write2_b64 v1, v[15:16], v[17:18] offset0:32 offset1:40
	ds_write2_b64 v1, v[19:20], v[21:22] offset0:48 offset1:56
.LBB0_64:
	s_or_b64 exec, exec, s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_66
; %bb.65:
	v_or_b32_e32 v1, v47, v48
	v_lshl_add_u32 v1, v1, 3, 0
	ds_read2st64_b64 v[11:14], v1 offset1:1
	ds_read2st64_b64 v[31:34], v1 offset0:2 offset1:3
	ds_read2st64_b64 v[15:18], v1 offset0:4 offset1:5
	ds_read2st64_b64 v[19:22], v1 offset0:6 offset1:7
.LBB0_66:
	s_or_b64 exec, exec, s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_68
; %bb.67:
	v_and_b32_e32 v1, 63, v0
	v_mul_u32_u24_e32 v1, 7, v1
	v_lshlrev_b32_e32 v1, 4, v1
	v_mov_b32_e32 v2, s9
	v_add_co_u32_e32 v1, vcc, s8, v1
	v_addc_co_u32_e32 v2, vcc, 0, v2, vcc
	global_load_dwordx4 v[35:38], v[1:2], off offset:912
	global_load_dwordx4 v[39:42], v[1:2], off offset:928
	global_load_dwordx4 v[43:46], v[1:2], off offset:896
	global_load_dwordx4 v[49:52], v[1:2], off offset:944
	s_mov_b32 s6, 0x667f3bcd
	s_mov_b32 s7, 0xbfe6a09e
	s_mov_b32 s9, 0x3fe6a09e
	s_mov_b32 s8, s6
	s_waitcnt vmcnt(3)
	v_mul_f64 v[53:54], v[31:32], v[37:38]
	v_mul_f64 v[55:56], v[27:28], v[37:38]
	s_waitcnt vmcnt(2)
	v_mul_f64 v[37:38], v[33:34], v[41:42]
	v_mul_f64 v[41:42], v[29:30], v[41:42]
	v_fma_f64 v[53:54], v[27:28], v[35:36], -v[53:54]
	v_fmac_f64_e32 v[55:56], v[31:32], v[35:36]
	v_fma_f64 v[57:58], v[29:30], v[39:40], -v[37:38]
	global_load_dwordx4 v[27:30], v[1:2], off offset:960
	v_fmac_f64_e32 v[41:42], v[33:34], v[39:40]
	global_load_dwordx4 v[31:34], v[1:2], off offset:976
	global_load_dwordx4 v[35:38], v[1:2], off offset:992
	s_waitcnt vmcnt(4)
	v_mul_f64 v[39:40], v[5:6], v[45:46]
	v_mul_f64 v[1:2], v[13:14], v[45:46]
	v_or_b32_e32 v45, v47, v48
	v_fmac_f64_e32 v[39:40], v[13:14], v[43:44]
	s_waitcnt vmcnt(3)
	v_mul_f64 v[13:14], v[23:24], v[51:52]
	v_fma_f64 v[1:2], v[5:6], v[43:44], -v[1:2]
	v_mul_f64 v[5:6], v[15:16], v[51:52]
	v_fmac_f64_e32 v[13:14], v[15:16], v[49:50]
	v_fma_f64 v[5:6], v[23:24], v[49:50], -v[5:6]
	v_add_f64 v[13:14], v[11:12], -v[13:14]
	v_add_f64 v[5:6], v[3:4], -v[5:6]
	v_fma_f64 v[11:12], v[11:12], 2.0, -v[13:14]
	s_waitcnt vmcnt(2)
	v_mul_f64 v[15:16], v[17:18], v[29:30]
	v_mul_f64 v[23:24], v[25:26], v[29:30]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[29:30], v[7:8], v[33:34]
	v_fma_f64 v[15:16], v[25:26], v[27:28], -v[15:16]
	v_mul_f64 v[25:26], v[19:20], v[33:34]
	v_fmac_f64_e32 v[29:30], v[19:20], v[31:32]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[19:20], v[21:22], v[37:38]
	v_fmac_f64_e32 v[23:24], v[17:18], v[27:28]
	v_add_f64 v[15:16], v[1:2], -v[15:16]
	v_fma_f64 v[7:8], v[7:8], v[31:32], -v[25:26]
	v_mul_f64 v[25:26], v[9:10], v[37:38]
	v_fma_f64 v[9:10], v[9:10], v[35:36], -v[19:20]
	v_add_f64 v[17:18], v[55:56], -v[29:30]
	v_add_f64 v[19:20], v[39:40], -v[23:24]
	v_fma_f64 v[23:24], v[3:4], 2.0, -v[5:6]
	v_fma_f64 v[27:28], v[1:2], 2.0, -v[15:16]
	v_add_f64 v[7:8], v[53:54], -v[7:8]
	v_fmac_f64_e32 v[25:26], v[21:22], v[35:36]
	v_add_f64 v[9:10], v[57:58], -v[9:10]
	v_fma_f64 v[29:30], v[39:40], 2.0, -v[19:20]
	v_fma_f64 v[3:4], v[53:54], 2.0, -v[7:8]
	v_add_f64 v[21:22], v[41:42], -v[25:26]
	v_fma_f64 v[25:26], v[55:56], 2.0, -v[17:18]
	v_add_f64 v[31:32], v[13:14], v[7:8]
	v_add_f64 v[33:34], v[19:20], v[9:10]
	v_fma_f64 v[7:8], v[57:58], 2.0, -v[9:10]
	v_add_f64 v[17:18], v[5:6], -v[17:18]
	v_fma_f64 v[1:2], v[41:42], 2.0, -v[21:22]
	v_add_f64 v[9:10], v[15:16], -v[21:22]
	v_add_f64 v[21:22], v[23:24], -v[3:4]
	v_add_f64 v[25:26], v[11:12], -v[25:26]
	v_fma_f64 v[37:38], v[13:14], 2.0, -v[31:32]
	v_fma_f64 v[19:20], v[19:20], 2.0, -v[33:34]
	v_add_f64 v[39:40], v[27:28], -v[7:8]
	v_fma_f64 v[35:36], v[5:6], 2.0, -v[17:18]
	v_add_f64 v[13:14], v[29:30], -v[1:2]
	v_fma_f64 v[15:16], v[15:16], 2.0, -v[9:10]
	v_fma_f64 v[3:4], s[8:9], v[33:34], v[31:32]
	v_fma_f64 v[1:2], s[8:9], v[9:10], v[17:18]
	v_fma_f64 v[41:42], v[23:24], 2.0, -v[21:22]
	v_fma_f64 v[43:44], v[11:12], 2.0, -v[25:26]
	v_fma_f64 v[7:8], s[6:7], v[19:20], v[37:38]
	v_fma_f64 v[27:28], v[27:28], 2.0, -v[39:40]
	v_fma_f64 v[23:24], v[29:30], 2.0, -v[13:14]
	v_fma_f64 v[5:6], s[6:7], v[15:16], v[35:36]
	v_fmac_f64_e32 v[3:4], s[8:9], v[9:10]
	v_add_f64 v[11:12], v[25:26], v[39:40]
	v_add_f64 v[9:10], v[21:22], -v[13:14]
	v_fmac_f64_e32 v[1:2], s[6:7], v[33:34]
	v_fmac_f64_e32 v[7:8], s[8:9], v[15:16]
	v_add_f64 v[13:14], v[41:42], -v[27:28]
	v_add_f64 v[15:16], v[43:44], -v[23:24]
	v_fmac_f64_e32 v[5:6], s[6:7], v[19:20]
	v_fma_f64 v[19:20], v[31:32], 2.0, -v[3:4]
	v_fma_f64 v[23:24], v[25:26], 2.0, -v[11:12]
	v_fma_f64 v[21:22], v[21:22], 2.0, -v[9:10]
	v_fma_f64 v[17:18], v[17:18], 2.0, -v[1:2]
	v_fma_f64 v[27:28], v[37:38], 2.0, -v[7:8]
	v_fma_f64 v[29:30], v[41:42], 2.0, -v[13:14]
	v_fma_f64 v[31:32], v[43:44], 2.0, -v[15:16]
	v_fma_f64 v[25:26], v[35:36], 2.0, -v[5:6]
	v_lshl_add_u32 v33, v45, 4, 0
	ds_write_b128 v33, v[9:12] offset:6144
	ds_write_b128 v33, v[21:24] offset:2048
	ds_write_b128 v33, v[17:20] offset:3072
	ds_write_b128 v33, v[13:16] offset:4096
	ds_write_b128 v33, v[5:8] offset:5120
	ds_write_b128 v33, v[29:32]
	ds_write_b128 v33, v[25:28] offset:1024
	ds_write_b128 v33, v[1:4] offset:7168
.LBB0_68:
	s_or_b64 exec, exec, s[0:1]
	v_and_b32_e32 v2, 3, v0
	v_or_b32_e32 v1, s19, v2
	v_add_u32_e32 v3, -1, v1
	s_movk_i32 s0, 0xff
	v_cmp_gt_u32_e32 vcc, s0, v3
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_70
; %bb.69:
	v_lshrrev_b32_e32 v7, 2, v0
	v_lshlrev_b32_e32 v11, 9, v2
	v_or_b32_e32 v3, v11, v7
	v_lshl_add_u32 v8, v3, 4, 0
	ds_read_b128 v[3:6], v8
	s_mov_b32 s8, 0x20000
	v_lshl_add_u32 v19, v7, 9, v1
	v_cmp_lt_u32_e64 s[0:1], s8, v19
	v_mov_b32_e32 v16, 0
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v12, 0x80000000, v6
	v_cndmask_b32_e64 v6, v6, v12, s[0:1]
	v_sub_u32_e32 v12, 0x40000, v19
	v_cndmask_b32_e64 v15, v19, v12, s[0:1]
	v_or_b32_e32 v12, 0x200, v0
	v_lshlrev_b64 v[17:18], 4, v[15:16]
	v_lshrrev_b32_e32 v15, 2, v12
	v_or_b32_e32 v11, v11, v15
	v_lshl_add_u32 v11, v11, 4, 0
	ds_read_b128 v[7:10], v8 offset:4096
	ds_read_b128 v[11:14], v11
	v_mov_b32_e32 v20, s3
	v_add_co_u32_e64 v17, s[0:1], s2, v17
	v_addc_co_u32_e64 v18, s[0:1], v20, v18, s[0:1]
	global_store_dwordx4 v[17:18], v[3:6], off
	s_nop 1
	v_lshl_add_u32 v3, v15, 9, v1
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v4, 0x80000000, v14
	v_cmp_lt_u32_e64 s[0:1], s8, v3
	v_cndmask_b32_e64 v14, v14, v4, s[0:1]
	v_sub_u32_e32 v4, 0x40000, v3
	v_cndmask_b32_e64 v15, v3, v4, s[0:1]
	v_lshlrev_b64 v[3:4], 4, v[15:16]
	v_add_co_u32_e64 v3, s[0:1], s2, v3
	v_addc_co_u32_e64 v4, s[0:1], v20, v4, s[0:1]
	global_store_dwordx4 v[3:4], v[11:14], off
	v_add_u32_e32 v3, 0x20000, v19
	v_xor_b32_e32 v4, 0x80000000, v10
	v_cmp_lt_u32_e64 s[0:1], s8, v3
	v_cndmask_b32_e64 v10, v10, v4, s[0:1]
	v_sub_u32_e32 v4, 0x20000, v19
	v_cndmask_b32_e64 v15, v3, v4, s[0:1]
	v_lshlrev_b64 v[3:4], 4, v[15:16]
	v_add_co_u32_e64 v3, s[0:1], s2, v3
	v_addc_co_u32_e64 v4, s[0:1], v20, v4, s[0:1]
	global_store_dwordx4 v[3:4], v[7:10], off
.LBB0_70:
	s_or_b64 exec, exec, s[6:7]
	s_movk_i32 s0, 0x200
	v_cmp_gt_u32_e64 s[0:1], s0, v0
	s_and_saveexec_b64 s[6:7], s[0:1]
	s_cbranch_execz .LBB0_73
; %bb.71:
	s_and_b64 exec, exec, vcc
	s_cbranch_execz .LBB0_73
; %bb.72:
	v_or_b32_e32 v3, 0x600, v0
	v_lshrrev_b32_e32 v6, 2, v3
	v_lshlrev_b32_e32 v3, 4, v6
	v_lshl_or_b32 v2, v2, 13, v3
	v_add_u32_e32 v2, 0, v2
	ds_read_b128 v[2:5], v2
	s_mov_b32 s0, 0x20000
	v_lshl_add_u32 v1, v6, 9, v1
	v_sub_u32_e32 v6, 0x40000, v1
	v_cmp_lt_u32_e32 vcc, s0, v1
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v7, 0x80000000, v5
	v_cndmask_b32_e32 v5, v5, v7, vcc
	v_cndmask_b32_e32 v6, v1, v6, vcc
	v_mov_b32_e32 v7, 0
	v_lshlrev_b64 v[6:7], 4, v[6:7]
	v_mov_b32_e32 v1, s3
	v_add_co_u32_e32 v6, vcc, s2, v6
	v_addc_co_u32_e32 v7, vcc, v1, v7, vcc
	global_store_dwordx4 v[6:7], v[2:5], off
.LBB0_73:
	s_or_b64 exec, exec, s[6:7]
	s_cmp_eq_u32 s18, 0
	s_movk_i32 s6, 0x101
	s_cselect_b64 s[0:1], -1, 0
	v_cmp_gt_u32_e32 vcc, s6, v0
	s_and_b64 s[0:1], s[0:1], vcc
	s_and_saveexec_b64 s[6:7], s[0:1]
	s_cbranch_execz .LBB0_81
; %bb.74:
	v_lshl_add_u32 v1, v0, 4, 0
	ds_read_b128 v[1:4], v1
	s_movk_i32 s0, 0xff
	v_cmp_lt_i32_e32 vcc, s0, v0
	s_and_saveexec_b64 s[0:1], vcc
	s_xor_b64 s[0:1], exec, s[0:1]
	s_cbranch_execz .LBB0_76
; %bb.75:
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v4, 0x80000000, v4
	v_mov_b32_e32 v0, 0x100000
	global_store_dwordx4 v0, v[1:4], s[2:3]
                                        ; implicit-def: $vgpr1_vgpr2
                                        ; implicit-def: $vgpr0
.LBB0_76:
	s_andn2_saveexec_b64 s[0:1], s[0:1]
	s_cbranch_execz .LBB0_81
; %bb.77:
	v_cmp_ne_u32_e32 vcc, 0, v0
	s_and_saveexec_b64 s[0:1], vcc
	s_xor_b64 s[0:1], exec, s[0:1]
	s_cbranch_execz .LBB0_79
; %bb.78:
	v_lshlrev_b32_e32 v9, 4, v0
	global_load_dwordx4 v[5:8], v9, s[4:5]
	v_sub_u32_e32 v9, 0, v9
	ds_read_b128 v[9:12], v9 offset:8192
	s_waitcnt lgkmcnt(0)
	v_add_f64 v[13:14], v[3:4], v[11:12]
	v_add_f64 v[15:16], v[1:2], -v[9:10]
	v_add_f64 v[1:2], v[1:2], v[9:10]
	v_add_f64 v[9:10], v[3:4], -v[11:12]
	v_mul_f64 v[13:14], v[13:14], 0.5
	v_mul_f64 v[15:16], v[15:16], 0.5
	s_waitcnt vmcnt(0)
	v_mul_f64 v[17:18], v[5:6], v[13:14]
	v_mul_f64 v[5:6], v[15:16], v[5:6]
	v_fmac_f64_e32 v[17:18], v[15:16], v[7:8]
	v_fma_f64 v[3:4], v[13:14], v[7:8], -v[5:6]
	v_fma_f64 v[5:6], 0.5, v[1:2], v[17:18]
	v_fma_f64 v[7:8], 0.5, v[9:10], v[3:4]
	v_fma_f64 v[1:2], v[1:2], 0.5, -v[17:18]
	v_fmac_f64_e32 v[3:4], -0.5, v[9:10]
	v_sub_u32_e32 v9, 0x200, v0
	v_lshlrev_b32_e32 v0, 12, v0
	v_lshlrev_b32_e32 v9, 12, v9
	global_store_dwordx4 v0, v[5:8], s[2:3]
	global_store_dwordx4 v9, v[1:4], s[2:3]
                                        ; implicit-def: $vgpr1_vgpr2
.LBB0_79:
	s_andn2_saveexec_b64 s[0:1], s[0:1]
	s_cbranch_execz .LBB0_81
; %bb.80:
	s_waitcnt lgkmcnt(0)
	v_add_f64 v[5:6], v[1:2], v[3:4]
	v_add_f64 v[0:1], v[1:2], -v[3:4]
	v_mov_b32_e32 v7, 0
	v_mov_b32_e32 v8, v7
	v_mov_b32_e32 v4, 0x200000
	v_mov_b32_e32 v2, v7
	v_mov_b32_e32 v3, v7
	global_store_dwordx4 v7, v[5:8], s[2:3]
	global_store_dwordx4 v4, v[0:3], s[2:3]
.LBB0_81:
	s_endpgm
	.section	.rodata,#alloc
	.p2align	6, 0x0
	.amdhsa_kernel fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg
		.amdhsa_group_segment_fixed_size 0
		.amdhsa_private_segment_fixed_size 0
		.amdhsa_kernarg_size 120
		.amdhsa_user_sgpr_count 6
		.amdhsa_user_sgpr_private_segment_buffer 1
		.amdhsa_user_sgpr_dispatch_ptr 0
		.amdhsa_user_sgpr_queue_ptr 0
		.amdhsa_user_sgpr_kernarg_segment_ptr 1
		.amdhsa_user_sgpr_dispatch_id 0
		.amdhsa_user_sgpr_flat_scratch_init 0
		.amdhsa_user_sgpr_private_segment_size 0
		.amdhsa_uses_dynamic_stack 0
		.amdhsa_system_sgpr_private_segment_wavefront_offset 0
		.amdhsa_system_sgpr_workgroup_id_x 1
		.amdhsa_system_sgpr_workgroup_id_y 0
		.amdhsa_system_sgpr_workgroup_id_z 0
		.amdhsa_system_sgpr_workgroup_info 0
		.amdhsa_system_vgpr_workitem_id 0
		.amdhsa_next_free_vgpr 60
		.amdhsa_next_free_sgpr 20
		.amdhsa_reserve_flat_scratch 0
		.amdhsa_reserve_xnack_mask 1
		.amdhsa_float_round_mode_32 0
		.amdhsa_float_round_mode_16_64 0
		.amdhsa_float_denorm_mode_32 3
		.amdhsa_float_denorm_mode_16_64 3
		.amdhsa_dx10_clamp 1
		.amdhsa_ieee_mode 1
		.amdhsa_fp16_overflow 0
		.amdhsa_exception_fp_ieee_invalid_op 0
		.amdhsa_exception_fp_denorm_src 0
		.amdhsa_exception_fp_ieee_div_zero 0
		.amdhsa_exception_fp_ieee_overflow 0
		.amdhsa_exception_fp_ieee_underflow 0
		.amdhsa_exception_fp_ieee_inexact 0
		.amdhsa_exception_int_div_zero 0
	.end_amdhsa_kernel
	.text
.Lfunc_end0:
	.size	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg, .Lfunc_end0-fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg
                                        ; -- End function
	.section	.AMDGPU.csdata
; Kernel info:
; codeLenInByte = 7924
; NumSgprs: 24
; NumVgprs: 60
; ScratchSize: 0
; MemoryBound: 0
; FloatMode: 240
; IeeeMode: 1
; LDSByteSize: 0 bytes/workgroup (compile time only)
; SGPRBlocks: 2
; VGPRBlocks: 14
; NumSGPRsForWavesPerEU: 24
; NumVGPRsForWavesPerEU: 60
; Occupancy: 4
; WaveLimiterHint : 1
; COMPUTE_PGM_RSRC2:SCRATCH_EN: 0
; COMPUTE_PGM_RSRC2:USER_SGPR: 6
; COMPUTE_PGM_RSRC2:TRAP_HANDLER: 0
; COMPUTE_PGM_RSRC2:TGID_X_EN: 1
; COMPUTE_PGM_RSRC2:TGID_Y_EN: 0
; COMPUTE_PGM_RSRC2:TGID_Z_EN: 0
; COMPUTE_PGM_RSRC2:TIDIG_COMP_CNT: 0
	.ident	"clang version 17.0.0 (http://112.11.119.99:55080/dcutoolkit/driverruntime/llvm-project.git ff5bf917a679c83afe927af051a20b86fef7b07d)"
	.section	".note.GNU-stack"
	.addrsig
	.amdgpu_metadata
---
amdhsa.kernels:
  - .args:
      - .actual_access:  read_only
        .address_space:  global
        .offset:         0
        .size:           8
        .value_kind:     global_buffer
      - .offset:         8
        .size:           8
        .value_kind:     by_value
      - .actual_access:  read_only
        .address_space:  global
        .offset:         16
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         24
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         32
        .size:           8
        .value_kind:     global_buffer
      - .offset:         40
        .size:           8
        .value_kind:     by_value
      - .actual_access:  read_only
        .address_space:  global
        .offset:         48
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         56
        .size:           8
        .value_kind:     global_buffer
      - .offset:         64
        .size:           4
        .value_kind:     by_value
      - .actual_access:  read_only
        .address_space:  global
        .offset:         72
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         80
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         88
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  write_only
        .address_space:  global
        .offset:         96
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         104
        .size:           8
        .value_kind:     global_buffer
      - .actual_access:  read_only
        .address_space:  global
        .offset:         112
        .size:           8
        .value_kind:     global_buffer
    .fp64_status:    0
    .group_segment_fixed_size: 0
    .kernarg_segment_align: 8
    .kernarg_segment_size: 120
    .language:       OpenCL C
    .language_version:
      - 2
      - 0
    .max_flat_workgroup_size: 512
    .name:           fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg
    .private_segment_fixed_size: 0
    .sgpr_count:     24
    .sgpr_spill_count: 0
    .symbol:         fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v2_role7_C256_Q512_N262144_reg.kd
    .uniform_work_group_size: 1
    .uses_dynamic_stack: false
    .vgpr_count:     60
    .vgpr_spill_count: 0
    .wavefront_size: 64
amdhsa.target:   'amdgcn-amd-amdhsa--gfx936:sramecc+'
amdhsa.version:
  - 1
  - 2
...

	.end_amdgpu_metadata
