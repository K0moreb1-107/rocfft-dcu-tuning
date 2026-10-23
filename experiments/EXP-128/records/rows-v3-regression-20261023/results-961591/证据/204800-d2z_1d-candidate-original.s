	.text
	.amdgcn_target "amdgcn-amd-amdhsa--gfx936:sramecc+"
	.protected	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg ; -- Begin function fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg
	.globl	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg
	.p2align	8
	.type	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg,@function
fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg: ; @fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg
; %bb.0:
	s_load_dwordx2 s[0:1], s[4:5], 0x10
                                        ; implicit-def: $vgpr35
                                        ; implicit-def: $vgpr33
	s_waitcnt lgkmcnt(0)
	s_load_dword s0, s[0:1], 0x8
	s_waitcnt lgkmcnt(0)
	s_add_i32 s0, s0, -1
	s_mul_hi_u32 s0, s0, 0xcccccccd
	s_lshr_b32 s0, s0, 3
	s_add_i32 s1, s0, 1
	v_cvt_f32_u32_e32 v1, s1
	s_not_b32 s0, s0
	v_rcp_iflag_f32_e32 v2, v1
	v_and_b32_e32 v1, 0xffff, v0
	v_mul_u32_u24_e32 v3, 0xcccd, v1
	v_lshrrev_b32_e32 v36, 21, v3
	v_mul_f32_e32 v2, 0x4f7ffffe, v2
	v_cvt_u32_f32_e32 v2, v2
	v_readfirstlane_b32 s2, v2
	s_mul_i32 s0, s0, s2
	s_mul_hi_u32 s0, s2, s0
	s_add_i32 s2, s2, s0
	s_mul_hi_u32 s0, s6, s2
	s_mul_i32 s0, s0, s1
	s_sub_i32 s0, s6, s0
	s_sub_i32 s2, s0, s1
	s_cmp_ge_u32 s0, s1
	s_cselect_b32 s0, s2, s0
	s_sub_i32 s2, s0, s1
	s_cmp_ge_u32 s0, s1
	s_cselect_b32 s16, s2, s0
	s_mul_i32 s17, s16, 10
	v_add_u32_e32 v34, s17, v36
	s_movk_i32 s0, 0x1ff
	v_cmp_lt_u32_e32 vcc, s0, v34
                                        ; implicit-def: $sgpr0_sgpr1
	s_and_saveexec_b64 s[2:3], vcc
	s_xor_b64 s[2:3], exec, s[2:3]
; %bb.1:
	v_mul_u32_u24_e32 v1, 0x667, v1
	v_mov_b32_e32 v2, 40
	v_mul_lo_u16_sdwa v1, v1, v2 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:WORD_1 src1_sel:DWORD
	v_sub_u16_e32 v35, v0, v1
	v_sub_u16_e32 v33, v0, v1
	s_mov_b64 s[0:1], 0
                                        ; implicit-def: $vgpr36
; %bb.2:
	s_or_saveexec_b64 s[6:7], s[2:3]
	s_load_dwordx2 s[2:3], s[4:5], 0x0
	v_mov_b64_e32 v[5:6], s[0:1]
	v_mov_b64_e32 v[1:2], s[0:1]
	v_mov_b64_e32 v[21:22], s[0:1]
	v_mov_b64_e32 v[17:18], s[0:1]
	v_mov_b64_e32 v[31:32], s[0:1]
	v_mov_b64_e32 v[27:28], s[0:1]
	v_mov_b64_e32 v[23:24], s[0:1]
	v_mov_b64_e32 v[19:20], s[0:1]
	v_mov_b64_e32 v[7:8], s[0:1]
	v_mov_b64_e32 v[3:4], s[0:1]
	v_mov_b64_e32 v[29:30], s[0:1]
	v_mov_b64_e32 v[25:26], s[0:1]
	v_mov_b64_e32 v[15:16], s[0:1]
	v_mov_b64_e32 v[13:14], s[0:1]
	v_mov_b64_e32 v[11:12], s[0:1]
	v_mov_b64_e32 v[9:10], s[0:1]
	s_xor_b64 exec, exec, s[6:7]
	s_cbranch_execz .LBB0_12
; %bb.3:
	s_load_dwordx2 s[8:9], s[4:5], 0x58
	v_mul_lo_u16_e32 v1, 40, v36
	v_sub_u16_e32 v33, v0, v1
	v_cmp_ne_u32_e64 s[0:1], 0, v34
	v_cmp_gt_u16_e32 vcc, 25, v33
                                        ; implicit-def: $vgpr9_vgpr10
                                        ; implicit-def: $vgpr13_vgpr14
                                        ; implicit-def: $vgpr25_vgpr26
                                        ; implicit-def: $vgpr29_vgpr30
                                        ; implicit-def: $vgpr3_vgpr4
                                        ; implicit-def: $vgpr7_vgpr8
                                        ; implicit-def: $vgpr19_vgpr20
                                        ; implicit-def: $vgpr23_vgpr24
	s_and_saveexec_b64 s[10:11], s[0:1]
	s_xor_b64 s[10:11], exec, s[10:11]
	s_cbranch_execz .LBB0_7
; %bb.4:
	v_mov_b64_e32 v[9:10], 0
	v_mov_b64_e32 v[13:14], v[9:10]
	v_mov_b64_e32 v[25:26], v[9:10]
	v_mov_b64_e32 v[29:30], v[9:10]
	v_mov_b64_e32 v[3:4], v[9:10]
	v_mov_b64_e32 v[7:8], v[9:10]
	v_mov_b64_e32 v[19:20], v[9:10]
	v_mov_b64_e32 v[23:24], v[9:10]
	v_mov_b64_e32 v[27:28], v[9:10]
	v_mov_b64_e32 v[31:32], v[9:10]
	v_mov_b64_e32 v[11:12], v[9:10]
	v_mov_b64_e32 v[15:16], v[9:10]
	v_mov_b64_e32 v[17:18], v[9:10]
	v_mov_b64_e32 v[21:22], v[9:10]
	v_mov_b64_e32 v[1:2], v[9:10]
	v_mov_b64_e32 v[5:6], v[9:10]
	s_and_saveexec_b64 s[12:13], vcc
	s_cbranch_execz .LBB0_6
