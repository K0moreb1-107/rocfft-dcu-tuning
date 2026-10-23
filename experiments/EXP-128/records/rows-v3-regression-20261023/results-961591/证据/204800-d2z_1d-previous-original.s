	.text
	.amdgcn_target "amdgcn-amd-amdhsa--gfx936:sramecc+"
	.protected	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg ; -- Begin function fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg
	.globl	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg
	.p2align	8
	.type	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg,@function
fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg: ; @fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg
; %bb.0:
	s_load_dwordx2 s[0:1], s[4:5], 0x10
	s_mov_b32 s2, 0xcccd
	v_mul_u32_u24_sdwa v1, v0, s2 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:WORD_0 src1_sel:DWORD
	v_lshrrev_b32_e32 v35, 21, v1
	s_load_dwordx2 s[8:9], s[4:5], 0x60
	s_waitcnt lgkmcnt(0)
	s_load_dword s3, s[0:1], 0x8
	v_mov_b64_e32 v[7:8], 0
	v_mul_lo_u16_e32 v4, 40, v35
	v_mov_b32_e32 v17, v8
	v_mov_b32_e32 v11, v8
	s_waitcnt lgkmcnt(0)
	s_add_i32 s3, s3, -1
	s_mul_hi_u32 s0, s3, 0xcccccccd
	s_lshr_b32 s0, s0, 3
	s_add_i32 s1, s0, 1
	v_cvt_f32_u32_e32 v3, s1
	s_not_b32 s0, s0
	v_mov_b32_e32 v19, v8
	v_mov_b32_e32 v21, v8
	v_rcp_iflag_f32_e32 v3, v3
	v_mov_b32_e32 v27, v8
	v_sub_u16_e32 v9, v0, v4
	v_mov_b32_e32 v31, v8
	v_mul_f32_e32 v3, 0x4f7ffffe, v3
	v_cvt_u32_f32_e32 v3, v3
	v_mov_b32_e32 v29, v8
	v_mov_b32_e32 v33, v8
	v_mov_b32_e32 v25, v8
	v_readfirstlane_b32 s2, v3
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
	s_cselect_b32 s18, s2, s0
	s_mul_i32 s19, s18, 10
	v_mov_b32_e32 v23, v8
	v_mov_b32_e32 v13, v8
	v_mov_b32_e32 v15, v8
	v_mov_b64_e32 v[1:2], v[7:8]
	v_mov_b32_e32 v16, v7
	v_mov_b32_e32 v10, v7
	v_mov_b32_e32 v18, v7
	v_mov_b32_e32 v20, v7
	v_mov_b32_e32 v26, v7
	v_cmp_gt_u16_e32 vcc, 25, v9
	v_add_u32_e32 v34, s19, v35
	v_mov_b32_e32 v30, v7
	v_mov_b32_e32 v28, v7
	v_mov_b32_e32 v32, v7
	v_mov_b32_e32 v24, v7
	v_mov_b32_e32 v22, v7
	v_mov_b32_e32 v12, v7
	v_mov_b32_e32 v14, v7
	v_mov_b64_e32 v[3:4], v[7:8]
	v_mov_b64_e32 v[5:6], v[7:8]
	s_and_saveexec_b64 s[6:7], vcc
	s_cbranch_execz .LBB0_50
; %bb.1:
	s_load_dwordx2 s[12:13], s[4:5], 0x70
	s_load_dwordx2 s[10:11], s[4:5], 0x58
	s_movk_i32 s0, 0x200
	v_mov_b64_e32 v[1:2], 0
	v_cmp_gt_u32_e64 s[0:1], s0, v34
	v_sub_u32_e32 v10, 0, v35
	v_mov_b64_e32 v[5:6], v[1:2]
	v_mov_b64_e32 v[3:4], v[1:2]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_7
; %bb.2:
	v_cmp_ne_u32_e64 s[2:3], s19, v10
                                        ; implicit-def: $vgpr3_vgpr4
                                        ; implicit-def: $vgpr5_vgpr6
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_4
; %bb.3:
	v_mul_lo_u32 v7, v34, v9
	s_mov_b32 s2, 0
	v_mov_b32_e32 v3, 4
	v_mov_b32_e32 v4, 0x1000
	v_lshlrev_b32_sdwa v8, v3, v7 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v3, s2, v7, 8
	v_lshl_or_b32 v15, v3, 4, v4
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[3:6], v8, s[12:13]
	global_load_dwordx4 v[11:14], v15, s[12:13]
	v_mov_b32_e32 v8, 0x2000
	v_alignbit_b32 v7, s2, v7, 16
	v_lshl_or_b32 v7, v7, 4, v8
	global_load_dwordx4 v[15:18], v7, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mad_u64_u32 v[7:8], s[2:3], v34, s2, v[9:10]
	v_mov_b32_e32 v8, 0
	v_mov_b32_e32 v19, s11
	v_lshlrev_b64 v[7:8], 4, v[7:8]
	v_add_co_u32_e64 v7, s[2:3], s10, v7
	v_addc_co_u32_e64 v8, s[2:3], v19, v8, s[2:3]
	global_load_dwordx4 v[19:22], v[7:8], off
	s_waitcnt vmcnt(2)
	v_mul_f64 v[7:8], v[5:6], v[13:14]
	v_mul_f64 v[13:14], v[3:4], v[13:14]
	v_fma_f64 v[3:4], v[3:4], v[11:12], -v[7:8]
	v_fmac_f64_e32 v[13:14], v[5:6], v[11:12]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[5:6], v[3:4], v[17:18]
	v_mul_f64 v[7:8], v[13:14], v[17:18]
	v_fmac_f64_e32 v[5:6], v[15:16], v[13:14]
	v_fma_f64 v[7:8], v[15:16], v[3:4], -v[7:8]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[11:12], v[21:22], v[5:6]
	v_mul_f64 v[3:4], v[19:20], v[5:6]
	v_fma_f64 v[5:6], v[19:20], v[7:8], -v[11:12]
	v_fmac_f64_e32 v[3:4], v[21:22], v[7:8]
.LBB0_4:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_6
; %bb.5:
	v_lshlrev_b32_e32 v7, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[5:6], v7, s[10:11]
	global_load_dwordx2 v[3:4], v7, s[10:11] offset:16
.LBB0_6:
	s_or_b64 exec, exec, s[2:3]
.LBB0_7:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[7:8], v[1:2]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_13
; %bb.8:
	v_cmp_ne_u32_e64 s[2:3], s19, v10
                                        ; implicit-def: $vgpr7_vgpr8
                                        ; implicit-def: $vgpr1_vgpr2
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_10
; %bb.9:
	v_add_u32_e32 v1, 25, v9
	v_mul_lo_u32 v1, v34, v1
	s_mov_b32 s2, 0
	v_mov_b32_e32 v2, 4
	v_mov_b32_e32 v8, 0x1000
	v_lshlrev_b32_sdwa v2, v2, v1 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v7, s2, v1, 8
	v_lshl_or_b32 v7, v7, 4, v8
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[10:13], v2, s[12:13]
	global_load_dwordx4 v[14:17], v7, s[12:13]
	v_mov_b32_e32 v2, 0x2000
	v_alignbit_b32 v1, s2, v1, 16
	v_lshl_or_b32 v1, v1, 4, v2
	global_load_dwordx4 v[18:21], v1, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mul_lo_u32 v1, v34, s2
	v_mov_b32_e32 v7, s11
	v_add_co_u32_e64 v1, s[2:3], v1, v9
	v_addc_co_u32_e64 v2, s[2:3], 0, 0, s[2:3]
	v_lshlrev_b64 v[1:2], 4, v[1:2]
	v_add_co_u32_e64 v1, s[2:3], s10, v1
	v_addc_co_u32_e64 v2, s[2:3], v7, v2, s[2:3]
	global_load_dwordx4 v[22:25], v[1:2], off offset:400
	s_waitcnt vmcnt(2)
	v_mul_f64 v[1:2], v[12:13], v[16:17]
	v_mul_f64 v[7:8], v[10:11], v[16:17]
	v_fma_f64 v[1:2], v[10:11], v[14:15], -v[1:2]
	v_fmac_f64_e32 v[7:8], v[12:13], v[14:15]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[10:11], v[1:2], v[20:21]
	v_mul_f64 v[12:13], v[7:8], v[20:21]
	v_fmac_f64_e32 v[10:11], v[18:19], v[7:8]
	v_fma_f64 v[12:13], v[18:19], v[1:2], -v[12:13]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[1:2], v[24:25], v[10:11]
	v_mul_f64 v[7:8], v[22:23], v[10:11]
	v_fma_f64 v[1:2], v[22:23], v[12:13], -v[1:2]
	v_fmac_f64_e32 v[7:8], v[24:25], v[12:13]
