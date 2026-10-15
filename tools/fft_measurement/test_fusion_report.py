"""Fusion control reports must not label the unfused arm as a stable release."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import summarize_cufft261012 as summary
import plot_cufft261012 as plots


class FusionReport(unittest.TestCase):
    def report(self,kind):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        run=Path(tmp.name)
        manifest=dict(experiment='EXP-999',arms={'previous':{},'candidate':{}},
                      cases=[dict(N=120224,func='d2z_1d')],event_iterations=30,a100_reference={},
                      case_scope='Synthetic explicit fusion attribution report case.')
        if kind:manifest['comparison_kind']=kind
        rows=[dict(N=120224,func='d2z_1d',previous_median_ms=.04,candidate_median_ms=.03,
                   speedup_previous_median=4/3,a100_median_ms=None,a100_performance_median_percent=None)]
        with patch.object(summary,'aggregate',return_value=(manifest,{'job_id':'synthetic','gpu':{}},rows,{})),\
             patch.object(plots,'render',return_value=['plots/test.svg']):
            summary.report(run)
        return (run/'comparison.md').read_text(encoding='utf-8')
    def test_fusion_report_names_and_median_ratio(self):
        text=self.report('real_boundary_fusion')
        self.assertIn('未融合（微秒）',text);self.assertIn('已融合（微秒）',text)
        self.assertIn('40.000000 | 30.000000 | 1.333333 | 10.000000',text)
        self.assertNotIn('稳定对照',text);self.assertNotIn('A100（微秒）',text)
    def test_existing_default_report_keeps_reference_columns(self):
        text=self.report(None)
        self.assertIn('baseline（微秒）',text);self.assertIn('A100（微秒）',text)
        self.assertNotIn('融合加速比',text)


if __name__=='__main__':unittest.main()