; %bb.5:
	v_mul_lo_u32 v9, v34, v33
	s_load_dwordx2 s[14:15], s[4:5], 0x70
	s_mov_b32 s0, 0
	v_mov_b32_e32 v10, 4
	v_lshlrev_b32_sdwa v1, v10, v9 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v2, s0, v9, 8
	s_movk_i32 s1, 0x1000
	v_lshl_or_b32 v2, v2, 4, s1
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[3:6], v1, s[14:15]
	global_load_dwordx4 v[15:18], v2, s[14:15]
	v_mul_lo_u32 v11, v34, 25
	v_mov_b32_e32 v14, 0x1000
	s_movk_i32 s1, 0x2000
	v_mov_b32_e32 v59, 0x2000
	v_add_u32_e32 v13, v9, v11
	v_lshlrev_b32_sdwa v1, v10, v13 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v2, 0, v13, 8
	v_lshl_or_b32 v2, v2, 4, v14
	global_load_dwordx4 v[19:22], v1, s[14:15]
	global_load_dwordx4 v[23:26], v2, s[14:15]
	v_add_u32_e32 v12, v13, v11
	v_alignbit_b32 v2, 0, v12, 8
	v_lshlrev_b32_sdwa v1, v10, v12 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_lshl_or_b32 v35, v2, 4, v14
	global_load_dwordx4 v[27:30], v1, s[14:15]
	v_alignbit_b32 v9, s0, v9, 16
	v_lshl_or_b32 v9, v9, 4, s1
	s_movk_i32 s0, 0xc8
	s_waitcnt vmcnt(3)
	v_mul_f64 v[7:8], v[5:6], v[17:18]
	v_mul_f64 v[31:32], v[3:4], v[17:18]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[17:18], v[21:22], v[25:26]
	v_mul_f64 v[1:2], v[19:20], v[25:26]
	v_fma_f64 v[25:26], v[3:4], v[15:16], -v[7:8]
	v_fmac_f64_e32 v[31:32], v[5:6], v[15:16]
	global_load_dwordx4 v[3:6], v35, s[14:15]
	v_add_u32_e32 v15, v12, v11
	v_lshlrev_b32_sdwa v7, v10, v15 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v8, 0, v15, 8
	v_fma_f64 v[35:36], v[19:20], v[23:24], -v[17:18]
	global_load_dwordx4 v[16:19], v7, s[14:15]
	v_lshl_or_b32 v7, v8, 4, v14
	v_fmac_f64_e32 v[1:2], v[21:22], v[23:24]
	global_load_dwordx4 v[20:23], v7, s[14:15]
	v_add_u32_e32 v55, v15, v11
	v_lshlrev_b32_sdwa v24, v10, v55 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_add_u32_e32 v56, v55, v11
	v_add_u32_e32 v57, v56, v11
	v_lshlrev_b32_sdwa v43, v10, v57 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_add_u32_e32 v58, v57, v11
	v_bfe_u32 v11, v58, 8, 8
	v_lshl_or_b32 v11, v11, 4, v14
	s_waitcnt vmcnt(2)
	v_mul_f64 v[7:8], v[29:30], v[5:6]
	v_mul_f64 v[5:6], v[27:28], v[5:6]
	v_fma_f64 v[7:8], v[27:28], v[3:4], -v[7:8]
	v_fmac_f64_e32 v[5:6], v[29:30], v[3:4]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[27:28], v[18:19], v[22:23]
	v_mul_f64 v[3:4], v[16:17], v[22:23]
	v_alignbit_b32 v22, 0, v55, 8
	v_lshl_or_b32 v29, v22, 4, v14
	v_fma_f64 v[27:28], v[16:17], v[20:21], -v[27:28]
	v_fmac_f64_e32 v[3:4], v[18:19], v[20:21]
	global_load_dwordx4 v[16:19], v24, s[14:15]
	global_load_dwordx4 v[20:23], v29, s[14:15]
	v_lshlrev_b32_sdwa v24, v10, v56 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_lshlrev_b32_sdwa v10, v10, v58 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	s_waitcnt vmcnt(0)
	v_mul_f64 v[29:30], v[18:19], v[22:23]
	v_mul_f64 v[37:38], v[16:17], v[22:23]
	v_fma_f64 v[29:30], v[16:17], v[20:21], -v[29:30]
	v_bfe_u32 v16, v56, 8, 8
	v_fmac_f64_e32 v[37:38], v[18:19], v[20:21]
	v_lshl_or_b32 v39, v16, 4, v14
	global_load_dwordx4 v[16:19], v24, s[14:15]
	global_load_dwordx4 v[20:23], v39, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[39:40], v[18:19], v[22:23]
	v_mul_f64 v[41:42], v[16:17], v[22:23]
	v_fma_f64 v[39:40], v[16:17], v[20:21], -v[39:40]
	v_bfe_u32 v16, v57, 8, 8
	v_fmac_f64_e32 v[41:42], v[18:19], v[20:21]
	v_lshl_or_b32 v24, v16, 4, v14
	global_load_dwordx4 v[16:19], v43, s[14:15]
	global_load_dwordx4 v[20:23], v24, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[43:44], v[18:19], v[22:23]
	v_mul_f64 v[45:46], v[16:17], v[22:23]
	v_fma_f64 v[43:44], v[16:17], v[20:21], -v[43:44]
	v_fmac_f64_e32 v[45:46], v[18:19], v[20:21]
	global_load_dwordx4 v[16:19], v10, s[14:15]
	global_load_dwordx4 v[20:23], v11, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[10:11], v[18:19], v[22:23]
	v_mul_f64 v[49:50], v[16:17], v[22:23]
	v_fma_f64 v[47:48], v[16:17], v[20:21], -v[10:11]
	v_fmac_f64_e32 v[49:50], v[18:19], v[20:21]
	global_load_dwordx4 v[16:19], v9, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[9:10], v[31:32], v[18:19]
	v_mul_f64 v[22:23], v[25:26], v[18:19]
	v_fma_f64 v[20:21], v[16:17], v[25:26], -v[9:10]
	v_alignbit_b32 v9, 0, v13, 16
	v_lshl_or_b32 v9, v9, 4, v59
	v_fmac_f64_e32 v[22:23], v[16:17], v[31:32]
	global_load_dwordx4 v[16:19], v9, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[9:10], v[1:2], v[18:19]
	v_mul_f64 v[18:19], v[35:36], v[18:19]
	v_fma_f64 v[24:25], v[16:17], v[35:36], -v[9:10]
	v_fmac_f64_e32 v[18:19], v[16:17], v[1:2]
	v_alignbit_b32 v1, 0, v12, 16
	v_lshl_or_b32 v1, v1, 4, v59
	global_load_dwordx4 v[9:12], v1, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[1:2], v[5:6], v[11:12]
	v_mul_f64 v[35:36], v[7:8], v[11:12]
	v_fma_f64 v[31:32], v[9:10], v[7:8], -v[1:2]
	v_alignbit_b32 v1, 0, v15, 16
	v_lshl_or_b32 v1, v1, 4, v59
	v_fmac_f64_e32 v[35:36], v[9:10], v[5:6]
	global_load_dwordx4 v[5:8], v1, s[14:15]
	v_mul_lo_u32 v9, v34, s0
	v_mov_b32_e32 v10, s9
	s_waitcnt vmcnt(0)
	v_mul_f64 v[1:2], v[3:4], v[7:8]
	v_mul_f64 v[53:54], v[27:28], v[7:8]
	v_fma_f64 v[51:52], v[5:6], v[27:28], -v[1:2]
	v_alignbit_b32 v1, 0, v55, 16
	v_lshl_or_b32 v1, v1, 4, v59
	v_fmac_f64_e32 v[53:54], v[5:6], v[3:4]
	global_load_dwordx4 v[1:4], v1, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[5:6], v[37:38], v[3:4]
	v_mul_f64 v[13:14], v[29:30], v[3:4]
	v_fma_f64 v[11:12], v[1:2], v[29:30], -v[5:6]
	v_fmac_f64_e32 v[13:14], v[1:2], v[37:38]
	v_mov_b32_e32 v2, 0
	v_add_u32_e32 v1, v9, v33
	v_lshlrev_b64 v[1:2], 4, v[1:2]
	v_add_co_u32_e64 v1, s[0:1], s8, v1
	v_addc_co_u32_e64 v2, s[0:1], v10, v2, s[0:1]
	global_load_dwordx4 v[3:6], v[1:2], off
	s_waitcnt vmcnt(0)
	v_mul_f64 v[7:8], v[5:6], v[22:23]
	v_mul_f64 v[1:2], v[3:4], v[22:23]
	v_fmac_f64_e32 v[1:2], v[5:6], v[20:21]
	v_fma_f64 v[5:6], v[3:4], v[20:21], -v[7:8]
	v_add_co_u32_e64 v3, s[0:1], v9, v33
	v_addc_co_u32_e64 v4, s[0:1], 0, 0, s[0:1]
	v_lshlrev_b64 v[3:4], 4, v[3:4]
	v_add_co_u32_e64 v37, s[0:1], s8, v3
	v_addc_co_u32_e64 v38, s[0:1], v10, v4, s[0:1]
	global_load_dwordx4 v[7:10], v[37:38], off offset:1600
	s_waitcnt vmcnt(0)
	v_mul_f64 v[3:4], v[7:8], v[13:14]
	v_mul_f64 v[13:14], v[9:10], v[13:14]
	v_fmac_f64_e32 v[3:4], v[9:10], v[11:12]
	v_alignbit_b32 v9, 0, v56, 16
	v_lshl_or_b32 v9, v9, 4, v59
	v_fma_f64 v[7:8], v[7:8], v[11:12], -v[13:14]
	global_load_dwordx4 v[9:12], v9, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[13:14], v[41:42], v[11:12]
	v_mul_f64 v[22:23], v[39:40], v[11:12]
	v_fma_f64 v[20:21], v[9:10], v[39:40], -v[13:14]
	global_load_dwordx4 v[11:14], v[37:38], off offset:400
	v_fmac_f64_e32 v[22:23], v[9:10], v[41:42]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[15:16], v[13:14], v[18:19]
	v_mul_f64 v[9:10], v[11:12], v[18:19]
	v_fmac_f64_e32 v[9:10], v[13:14], v[24:25]
	v_fma_f64 v[13:14], v[11:12], v[24:25], -v[15:16]
	global_load_dwordx4 v[15:18], v[37:38], off offset:2000
	s_waitcnt vmcnt(0)
	v_mul_f64 v[11:12], v[15:16], v[22:23]
	v_mul_f64 v[22:23], v[17:18], v[22:23]
	v_fmac_f64_e32 v[11:12], v[17:18], v[20:21]
	v_alignbit_b32 v17, 0, v57, 16
	v_lshl_or_b32 v17, v17, 4, v59
	v_fma_f64 v[15:16], v[15:16], v[20:21], -v[22:23]
	global_load_dwordx4 v[17:20], v17, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[21:22], v[45:46], v[19:20]
	v_mul_f64 v[29:30], v[43:44], v[19:20]
	v_fma_f64 v[27:28], v[17:18], v[43:44], -v[21:22]
	global_load_dwordx4 v[19:22], v[37:38], off offset:800
	v_fmac_f64_e32 v[29:30], v[17:18], v[45:46]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[23:24], v[21:22], v[35:36]
	v_mul_f64 v[17:18], v[19:20], v[35:36]
	v_fmac_f64_e32 v[17:18], v[21:22], v[31:32]
	v_fma_f64 v[21:22], v[19:20], v[31:32], -v[23:24]
	global_load_dwordx4 v[23:26], v[37:38], off offset:2400
	s_waitcnt vmcnt(0)
	v_mul_f64 v[19:20], v[23:24], v[29:30]
	v_mul_f64 v[29:30], v[25:26], v[29:30]
	v_fmac_f64_e32 v[19:20], v[25:26], v[27:28]
	v_alignbit_b32 v25, 0, v58, 16
	v_lshl_or_b32 v25, v25, 4, v59
	v_fma_f64 v[23:24], v[23:24], v[27:28], -v[29:30]
	global_load_dwordx4 v[25:28], v25, s[14:15]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[29:30], v[49:50], v[27:28]
	v_mul_f64 v[31:32], v[47:48], v[27:28]
	v_fma_f64 v[39:40], v[25:26], v[47:48], -v[29:30]
	global_load_dwordx4 v[27:30], v[37:38], off offset:1200
	v_fmac_f64_e32 v[31:32], v[25:26], v[49:50]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[35:36], v[29:30], v[53:54]
	v_mul_f64 v[25:26], v[27:28], v[53:54]
	v_fmac_f64_e32 v[25:26], v[29:30], v[51:52]
	v_fma_f64 v[29:30], v[27:28], v[51:52], -v[35:36]
	global_load_dwordx4 v[35:38], v[37:38], off offset:2800
	s_waitcnt vmcnt(0)
	v_mul_f64 v[27:28], v[35:36], v[31:32]
	v_mul_f64 v[31:32], v[37:38], v[31:32]
	v_fmac_f64_e32 v[27:28], v[37:38], v[39:40]
	v_fma_f64 v[31:32], v[35:36], v[39:40], -v[31:32]