.LBB0_10:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_12
; %bb.11:
	v_lshlrev_b32_e32 v10, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[1:2], v10, s[10:11] offset:800
	global_load_dwordx2 v[7:8], v10, s[10:11] offset:816
.LBB0_12:
	s_or_b64 exec, exec, s[2:3]
.LBB0_13:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[10:11], 0
	v_mov_b64_e32 v[14:15], v[10:11]
	v_mov_b64_e32 v[12:13], v[10:11]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_19
; %bb.14:
	v_sub_u32_e32 v12, 0, v35
	v_cmp_ne_u32_e64 s[2:3], s19, v12
                                        ; implicit-def: $vgpr12_vgpr13
                                        ; implicit-def: $vgpr14_vgpr15
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_16
; %bb.15:
	v_add_u32_e32 v12, 50, v9
	v_mul_lo_u32 v20, v34, v12
	s_mov_b32 s2, 0
	v_mov_b32_e32 v12, 4
	v_mov_b32_e32 v13, 0x1000
	v_lshlrev_b32_sdwa v21, v12, v20 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v12, s2, v20, 8
	v_lshl_or_b32 v22, v12, 4, v13
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[12:15], v21, s[12:13]
	global_load_dwordx4 v[16:19], v22, s[12:13]
	v_mov_b32_e32 v21, 0x2000
	v_alignbit_b32 v20, s2, v20, 16
	v_lshl_or_b32 v20, v20, 4, v21
	global_load_dwordx4 v[20:23], v20, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mul_lo_u32 v24, v34, s2
	v_mov_b32_e32 v26, s11
	v_add_co_u32_e64 v24, s[2:3], v24, v9
	v_addc_co_u32_e64 v25, s[2:3], 0, 0, s[2:3]
	v_lshlrev_b64 v[24:25], 4, v[24:25]
	v_add_co_u32_e64 v24, s[2:3], s10, v24
	v_addc_co_u32_e64 v25, s[2:3], v26, v25, s[2:3]
	global_load_dwordx4 v[24:27], v[24:25], off offset:800
	s_waitcnt vmcnt(2)
	v_mul_f64 v[28:29], v[14:15], v[18:19]
	v_mul_f64 v[18:19], v[12:13], v[18:19]
	v_fma_f64 v[12:13], v[12:13], v[16:17], -v[28:29]
	v_fmac_f64_e32 v[18:19], v[14:15], v[16:17]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[14:15], v[12:13], v[22:23]
	v_mul_f64 v[16:17], v[18:19], v[22:23]
	v_fmac_f64_e32 v[14:15], v[20:21], v[18:19]
	v_fma_f64 v[16:17], v[20:21], v[12:13], -v[16:17]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[18:19], v[26:27], v[14:15]
	v_mul_f64 v[12:13], v[24:25], v[14:15]
	v_fma_f64 v[14:15], v[24:25], v[16:17], -v[18:19]
	v_fmac_f64_e32 v[12:13], v[26:27], v[16:17]
.LBB0_16:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_18
; %bb.17:
	v_lshlrev_b32_e32 v16, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[14:15], v16, s[10:11] offset:1600
	global_load_dwordx2 v[12:13], v16, s[10:11] offset:1616
.LBB0_18:
	s_or_b64 exec, exec, s[2:3]
.LBB0_19:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[16:17], v[10:11]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_25
; %bb.20:
	v_sub_u32_e32 v10, 0, v35
	v_cmp_ne_u32_e64 s[2:3], s19, v10
                                        ; implicit-def: $vgpr16_vgpr17
                                        ; implicit-def: $vgpr10_vgpr11
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_22
; %bb.21:
	v_add_u32_e32 v10, 0x4b, v9
	v_mul_lo_u32 v10, v34, v10
	s_mov_b32 s2, 0
	v_mov_b32_e32 v11, 4
	v_mov_b32_e32 v17, 0x1000
	v_lshlrev_b32_sdwa v11, v11, v10 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v16, s2, v10, 8
	v_lshl_or_b32 v24, v16, 4, v17
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[16:19], v11, s[12:13]
	global_load_dwordx4 v[20:23], v24, s[12:13]
	v_mov_b32_e32 v11, 0x2000
	v_alignbit_b32 v10, s2, v10, 16
	v_lshl_or_b32 v10, v10, 4, v11
	global_load_dwordx4 v[24:27], v10, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mul_lo_u32 v10, v34, s2
	v_mov_b32_e32 v28, s11
	v_add_co_u32_e64 v10, s[2:3], v10, v9
	v_addc_co_u32_e64 v11, s[2:3], 0, 0, s[2:3]
	v_lshlrev_b64 v[10:11], 4, v[10:11]
	v_add_co_u32_e64 v10, s[2:3], s10, v10
	v_addc_co_u32_e64 v11, s[2:3], v28, v11, s[2:3]
	global_load_dwordx4 v[28:31], v[10:11], off offset:1200
	s_waitcnt vmcnt(2)
	v_mul_f64 v[10:11], v[18:19], v[22:23]
	v_mul_f64 v[22:23], v[16:17], v[22:23]
	v_fma_f64 v[10:11], v[16:17], v[20:21], -v[10:11]
	v_fmac_f64_e32 v[22:23], v[18:19], v[20:21]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[16:17], v[10:11], v[26:27]
	v_mul_f64 v[18:19], v[22:23], v[26:27]
	v_fmac_f64_e32 v[16:17], v[24:25], v[22:23]
	v_fma_f64 v[18:19], v[24:25], v[10:11], -v[18:19]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[10:11], v[30:31], v[16:17]
	v_mul_f64 v[16:17], v[28:29], v[16:17]
	v_fma_f64 v[10:11], v[28:29], v[18:19], -v[10:11]
	v_fmac_f64_e32 v[16:17], v[30:31], v[18:19]
.LBB0_22:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_24
; %bb.23:
	v_lshlrev_b32_e32 v18, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[10:11], v18, s[10:11] offset:2400
	global_load_dwordx2 v[16:17], v18, s[10:11] offset:2416
.LBB0_24:
	s_or_b64 exec, exec, s[2:3]
.LBB0_25:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[22:23], 0
	v_mov_b64_e32 v[20:21], v[22:23]
	v_mov_b64_e32 v[18:19], v[22:23]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_31
