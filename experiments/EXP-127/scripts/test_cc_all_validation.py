"""Regressions for callback versions and retained build identity reuse."""
import unittest
from cc_all_validation import inspect_callback_sources, matching_source_tree


class CallbackSources(unittest.TestCase):
    def setUp(self):
        self.prefix='fft_rtc_fwd_len_200_factors_8_5_5_wgs_400_tpt_40_halfLds_dim_2_dp_op_CI_CI_unitstride_sbrc_aligned_dirReg'
        self.suffix='_generic_paired_post_v3_C168_Q200_N67200_reg_direct_scalar_packed1_phase_fft'
        self.expected=dict(name=self.prefix+self.suffix,factors=[8,5,5],W=400,P=40)
        self.names=[self.prefix+middle+self.suffix for middle in ('','_CB','_scale','_scale_CB')]

    def check(self,names=None,expected=None,func='d2z_1d'):
        return inspect_callback_sources(dict.fromkeys(self.names if names is None else names,''),
                                        self.expected if expected is None else expected,func)

    def test_scalar_v3_callbacks_and_scaling(self):
        self.assertEqual(self.check(),self.names)

    def test_complex_v2(self):
        names=[n.replace('_v3_','_v2_').replace('direct_scalar','direct_complex') for n in self.names]
        expected=dict(self.expected,name=names[0])
        self.assertEqual(self.check(names,expected),names)

    def test_preprocessing_version_from_expected(self):
        names=[n.replace('generic_paired_post_v3','paired_pre_columns_v2') for n in self.names]
        self.assertEqual(self.check(names,dict(self.expected,name=names[0]),'z2d_1d'),names)

    def test_missing_callback_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'missing callback'):
            self.check([self.names[0],self.names[2]])

    def test_wrong_or_mixed_boundary_identity_is_rejected(self):
        replacements=[('_v3_','_v2_'),('C168','C169'),('Q200','Q201'),('N67200','N67202'),
                      ('direct_scalar','direct_complex'),('phase_fft','phase_store'),
                      ('_reg_','_lds_'),('factors_8_5_5','factors_5_8_5'),('wgs_400','wgs_200'),('tpt_40','tpt_20')]
        for before,after in replacements:
            with self.subTest(before=before),self.assertRaisesRegex(ValueError,'different boundary'):
                self.check(self.names+[self.names[1].replace(before,after)])

    def test_opposite_role_does_not_satisfy_callback(self):
        with self.assertRaisesRegex(ValueError,'missing callback'):
            self.check([n.replace('generic_paired_post','paired_pre_columns') for n in self.names])

    def test_missing_expected_role_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'expected generic boundary'):
            self.check(expected=dict(self.expected,name='unrelated_kernel'))


class RetainedSource(unittest.TestCase):
    def setUp(self):
        self.previous=dict(repo='/public/home/zhangkewei/zr',source='/public/home/zhangkewei/zr/rocfft',
                           source_status='',commit='a'*40)
        self.current=dict(self.previous,commit='b'*40)

    def check(self,previous=None,current=None,read_tree=lambda commit,subtree:'c'*40):
        return matching_source_tree(self.previous if previous is None else previous,
                                    self.current if current is None else current,read_tree)

    def test_harness_commit_may_differ_when_fft_tree_is_identical(self):
        calls=[]
        proof=self.check(read_tree=lambda commit,subtree:(calls.append((commit,subtree)) or 'c'*40))
        self.assertEqual(calls,[('a'*40,'rocfft'),('b'*40,'rocfft')])
        self.assertEqual(proof['tree_sha1'],'c'*40)

    def test_fft_change_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'source tree differs'):
            self.check(read_tree=lambda commit,subtree:commit)

    def test_changed_location_is_rejected(self):
        for field in ('repo','source'):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'location differs'):
                self.check(current=dict(self.current,**{field:'/other'}))

    def test_dirty_source_is_rejected(self):
        for field in ('previous','current'):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'source is dirty'):
                self.check(**{field:dict(getattr(self,field),source_status='M kernel.cpp')})

    def test_invalid_source_or_commit_is_rejected(self):
        for field,value in [('source','/outside/rocfft'),('commit','HEAD')]:
            previous=dict(self.previous,**{field:value});current=dict(self.current,**{field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.check(previous,current)


if __name__=='__main__':
    unittest.main()