.LBB0_6:
	s_or_b64 exec, exec, s[12:13]
.LBB0_7:
	s_andn2_saveexec_b64 s[0:1], s[10:11]
	s_cbranch_execz .LBB0_11
; %bb.8:
	v_mov_b64_e32 v[9:10], 0
	v_mov_b64_e32 v[13:14], v[9:10]
	v_mov_b64_e32 v[25:26], v[9:10]
	v_mov_b64_e32 v[29:30], v[9:10]
	v_mov_b64_e32 v[3:4], v[9:10]
	v_mov_b64_e32 v[7:8], v[9:10]
	v_mov_b64_e32 v[19:20], v[9:10]
	v_mov_b64_e32 v[23:24], v[9:10]
	v_mov_b64_e32 v[27:28], v[9:10]
	v_mov_b64_e32 v[31:32], v[9:10]
	v_mov_b64_e32 v[11:12], v[9:10]
	v_mov_b64_e32 v[15:16], v[9:10]
	v_mov_b64_e32 v[17:18], v[9:10]
	v_mov_b64_e32 v[21:22], v[9:10]
	v_mov_b64_e32 v[1:2], v[9:10]
	v_mov_b64_e32 v[5:6], v[9:10]
	s_and_saveexec_b64 s[10:11], vcc
	s_cbranch_execz .LBB0_10
