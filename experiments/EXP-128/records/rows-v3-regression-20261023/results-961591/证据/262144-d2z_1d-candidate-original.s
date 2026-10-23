	.text
	.amdgcn_target "amdgcn-amd-amdhsa--gfx936:sramecc+"
	.protected	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg ; -- Begin function fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg
	.globl	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg
	.p2align	8
	.type	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg,@function
fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg: ; @fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg
; %bb.0:
	s_load_dwordx2 s[0:1], s[4:5], 0x10
	v_lshrrev_b32_e32 v25, 7, v0
	v_mov_b64_e32 v[5:6], 0
	s_movk_i32 s2, 0x100
	v_mov_b64_e32 v[1:2], v[5:6]
	s_waitcnt lgkmcnt(0)
	s_load_dword s0, s[0:1], 0x8
	v_mov_b64_e32 v[21:22], v[5:6]
	v_mov_b64_e32 v[17:18], v[5:6]
	v_mov_b64_e32 v[23:24], v[5:6]
	v_mov_b64_e32 v[19:20], v[5:6]
	s_waitcnt lgkmcnt(0)
	s_add_i32 s0, s0, -1
	s_lshr_b32 s0, s0, 2
	s_add_i32 s1, s0, 1
	v_cvt_f32_u32_e32 v3, s1
	s_not_b32 s0, s0
	v_mov_b64_e32 v[7:8], v[5:6]
	v_mov_b64_e32 v[11:12], v[5:6]
	v_rcp_iflag_f32_e32 v13, v3
	v_mov_b64_e32 v[3:4], v[5:6]
	v_mov_b64_e32 v[9:10], v[5:6]
	v_mov_b64_e32 v[15:16], v[5:6]
	v_mul_f32_e32 v13, 0x4f7ffffe, v13
	v_cvt_u32_f32_e32 v26, v13
	v_mov_b64_e32 v[13:14], v[5:6]
	v_lshlrev_b32_e32 v29, 2, v0
	v_mov_b64_e32 v[39:40], v[5:6]
	v_readfirstlane_b32 s3, v26
	s_mul_i32 s0, s0, s3
	s_mul_hi_u32 s0, s3, s0
	s_add_i32 s3, s3, s0
	s_mul_hi_u32 s0, s6, s3
	s_mul_i32 s0, s0, s1
	s_sub_i32 s0, s6, s0
	s_sub_i32 s3, s0, s1
	s_cmp_ge_u32 s0, s1
	s_cselect_b32 s0, s3, s0
	s_sub_i32 s3, s0, s1
	s_cmp_ge_u32 s0, s1
	s_cselect_b32 s14, s3, s0
	s_lshl_b32 s15, s14, 2
	v_or_b32_e32 v30, s15, v25
	v_cmp_gt_u32_e32 vcc, s2, v30
	v_mov_b64_e32 v[35:36], v[5:6]
	v_mov_b64_e32 v[31:32], v[5:6]
	v_mov_b64_e32 v[27:28], v[5:6]
	s_and_saveexec_b64 s[2:3], vcc
	s_cbranch_execz .LBB0_10
; %bb.1:
	s_load_dwordx2 s[6:7], s[4:5], 0x58
	v_and_b32_e32 v1, 64, v0
	v_cmp_ne_u32_e64 s[0:1], 0, v30
	v_cmp_eq_u32_e32 vcc, 0, v1
                                        ; implicit-def: $vgpr13_vgpr14
                                        ; implicit-def: $vgpr9_vgpr10
                                        ; implicit-def: $vgpr27_vgpr28
                                        ; implicit-def: $vgpr31_vgpr32
                                        ; implicit-def: $vgpr3_vgpr4
                                        ; implicit-def: $vgpr7_vgpr8
                                        ; implicit-def: $vgpr19_vgpr20
                                        ; implicit-def: $vgpr23_vgpr24
                                        ; implicit-def: $vgpr35_vgpr36
                                        ; implicit-def: $vgpr39_vgpr40
	s_and_saveexec_b64 s[8:9], s[0:1]
	s_xor_b64 s[8:9], exec, s[8:9]
	s_cbranch_execz .LBB0_5
; %bb.2:
	v_mov_b64_e32 v[13:14], 0
	v_mov_b64_e32 v[9:10], v[13:14]
	v_mov_b64_e32 v[27:28], v[13:14]
	v_mov_b64_e32 v[31:32], v[13:14]
	v_mov_b64_e32 v[3:4], v[13:14]
	v_mov_b64_e32 v[7:8], v[13:14]
	v_mov_b64_e32 v[19:20], v[13:14]
	v_mov_b64_e32 v[23:24], v[13:14]
	v_mov_b64_e32 v[15:16], v[13:14]
	v_mov_b64_e32 v[11:12], v[13:14]
	v_mov_b64_e32 v[17:18], v[13:14]
	v_mov_b64_e32 v[21:22], v[13:14]
	v_mov_b64_e32 v[1:2], v[13:14]
	v_mov_b64_e32 v[5:6], v[13:14]
	v_mov_b64_e32 v[35:36], v[13:14]
	v_mov_b64_e32 v[39:40], v[13:14]
	s_and_saveexec_b64 s[10:11], vcc
	s_cbranch_execz .LBB0_4