; %bb.26:
	v_sub_u32_e32 v18, 0, v35
	v_cmp_ne_u32_e64 s[2:3], s19, v18
                                        ; implicit-def: $vgpr18_vgpr19
                                        ; implicit-def: $vgpr20_vgpr21
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_28
; %bb.27:
	v_add_u32_e32 v18, 0x64, v9
	v_mul_lo_u32 v28, v34, v18
	s_mov_b32 s2, 0
	v_mov_b32_e32 v18, 4
	v_mov_b32_e32 v19, 0x1000
	v_lshlrev_b32_sdwa v29, v18, v28 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_alignbit_b32 v18, s2, v28, 8
	v_lshl_or_b32 v30, v18, 4, v19
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[18:21], v29, s[12:13]
	global_load_dwordx4 v[24:27], v30, s[12:13]
	v_mov_b32_e32 v29, 0x2000
	v_alignbit_b32 v28, s2, v28, 16
	v_lshl_or_b32 v28, v28, 4, v29
	global_load_dwordx4 v[28:31], v28, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mul_lo_u32 v32, v34, s2
	v_mov_b32_e32 v36, s11
	v_add_co_u32_e64 v32, s[2:3], v32, v9
	v_addc_co_u32_e64 v33, s[2:3], 0, 0, s[2:3]
	v_lshlrev_b64 v[32:33], 4, v[32:33]
	v_add_co_u32_e64 v32, s[2:3], s10, v32
	v_addc_co_u32_e64 v33, s[2:3], v36, v33, s[2:3]
	global_load_dwordx4 v[36:39], v[32:33], off offset:1600
	s_waitcnt vmcnt(2)
	v_mul_f64 v[32:33], v[20:21], v[26:27]
	v_mul_f64 v[26:27], v[18:19], v[26:27]
	v_fma_f64 v[18:19], v[18:19], v[24:25], -v[32:33]
	v_fmac_f64_e32 v[26:27], v[20:21], v[24:25]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[20:21], v[18:19], v[30:31]
	v_mul_f64 v[24:25], v[26:27], v[30:31]
	v_fmac_f64_e32 v[20:21], v[28:29], v[26:27]
	v_fma_f64 v[24:25], v[28:29], v[18:19], -v[24:25]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[26:27], v[38:39], v[20:21]
	v_mul_f64 v[18:19], v[36:37], v[20:21]
	v_fma_f64 v[20:21], v[36:37], v[24:25], -v[26:27]
	v_fmac_f64_e32 v[18:19], v[38:39], v[24:25]
.LBB0_28:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_30
; %bb.29:
	v_lshlrev_b32_e32 v24, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[20:21], v24, s[10:11] offset:8
	global_load_dwordx2 v[18:19], v24, s[10:11] offset:24
.LBB0_30:
	s_or_b64 exec, exec, s[2:3]
.LBB0_31:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[24:25], v[22:23]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_37
; %bb.32:
	v_sub_u32_e32 v22, 0, v35
	v_cmp_ne_u32_e64 s[2:3], s19, v22
                                        ; implicit-def: $vgpr24_vgpr25
                                        ; implicit-def: $vgpr22_vgpr23
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_34
; %bb.33:
	v_add_u32_e32 v22, 0x7d, v9
	v_mul_lo_u32 v30, v34, v22
	v_mov_b32_e32 v22, 4
	v_mov_b32_e32 v23, 0x1000
	s_mov_b32 s2, 0
	v_lshlrev_b32_sdwa v31, v22, v30 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v22, v30, 8, 8
	v_lshl_or_b32 v32, v22, 4, v23
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[22:25], v31, s[12:13]
	global_load_dwordx4 v[26:29], v32, s[12:13]
	v_mov_b32_e32 v31, 0x2000
	v_alignbit_b32 v30, s2, v30, 16
	v_lshl_or_b32 v30, v30, 4, v31
	global_load_dwordx4 v[30:33], v30, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mul_lo_u32 v36, v34, s2
	v_mov_b32_e32 v38, s11
	v_add_co_u32_e64 v36, s[2:3], v36, v9
	v_addc_co_u32_e64 v37, s[2:3], 0, 0, s[2:3]
	v_lshlrev_b64 v[36:37], 4, v[36:37]
	v_add_co_u32_e64 v36, s[2:3], s10, v36
	v_addc_co_u32_e64 v37, s[2:3], v38, v37, s[2:3]
	global_load_dwordx4 v[36:39], v[36:37], off offset:2000
	s_waitcnt vmcnt(2)
	v_mul_f64 v[40:41], v[24:25], v[28:29]
	v_mul_f64 v[28:29], v[22:23], v[28:29]
	v_fma_f64 v[22:23], v[22:23], v[26:27], -v[40:41]
	v_fmac_f64_e32 v[28:29], v[24:25], v[26:27]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[24:25], v[22:23], v[32:33]
	v_mul_f64 v[26:27], v[28:29], v[32:33]
	v_fmac_f64_e32 v[24:25], v[30:31], v[28:29]
	v_fma_f64 v[26:27], v[30:31], v[22:23], -v[26:27]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[22:23], v[38:39], v[24:25]
	v_mul_f64 v[24:25], v[36:37], v[24:25]
	v_fma_f64 v[22:23], v[36:37], v[26:27], -v[22:23]
	v_fmac_f64_e32 v[24:25], v[38:39], v[26:27]
.LBB0_34:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_36
; %bb.35:
	v_lshlrev_b32_e32 v26, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[22:23], v26, s[10:11] offset:808
	global_load_dwordx2 v[24:25], v26, s[10:11] offset:824
.LBB0_36:
	s_or_b64 exec, exec, s[2:3]
.LBB0_37:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[28:29], 0
	v_mov_b64_e32 v[30:31], v[28:29]
	v_mov_b64_e32 v[26:27], v[28:29]
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_cbranch_execz .LBB0_43
; %bb.38:
	v_sub_u32_e32 v26, 0, v35
	v_cmp_ne_u32_e64 s[2:3], s19, v26
                                        ; implicit-def: $vgpr26_vgpr27
                                        ; implicit-def: $vgpr30_vgpr31
	s_and_saveexec_b64 s[16:17], s[2:3]
	s_xor_b64 s[16:17], exec, s[16:17]
	s_cbranch_execz .LBB0_40
; %bb.39:
	v_add_u32_e32 v26, 0x96, v9
	v_mul_lo_u32 v26, v34, v26
	v_mov_b32_e32 v27, 4
	v_mov_b32_e32 v30, 0x1000
	s_mov_b32 s2, 0
	v_lshlrev_b32_sdwa v27, v27, v26 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v31, v26, 8, 8
	v_lshl_or_b32 v40, v31, 4, v30
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[30:33], v27, s[12:13]
	global_load_dwordx4 v[36:39], v40, s[12:13]
	v_mov_b32_e32 v27, 0x2000
	v_alignbit_b32 v26, s2, v26, 16
	v_lshl_or_b32 v26, v26, 4, v27
	global_load_dwordx4 v[40:43], v26, s[12:13]
	s_movk_i32 s2, 0xc8
	v_mul_lo_u32 v26, v34, s2
	v_mov_b32_e32 v44, s11
	v_add_co_u32_e64 v26, s[2:3], v26, v9
	v_addc_co_u32_e64 v27, s[2:3], 0, 0, s[2:3]
	v_lshlrev_b64 v[26:27], 4, v[26:27]
	v_add_co_u32_e64 v26, s[2:3], s10, v26
	v_addc_co_u32_e64 v27, s[2:3], v44, v27, s[2:3]
	global_load_dwordx4 v[44:47], v[26:27], off offset:2400
	s_waitcnt vmcnt(2)
	v_mul_f64 v[26:27], v[32:33], v[38:39]
	v_mul_f64 v[38:39], v[30:31], v[38:39]
	v_fma_f64 v[26:27], v[30:31], v[36:37], -v[26:27]
	v_fmac_f64_e32 v[38:39], v[32:33], v[36:37]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[30:31], v[26:27], v[42:43]
	v_mul_f64 v[32:33], v[38:39], v[42:43]
	v_fmac_f64_e32 v[30:31], v[40:41], v[38:39]
	v_fma_f64 v[32:33], v[40:41], v[26:27], -v[32:33]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[36:37], v[46:47], v[30:31]
	v_mul_f64 v[26:27], v[44:45], v[30:31]
	v_fma_f64 v[30:31], v[44:45], v[32:33], -v[36:37]
	v_fmac_f64_e32 v[26:27], v[46:47], v[32:33]