; %bb.9:
	v_lshlrev_b32_e32 v35, 5, v33
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[1:4], v35, s[8:9] offset:16
	global_load_dwordx4 v[5:8], v35, s[8:9]
	global_load_dwordx4 v[9:12], v35, s[8:9] offset:816
	global_load_dwordx4 v[13:16], v35, s[8:9] offset:800
	global_load_dwordx4 v[17:20], v35, s[8:9] offset:1616
	global_load_dwordx4 v[21:24], v35, s[8:9] offset:1600
	global_load_dwordx4 v[25:28], v35, s[8:9] offset:2416
	global_load_dwordx4 v[29:32], v35, s[8:9] offset:2400
.LBB0_10:
	s_or_b64 exec, exec, s[10:11]
.LBB0_11:
	s_or_b64 exec, exec, s[0:1]
	v_mov_b32_e32 v35, v33
.LBB0_12:
	s_or_b64 exec, exec, s[6:7]
	s_mov_b32 s0, 0xcccccccd
	v_mul_hi_u32 v36, v34, s0
	s_load_dwordx2 s[0:1], s[4:5], 0x60
	v_cmp_gt_u16_e32 vcc, 25, v35
	v_lshrrev_b32_e32 v36, 3, v36
	v_mul_lo_u32 v36, v36, 10
	v_sub_u32_e32 v34, v34, v36
	v_mul_u32_u24_e32 v34, 0xc8, v34
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_14
; %bb.13:
	s_waitcnt vmcnt(6)
	v_add_f64 v[7:8], v[5:6], -v[7:8]
	v_add_f64 v[3:4], v[1:2], -v[3:4]
	s_waitcnt vmcnt(2)
	v_add_f64 v[23:24], v[21:22], -v[23:24]
	v_add_f64 v[19:20], v[17:18], -v[19:20]
	v_add_f64 v[15:16], v[13:14], -v[15:16]
	v_add_f64 v[11:12], v[9:10], -v[11:12]
	s_waitcnt vmcnt(0)
	v_add_f64 v[31:32], v[29:30], -v[31:32]
	v_add_f64 v[27:28], v[25:26], -v[27:28]
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[7:8]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[3:4]
	v_fma_f64 v[21:22], v[21:22], 2.0, -v[23:24]
	v_fma_f64 v[17:18], v[17:18], 2.0, -v[19:20]
	v_fma_f64 v[13:14], v[13:14], 2.0, -v[15:16]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[11:12]
	v_fma_f64 v[29:30], v[29:30], 2.0, -v[31:32]
	v_fma_f64 v[25:26], v[25:26], 2.0, -v[27:28]
	v_add_f64 v[35:36], v[7:8], -v[19:20]
	v_add_f64 v[37:38], v[23:24], v[3:4]
	v_add_f64 v[19:20], v[15:16], -v[27:28]
	v_add_f64 v[23:24], v[31:32], v[11:12]
	v_add_f64 v[27:28], v[5:6], -v[21:22]
	v_add_f64 v[31:32], v[1:2], -v[17:18]
	v_add_f64 v[17:18], v[13:14], -v[29:30]
	v_add_f64 v[21:22], v[9:10], -v[25:26]
	v_fma_f64 v[25:26], v[7:8], 2.0, -v[35:36]
	v_fma_f64 v[29:30], v[3:4], 2.0, -v[37:38]
	v_fma_f64 v[15:16], v[15:16], 2.0, -v[19:20]
	v_fma_f64 v[39:40], v[11:12], 2.0, -v[23:24]
	s_waitcnt lgkmcnt(0)
	s_mov_b32 s8, 0x667f3bcd
	v_fma_f64 v[41:42], v[5:6], 2.0, -v[27:28]
	v_fma_f64 v[43:44], v[1:2], 2.0, -v[31:32]
	v_fma_f64 v[11:12], v[13:14], 2.0, -v[17:18]
	v_fma_f64 v[13:14], v[9:10], 2.0, -v[21:22]
	s_mov_b32 s9, 0xbfe6a09e
	v_fma_f64 v[1:2], s[8:9], v[15:16], v[25:26]
	v_fma_f64 v[3:4], s[8:9], v[39:40], v[29:30]
	s_mov_b32 s11, 0x3fe6a09e
	s_mov_b32 s10, s8
	v_fma_f64 v[5:6], s[10:11], v[19:20], v[35:36]
	v_fma_f64 v[7:8], s[10:11], v[23:24], v[37:38]
	v_add_f64 v[9:10], v[41:42], -v[11:12]
	v_add_f64 v[11:12], v[43:44], -v[13:14]
	v_fmac_f64_e32 v[1:2], s[8:9], v[39:40]
	v_fmac_f64_e32 v[3:4], s[10:11], v[15:16]
	v_add_f64 v[13:14], v[27:28], -v[21:22]
	v_add_f64 v[15:16], v[31:32], v[17:18]
	v_fmac_f64_e32 v[5:6], s[8:9], v[23:24]
	v_fmac_f64_e32 v[7:8], s[10:11], v[19:20]
	v_fma_f64 v[17:18], v[41:42], 2.0, -v[9:10]
	v_fma_f64 v[19:20], v[43:44], 2.0, -v[11:12]
	v_fma_f64 v[21:22], v[25:26], 2.0, -v[1:2]
	v_fma_f64 v[23:24], v[29:30], 2.0, -v[3:4]
	v_fma_f64 v[25:26], v[27:28], 2.0, -v[13:14]
	v_fma_f64 v[27:28], v[31:32], 2.0, -v[15:16]
	v_fma_f64 v[29:30], v[35:36], 2.0, -v[5:6]
	v_fma_f64 v[31:32], v[37:38], 2.0, -v[7:8]
	v_lshl_add_u32 v35, v33, 3, v34
	v_lshl_add_u32 v35, v35, 4, 0
	ds_write_b128 v35, v[17:20]
	ds_write_b128 v35, v[21:24] offset:16
	ds_write_b128 v35, v[25:28] offset:32
	ds_write_b128 v35, v[29:32] offset:48
	ds_write_b128 v35, v[9:12] offset:64
	ds_write_b128 v35, v[1:4] offset:80
	ds_write_b128 v35, v[13:16] offset:96
	ds_write_b128 v35, v[5:8] offset:112