; %bb.3:
	v_and_b32_e32 v15, 0x7f, v0
	v_mul_lo_u32 v21, v30, v15
	s_load_dwordx2 s[12:13], s[4:5], 0x70
	s_mov_b32 s0, 0
	v_mov_b32_e32 v23, 4
	v_lshlrev_b32_sdwa v9, v23, v21 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v1, s0, v21, 8
	s_movk_i32 s1, 0x1000
	v_lshl_or_b32 v10, v1, 4, s1
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[1:4], v9, s[12:13]
	global_load_dwordx4 v[5:8], v10, s[12:13]
	v_lshlrev_b32_e32 v28, 6, v30
	v_add_u32_e32 v51, v21, v28
	v_mov_b32_e32 v25, 0x1000
	v_lshlrev_b32_sdwa v13, v23, v51 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v9, 0, v51, 8
	v_lshl_or_b32 v14, v9, 4, v25
	global_load_dwordx4 v[9:12], v13, s[12:13]
	global_load_dwordx4 v[17:20], v14, s[12:13]
	v_add_u32_e32 v16, v51, v28
	v_lshlrev_b32_sdwa v13, v23, v16 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v14, 0, v16, 8
	global_load_dwordx4 v[31:34], v13, s[12:13]
	v_lshl_or_b32 v13, v14, 4, v25
	global_load_dwordx4 v[35:38], v13, s[12:13]
	v_add_u32_e32 v22, v16, v28
	v_add_u32_e32 v57, v22, v28
	v_lshlrev_b32_sdwa v24, v23, v57 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	s_movk_i32 s1, 0x2000
	v_alignbit_b32 v21, s0, v21, 16
	v_lshl_or_b32 v21, v21, 4, s1
	v_mov_b32_e32 v58, 0x2000
	v_lshlrev_b32_e32 v30, 9, v30
	s_waitcnt vmcnt(4)
	v_mul_f64 v[13:14], v[3:4], v[7:8]
	v_mul_f64 v[41:42], v[1:2], v[7:8]
	v_fma_f64 v[43:44], v[1:2], v[5:6], -v[13:14]
	v_fmac_f64_e32 v[41:42], v[3:4], v[5:6]
	s_waitcnt vmcnt(2)
	v_mul_f64 v[5:6], v[11:12], v[19:20]
	v_mul_f64 v[3:4], v[9:10], v[19:20]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[7:8], v[33:34], v[37:38]
	v_mul_f64 v[1:2], v[31:32], v[37:38]
	v_fma_f64 v[5:6], v[9:10], v[17:18], -v[5:6]
	v_bfe_u32 v10, v22, 8, 8
	v_fmac_f64_e32 v[3:4], v[11:12], v[17:18]
	v_lshlrev_b32_sdwa v9, v23, v22 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_lshl_or_b32 v17, v10, 4, v25
	global_load_dwordx4 v[11:14], v9, s[12:13]
	v_fmac_f64_e32 v[1:2], v[33:34], v[35:36]
	global_load_dwordx4 v[17:20], v17, s[12:13]
	v_fma_f64 v[9:10], v[31:32], v[35:36], -v[7:8]
	v_add_u32_e32 v32, v57, v28
	s_waitcnt vmcnt(0)
	v_mul_f64 v[26:27], v[13:14], v[19:20]
	v_mul_f64 v[7:8], v[11:12], v[19:20]
	v_bfe_u32 v19, v57, 8, 8
	v_lshl_or_b32 v31, v19, 4, v25
	v_fma_f64 v[45:46], v[11:12], v[17:18], -v[26:27]
	v_fmac_f64_e32 v[7:8], v[13:14], v[17:18]
	global_load_dwordx4 v[11:14], v24, s[12:13]
	global_load_dwordx4 v[17:20], v31, s[12:13]
	v_add_u32_e32 v24, v32, v28
	v_add_u32_e32 v31, v24, v28
	s_waitcnt vmcnt(0)
	v_mul_f64 v[26:27], v[13:14], v[19:20]
	v_mul_f64 v[49:50], v[11:12], v[19:20]
	v_fma_f64 v[47:48], v[11:12], v[17:18], -v[26:27]
	v_bfe_u32 v11, v32, 8, 8
	v_lshlrev_b32_sdwa v12, v23, v32 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_fmac_f64_e32 v[49:50], v[13:14], v[17:18]
	v_lshl_or_b32 v11, v11, 4, v25
	global_load_dwordx4 v[17:20], v12, s[12:13]
	global_load_dwordx4 v[33:36], v11, s[12:13]
	v_bfe_u32 v26, v31, 8, 8
	s_waitcnt vmcnt(0)
	v_mul_f64 v[11:12], v[19:20], v[35:36]
	v_mul_f64 v[13:14], v[17:18], v[35:36]
	v_fma_f64 v[11:12], v[17:18], v[33:34], -v[11:12]
	v_bfe_u32 v17, v24, 8, 8
	v_lshlrev_b32_sdwa v18, v23, v24 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_fmac_f64_e32 v[13:14], v[19:20], v[33:34]
	v_lshl_or_b32 v17, v17, 4, v25
	global_load_dwordx4 v[33:36], v18, s[12:13]
	global_load_dwordx4 v[37:40], v17, s[12:13]
	v_lshlrev_b32_sdwa v23, v23, v31 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_lshl_or_b32 v25, v26, 4, v25
	s_waitcnt vmcnt(0)
	v_mul_f64 v[17:18], v[35:36], v[39:40]
	v_mul_f64 v[19:20], v[33:34], v[39:40]
	v_fma_f64 v[17:18], v[33:34], v[37:38], -v[17:18]
	v_fmac_f64_e32 v[19:20], v[35:36], v[37:38]
	global_load_dwordx4 v[33:36], v23, s[12:13]
	global_load_dwordx4 v[37:40], v25, s[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[25:26], v[35:36], v[39:40]
	v_mul_f64 v[27:28], v[33:34], v[39:40]
	v_fma_f64 v[25:26], v[33:34], v[37:38], -v[25:26]
	v_fmac_f64_e32 v[27:28], v[35:36], v[37:38]
	global_load_dwordx4 v[33:36], v21, s[12:13]
	v_alignbit_b32 v21, 0, v51, 16
	v_lshl_or_b32 v21, v21, 4, v58
	s_waitcnt vmcnt(0)
	v_mul_f64 v[37:38], v[41:42], v[35:36]
	v_mul_f64 v[39:40], v[43:44], v[35:36]
	v_fma_f64 v[37:38], v[33:34], v[43:44], -v[37:38]
	v_fmac_f64_e32 v[39:40], v[33:34], v[41:42]
	global_load_dwordx4 v[33:36], v21, s[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[43:44], v[5:6], v[35:36]
	v_mul_f64 v[41:42], v[3:4], v[35:36]
	v_fmac_f64_e32 v[43:44], v[33:34], v[3:4]
	v_alignbit_b32 v3, 0, v16, 16
	v_lshl_or_b32 v3, v3, 4, v58
	v_fma_f64 v[41:42], v[33:34], v[5:6], -v[41:42]
	global_load_dwordx4 v[3:6], v3, s[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[53:54], v[9:10], v[5:6]
	v_mul_f64 v[33:34], v[1:2], v[5:6]
	v_fmac_f64_e32 v[53:54], v[3:4], v[1:2]
	v_alignbit_b32 v1, 0, v22, 16
	v_lshl_or_b32 v1, v1, 4, v58
	v_fma_f64 v[51:52], v[3:4], v[9:10], -v[33:34]
	global_load_dwordx4 v[1:4], v1, s[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[5:6], v[7:8], v[3:4]
	v_fma_f64 v[55:56], v[1:2], v[45:46], -v[5:6]
	v_mul_f64 v[45:46], v[45:46], v[3:4]
	v_fmac_f64_e32 v[45:46], v[1:2], v[7:8]
	v_alignbit_b32 v1, 0, v57, 16
	v_lshl_or_b32 v1, v1, 4, v58
	global_load_dwordx4 v[1:4], v1, s[12:13]
	v_mov_b32_e32 v57, s7
	s_waitcnt vmcnt(0)
	v_mul_f64 v[5:6], v[49:50], v[3:4]
	v_mul_f64 v[33:34], v[47:48], v[3:4]
	v_fma_f64 v[21:22], v[1:2], v[47:48], -v[5:6]
	v_or_b32_e32 v47, v30, v15
	v_mov_b32_e32 v48, 0
	v_fmac_f64_e32 v[33:34], v[1:2], v[49:50]
	v_lshlrev_b64 v[1:2], 4, v[47:48]
	v_add_co_u32_e64 v49, s[0:1], s6, v1
	v_addc_co_u32_e64 v50, s[0:1], v57, v2, s[0:1]
	global_load_dwordx4 v[3:6], v[49:50], off
	s_waitcnt vmcnt(0)
	v_mul_f64 v[7:8], v[5:6], v[39:40]
	v_mul_f64 v[1:2], v[3:4], v[39:40]
	v_fmac_f64_e32 v[1:2], v[5:6], v[37:38]
	v_fma_f64 v[5:6], v[3:4], v[37:38], -v[7:8]
	v_or_b32_e32 v3, 0x100, v47
	v_mov_b32_e32 v4, v48
	v_lshlrev_b64 v[3:4], 4, v[3:4]
	v_add_co_u32_e64 v3, s[0:1], s6, v3
	v_addc_co_u32_e64 v4, s[0:1], v57, v4, s[0:1]
	global_load_dwordx4 v[7:10], v[3:4], off
	s_waitcnt vmcnt(0)
	v_mul_f64 v[3:4], v[7:8], v[33:34]
	v_mul_f64 v[15:16], v[9:10], v[33:34]
	v_fmac_f64_e32 v[3:4], v[9:10], v[21:22]
	v_alignbit_b32 v9, 0, v32, 16
	v_lshl_or_b32 v9, v9, 4, v58
	global_load_dwordx4 v[32:35], v9, s[12:13]
	v_fma_f64 v[7:8], v[7:8], v[21:22], -v[15:16]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[9:10], v[13:14], v[34:35]
	v_mul_f64 v[36:37], v[11:12], v[34:35]
	v_fma_f64 v[21:22], v[32:33], v[11:12], -v[9:10]
	global_load_dwordx4 v[9:12], v[49:50], off offset:1024
	v_fmac_f64_e32 v[36:37], v[32:33], v[13:14]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[13:14], v[9:10], v[43:44]
	v_mul_f64 v[15:16], v[11:12], v[43:44]
	v_fmac_f64_e32 v[13:14], v[11:12], v[41:42]
	v_add_u32_e32 v11, 0x140, v47
	v_mov_b32_e32 v12, v48
	v_lshlrev_b64 v[11:12], 4, v[11:12]
	v_fma_f64 v[9:10], v[9:10], v[41:42], -v[15:16]
	v_add_co_u32_e64 v11, s[0:1], s6, v11
	v_addc_co_u32_e64 v12, s[0:1], v57, v12, s[0:1]
	global_load_dwordx4 v[32:35], v[11:12], off
	s_movk_i32 s0, 0x180
	v_add_u32_e32 v47, 0x1c0, v47
	s_waitcnt vmcnt(0)
	v_mul_f64 v[15:16], v[32:33], v[36:37]
	v_mul_f64 v[11:12], v[34:35], v[36:37]
	v_fmac_f64_e32 v[15:16], v[34:35], v[21:22]
	v_fma_f64 v[11:12], v[32:33], v[21:22], -v[11:12]
	v_alignbit_b32 v21, 0, v24, 16
	v_lshl_or_b32 v21, v21, 4, v58
	global_load_dwordx4 v[21:24], v21, s[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[32:33], v[19:20], v[23:24]
	v_mul_f64 v[23:24], v[17:18], v[23:24]
	v_fma_f64 v[36:37], v[21:22], v[17:18], -v[32:33]
	v_fmac_f64_e32 v[23:24], v[21:22], v[19:20]
	global_load_dwordx4 v[19:22], v[49:50], off offset:2048
	s_waitcnt vmcnt(0)
	v_mul_f64 v[32:33], v[21:22], v[53:54]
	v_mul_f64 v[17:18], v[19:20], v[53:54]
	v_fmac_f64_e32 v[17:18], v[21:22], v[51:52]
	v_fma_f64 v[21:22], v[19:20], v[51:52], -v[32:33]
	v_or3_b32 v19, v0, v30, s0
	v_mov_b32_e32 v20, v48
	v_lshlrev_b64 v[19:20], 4, v[19:20]
	v_alignbit_b32 v30, 0, v31, 16
	v_add_co_u32_e64 v19, s[0:1], s6, v19
	v_addc_co_u32_e64 v20, s[0:1], v57, v20, s[0:1]
	global_load_dwordx4 v[32:35], v[19:20], off
	v_lshl_or_b32 v30, v30, 4, v58
	s_waitcnt vmcnt(0)
	v_mul_f64 v[19:20], v[32:33], v[23:24]
	v_mul_f64 v[23:24], v[34:35], v[23:24]
	v_fmac_f64_e32 v[19:20], v[34:35], v[36:37]
	v_fma_f64 v[23:24], v[32:33], v[36:37], -v[23:24]
	global_load_dwordx4 v[30:33], v30, s[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[34:35], v[27:28], v[32:33]
	v_fma_f64 v[41:42], v[30:31], v[25:26], -v[34:35]
	v_mul_f64 v[25:26], v[25:26], v[32:33]
	v_fmac_f64_e32 v[25:26], v[30:31], v[27:28]
	global_load_dwordx4 v[30:33], v[49:50], off offset:3072
	s_waitcnt vmcnt(0)
	v_mul_f64 v[34:35], v[32:33], v[45:46]
	v_mul_f64 v[27:28], v[30:31], v[45:46]
	v_fmac_f64_e32 v[27:28], v[32:33], v[55:56]
	v_fma_f64 v[31:32], v[30:31], v[55:56], -v[34:35]
	v_lshlrev_b64 v[33:34], 4, v[47:48]
	v_add_co_u32_e64 v33, s[0:1], s6, v33
	v_addc_co_u32_e64 v34, s[0:1], v57, v34, s[0:1]
	global_load_dwordx4 v[37:40], v[33:34], off
	s_waitcnt vmcnt(0)
	v_mul_f64 v[33:34], v[39:40], v[25:26]
	v_mul_f64 v[35:36], v[37:38], v[25:26]
	v_fmac_f64_e32 v[35:36], v[39:40], v[41:42]
	v_fma_f64 v[39:40], v[37:38], v[41:42], -v[33:34]
.LBB0_4:
	s_or_b64 exec, exec, s[10:11]
.LBB0_5:
	s_andn2_saveexec_b64 s[0:1], s[8:9]
	s_cbranch_execz .LBB0_9
; %bb.6:
	v_mov_b64_e32 v[13:14], 0
	v_mov_b64_e32 v[9:10], v[13:14]
	v_mov_b64_e32 v[27:28], v[13:14]
	v_mov_b64_e32 v[31:32], v[13:14]
	v_mov_b64_e32 v[3:4], v[13:14]
	v_mov_b64_e32 v[7:8], v[13:14]
	v_mov_b64_e32 v[19:20], v[13:14]
	v_mov_b64_e32 v[23:24], v[13:14]
	v_mov_b64_e32 v[15:16], v[13:14]
	v_mov_b64_e32 v[11:12], v[13:14]
	v_mov_b64_e32 v[17:18], v[13:14]
	v_mov_b64_e32 v[21:22], v[13:14]
	v_mov_b64_e32 v[1:2], v[13:14]
	v_mov_b64_e32 v[5:6], v[13:14]
	v_mov_b64_e32 v[35:36], v[13:14]
	v_mov_b64_e32 v[39:40], v[13:14]
	s_and_saveexec_b64 s[8:9], vcc
	s_cbranch_execz .LBB0_8
; %bb.7:
	v_lshlrev_b32_e32 v9, 1, v0
	v_lshlrev_b32_e32 v11, 3, v0
	v_and_b32_e32 v9, 0xfe, v9
	v_and_b32_e32 v11, 0x200, v11
	v_sub_u32_e32 v9, v9, v11
	v_bfe_u32 v11, v0, 6, 1
	v_and_b32_e32 v1, 0x1fc, v29
	v_lshl_or_b32 v16, v9, 1, v11
	v_lshlrev_b32_e32 v30, 3, v1
	v_mov_b32_e32 v10, 0
	v_add_u32_e32 v9, 0x300, v16
	s_waitcnt lgkmcnt(0)
	v_mov_b32_e32 v13, s7
	v_add_co_u32_e32 v14, vcc, s6, v30
	v_lshlrev_b64 v[11:12], 3, v[9:10]
	v_addc_co_u32_e32 v15, vcc, 0, v13, vcc
	v_add_u32_e32 v9, 0x302, v16
	v_add_co_u32_e32 v25, vcc, s6, v11
	v_lshlrev_b64 v[9:10], 3, v[9:10]
	v_addc_co_u32_e32 v26, vcc, v13, v12, vcc
	v_add_co_u32_e32 v33, vcc, s6, v9
	v_addc_co_u32_e32 v34, vcc, v13, v10, vcc
	v_add_co_u32_e32 v37, vcc, 0x1000, v14
	global_load_dwordx4 v[1:4], v30, s[6:7] offset:16
	global_load_dwordx4 v[5:8], v30, s[6:7]
	v_or_b32_e32 v41, 0x1000, v30
	v_addc_co_u32_e32 v38, vcc, 0, v15, vcc
	global_load_dwordx2 v[31:32], v[25:26], off
	global_load_dwordx2 v[27:28], v[33:34], off
	global_load_dwordx2 v[39:40], v[37:38], off offset:2056
	global_load_dwordx2 v[35:36], v[37:38], off offset:2072
	global_load_dwordx4 v[13:16], v30, s[6:7] offset:2064
	global_load_dwordx4 v[9:12], v30, s[6:7] offset:2048
	global_load_dwordx4 v[17:20], v41, s[6:7] offset:16
	global_load_dwordx4 v[21:24], v41, s[6:7]
.LBB0_8:
	s_or_b64 exec, exec, s[8:9]
.LBB0_9:
	s_or_b64 exec, exec, s[0:1]
.LBB0_10:
	s_or_b64 exec, exec, s[2:3]
	v_and_b32_e32 v47, 0x600, v29
	v_and_b32_e32 v48, 0x7f, v0
	v_cmp_gt_u32_e32 vcc, 64, v48
	v_lshl_add_u32 v25, v48, 3, v47
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_12
; %bb.11:
	s_waitcnt vmcnt(8)
	v_add_f64 v[7:8], v[5:6], -v[7:8]
	s_waitcnt vmcnt(0)
	v_add_f64 v[23:24], v[21:22], -v[23:24]
	v_add_f64 v[19:20], v[17:18], -v[19:20]
	v_add_f64 v[11:12], v[9:10], -v[11:12]
	v_add_f64 v[29:30], v[31:32], -v[39:40]
	v_add_f64 v[33:34], v[27:28], -v[35:36]
	v_add_f64 v[3:4], v[1:2], -v[3:4]
	v_add_f64 v[15:16], v[13:14], -v[15:16]
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[7:8]
	v_fma_f64 v[21:22], v[21:22], 2.0, -v[23:24]
	v_add_f64 v[45:46], v[7:8], -v[19:20]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[11:12]
	v_fma_f64 v[31:32], v[31:32], 2.0, -v[29:30]
	v_add_f64 v[43:44], v[11:12], -v[33:34]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[3:4]
	v_fma_f64 v[17:18], v[17:18], 2.0, -v[19:20]
	v_fma_f64 v[13:14], v[13:14], 2.0, -v[15:16]
	v_add_f64 v[23:24], v[23:24], v[3:4]
	v_fma_f64 v[19:20], v[27:28], 2.0, -v[33:34]
	v_add_f64 v[28:29], v[29:30], v[15:16]
	v_add_f64 v[21:22], v[5:6], -v[21:22]
	v_add_f64 v[26:27], v[9:10], -v[31:32]
	v_fma_f64 v[7:8], v[7:8], 2.0, -v[45:46]
	v_fma_f64 v[30:31], v[11:12], 2.0, -v[43:44]
	v_add_f64 v[17:18], v[1:2], -v[17:18]
	v_fma_f64 v[33:34], v[3:4], 2.0, -v[23:24]
	v_add_f64 v[3:4], v[13:14], -v[19:20]
	v_fma_f64 v[19:20], v[15:16], 2.0, -v[28:29]
	s_mov_b32 s2, 0x667f3bcd
	s_mov_b32 s3, 0xbfe6a09e
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[21:22]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[26:27]
	v_fma_f64 v[11:12], s[2:3], v[30:31], v[7:8]
	s_waitcnt lgkmcnt(0)
	s_mov_b32 s7, 0x3fe6a09e
	s_mov_b32 s6, s2
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[17:18]
	v_fma_f64 v[39:40], s[6:7], v[43:44], v[45:46]
	v_fma_f64 v[13:14], v[13:14], 2.0, -v[3:4]
	v_fma_f64 v[15:16], s[2:3], v[19:20], v[33:34]
	v_fma_f64 v[35:36], s[6:7], v[28:29], v[23:24]
	v_add_f64 v[9:10], v[5:6], -v[9:10]
	v_fmac_f64_e32 v[11:12], s[2:3], v[19:20]
	v_add_f64 v[37:38], v[21:22], -v[3:4]
	v_add_f64 v[19:20], v[17:18], v[26:27]
	v_fmac_f64_e32 v[39:40], s[2:3], v[28:29]
	v_add_f64 v[3:4], v[1:2], -v[13:14]
	v_fmac_f64_e32 v[15:16], s[6:7], v[30:31]
	v_fmac_f64_e32 v[35:36], s[6:7], v[43:44]
	v_fma_f64 v[41:42], v[5:6], 2.0, -v[9:10]
	v_fma_f64 v[43:44], v[7:8], 2.0, -v[11:12]
	v_fma_f64 v[29:30], v[21:22], 2.0, -v[37:38]
	v_fma_f64 v[17:18], v[17:18], 2.0, -v[19:20]
	v_fma_f64 v[31:32], v[45:46], 2.0, -v[39:40]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[3:4]
	v_fma_f64 v[13:14], v[33:34], 2.0, -v[15:16]
	v_fma_f64 v[27:28], v[23:24], 2.0, -v[35:36]
	v_lshl_add_u32 v5, v25, 3, 0
	ds_write_b128 v5, v[41:44]
	ds_write_b128 v5, v[29:32] offset:16
	ds_write_b128 v5, v[9:12] offset:32
	ds_write_b128 v5, v[37:40] offset:48
	v_mov_b64_e32 v[5:6], v[41:42]
	v_mov_b64_e32 v[21:22], v[29:30]
	v_mov_b64_e32 v[23:24], v[37:38]
	v_mov_b64_e32 v[7:8], v[9:10]
	v_mov_b64_e32 v[9:10], v[43:44]
.LBB0_12:
	s_or_b64 exec, exec, s[0:1]
	v_or_b32_e32 v25, v47, v48
	s_waitcnt vmcnt(0) lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_14
; %bb.13:
	v_lshl_add_u32 v5, v25, 3, 0
	ds_read2st64_b64 v[23:26], v5 offset1:1
	ds_read2st64_b64 v[29:32], v5 offset0:2 offset1:3
	ds_read2st64_b64 v[37:40], v5 offset0:6 offset1:7
	ds_read2st64_b64 v[9:12], v5 offset0:4 offset1:5
	s_waitcnt lgkmcnt(3)
	v_mov_b64_e32 v[5:6], v[23:24]
	s_waitcnt lgkmcnt(2)
	v_mov_b64_e32 v[21:22], v[29:30]
	s_waitcnt lgkmcnt(1)
	v_mov_b64_e32 v[23:24], v[37:38]
	s_waitcnt lgkmcnt(0)
	v_mov_b64_e32 v[7:8], v[9:10]
	v_mov_b64_e32 v[9:10], v[25:26]
.LBB0_14:
	s_or_b64 exec, exec, s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_16
; %bb.15:
	v_lshl_add_u32 v25, v48, 3, v47
	v_lshl_add_u32 v29, v25, 3, 0
	v_mov_b32_e32 v41, v1
	v_mov_b32_e32 v42, v2
	v_mov_b32_e32 v43, v13
	v_mov_b32_e32 v44, v14
	ds_write_b128 v29, v[41:44]
	v_mov_b32_e32 v25, v17
	v_mov_b32_e32 v26, v18
	v_mov_b32_e32 v41, v3
	v_mov_b32_e32 v42, v4
	v_mov_b32_e32 v43, v15
	v_mov_b32_e32 v44, v16
	v_mov_b32_e32 v33, v19
	v_mov_b32_e32 v34, v20
	ds_write_b128 v29, v[25:28] offset:16
	ds_write_b128 v29, v[41:44] offset:32
	ds_write_b128 v29, v[33:36] offset:48
.LBB0_16:
	s_or_b64 exec, exec, s[0:1]
	s_load_dwordx2 s[2:3], s[4:5], 0x0
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_18
; %bb.17:
	v_or_b32_e32 v1, v47, v48
	v_lshl_add_u32 v1, v1, 3, 0
	ds_read2st64_b64 v[41:44], v1 offset1:1
	ds_read2st64_b64 v[33:36], v1 offset0:6 offset1:7
	ds_read2st64_b64 v[13:16], v1 offset0:4 offset1:5
	ds_read2st64_b64 v[25:28], v1 offset0:2 offset1:3
	s_waitcnt lgkmcnt(3)
	v_mov_b64_e32 v[1:2], v[41:42]
	s_waitcnt lgkmcnt(2)
	v_mov_b64_e32 v[19:20], v[33:34]
	s_waitcnt lgkmcnt(1)
	v_mov_b64_e32 v[3:4], v[13:14]
	s_waitcnt lgkmcnt(0)
	v_mov_b64_e32 v[17:18], v[25:26]
	v_mov_b64_e32 v[13:14], v[43:44]
.LBB0_18:
	s_or_b64 exec, exec, s[0:1]
	v_and_b32_e32 v49, 7, v0
	v_mul_u32_u24_e32 v25, 7, v49
	v_lshlrev_b32_e32 v58, 4, v25
	global_load_dwordx4 v[50:53], v58, s[2:3] offset:32
	global_load_dwordx4 v[54:57], v58, s[2:3] offset:16
	global_load_dwordx4 v[41:44], v58, s[2:3] offset:48
	s_mov_b32 s0, 0x667f3bcd
	s_mov_b32 s1, 0x3fe6a09e
	s_mov_b32 s7, 0xbfe6a09e
	s_mov_b32 s6, s0
	s_waitcnt vmcnt(2)
	v_mul_f64 v[25:26], v[27:28], v[52:53]
	v_mul_f64 v[45:46], v[31:32], v[52:53]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[29:30], v[21:22], v[56:57]
	v_fma_f64 v[37:38], v[31:32], v[50:51], -v[25:26]
	global_load_dwordx4 v[31:34], v58, s[2:3] offset:80
	v_fmac_f64_e32 v[45:46], v[27:28], v[50:51]
	v_mul_f64 v[50:51], v[17:18], v[56:57]
	v_fmac_f64_e32 v[29:30], v[17:18], v[54:55]
	global_load_dwordx4 v[25:28], v58, s[2:3]
	v_fma_f64 v[21:22], v[21:22], v[54:55], -v[50:51]
	global_load_dwordx4 v[50:53], v58, s[2:3] offset:64
	s_waitcnt vmcnt(2)
	v_mul_f64 v[17:18], v[19:20], v[33:34]
	v_fma_f64 v[54:55], v[23:24], v[31:32], -v[17:18]
	v_mul_f64 v[23:24], v[23:24], v[33:34]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[33:34], v[15:16], v[52:53]
	v_fmac_f64_e32 v[23:24], v[19:20], v[31:32]
	global_load_dwordx4 v[17:20], v58, s[2:3] offset:96
	v_mul_f64 v[31:32], v[13:14], v[27:28]
	v_mul_f64 v[27:28], v[9:10], v[27:28]
	v_fma_f64 v[9:10], v[9:10], v[25:26], -v[31:32]
	v_fma_f64 v[31:32], v[11:12], v[50:51], -v[33:34]
	v_mul_f64 v[11:12], v[11:12], v[52:53]
	v_fmac_f64_e32 v[27:28], v[13:14], v[25:26]
	v_fmac_f64_e32 v[11:12], v[15:16], v[50:51]
	v_add_f64 v[15:16], v[9:10], -v[31:32]
	v_add_f64 v[11:12], v[27:28], -v[11:12]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[15:16]
	v_fma_f64 v[31:32], v[27:28], 2.0, -v[11:12]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[33:34], v[35:36], v[19:20]
	v_fma_f64 v[33:34], v[39:40], v[17:18], -v[33:34]
	v_mul_f64 v[39:40], v[39:40], v[19:20]
	v_mul_f64 v[19:20], v[3:4], v[43:44]
	v_fmac_f64_e32 v[39:40], v[35:36], v[17:18]
	v_fma_f64 v[19:20], v[7:8], v[41:42], -v[19:20]
	v_add_f64 v[17:18], v[21:22], -v[54:55]
	v_add_f64 v[25:26], v[45:46], -v[39:40]
	v_add_f64 v[13:14], v[5:6], -v[19:20]
	v_add_f64 v[19:20], v[29:30], -v[23:24]
	v_add_f64 v[23:24], v[37:38], -v[33:34]
	v_fma_f64 v[50:51], v[5:6], 2.0, -v[13:14]
	v_fma_f64 v[5:6], v[21:22], 2.0, -v[17:18]
	v_add_f64 v[52:53], v[13:14], -v[19:20]
	v_fma_f64 v[21:22], v[37:38], 2.0, -v[23:24]
	v_add_f64 v[37:38], v[15:16], -v[25:26]
	v_fma_f64 v[25:26], v[45:46], 2.0, -v[25:26]
	v_add_f64 v[39:40], v[11:12], v[23:24]
	v_add_f64 v[27:28], v[50:51], -v[5:6]
	v_fma_f64 v[54:55], v[13:14], 2.0, -v[52:53]
	v_add_f64 v[5:6], v[9:10], -v[21:22]
	v_fma_f64 v[35:36], v[15:16], 2.0, -v[37:38]
	v_add_f64 v[33:34], v[31:32], -v[25:26]
	v_fma_f64 v[45:46], v[11:12], 2.0, -v[39:40]
	v_fma_f64 v[15:16], s[0:1], v[37:38], v[52:53]
	v_fma_f64 v[11:12], v[50:51], 2.0, -v[27:28]
	v_lshlrev_b32_e32 v50, 3, v0
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[5:6]
	v_fma_f64 v[23:24], s[6:7], v[35:36], v[54:55]
	v_add_f64 v[13:14], v[27:28], -v[33:34]
	s_waitcnt lgkmcnt(0)
	v_fmac_f64_e32 v[15:16], s[6:7], v[39:40]
	s_barrier
	s_waitcnt lgkmcnt(0)
	v_add_f64 v[21:22], v[11:12], -v[9:10]
	v_fmac_f64_e32 v[23:24], s[6:7], v[45:46]
	v_fma_f64 v[25:26], v[27:28], 2.0, -v[13:14]
	v_fma_f64 v[27:28], v[52:53], 2.0, -v[15:16]
	v_fma_f64 v[9:10], v[11:12], 2.0, -v[21:22]
	v_fma_f64 v[11:12], v[54:55], 2.0, -v[23:24]
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_20
; %bb.19:
	s_movk_i32 s8, 0x3c0
	v_and_or_b32 v50, v50, s8, v49
	v_add_u32_e32 v50, v50, v47
	v_lshl_add_u32 v50, v50, 3, 0
	ds_write2_b64 v50, v[9:10], v[11:12] offset1:8
	ds_write2_b64 v50, v[25:26], v[27:28] offset0:16 offset1:24
	ds_write2_b64 v50, v[21:22], v[23:24] offset0:32 offset1:40
	ds_write2_b64 v50, v[13:14], v[15:16] offset0:48 offset1:56
.LBB0_20:
	s_or_b64 exec, exec, s[6:7]
	v_mul_f64 v[35:36], v[35:36], s[0:1]
	v_mul_f64 v[45:46], v[45:46], s[0:1]
	v_mul_f64 v[37:38], v[37:38], s[0:1]
	v_mul_f64 v[39:40], v[39:40], s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_22
; %bb.21:
	v_or_b32_e32 v9, v47, v48
	v_lshl_add_u32 v13, v9, 3, 0
	ds_read2st64_b64 v[9:12], v13 offset1:1
	ds_read2st64_b64 v[25:28], v13 offset0:2 offset1:3
	ds_read2st64_b64 v[21:24], v13 offset0:4 offset1:5
	ds_read2st64_b64 v[13:16], v13 offset0:6 offset1:7
.LBB0_22:
	s_or_b64 exec, exec, s[0:1]
	v_mul_f64 v[7:8], v[7:8], v[43:44]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	v_fmac_f64_e32 v[7:8], v[3:4], v[41:42]
	v_add_f64 v[3:4], v[1:2], -v[7:8]
	v_fma_f64 v[7:8], v[29:30], 2.0, -v[19:20]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[3:4]
	v_add_f64 v[41:42], v[3:4], v[17:18]
	v_add_f64 v[29:30], v[1:2], -v[7:8]
	v_fma_f64 v[3:4], v[3:4], 2.0, -v[41:42]
	v_fma_f64 v[7:8], v[31:32], 2.0, -v[33:34]
	v_add_f64 v[31:32], v[41:42], v[39:40]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[29:30]
	v_add_f64 v[19:20], v[3:4], -v[45:46]
	v_add_f64 v[17:18], v[29:30], v[5:6]
	v_add_f64 v[5:6], v[1:2], -v[7:8]
	v_add_f64 v[7:8], v[35:36], v[19:20]
	v_add_f64 v[19:20], v[37:38], v[31:32]
	v_fma_f64 v[29:30], v[29:30], 2.0, -v[17:18]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[5:6]
	v_fma_f64 v[3:4], v[3:4], 2.0, -v[7:8]
	v_fma_f64 v[31:32], v[41:42], 2.0, -v[19:20]
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_24
; %bb.23:
	v_lshlrev_b32_e32 v33, 3, v0
	s_movk_i32 s6, 0x3c0
	v_and_or_b32 v33, v33, s6, v49
	v_add_u32_e32 v33, v33, v47
	v_lshl_add_u32 v33, v33, 3, 0
	ds_write2_b64 v33, v[1:2], v[3:4] offset1:8
	ds_write2_b64 v33, v[29:30], v[31:32] offset0:16 offset1:24
	ds_write2_b64 v33, v[5:6], v[7:8] offset0:32 offset1:40
	ds_write2_b64 v33, v[17:18], v[19:20] offset0:48 offset1:56
.LBB0_24:
	s_or_b64 exec, exec, s[0:1]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_26
; %bb.25:
	v_or_b32_e32 v1, v47, v48
	v_lshl_add_u32 v17, v1, 3, 0
	ds_read2st64_b64 v[1:4], v17 offset1:1
	ds_read2st64_b64 v[29:32], v17 offset0:2 offset1:3
	ds_read2st64_b64 v[5:8], v17 offset0:4 offset1:5
	ds_read2st64_b64 v[17:20], v17 offset0:6 offset1:7
.LBB0_26:
	s_or_b64 exec, exec, s[0:1]
	s_load_dwordx2 s[0:1], s[4:5], 0x60
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_28
; %bb.27:
	v_and_b32_e32 v33, 63, v0
	v_mul_u32_u24_e32 v33, 7, v33
	v_lshlrev_b32_e32 v33, 4, v33
	v_mov_b32_e32 v34, s3
	v_add_co_u32_e32 v45, vcc, s2, v33
	v_addc_co_u32_e32 v46, vcc, 0, v34, vcc
	global_load_dwordx4 v[33:36], v[45:46], off offset:912
	global_load_dwordx4 v[37:40], v[45:46], off offset:928
	global_load_dwordx4 v[41:44], v[45:46], off offset:896
	global_load_dwordx4 v[49:52], v[45:46], off offset:944
	s_mov_b32 s2, 0x667f3bcd
	s_mov_b32 s3, 0xbfe6a09e
	s_mov_b32 s9, 0x3fe6a09e
	s_mov_b32 s8, s2
	s_waitcnt vmcnt(3)
	v_mul_f64 v[53:54], v[29:30], v[35:36]
	v_mul_f64 v[55:56], v[25:26], v[35:36]
	s_waitcnt vmcnt(2)
	v_mul_f64 v[35:36], v[31:32], v[39:40]
	v_mul_f64 v[39:40], v[27:28], v[39:40]
	v_fma_f64 v[53:54], v[25:26], v[33:34], -v[53:54]
	v_fmac_f64_e32 v[55:56], v[29:30], v[33:34]
	v_fma_f64 v[57:58], v[27:28], v[37:38], -v[35:36]
	global_load_dwordx4 v[25:28], v[45:46], off offset:960
	v_fmac_f64_e32 v[39:40], v[31:32], v[37:38]
	global_load_dwordx4 v[29:32], v[45:46], off offset:976
	global_load_dwordx4 v[33:36], v[45:46], off offset:992
	s_waitcnt vmcnt(4)
	v_mul_f64 v[37:38], v[3:4], v[43:44]
	v_mul_f64 v[43:44], v[11:12], v[43:44]
	v_or_b32_e32 v45, v47, v48
	v_fma_f64 v[11:12], v[11:12], v[41:42], -v[37:38]
	s_waitcnt vmcnt(3)
	v_mul_f64 v[37:38], v[21:22], v[51:52]
	v_fmac_f64_e32 v[43:44], v[3:4], v[41:42]
	v_mul_f64 v[3:4], v[5:6], v[51:52]
	v_fmac_f64_e32 v[37:38], v[5:6], v[49:50]
	v_fma_f64 v[3:4], v[21:22], v[49:50], -v[3:4]
	v_add_f64 v[3:4], v[9:10], -v[3:4]
	v_fma_f64 v[9:10], v[9:10], 2.0, -v[3:4]
	s_waitcnt vmcnt(2)
	v_mul_f64 v[5:6], v[7:8], v[27:28]
	v_mul_f64 v[21:22], v[23:24], v[27:28]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[27:28], v[13:14], v[31:32]
	v_fma_f64 v[5:6], v[23:24], v[25:26], -v[5:6]
	v_mul_f64 v[23:24], v[17:18], v[31:32]
	v_fmac_f64_e32 v[27:28], v[17:18], v[29:30]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[17:18], v[19:20], v[35:36]
	v_fmac_f64_e32 v[21:22], v[7:8], v[25:26]
	v_add_f64 v[5:6], v[11:12], -v[5:6]
	v_fma_f64 v[13:14], v[13:14], v[29:30], -v[23:24]
	v_mul_f64 v[23:24], v[15:16], v[35:36]
	v_fma_f64 v[7:8], v[15:16], v[33:34], -v[17:18]
	v_add_f64 v[15:16], v[1:2], -v[37:38]
	v_add_f64 v[17:18], v[55:56], -v[27:28]
	v_fma_f64 v[11:12], v[11:12], 2.0, -v[5:6]
	v_add_f64 v[13:14], v[53:54], -v[13:14]
	v_fmac_f64_e32 v[23:24], v[19:20], v[33:34]
	v_add_f64 v[19:20], v[43:44], -v[21:22]
	v_add_f64 v[7:8], v[57:58], -v[7:8]
	v_fma_f64 v[25:26], v[55:56], 2.0, -v[17:18]
	v_add_f64 v[17:18], v[3:4], -v[17:18]
	v_add_f64 v[29:30], v[15:16], v[13:14]
	v_add_f64 v[21:22], v[39:40], -v[23:24]
	v_fma_f64 v[23:24], v[1:2], 2.0, -v[15:16]
	v_fma_f64 v[1:2], v[53:54], 2.0, -v[13:14]
	v_fma_f64 v[27:28], v[43:44], 2.0, -v[19:20]
	v_add_f64 v[13:14], v[19:20], v[7:8]
	v_fma_f64 v[7:8], v[57:58], 2.0, -v[7:8]
	v_fma_f64 v[35:36], v[3:4], 2.0, -v[17:18]
	v_fma_f64 v[37:38], v[15:16], 2.0, -v[29:30]
	v_fma_f64 v[31:32], v[39:40], 2.0, -v[21:22]
	v_add_f64 v[21:22], v[5:6], -v[21:22]
	v_add_f64 v[33:34], v[9:10], -v[1:2]
	v_add_f64 v[25:26], v[23:24], -v[25:26]
	v_fma_f64 v[19:20], v[19:20], 2.0, -v[13:14]
	v_fma_f64 v[3:4], s[8:9], v[13:14], v[29:30]
	v_add_f64 v[15:16], v[27:28], -v[31:32]
	v_add_f64 v[31:32], v[11:12], -v[7:8]
	v_fma_f64 v[39:40], v[5:6], 2.0, -v[21:22]
	v_fma_f64 v[1:2], s[8:9], v[21:22], v[17:18]
	v_fma_f64 v[41:42], v[9:10], 2.0, -v[33:34]
	v_fma_f64 v[43:44], v[23:24], 2.0, -v[25:26]
	v_fma_f64 v[7:8], s[2:3], v[19:20], v[37:38]
	v_fmac_f64_e32 v[3:4], s[8:9], v[21:22]
	v_fma_f64 v[23:24], v[27:28], 2.0, -v[15:16]
	v_fma_f64 v[27:28], v[11:12], 2.0, -v[31:32]
	v_fma_f64 v[5:6], s[2:3], v[39:40], v[35:36]
	v_add_f64 v[11:12], v[25:26], v[31:32]
	v_add_f64 v[9:10], v[33:34], -v[15:16]
	v_fmac_f64_e32 v[1:2], s[2:3], v[13:14]
	v_fmac_f64_e32 v[7:8], s[8:9], v[39:40]
	v_add_f64 v[15:16], v[43:44], -v[23:24]
	v_add_f64 v[13:14], v[41:42], -v[27:28]
	v_fmac_f64_e32 v[5:6], s[2:3], v[19:20]
	v_fma_f64 v[23:24], v[25:26], 2.0, -v[11:12]
	v_fma_f64 v[21:22], v[33:34], 2.0, -v[9:10]
	v_fma_f64 v[19:20], v[29:30], 2.0, -v[3:4]
	v_fma_f64 v[17:18], v[17:18], 2.0, -v[1:2]
	v_fma_f64 v[27:28], v[37:38], 2.0, -v[7:8]
	v_fma_f64 v[31:32], v[43:44], 2.0, -v[15:16]
	v_fma_f64 v[29:30], v[41:42], 2.0, -v[13:14]
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
.LBB0_28:
	s_or_b64 exec, exec, s[6:7]
	v_and_b32_e32 v2, 3, v0
	v_or_b32_e32 v1, s15, v2
	v_add_u32_e32 v3, -1, v1
	s_movk_i32 s2, 0xff
	v_cmp_gt_u32_e32 vcc, s2, v3
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[2:3], vcc
	s_cbranch_execz .LBB0_31
; %bb.29:
	v_lshrrev_b32_e32 v4, 2, v0
	v_lshlrev_b32_e32 v3, 4, v4
	v_lshl_or_b32 v2, v2, 13, v3
	v_add_u32_e32 v3, 0, v2
	v_lshl_add_u32 v1, v4, 9, v1
	v_mov_b32_e32 v2, 0
	ds_read_b128 v[4:7], v3
	ds_read_b128 v[8:11], v3 offset:2048
	v_lshlrev_b64 v[12:13], 4, v[1:2]
	v_mov_b32_e32 v14, s1
	v_add_co_u32_e32 v12, vcc, s0, v12
	v_addc_co_u32_e32 v13, vcc, v14, v13, vcc
	s_movk_i32 s6, 0x1ff
	s_waitcnt lgkmcnt(1)
	global_store_dwordx4 v[12:13], v[4:7], off
	v_cmp_lt_u32_e32 vcc, s6, v0
	s_movk_i32 s6, 0x200
	v_add_u32_e32 v4, 0x10000, v1
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v5, 0x80000000, v11
	v_sub_u32_e32 v6, 0x30000, v1
	v_cndmask_b32_e32 v11, v11, v5, vcc
	v_cndmask_b32_e32 v4, v4, v6, vcc
	v_mov_b32_e32 v5, v2
	v_lshlrev_b64 v[12:13], 4, v[4:5]
	ds_read_b128 v[4:7], v3 offset:4096
	v_add_co_u32_e32 v12, vcc, s0, v12
	v_addc_co_u32_e32 v13, vcc, v14, v13, vcc
	global_store_dwordx4 v[12:13], v[8:11], off
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v7, 0x80000000, v7
	v_sub_u32_e32 v8, 0x20000, v1
	v_mov_b32_e32 v9, v2
	v_lshlrev_b64 v[8:9], 4, v[8:9]
	v_add_co_u32_e32 v8, vcc, s0, v8
	v_addc_co_u32_e32 v9, vcc, v14, v9, vcc
	v_cmp_gt_u32_e32 vcc, s6, v0
	global_store_dwordx4 v[8:9], v[4:7], off
	s_and_b64 exec, exec, vcc
	s_cbranch_execz .LBB0_31
; %bb.30:
	ds_read_b128 v[3:6], v3 offset:6144
	v_sub_u32_e32 v1, 0x10000, v1
	v_lshlrev_b64 v[1:2], 4, v[1:2]
	v_mov_b32_e32 v7, s1
	v_add_co_u32_e32 v1, vcc, s0, v1
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v6
	v_addc_co_u32_e32 v2, vcc, v7, v2, vcc
	global_store_dwordx4 v[1:2], v[3:6], off
.LBB0_31:
	s_or_b64 exec, exec, s[2:3]
	s_cmp_eq_u32 s14, 0
	s_movk_i32 s6, 0x101
	s_cselect_b64 s[2:3], -1, 0
	v_cmp_gt_u32_e32 vcc, s6, v0
	s_and_b64 s[2:3], s[2:3], vcc
	s_and_saveexec_b64 s[6:7], s[2:3]
	s_cbranch_execz .LBB0_39
; %bb.32:
	v_lshl_add_u32 v1, v0, 4, 0
	s_load_dwordx2 s[2:3], s[4:5], 0x68
	ds_read_b128 v[1:4], v1
	s_movk_i32 s4, 0xff
	v_cmp_lt_i32_e32 vcc, s4, v0
	s_and_saveexec_b64 s[4:5], vcc
	s_xor_b64 s[4:5], exec, s[4:5]
	s_cbranch_execz .LBB0_34
; %bb.33:
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v4, 0x80000000, v4
	v_mov_b32_e32 v0, 0x100000
	global_store_dwordx4 v0, v[1:4], s[0:1]
                                        ; implicit-def: $vgpr1_vgpr2
                                        ; implicit-def: $vgpr0
.LBB0_34:
	s_andn2_saveexec_b64 s[4:5], s[4:5]
	s_cbranch_execz .LBB0_39
; %bb.35:
	v_cmp_ne_u32_e32 vcc, 0, v0
	s_and_saveexec_b64 s[4:5], vcc
	s_xor_b64 s[4:5], exec, s[4:5]
	s_cbranch_execz .LBB0_37
; %bb.36:
	v_lshlrev_b32_e32 v9, 4, v0
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[5:8], v9, s[2:3]
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
	global_store_dwordx4 v0, v[5:8], s[0:1]
	global_store_dwordx4 v9, v[1:4], s[0:1]
                                        ; implicit-def: $vgpr1_vgpr2
.LBB0_37:
	s_waitcnt lgkmcnt(0)
	s_andn2_saveexec_b64 s[2:3], s[4:5]
	s_cbranch_execz .LBB0_39
; %bb.38:
	v_add_f64 v[5:6], v[1:2], v[3:4]
	v_add_f64 v[0:1], v[1:2], -v[3:4]
	v_mov_b32_e32 v7, 0
	v_mov_b32_e32 v8, v7
	v_mov_b32_e32 v4, 0x200000
	v_mov_b32_e32 v2, v7
	v_mov_b32_e32 v3, v7
	global_store_dwordx4 v7, v[5:8], s[0:1]
	global_store_dwordx4 v4, v[0:3], s[0:1]
.LBB0_39:
	s_endpgm
	.section	.rodata,#alloc
	.p2align	6, 0x0
	.amdhsa_kernel fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg
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
		.amdhsa_next_free_vgpr 59
		.amdhsa_next_free_sgpr 16
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
	.size	fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg, .Lfunc_end0-fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg
                                        ; -- End function
	.section	.AMDGPU.csdata
; Kernel info:
; codeLenInByte = 6904
; NumSgprs: 20
; NumVgprs: 59
; ScratchSize: 0
; MemoryBound: 0
; FloatMode: 240
; IeeeMode: 1
; LDSByteSize: 0 bytes/workgroup (compile time only)
; SGPRBlocks: 2
; VGPRBlocks: 14
; NumSGPRsForWavesPerEU: 20
; NumVGPRsForWavesPerEU: 59
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
    .name:           fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg
    .private_segment_fixed_size: 0
    .sgpr_count:     20
    .sgpr_spill_count: 0
    .symbol:         fft_rtc_fwd_len_512_factors_8_8_8_wgs_512_tpt_128_dp_op_CI_CI_unitstride_sbrc_aligned_cc_local_v3_role7_C256_Q512_N262144_reg.kd
    .uniform_work_group_size: 1
    .uses_dynamic_stack: false
    .vgpr_count:     59
    .vgpr_spill_count: 0
    .wavefront_size: 64
amdhsa.target:   'amdgcn-amd-amdhsa--gfx936:sramecc+'
amdhsa.version:
  - 1
  - 2
...

	.end_amdgpu_metadata