.LBB0_40:
	s_andn2_saveexec_b64 s[2:3], s[16:17]
	s_cbranch_execz .LBB0_42
; %bb.41:
	v_lshlrev_b32_e32 v32, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[30:31], v32, s[10:11] offset:1608
	global_load_dwordx2 v[26:27], v32, s[10:11] offset:1624
.LBB0_42:
	s_or_b64 exec, exec, s[2:3]
.LBB0_43:
	s_or_b64 exec, exec, s[14:15]
	v_mov_b64_e32 v[32:33], v[28:29]
	s_and_saveexec_b64 s[2:3], s[0:1]
	s_cbranch_execz .LBB0_49
; %bb.44:
	v_sub_u32_e32 v28, 0, v35
	v_cmp_ne_u32_e64 s[0:1], s19, v28
                                        ; implicit-def: $vgpr28_vgpr29
                                        ; implicit-def: $vgpr32_vgpr33
	s_and_saveexec_b64 s[14:15], s[0:1]
	s_xor_b64 s[14:15], exec, s[14:15]
	s_cbranch_execz .LBB0_46
; %bb.45:
	v_add_u32_e32 v28, 0xaf, v9
	v_mul_lo_u32 v28, v34, v28
	v_mov_b32_e32 v29, 4
	v_mov_b32_e32 v32, 0x1000
	s_mov_b32 s0, 0
	v_lshlrev_b32_sdwa v29, v29, v28 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:DWORD src1_sel:BYTE_0
	v_bfe_u32 v33, v28, 8, 8
	v_lshl_or_b32 v32, v33, 4, v32
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[35:38], v29, s[12:13]
	global_load_dwordx4 v[39:42], v32, s[12:13]
	v_mov_b32_e32 v29, 0x2000
	v_alignbit_b32 v28, s0, v28, 16
	v_lshl_or_b32 v28, v28, 4, v29
	global_load_dwordx4 v[43:46], v28, s[12:13]
	s_movk_i32 s0, 0xc8
	v_mul_lo_u32 v28, v34, s0
	v_mov_b32_e32 v32, s11
	v_add_co_u32_e64 v28, s[0:1], v28, v9
	v_addc_co_u32_e64 v29, s[0:1], 0, 0, s[0:1]
	v_lshlrev_b64 v[28:29], 4, v[28:29]
	v_add_co_u32_e64 v28, s[0:1], s10, v28
	v_addc_co_u32_e64 v29, s[0:1], v32, v29, s[0:1]
	global_load_dwordx4 v[47:50], v[28:29], off offset:2800
	s_waitcnt vmcnt(2)
	v_mul_f64 v[28:29], v[37:38], v[41:42]
	v_mul_f64 v[32:33], v[35:36], v[41:42]
	v_fma_f64 v[28:29], v[35:36], v[39:40], -v[28:29]
	v_fmac_f64_e32 v[32:33], v[37:38], v[39:40]
	s_waitcnt vmcnt(1)
	v_mul_f64 v[35:36], v[28:29], v[45:46]
	v_mul_f64 v[37:38], v[32:33], v[45:46]
	v_fmac_f64_e32 v[35:36], v[43:44], v[32:33]
	v_fma_f64 v[37:38], v[43:44], v[28:29], -v[37:38]
	s_waitcnt vmcnt(0)
	v_mul_f64 v[32:33], v[49:50], v[35:36]
	v_mul_f64 v[28:29], v[47:48], v[35:36]
	v_fma_f64 v[32:33], v[47:48], v[37:38], -v[32:33]
	v_fmac_f64_e32 v[28:29], v[49:50], v[37:38]
.LBB0_46:
	s_andn2_saveexec_b64 s[0:1], s[14:15]
	s_cbranch_execz .LBB0_48
; %bb.47:
	v_lshlrev_b32_e32 v35, 5, v9
	s_waitcnt lgkmcnt(0)
	global_load_dwordx2 v[32:33], v35, s[10:11] offset:2408
	global_load_dwordx2 v[28:29], v35, s[10:11] offset:2424
.LBB0_48:
	s_or_b64 exec, exec, s[0:1]
.LBB0_49:
	s_or_b64 exec, exec, s[2:3]
.LBB0_50:
	s_or_b64 exec, exec, s[6:7]
	s_load_dwordx2 s[2:3], s[4:5], 0x68
	s_load_dwordx2 s[0:1], s[4:5], 0x0
	s_mov_b32 s4, 0xcccccccd
	v_mul_hi_u32 v35, v34, s4
	v_lshrrev_b32_e32 v35, 3, v35
	v_mul_lo_u32 v35, v35, 10
	v_sub_u32_e32 v34, v34, v35
	v_mul_u32_u24_e32 v34, 0xc8, v34
	s_and_saveexec_b64 s[4:5], vcc
	s_cbranch_execz .LBB0_52