.LBB0_14:
	s_or_b64 exec, exec, s[6:7]
	s_waitcnt vmcnt(3)
	v_and_b32_e32 v19, 7, v33
	v_lshlrev_b32_e32 v17, 6, v19
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[13:16], v17, s[2:3]
	global_load_dwordx4 v[5:8], v17, s[2:3] offset:16
	global_load_dwordx4 v[1:4], v17, s[2:3] offset:32
	global_load_dwordx4 v[9:12], v17, s[2:3] offset:48
	v_add_u32_e32 v20, v34, v33
	s_waitcnt vmcnt(6)
	v_lshrrev_b32_e32 v21, 3, v33
	v_lshl_add_u32 v63, v20, 4, 0
	s_waitcnt vmcnt(0) lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	v_lshlrev_b32_e32 v17, 2, v33
	v_mov_b32_e32 v18, 0
	v_mul_u32_u24_e32 v44, 40, v21
	ds_read_b128 v[20:23], v63
	ds_read_b128 v[24:27], v63 offset:640
	ds_read_b128 v[28:31], v63 offset:1280
	ds_read_b128 v[35:38], v63 offset:1920
	ds_read_b128 v[39:42], v63 offset:2560
	v_lshlrev_b64 v[32:33], 4, v[17:18]
	v_mov_b32_e32 v43, s3
	v_add_co_u32_e32 v32, vcc, s2, v32
	v_or_b32_e32 v17, v44, v19
	v_addc_co_u32_e32 v33, vcc, v43, v33, vcc
	s_mov_b32 s8, 0x134454ff
	s_mov_b32 s9, 0x3fee6f0e
	s_mov_b32 s11, 0xbfee6f0e
	s_mov_b32 s10, s8
	s_mov_b32 s6, 0x4755a5e
	s_mov_b32 s7, 0x3fe2cf23
	s_mov_b32 s13, 0xbfe2cf23
	s_mov_b32 s12, s6
	s_mov_b32 s2, 0x372fe950
	s_mov_b32 s3, 0x3fd3c6ef
	v_add_u32_e32 v17, v34, v17
	v_lshl_add_u32 v17, v17, 4, 0
	s_waitcnt lgkmcnt(3)
	v_mul_f64 v[43:44], v[26:27], v[15:16]
	v_mul_f64 v[15:16], v[24:25], v[15:16]
	s_waitcnt lgkmcnt(2)
	v_mul_f64 v[45:46], v[30:31], v[7:8]
	s_waitcnt lgkmcnt(1)
	v_mul_f64 v[47:48], v[37:38], v[3:4]
	s_waitcnt lgkmcnt(0)
	v_mul_f64 v[49:50], v[39:40], v[11:12]
	v_mul_f64 v[11:12], v[41:42], v[11:12]
	v_mul_f64 v[53:54], v[35:36], v[3:4]
	v_mul_f64 v[51:52], v[28:29], v[7:8]
	v_fma_f64 v[43:44], v[24:25], v[13:14], -v[43:44]
	v_fmac_f64_e32 v[15:16], v[26:27], v[13:14]
	v_fma_f64 v[3:4], v[28:29], v[5:6], -v[45:46]
	v_fma_f64 v[26:27], v[35:36], v[1:2], -v[47:48]
	v_fmac_f64_e32 v[49:50], v[41:42], v[9:10]
	v_fma_f64 v[45:46], v[39:40], v[9:10], -v[11:12]
	v_fmac_f64_e32 v[53:54], v[37:38], v[1:2]
	global_load_dwordx4 v[7:10], v[32:33], off offset:528
	global_load_dwordx4 v[11:14], v[32:33], off offset:512
	v_fmac_f64_e32 v[51:52], v[30:31], v[5:6]
	v_add_f64 v[39:40], v[22:23], v[15:16]
	v_add_f64 v[24:25], v[43:44], -v[3:4]
	v_add_f64 v[1:2], v[3:4], v[26:27]
	v_add_f64 v[47:48], v[15:16], -v[49:50]
	v_add_f64 v[28:29], v[45:46], -v[26:27]
	v_add_f64 v[30:31], v[43:44], v[45:46]
	v_add_f64 v[35:36], v[3:4], -v[43:44]
	v_add_f64 v[37:38], v[26:27], -v[45:46]
	v_add_f64 v[5:6], v[20:21], v[43:44]
	v_add_f64 v[41:42], v[51:52], v[53:54]
	v_fma_f64 v[1:2], -0.5, v[1:2], v[20:21]
	v_add_f64 v[55:56], v[15:16], -v[51:52]
	v_add_f64 v[59:60], v[24:25], v[28:29]
	v_fmac_f64_e32 v[20:21], -0.5, v[30:31]
	v_add_f64 v[28:29], v[15:16], v[49:50]
	v_add_f64 v[61:62], v[35:36], v[37:38]
	v_add_f64 v[35:36], v[39:40], v[51:52]
	v_add_f64 v[37:38], v[51:52], -v[53:54]
	v_fma_f64 v[24:25], s[8:9], v[47:48], v[1:2]
	v_fmac_f64_e32 v[1:2], s[10:11], v[47:48]
	v_add_f64 v[57:58], v[49:50], -v[53:54]
	v_add_f64 v[15:16], v[51:52], -v[15:16]
	v_add_f64 v[30:31], v[53:54], -v[49:50]
	v_add_f64 v[5:6], v[5:6], v[3:4]
	v_add_f64 v[51:52], v[3:4], -v[26:27]
	v_fma_f64 v[3:4], -0.5, v[41:42], v[22:23]
	v_fmac_f64_e32 v[22:23], -0.5, v[28:29]
	v_add_f64 v[53:54], v[35:36], v[53:54]
	v_fma_f64 v[28:29], s[10:11], v[37:38], v[20:21]
	v_fmac_f64_e32 v[20:21], s[8:9], v[37:38]
	v_fmac_f64_e32 v[24:25], s[6:7], v[37:38]
	v_fmac_f64_e32 v[1:2], s[12:13], v[37:38]
	global_load_dwordx4 v[35:38], v[32:33], off offset:544
	global_load_dwordx4 v[39:42], v[32:33], off offset:560
	v_add_f64 v[32:33], v[43:44], -v[45:46]
	v_add_f64 v[5:6], v[5:6], v[26:27]
	v_add_f64 v[15:16], v[15:16], v[30:31]
	v_fma_f64 v[30:31], s[8:9], v[51:52], v[22:23]
	v_fmac_f64_e32 v[22:23], s[10:11], v[51:52]
	v_add_f64 v[55:56], v[55:56], v[57:58]
	v_fmac_f64_e32 v[28:29], s[6:7], v[47:48]
	v_fmac_f64_e32 v[20:21], s[12:13], v[47:48]
	v_fma_f64 v[26:27], s[10:11], v[32:33], v[3:4]
	v_fmac_f64_e32 v[3:4], s[8:9], v[32:33]
	v_add_f64 v[43:44], v[5:6], v[45:46]
	v_fmac_f64_e32 v[30:31], s[12:13], v[32:33]
	v_fmac_f64_e32 v[22:23], s[6:7], v[32:33]
	v_add_f64 v[45:46], v[53:54], v[49:50]
	v_fmac_f64_e32 v[24:25], s[2:3], v[59:60]
	v_fmac_f64_e32 v[28:29], s[2:3], v[61:62]
	v_fmac_f64_e32 v[26:27], s[12:13], v[51:52]
	v_fmac_f64_e32 v[3:4], s[6:7], v[51:52]
	v_fmac_f64_e32 v[20:21], s[2:3], v[61:62]
	v_fmac_f64_e32 v[30:31], s[2:3], v[15:16]
	v_fmac_f64_e32 v[22:23], s[2:3], v[15:16]
	v_fmac_f64_e32 v[1:2], s[2:3], v[59:60]
	s_waitcnt vmcnt(0) lgkmcnt(0)
	s_barrier
	v_fmac_f64_e32 v[26:27], s[2:3], v[55:56]
	v_fmac_f64_e32 v[3:4], s[2:3], v[55:56]
	s_waitcnt lgkmcnt(0)
	ds_write_b128 v17, v[43:46]
	ds_write_b128 v17, v[24:27] offset:128
	ds_write_b128 v17, v[28:31] offset:256
	ds_write_b128 v17, v[20:23] offset:384
	ds_write_b128 v17, v[1:4] offset:512
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	ds_read_b128 v[1:4], v63 offset:640
	ds_read_b128 v[19:22], v63
	ds_read_b128 v[23:26], v63 offset:1280
	ds_read_b128 v[27:30], v63 offset:1920
	ds_read_b128 v[31:34], v63 offset:2560
	s_waitcnt lgkmcnt(2)
	v_mul_f64 v[15:16], v[25:26], v[9:10]
	v_mul_f64 v[5:6], v[3:4], v[13:14]
	v_mul_f64 v[13:14], v[1:2], v[13:14]
	v_mul_f64 v[9:10], v[23:24], v[9:10]
	v_fma_f64 v[1:2], v[1:2], v[11:12], -v[5:6]
	v_fmac_f64_e32 v[13:14], v[3:4], v[11:12]
	v_fma_f64 v[3:4], v[23:24], v[7:8], -v[15:16]
	v_fmac_f64_e32 v[9:10], v[25:26], v[7:8]
	v_add_f64 v[7:8], v[19:20], v[1:2]
	v_add_f64 v[49:50], v[13:14], -v[9:10]
	v_add_f64 v[55:56], v[9:10], -v[13:14]
	v_add_f64 v[7:8], v[7:8], v[3:4]
	s_waitcnt lgkmcnt(1)
	v_mul_f64 v[43:44], v[29:30], v[37:38]
	v_mul_f64 v[37:38], v[27:28], v[37:38]
	s_waitcnt lgkmcnt(0)
	v_mul_f64 v[45:46], v[31:32], v[41:42]
	v_mul_f64 v[41:42], v[33:34], v[41:42]
	v_fma_f64 v[5:6], v[27:28], v[35:36], -v[43:44]
	v_fmac_f64_e32 v[37:38], v[29:30], v[35:36]
	v_fmac_f64_e32 v[45:46], v[33:34], v[39:40]
	v_fma_f64 v[15:16], v[31:32], v[39:40], -v[41:42]
	v_add_f64 v[39:40], v[21:22], v[13:14]
	v_add_f64 v[27:28], v[1:2], -v[3:4]
	v_add_f64 v[33:34], v[3:4], -v[1:2]
	v_add_f64 v[11:12], v[3:4], v[5:6]
	v_add_f64 v[41:42], v[9:10], v[37:38]
	v_add_f64 v[53:54], v[13:14], v[45:46]
	v_add_f64 v[31:32], v[1:2], v[15:16]
	v_add_f64 v[23:24], v[13:14], -v[45:46]
	v_add_f64 v[43:44], v[1:2], -v[15:16]
	v_add_f64 v[47:48], v[3:4], -v[5:6]
	v_add_f64 v[25:26], v[9:10], -v[37:38]
	v_fma_f64 v[1:2], -0.5, v[11:12], v[19:20]
	v_fma_f64 v[3:4], -0.5, v[41:42], v[21:22]
	v_add_f64 v[29:30], v[15:16], -v[5:6]
	v_add_f64 v[35:36], v[5:6], -v[15:16]
	v_fmac_f64_e32 v[19:20], -0.5, v[31:32]
	v_add_f64 v[11:12], v[39:40], v[9:10]
	v_fmac_f64_e32 v[21:22], -0.5, v[53:54]
	v_add_f64 v[51:52], v[45:46], -v[37:38]
	v_add_f64 v[13:14], v[7:8], v[5:6]
	v_fma_f64 v[5:6], s[8:9], v[23:24], v[1:2]
	v_fma_f64 v[7:8], s[10:11], v[43:44], v[3:4]
	v_add_f64 v[57:58], v[37:38], -v[45:46]
	v_add_f64 v[27:28], v[27:28], v[29:30]
	v_add_f64 v[29:30], v[33:34], v[35:36]
	v_fma_f64 v[9:10], s[10:11], v[25:26], v[19:20]
	v_fmac_f64_e32 v[19:20], s[8:9], v[25:26]
	v_add_f64 v[33:34], v[11:12], v[37:38]
	v_fma_f64 v[11:12], s[8:9], v[47:48], v[21:22]
	v_fmac_f64_e32 v[21:22], s[10:11], v[47:48]
	v_fmac_f64_e32 v[1:2], s[10:11], v[23:24]
	v_fmac_f64_e32 v[3:4], s[8:9], v[43:44]
	v_add_f64 v[31:32], v[49:50], v[51:52]
	v_fmac_f64_e32 v[5:6], s[6:7], v[25:26]
	v_fmac_f64_e32 v[7:8], s[12:13], v[47:48]
	v_fmac_f64_e32 v[9:10], s[6:7], v[23:24]
	v_fmac_f64_e32 v[19:20], s[12:13], v[23:24]
	v_fmac_f64_e32 v[11:12], s[12:13], v[43:44]
	v_add_f64 v[23:24], v[55:56], v[57:58]
	v_fmac_f64_e32 v[21:22], s[6:7], v[43:44]
	v_fmac_f64_e32 v[1:2], s[12:13], v[25:26]
	v_fmac_f64_e32 v[3:4], s[6:7], v[47:48]
	v_add_f64 v[13:14], v[13:14], v[15:16]
	v_add_f64 v[15:16], v[33:34], v[45:46]
	v_fmac_f64_e32 v[5:6], s[2:3], v[27:28]
	v_fmac_f64_e32 v[7:8], s[2:3], v[31:32]
	v_fmac_f64_e32 v[9:10], s[2:3], v[29:30]
	v_fmac_f64_e32 v[11:12], s[2:3], v[23:24]
	v_fmac_f64_e32 v[19:20], s[2:3], v[29:30]
	v_fmac_f64_e32 v[21:22], s[2:3], v[23:24]
	v_fmac_f64_e32 v[1:2], s[2:3], v[27:28]
	v_fmac_f64_e32 v[3:4], s[2:3], v[31:32]
	s_mov_b32 s2, 0xcccd
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	ds_write_b128 v63, v[13:16]
	ds_write_b128 v63, v[5:8] offset:640
	ds_write_b128 v63, v[9:12] offset:1280
	ds_write_b128 v63, v[19:22] offset:1920
	ds_write_b128 v63, v[1:4] offset:2560
	v_mul_u32_u24_sdwa v1, v0, s2 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:WORD_0 src1_sel:DWORD
	v_lshrrev_b32_e32 v3, 19, v1
	v_mul_lo_u16_e32 v1, 10, v3
	v_sub_u16_e32 v1, v0, v1
	v_add_u32_e32 v2, s17, v1
	v_add_u32_e32 v4, -1, v2
	s_movk_i32 s2, 0x1ff
	v_cmp_gt_u32_e32 vcc, s2, v4
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[2:3], vcc
	s_cbranch_execz .LBB0_19