; %bb.51:
	s_waitcnt vmcnt(1)
	v_add_f64 v[20:21], v[5:6], -v[20:21]
	s_waitcnt vmcnt(0)
	v_add_f64 v[18:19], v[3:4], -v[18:19]
	v_add_f64 v[30:31], v[14:15], -v[30:31]
	v_add_f64 v[26:27], v[12:13], -v[26:27]
	v_add_f64 v[22:23], v[1:2], -v[22:23]
	v_add_f64 v[24:25], v[7:8], -v[24:25]
	v_add_f64 v[32:33], v[10:11], -v[32:33]
	v_add_f64 v[28:29], v[16:17], -v[28:29]
	v_fma_f64 v[5:6], v[5:6], 2.0, -v[20:21]
	v_fma_f64 v[3:4], v[3:4], 2.0, -v[18:19]
	v_fma_f64 v[14:15], v[14:15], 2.0, -v[30:31]
	v_fma_f64 v[12:13], v[12:13], 2.0, -v[26:27]
	v_fma_f64 v[1:2], v[1:2], 2.0, -v[22:23]
	v_fma_f64 v[7:8], v[7:8], 2.0, -v[24:25]
	v_fma_f64 v[10:11], v[10:11], 2.0, -v[32:33]
	v_fma_f64 v[16:17], v[16:17], 2.0, -v[28:29]
	v_add_f64 v[35:36], v[20:21], -v[26:27]
	v_add_f64 v[37:38], v[30:31], v[18:19]
	v_add_f64 v[26:27], v[22:23], -v[28:29]
	v_add_f64 v[28:29], v[32:33], v[24:25]
	v_add_f64 v[30:31], v[5:6], -v[14:15]
	v_add_f64 v[32:33], v[3:4], -v[12:13]
	v_add_f64 v[39:40], v[1:2], -v[10:11]
	v_add_f64 v[14:15], v[7:8], -v[16:17]
	v_fma_f64 v[41:42], v[20:21], 2.0, -v[35:36]
	v_fma_f64 v[43:44], v[18:19], 2.0, -v[37:38]
	v_fma_f64 v[16:17], v[22:23], 2.0, -v[26:27]
	v_fma_f64 v[18:19], v[24:25], 2.0, -v[28:29]
	s_mov_b32 s6, 0x667f3bcd
	v_fma_f64 v[20:21], v[5:6], 2.0, -v[30:31]
	v_fma_f64 v[22:23], v[3:4], 2.0, -v[32:33]
	v_fma_f64 v[10:11], v[1:2], 2.0, -v[39:40]
	v_fma_f64 v[12:13], v[7:8], 2.0, -v[14:15]
	s_mov_b32 s7, 0xbfe6a09e
	v_fma_f64 v[1:2], s[6:7], v[16:17], v[41:42]
	v_fma_f64 v[3:4], s[6:7], v[18:19], v[43:44]
	s_waitcnt lgkmcnt(0)
	s_mov_b32 s11, 0x3fe6a09e
	s_mov_b32 s10, s6
	v_fma_f64 v[5:6], s[10:11], v[26:27], v[35:36]
	v_fma_f64 v[7:8], s[10:11], v[28:29], v[37:38]
	v_add_f64 v[10:11], v[20:21], -v[10:11]
	v_add_f64 v[12:13], v[22:23], -v[12:13]
	v_fmac_f64_e32 v[1:2], s[6:7], v[18:19]
	v_fmac_f64_e32 v[3:4], s[10:11], v[16:17]
	v_add_f64 v[14:15], v[30:31], -v[14:15]
	v_add_f64 v[16:17], v[32:33], v[39:40]
	v_fmac_f64_e32 v[5:6], s[6:7], v[28:29]
	v_fmac_f64_e32 v[7:8], s[10:11], v[26:27]
	v_fma_f64 v[18:19], v[20:21], 2.0, -v[10:11]
	v_fma_f64 v[20:21], v[22:23], 2.0, -v[12:13]
	v_fma_f64 v[22:23], v[41:42], 2.0, -v[1:2]
	v_fma_f64 v[24:25], v[43:44], 2.0, -v[3:4]
	v_fma_f64 v[26:27], v[30:31], 2.0, -v[14:15]
	v_fma_f64 v[28:29], v[32:33], 2.0, -v[16:17]
	v_fma_f64 v[30:31], v[35:36], 2.0, -v[5:6]
	v_fma_f64 v[32:33], v[37:38], 2.0, -v[7:8]
	v_lshl_add_u32 v35, v9, 3, v34
	v_lshl_add_u32 v35, v35, 4, 0
	ds_write_b128 v35, v[18:21]
	ds_write_b128 v35, v[22:25] offset:16
	ds_write_b128 v35, v[26:29] offset:32
	ds_write_b128 v35, v[30:33] offset:48
	ds_write_b128 v35, v[10:13] offset:64
	ds_write_b128 v35, v[1:4] offset:80
	ds_write_b128 v35, v[14:17] offset:96
	ds_write_b128 v35, v[5:8] offset:112