; %bb.15:
	v_and_b32_e32 v7, 0xffff, v3
	s_movk_i32 s6, 0xc8
	v_mad_u32_u24 v1, v1, s6, v7
	v_lshl_add_u32 v1, v1, 4, 0
	ds_read_b128 v[3:6], v1
	s_movk_i32 s6, 0x3e7
	v_lshl_add_u32 v2, v7, 10, v2
	ds_read_b128 v[7:10], v1 offset:640
	v_sub_u32_e32 v12, 0x32000, v2
	v_cmp_lt_u32_e32 vcc, s6, v0
	s_waitcnt lgkmcnt(1)
	v_xor_b32_e32 v11, 0x80000000, v6
	v_cndmask_b32_e32 v17, v2, v12, vcc
	v_cndmask_b32_e32 v6, v6, v11, vcc
	v_lshlrev_b64 v[11:12], 4, v[17:18]
	v_mov_b32_e32 v13, s1
	v_add_co_u32_e32 v11, vcc, s0, v11
	v_addc_co_u32_e32 v12, vcc, v13, v12, vcc
	s_movk_i32 s6, 0x257
	global_store_dwordx4 v[11:12], v[3:6], off
	v_cmp_lt_u32_e32 vcc, s6, v0
	s_movk_i32 s6, 0xc7
	v_add_u32_e32 v3, 0xa000, v2
	v_sub_u32_e32 v5, 0x28000, v2
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v4, 0x80000000, v10
	v_cndmask_b32_e32 v17, v3, v5, vcc
	v_cndmask_b32_e32 v10, v10, v4, vcc
	v_lshlrev_b64 v[11:12], 4, v[17:18]
	ds_read_b128 v[3:6], v1 offset:1280
	v_add_co_u32_e32 v11, vcc, s0, v11
	v_addc_co_u32_e32 v12, vcc, v13, v12, vcc
	global_store_dwordx4 v[11:12], v[7:10], off
	v_cmp_lt_u32_e32 vcc, s6, v0
	s_movk_i32 s6, 0x320
	v_add_u32_e32 v7, 0x14000, v2
	v_sub_u32_e32 v9, 0x1e000, v2
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v8, 0x80000000, v6
	v_cndmask_b32_e32 v17, v7, v9, vcc
	v_cndmask_b32_e32 v6, v6, v8, vcc
	v_lshlrev_b64 v[7:8], 4, v[17:18]
	v_add_co_u32_e32 v7, vcc, s0, v7
	v_addc_co_u32_e32 v8, vcc, v13, v8, vcc
	v_cmp_gt_u32_e32 vcc, s6, v0
	global_store_dwordx4 v[7:8], v[3:6], off
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_17
; %bb.16:
	ds_read_b128 v[3:6], v1 offset:1920
	v_sub_u32_e32 v7, 0x14000, v2
	v_mov_b32_e32 v8, 0
	v_lshlrev_b64 v[7:8], 4, v[7:8]
	v_mov_b32_e32 v9, s1
	v_add_co_u32_e32 v7, vcc, s0, v7
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v6
	v_addc_co_u32_e32 v8, vcc, v9, v8, vcc
	global_store_dwordx4 v[7:8], v[3:6], off