.LBB0_52:
	s_or_b64 exec, exec, s[4:5]
	s_waitcnt vmcnt(1)
	v_and_b32_e32 v10, 7, v9
	s_waitcnt vmcnt(0)
	v_lshlrev_b32_e32 v19, 6, v10
	s_waitcnt lgkmcnt(0)
	global_load_dwordx4 v[11:14], v19, s[0:1]
	global_load_dwordx4 v[15:18], v19, s[0:1] offset:16
	global_load_dwordx4 v[5:8], v19, s[0:1] offset:32
	global_load_dwordx4 v[1:4], v19, s[0:1] offset:48
	v_add_u32_e32 v19, v34, v9
	v_lshl_add_u32 v61, v19, 4, 0
	s_waitcnt vmcnt(0) lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	v_lshrrev_b32_e32 v27, 3, v9
	ds_read_b128 v[19:22], v61
	ds_read_b128 v[23:26], v61 offset:640
	v_mul_u32_u24_e32 v33, 40, v27
	ds_read_b128 v[27:30], v61 offset:1280
	ds_read_b128 v[35:38], v61 offset:1920
	v_lshlrev_b32_e32 v9, 6, v9
	global_load_dwordx4 v[39:42], v9, s[0:1] offset:560
	global_load_dwordx4 v[43:46], v9, s[0:1] offset:544
	ds_read_b128 v[47:50], v61 offset:2560
	s_mov_b32 s6, 0x134454ff
	s_mov_b32 s7, 0x3fee6f0e
	s_mov_b32 s13, 0xbfee6f0e
	s_mov_b32 s12, s6
	s_mov_b32 s4, 0x4755a5e
	s_mov_b32 s5, 0x3fe2cf23
	s_mov_b32 s15, 0xbfe2cf23
	s_mov_b32 s14, s4
	s_mov_b32 s10, 0x372fe950
	s_mov_b32 s11, 0x3fd3c6ef
	s_waitcnt lgkmcnt(3)
	v_mul_f64 v[31:32], v[25:26], v[13:14]
	v_mul_f64 v[51:52], v[23:24], v[13:14]
	s_waitcnt lgkmcnt(2)
	v_mul_f64 v[13:14], v[29:30], v[17:18]
	v_mul_f64 v[53:54], v[27:28], v[17:18]
	s_waitcnt lgkmcnt(1)
	v_mul_f64 v[55:56], v[37:38], v[7:8]
	v_mul_f64 v[7:8], v[35:36], v[7:8]
	v_fma_f64 v[23:24], v[23:24], v[11:12], -v[31:32]
	v_fmac_f64_e32 v[51:52], v[25:26], v[11:12]
	v_fma_f64 v[27:28], v[27:28], v[15:16], -v[13:14]
	v_fmac_f64_e32 v[53:54], v[29:30], v[15:16]
	global_load_dwordx4 v[11:14], v9, s[0:1] offset:528
	global_load_dwordx4 v[15:18], v9, s[0:1] offset:512
	s_waitcnt lgkmcnt(0)
	v_mul_f64 v[25:26], v[49:50], v[3:4]
	v_mul_f64 v[31:32], v[47:48], v[3:4]
	v_fma_f64 v[29:30], v[35:36], v[5:6], -v[55:56]
	v_or_b32_e32 v3, v33, v10
	v_add_u32_e32 v3, v34, v3
	v_lshl_add_u32 v62, v3, 4, 0
	v_fmac_f64_e32 v[7:8], v[37:38], v[5:6]
	v_add_f64 v[5:6], v[19:20], v[23:24]
	v_fma_f64 v[35:36], v[47:48], v[1:2], -v[25:26]
	v_fmac_f64_e32 v[31:32], v[49:50], v[1:2]
	v_add_f64 v[1:2], v[23:24], -v[27:28]
	v_add_f64 v[9:10], v[27:28], v[29:30]
	v_add_f64 v[33:34], v[27:28], -v[23:24]
	v_add_f64 v[49:50], v[51:52], -v[53:54]
	v_add_f64 v[47:48], v[53:54], v[7:8]
	v_add_f64 v[5:6], v[5:6], v[27:28]
	v_add_f64 v[3:4], v[35:36], -v[29:30]
	v_add_f64 v[25:26], v[23:24], v[35:36]
	v_add_f64 v[37:38], v[29:30], -v[35:36]
	v_add_f64 v[55:56], v[31:32], -v[7:8]
	v_add_f64 v[59:60], v[27:28], -v[29:30]
	s_mov_b32 s0, 0xcccd
	v_add_f64 v[27:28], v[5:6], v[29:30]
	v_add_f64 v[57:58], v[1:2], v[3:4]
	v_fma_f64 v[1:2], -0.5, v[9:10], v[19:20]
	v_add_f64 v[9:10], v[21:22], v[51:52]
	v_fmac_f64_e32 v[19:20], -0.5, v[25:26]
	v_add_f64 v[25:26], v[51:52], v[31:32]
	v_add_f64 v[33:34], v[33:34], v[37:38]
	v_fma_f64 v[3:4], -0.5, v[47:48], v[21:22]
	v_add_f64 v[37:38], v[53:54], -v[51:52]
	v_add_f64 v[47:48], v[49:50], v[55:56]
	v_add_f64 v[51:52], v[51:52], -v[31:32]
	v_add_f64 v[9:10], v[9:10], v[53:54]
	v_add_f64 v[55:56], v[23:24], -v[35:36]
	v_add_f64 v[53:54], v[53:54], -v[7:8]
	v_fmac_f64_e32 v[21:22], -0.5, v[25:26]
	v_add_f64 v[49:50], v[7:8], -v[31:32]
	v_add_f64 v[27:28], v[27:28], v[35:36]
	v_fma_f64 v[5:6], s[6:7], v[51:52], v[1:2]
	v_add_f64 v[9:10], v[9:10], v[7:8]
	v_fma_f64 v[7:8], s[12:13], v[55:56], v[3:4]
	v_fma_f64 v[23:24], s[12:13], v[53:54], v[19:20]
	v_fma_f64 v[25:26], s[6:7], v[59:60], v[21:22]
	v_fmac_f64_e32 v[19:20], s[6:7], v[53:54]
	v_fmac_f64_e32 v[21:22], s[12:13], v[59:60]
	v_fmac_f64_e32 v[1:2], s[12:13], v[51:52]
	v_fmac_f64_e32 v[3:4], s[6:7], v[55:56]
	v_fmac_f64_e32 v[5:6], s[4:5], v[53:54]
	v_fmac_f64_e32 v[7:8], s[14:15], v[59:60]
	v_add_f64 v[37:38], v[37:38], v[49:50]
	v_fmac_f64_e32 v[23:24], s[4:5], v[51:52]
	v_fmac_f64_e32 v[25:26], s[14:15], v[55:56]
	v_fmac_f64_e32 v[19:20], s[14:15], v[51:52]
	v_fmac_f64_e32 v[21:22], s[4:5], v[55:56]
	v_fmac_f64_e32 v[1:2], s[14:15], v[53:54]
	v_fmac_f64_e32 v[3:4], s[4:5], v[59:60]
	v_add_f64 v[29:30], v[9:10], v[31:32]
	v_fmac_f64_e32 v[5:6], s[10:11], v[57:58]
	v_fmac_f64_e32 v[7:8], s[10:11], v[47:48]
	v_fmac_f64_e32 v[23:24], s[10:11], v[33:34]
	v_fmac_f64_e32 v[25:26], s[10:11], v[37:38]
	v_fmac_f64_e32 v[19:20], s[10:11], v[33:34]
	v_fmac_f64_e32 v[21:22], s[10:11], v[37:38]
	v_fmac_f64_e32 v[1:2], s[10:11], v[57:58]
	v_fmac_f64_e32 v[3:4], s[10:11], v[47:48]
	s_waitcnt vmcnt(0) lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	ds_write_b128 v62, v[27:30]
	ds_write_b128 v62, v[5:8] offset:128
	ds_write_b128 v62, v[23:26] offset:256
	ds_write_b128 v62, v[19:22] offset:384
	ds_write_b128 v62, v[1:4] offset:512
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	ds_read_b128 v[1:4], v61 offset:640
	ds_read_b128 v[5:8], v61
	ds_read_b128 v[19:22], v61 offset:1280
	ds_read_b128 v[23:26], v61 offset:1920
	ds_read_b128 v[27:30], v61 offset:2560
	s_waitcnt lgkmcnt(2)
	v_mul_f64 v[31:32], v[21:22], v[13:14]
	v_mul_f64 v[9:10], v[3:4], v[17:18]
	v_mul_f64 v[17:18], v[1:2], v[17:18]
	v_mul_f64 v[13:14], v[19:20], v[13:14]
	s_waitcnt lgkmcnt(1)
	v_mul_f64 v[33:34], v[25:26], v[45:46]
	v_mul_f64 v[37:38], v[23:24], v[45:46]
	s_waitcnt lgkmcnt(0)
	v_mul_f64 v[35:36], v[27:28], v[41:42]
	v_mul_f64 v[41:42], v[29:30], v[41:42]
	v_fma_f64 v[1:2], v[1:2], v[15:16], -v[9:10]
	v_fmac_f64_e32 v[17:18], v[3:4], v[15:16]
	v_fma_f64 v[3:4], v[19:20], v[11:12], -v[31:32]
	v_fmac_f64_e32 v[13:14], v[21:22], v[11:12]
	v_fma_f64 v[9:10], v[23:24], v[43:44], -v[33:34]
	v_fmac_f64_e32 v[37:38], v[25:26], v[43:44]
	v_fmac_f64_e32 v[35:36], v[29:30], v[39:40]
	v_fma_f64 v[19:20], v[27:28], v[39:40], -v[41:42]
	v_add_f64 v[11:12], v[5:6], v[1:2]
	v_add_f64 v[39:40], v[7:8], v[17:18]
	v_add_f64 v[25:26], v[1:2], -v[3:4]
	v_add_f64 v[31:32], v[3:4], -v[1:2]
	v_add_f64 v[15:16], v[3:4], v[9:10]
	v_add_f64 v[41:42], v[13:14], v[37:38]
	v_add_f64 v[51:52], v[17:18], v[35:36]
	v_add_f64 v[29:30], v[1:2], v[19:20]
	v_add_f64 v[21:22], v[17:18], -v[35:36]
	v_add_f64 v[27:28], v[19:20], -v[9:10]
	v_add_f64 v[33:34], v[9:10], -v[19:20]
	v_add_f64 v[43:44], v[1:2], -v[19:20]
	v_add_f64 v[45:46], v[3:4], -v[9:10]
	v_add_f64 v[47:48], v[17:18], -v[13:14]
	v_add_f64 v[17:18], v[13:14], -v[17:18]
	v_add_f64 v[53:54], v[37:38], -v[35:36]
	v_add_f64 v[11:12], v[11:12], v[3:4]
	v_fma_f64 v[1:2], -0.5, v[15:16], v[5:6]
	v_fma_f64 v[3:4], -0.5, v[41:42], v[7:8]
	v_add_f64 v[23:24], v[13:14], -v[37:38]
	v_fmac_f64_e32 v[5:6], -0.5, v[29:30]
	v_add_f64 v[15:16], v[39:40], v[13:14]
	v_fmac_f64_e32 v[7:8], -0.5, v[51:52]
	v_add_f64 v[49:50], v[35:36], -v[37:38]
	v_add_f64 v[25:26], v[25:26], v[27:28]
	v_add_f64 v[27:28], v[31:32], v[33:34]
	v_add_f64 v[31:32], v[17:18], v[53:54]
	v_add_f64 v[17:18], v[11:12], v[9:10]
	v_fma_f64 v[9:10], s[6:7], v[21:22], v[1:2]
	v_fma_f64 v[11:12], s[12:13], v[43:44], v[3:4]
	v_fma_f64 v[13:14], s[12:13], v[23:24], v[5:6]
	v_add_f64 v[33:34], v[15:16], v[37:38]
	v_fma_f64 v[15:16], s[6:7], v[45:46], v[7:8]
	v_fmac_f64_e32 v[5:6], s[6:7], v[23:24]
	v_fmac_f64_e32 v[7:8], s[12:13], v[45:46]
	v_fmac_f64_e32 v[1:2], s[12:13], v[21:22]
	v_fmac_f64_e32 v[3:4], s[6:7], v[43:44]
	v_add_f64 v[29:30], v[47:48], v[49:50]
	v_fmac_f64_e32 v[9:10], s[4:5], v[23:24]
	v_fmac_f64_e32 v[11:12], s[14:15], v[45:46]
	v_fmac_f64_e32 v[13:14], s[4:5], v[21:22]
	v_fmac_f64_e32 v[15:16], s[14:15], v[43:44]
	v_fmac_f64_e32 v[5:6], s[14:15], v[21:22]
	v_fmac_f64_e32 v[7:8], s[4:5], v[43:44]
	v_fmac_f64_e32 v[1:2], s[14:15], v[23:24]
	v_fmac_f64_e32 v[3:4], s[4:5], v[45:46]
	v_add_f64 v[17:18], v[17:18], v[19:20]
	v_add_f64 v[19:20], v[33:34], v[35:36]
	v_fmac_f64_e32 v[9:10], s[10:11], v[25:26]
	v_fmac_f64_e32 v[11:12], s[10:11], v[29:30]
	v_fmac_f64_e32 v[13:14], s[10:11], v[27:28]
	v_fmac_f64_e32 v[15:16], s[10:11], v[31:32]
	v_fmac_f64_e32 v[5:6], s[10:11], v[27:28]
	v_fmac_f64_e32 v[7:8], s[10:11], v[31:32]
	v_fmac_f64_e32 v[1:2], s[10:11], v[25:26]
	v_fmac_f64_e32 v[3:4], s[10:11], v[29:30]
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	ds_write_b128 v61, v[17:20]
	ds_write_b128 v61, v[9:12] offset:640
	ds_write_b128 v61, v[13:16] offset:1280
	ds_write_b128 v61, v[5:8] offset:1920
	ds_write_b128 v61, v[1:4] offset:2560
	v_mul_u32_u24_sdwa v1, v0, s0 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:WORD_0 src1_sel:DWORD
	v_lshrrev_b32_e32 v3, 19, v1
	v_mul_lo_u16_e32 v1, 10, v3
	v_sub_u16_e32 v2, v0, v1
	v_add_u32_e32 v1, s19, v2
	v_add_u32_e32 v4, -1, v1
	s_movk_i32 s4, 0x1ff
	v_cmp_gt_u32_e32 vcc, s4, v4
	s_waitcnt lgkmcnt(0)
	s_barrier
	s_waitcnt lgkmcnt(0)
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_54
; %bb.53:
	v_and_b32_e32 v6, 0xffff, v3
	s_movk_i32 s5, 0xc8
	v_mad_u32_u24 v2, v2, s5, v6
	v_lshl_add_u32 v2, v2, 4, 0
	ds_read_b128 v[2:5], v2
	s_mov_b32 s5, 0x19000
	v_lshl_add_u32 v1, v6, 10, v1
	v_cmp_lt_u32_e32 vcc, s5, v1
	v_mov_b32_e32 v7, 0
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v5
	v_cndmask_b32_e32 v5, v5, v6, vcc
	v_sub_u32_e32 v6, 0x32000, v1
	v_cndmask_b32_e32 v6, v1, v6, vcc
	v_lshlrev_b64 v[6:7], 4, v[6:7]
	v_mov_b32_e32 v1, s9
	v_add_co_u32_e32 v6, vcc, s8, v6
	v_addc_co_u32_e32 v7, vcc, v1, v7, vcc
	global_store_dwordx4 v[6:7], v[2:5], off