.LBB0_17:
	s_or_b64 exec, exec, s[6:7]
	s_movk_i32 s6, 0x190
	v_cmp_gt_u32_e32 vcc, s6, v0
	s_and_b64 exec, exec, vcc
	s_cbranch_execz .LBB0_19
; %bb.18:
	ds_read_b128 v[3:6], v1 offset:2560
	v_sub_u32_e32 v1, 0xa000, v2
	v_mov_b32_e32 v2, 0
	v_lshlrev_b64 v[1:2], 4, v[1:2]
	v_mov_b32_e32 v7, s1
	v_add_co_u32_e32 v1, vcc, s0, v1
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v6
	v_addc_co_u32_e32 v2, vcc, v7, v2, vcc
	global_store_dwordx4 v[1:2], v[3:6], off
.LBB0_19:
	s_or_b64 exec, exec, s[2:3]
	s_load_dwordx2 s[2:3], s[4:5], 0x68
	s_cmp_eq_u32 s16, 0
	s_movk_i32 s6, 0x65
	s_cselect_b64 s[4:5], -1, 0
	v_cmp_gt_u32_e32 vcc, s6, v0
	s_and_b64 s[4:5], s[4:5], vcc
	s_and_saveexec_b64 s[6:7], s[4:5]
	s_cbranch_execz .LBB0_27