.LBB0_54:
	s_or_b64 exec, exec, s[0:1]
	v_add_u16_e32 v1, 0x190, v0
	v_mul_u32_u24_e32 v2, 0xcccd, v1
	v_lshrrev_b32_e32 v3, 19, v2
	v_mul_lo_u16_e32 v2, 10, v3
	v_sub_u16_e32 v2, v1, v2
	v_add_u32_e32 v1, s19, v2
	v_add_u32_e32 v4, -1, v1
	v_cmp_gt_u32_e32 vcc, s4, v4
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_56
; %bb.55:
	v_and_b32_e32 v6, 0xffff, v3
	s_movk_i32 s4, 0xc8
	v_mad_u32_u24 v2, v2, s4, v6
	v_lshl_add_u32 v2, v2, 4, 0
	ds_read_b128 v[2:5], v2
	s_mov_b32 s4, 0x19000
	v_lshl_add_u32 v1, v6, 10, v1
	v_cmp_lt_u32_e32 vcc, s4, v1
	v_mov_b32_e32 v7, 0
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v5
	v_cndmask_b32_e32 v5, v5, v6, vcc
	v_sub_u32_e32 v6, 0x32000, v1
	v_cndmask_b32_e32 v6, v1, v6, vcc
	v_lshlrev_b64 v[6:7], 4, v[6:7]
	v_mov_b32_e32 v1, s9
	v_add_co_u32_e32 v6, vcc, s8, v6
	v_addc_co_u32_e32 v7, vcc, v1, v7, vcc
	global_store_dwordx4 v[6:7], v[2:5], off
.LBB0_56:
	s_or_b64 exec, exec, s[0:1]
	v_add_u16_e32 v1, 0x320, v0
	v_mul_u32_u24_e32 v2, 0xcccd, v1
	v_lshrrev_b32_e32 v3, 19, v2
	v_mul_lo_u16_e32 v2, 10, v3
	v_sub_u16_e32 v2, v1, v2
	v_add_u32_e32 v1, s19, v2
	v_add_u32_e32 v4, -1, v1
	s_movk_i32 s5, 0x1ff
	s_movk_i32 s4, 0x320
	v_cmp_gt_u32_e32 vcc, s5, v4
	s_and_saveexec_b64 s[0:1], vcc
	s_cbranch_execz .LBB0_58
; %bb.57:
	v_and_b32_e32 v6, 0xffff, v3
	s_movk_i32 s6, 0xc8
	v_mad_u32_u24 v2, v2, s6, v6
	v_lshl_add_u32 v2, v2, 4, 0
	ds_read_b128 v[2:5], v2
	s_mov_b32 s6, 0x19000
	v_lshl_add_u32 v1, v6, 10, v1
	v_cmp_lt_u32_e32 vcc, s6, v1
	v_mov_b32_e32 v7, 0
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v5
	v_cndmask_b32_e32 v5, v5, v6, vcc
	v_sub_u32_e32 v6, 0x32000, v1
	v_cndmask_b32_e32 v6, v1, v6, vcc
	v_lshlrev_b64 v[6:7], 4, v[6:7]
	v_mov_b32_e32 v1, s9
	v_add_co_u32_e32 v6, vcc, s8, v6
	v_addc_co_u32_e32 v7, vcc, v1, v7, vcc
	global_store_dwordx4 v[6:7], v[2:5], off
.LBB0_58:
	s_or_b64 exec, exec, s[0:1]
	v_add_u16_e32 v1, 0x4b0, v0
	v_mul_u32_u24_e32 v2, 0xcccd, v1
	v_lshrrev_b32_e32 v3, 19, v2
	v_mul_lo_u16_e32 v2, 10, v3
	v_sub_u16_e32 v2, v1, v2
	v_add_u32_e32 v1, s19, v2
	v_add_u32_e32 v4, -1, v1
	v_cmp_gt_u32_e32 vcc, s4, v0
	v_cmp_gt_u32_e64 s[0:1], s5, v4
	s_and_b64 s[4:5], vcc, s[0:1]
	s_and_saveexec_b64 s[0:1], s[4:5]
	s_cbranch_execz .LBB0_60
; %bb.59:
	v_and_b32_e32 v6, 0xffff, v3
	s_movk_i32 s4, 0xc8
	v_mad_u32_u24 v2, v2, s4, v6
	v_lshl_add_u32 v2, v2, 4, 0
	ds_read_b128 v[2:5], v2
	s_mov_b32 s4, 0x19000
	v_lshl_add_u32 v1, v6, 10, v1
	v_cmp_lt_u32_e32 vcc, s4, v1
	v_mov_b32_e32 v7, 0
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v5
	v_cndmask_b32_e32 v5, v5, v6, vcc
	v_sub_u32_e32 v6, 0x32000, v1
	v_cndmask_b32_e32 v6, v1, v6, vcc
	v_lshlrev_b64 v[6:7], 4, v[6:7]
	v_mov_b32_e32 v1, s9
	v_add_co_u32_e32 v6, vcc, s8, v6
	v_addc_co_u32_e32 v7, vcc, v1, v7, vcc
	global_store_dwordx4 v[6:7], v[2:5], off
.LBB0_60:
	s_or_b64 exec, exec, s[0:1]
	v_add_u16_e32 v1, 0x640, v0
	v_mul_u32_u24_e32 v2, 0xcccd, v1
	v_lshrrev_b32_e32 v3, 19, v2
	v_mul_lo_u16_e32 v2, 10, v3
	v_sub_u16_e32 v2, v1, v2
	s_movk_i32 s0, 0x190
	v_add_u32_e32 v1, s19, v2
	v_cmp_gt_u32_e32 vcc, s0, v0
	v_add_u32_e32 v4, -1, v1
	s_movk_i32 s0, 0x1ff
	v_cmp_gt_u32_e64 s[0:1], s0, v4
	s_and_b64 s[4:5], vcc, s[0:1]
	s_and_saveexec_b64 s[0:1], s[4:5]
	s_cbranch_execz .LBB0_62
; %bb.61:
	v_and_b32_e32 v6, 0xffff, v3
	s_movk_i32 s4, 0xc8
	v_mad_u32_u24 v2, v2, s4, v6
	v_lshl_add_u32 v2, v2, 4, 0
	ds_read_b128 v[2:5], v2
	s_mov_b32 s4, 0x19000
	v_lshl_add_u32 v1, v6, 10, v1
	v_cmp_lt_u32_e32 vcc, s4, v1
	v_mov_b32_e32 v7, 0
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v6, 0x80000000, v5
	v_cndmask_b32_e32 v5, v5, v6, vcc
	v_sub_u32_e32 v6, 0x32000, v1
	v_cndmask_b32_e32 v6, v1, v6, vcc
	v_lshlrev_b64 v[6:7], 4, v[6:7]
	v_mov_b32_e32 v1, s9
	v_add_co_u32_e32 v6, vcc, s8, v6
	v_addc_co_u32_e32 v7, vcc, v1, v7, vcc
	global_store_dwordx4 v[6:7], v[2:5], off
.LBB0_62:
	s_or_b64 exec, exec, s[0:1]
	s_cmp_eq_u32 s18, 0
	s_movk_i32 s4, 0x65
	s_cselect_b64 s[0:1], -1, 0
	v_cmp_gt_u32_e32 vcc, s4, v0
	s_and_b64 s[0:1], s[0:1], vcc
	s_and_saveexec_b64 s[4:5], s[0:1]
	s_cbranch_execz .LBB0_70
; %bb.63:
	v_lshl_add_u32 v1, v0, 4, 0
	ds_read_b128 v[1:4], v1
	s_movk_i32 s0, 0x63
	v_cmp_lt_i32_e32 vcc, s0, v0
	s_and_saveexec_b64 s[0:1], vcc
	s_xor_b64 s[0:1], exec, s[0:1]
	s_cbranch_execz .LBB0_65
; %bb.64:
	s_waitcnt lgkmcnt(0)
	v_xor_b32_e32 v4, 0x80000000, v4
	v_mov_b32_e32 v0, 0xc8000
	global_store_dwordx4 v0, v[1:4], s[8:9]
                                        ; implicit-def: $vgpr1_vgpr2
                                        ; implicit-def: $vgpr0
.LBB0_65:
	s_andn2_saveexec_b64 s[0:1], s[0:1]
	s_cbranch_execz .LBB0_70
; %bb.66:
	v_cmp_ne_u32_e32 vcc, 0, v0
	s_and_saveexec_b64 s[0:1], vcc
	s_xor_b64 s[0:1], exec, s[0:1]
	s_cbranch_execz .LBB0_68
; %bb.67:
	v_lshlrev_b32_e32 v9, 4, v0
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
	v_mov_b32_e32 v15, s9
	v_fma_f64 v[4:5], 0.5, v[9:10], v[17:18]
	v_fma_f64 v[6:7], 0.5, v[11:12], v[2:3]
	v_fma_f64 v[0:1], v[9:10], 0.5, -v[17:18]
	v_fmac_f64_e32 v[2:3], -0.5, v[11:12]
	v_lshlrev_b32_e32 v12, 9, v8
	v_lshlrev_b64 v[8:9], 4, v[12:13]
	v_add_co_u32_e32 v8, vcc, s8, v8
	v_addc_co_u32_e32 v9, vcc, v15, v9, vcc
	global_store_dwordx4 v14, v[4:7], s[8:9]
	global_store_dwordx4 v[8:9], v[0:3], off
                                        ; implicit-def: $vgpr1_vgpr2
.LBB0_68:
	s_andn2_saveexec_b64 s[0:1], s[0:1]
	s_cbranch_execz .LBB0_70
; %bb.69:
	s_waitcnt lgkmcnt(0)
	v_add_f64 v[5:6], v[1:2], v[3:4]
	v_add_f64 v[0:1], v[1:2], -v[3:4]
	v_mov_b32_e32 v7, 0
	v_mov_b32_e32 v8, v7
	v_mov_b32_e32 v4, 0x190000
	v_mov_b32_e32 v2, v7
	v_mov_b32_e32 v3, v7
	global_store_dwordx4 v7, v[5:8], s[8:9]
	global_store_dwordx4 v4, v[0:3], s[8:9]
.LBB0_70:
	s_endpgm
	.section	.rodata,#alloc
	.p2align	6, 0x0
	.amdhsa_kernel fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg
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
		.amdhsa_next_free_vgpr 63
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
	.size	fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg, .Lfunc_end0-fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg
                                        ; -- End function
	.section	.AMDGPU.csdata
; Kernel info:
; codeLenInByte = 7400
; NumSgprs: 24
; NumVgprs: 63
; ScratchSize: 0
; MemoryBound: 0
; FloatMode: 240
; IeeeMode: 1
; LDSByteSize: 0 bytes/workgroup (compile time only)
; SGPRBlocks: 2
; VGPRBlocks: 15
; NumSGPRsForWavesPerEU: 24
; NumVGPRsForWavesPerEU: 63
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
    .name:           fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg
    .private_segment_fixed_size: 0
    .sgpr_count:     24
    .sgpr_spill_count: 0
    .symbol:         fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_dp_op_CI_CI_unitstride_sbrc_unaligned_cc_local_v2_role7_C512_Q200_N204800_reg.kd
    .uniform_work_group_size: 1
    .uses_dynamic_stack: false
    .vgpr_count:     63
    .vgpr_spill_count: 0
    .wavefront_size: 64
amdhsa.target:   'amdgcn-amd-amdhsa--gfx936:sramecc+'
amdhsa.version:
  - 1
  - 2
...

	.end_amdgpu_metadata