; %bb.20:
	v_lshl_add_u32 v1, v0, 4, 0
	ds_read_b128 v[1:4], v1
	s_movk_i32 s4, 0x63
	v_cmp_lt_i32_e32 vcc, s4, v0
	s_and_saveexec_b64 s[4:5], vcc
	s_xor_b64 s[4:5], exec, s[4:5]
	s_cbranch_execz .LBB0_22
; %bb.21:
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v4, 0x80000000, v4
	v_mov_b32_e32 v0, 0xc8000
	global_store_dwordx4 v0, v[1:4], s[0:1]
                                        ; implicit-def: $vgpr1_vgpr2
                                        ; implicit-def: $vgpr0
.LBB0_22:
	s_andn2_saveexec_b64 s[4:5], s[4:5]
	s_cbranch_execz .LBB0_27
; %bb.23:
	v_cmp_ne_u32_e32 vcc, 0, v0
	s_and_saveexec_b64 s[4:5], vcc
	s_xor_b64 s[4:5], exec, s[4:5]
	s_cbranch_execz .LBB0_25
; %bb.24:
	v_lshlrev_b32_e32 v9, 4, v0
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[5:8], v9, s[2:3]
	v_sub_u32_e32 v9, 0, v9
	ds_read_b128 v[9:12], v9 offset:3200
	s_waitcnt lgkmcnt(0)
	v_add_f64 v[13:14], v[3:4], v[11:12]
	v_add_f64 v[15:16], v[1:2], -v[9:10]
	v_add_f64 v[9:10], v[1:2], v[9:10]
	v_add_f64 v[11:12], v[3:4], -v[11:12]
	v_mul_f64 v[13:14], v[13:14], 0.5
	v_mul_f64 v[15:16], v[15:16], 0.5
	s_waitcnt vmcnt(0)
	v_mul_f64 v[17:18], v[5:6], v[13:14]
	v_mul_f64 v[5:6], v[15:16], v[5:6]
	v_fmac_f64_e32 v[17:18], v[15:16], v[7:8]
	v_fma_f64 v[2:3], v[13:14], v[7:8], -v[5:6]
	v_sub_u32_e32 v8, 0xc8, v0
	v_lshlrev_b32_e32 v14, 13, v0
	v_mov_b32_e32 v13, 0
	v_mov_b32_e32 v15, s1
	v_fma_f64 v[4:5], 0.5, v[9:10], v[17:18]
	v_fma_f64 v[6:7], 0.5, v[11:12], v[2:3]
	v_fma_f64 v[0:1], v[9:10], 0.5, -v[17:18]
	v_fmac_f64_e32 v[2:3], -0.5, v[11:12]
	v_lshlrev_b32_e32 v12, 9, v8
	v_lshlrev_b64 v[8:9], 4, v[12:13]
	v_add_co_u32_e32 v8, vcc, s0, v8
	v_addc_co_u32_e32 v9, vcc, v15, v9, vcc
	global_store_dwordx4 v14, v[4:7], s[0:1]
	global_store_dwordx4 v[8:9], v[0:3], off
                                        ; implicit-def: $vgpr1_vgpr2
.LBB0_25:
	s_waitcnt lgkmcnt(0)
	s_andn2_saveexec_b64 s[2:3], s[4:5]
	s_cbranch_execz .LBB0_27
; %bb.26:
	v_add_f64 v[5:6], v[1:2], v[3:4]
	v_add_f64 v[0:1], v[1:2], -v[3:4]
	v_mov_b32_e32 v7, 0
	v_mov_b32_e32 v8, v7
	v_mov_b32_e32 v4, 0x190000
	v_mov_b32_e32 v2, v7
	v_mov_b32_e32 v3, v7
	global_store_dwordx4 v7, v[5:8], s[0:1]
	global_store_dwordx4 v4, v[0:3], s[0:1]
.LBB0_27:
	s_endpgm
	.section	.rodata,#alloc
	.p2align	6, 0x0
	.amdhsa_kernel fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg
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
		.amdhsa_next_free_vgpr 64
		.amdhsa_next_free_sgpr 18
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
	.size	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg, .Lfunc_end0-fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg
                                        ; -- End function
	.section	.AMDGPU.csdata
; Kernel info:
; codeLenInByte = 5920
; NumSgprs: 22
; NumVgprs: 64
; ScratchSize: 0
; MemoryBound: 1
; FloatMode: 240
; IeeeMode: 1
; LDSByteSize: 0 bytes/workgroup (compile time only)
; SGPRBlocks: 2
; VGPRBlocks: 15
; NumSGPRsForWavesPerEU: 22
; NumVGPRsForWavesPerEU: 64
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
    .max_flat_workgroup_size: 400
    .name:           fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg
    .private_segment_fixed_size: 0
    .sgpr_count:     22
    .sgpr_spill_count: 0
    .symbol:         fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v3_role7_C512_Q200_N204800_reg.kd
    .uniform_work_group_size: 1
    .uses_dynamic_stack: false
    .vgpr_count:     64
    .vgpr_spill_count: 0
    .wavefront_size: 64
amdhsa.target:   'amdgcn-amd-amdhsa--gfx936:sramecc+'
amdhsa.version:
  - 1
  - 2
...

	.end_amdgpu_metadata
