"""Host checks of complete selection, whole-region interventions and profiler anomaly separation."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path('/public/home/zhangkewei/zr');sys.path[:0]=[str(ROOT),str(ROOT/'experiments/EXP-128/scripts')]
from cc_v5_regression_common import select,restore_row,adaptive_pairs,profile_evidence

RECORD=ROOT/'experiments/EXP-128/records/v5-regression-20261027'


class DiagnosticContract(unittest.TestCase):
    def test_all_negative_pairs_and_severe_pairs_are_covered(self):
        data=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/results-983952-984725/all-samples-and-statistics.json'
        rows=json.loads(data.read_text());selection=select(rows)
        actual={(x['N'],x['func'],a) for x in selection['cases'] for a in x['references']}
        expected={(x['N'],x['type']+'_1d',a) for x in rows for a in ('previous','unfused_cc') if x['speedup_'+a]<1}
        self.assertTrue(expected<=actual)
        self.assertEqual(len({(n,f) for n,f,a in expected}),115)
        detailed={(x['N'],x['func'],x['arm']) for x in selection['mandatory_detailed']}
        severe={(x['N'],x['type']+'_1d',a) for x in rows for a in ('previous','unfused_cc') if x['speedup_'+a]<.95}
        self.assertTrue(severe<=detailed)
        self.assertTrue({(n,f,'candidate') for n,f,a in severe}<=detailed)

    def test_real_generated_restorations_equal_the_complete_old_row(self):
        report=json.loads((RECORD/'compile-preflight.json').read_text())
        self.assertTrue(report['complete']);self.assertFalse(report['failures'])
        facts=json.loads((RECORD/'source-facts.json').read_text())['cases']
        by={(x['N'],x['func']):x for x in facts}
        for trial in json.loads((RECORD/'selection.json').read_text())['ablations']:
            c=by[trial['N'],trial['func']];paths=c['sources']['row']
            old=Path(paths['v4']).read_text();current=Path(paths['v5']).read_text()
            with self.subTest(N=trial['N'],func=trial['func']):
                self.assertEqual(restore_row(current,old,trial['variant']),old.replace('_cc_local_v4_','_cc_local_v5_'))
                self.assertEqual(restore_row(current,old,'identity'),current)
                with self.assertRaises(AssertionError):restore_row(current,old.replace('scalar_type R[','scalar_type R[999',1),trial['variant'])

    def test_adaptive_instrumentation_requires_two_valid_repeats(self):
        selection=dict(cases=[dict(N=131072,func='z2d_1d',references=['previous'],ratios=dict(previous=.99),reasons=[])])
        def item(arm,phase,value,valid=True):
            return dict(N=131072,func='z2d_1d',arm=arm,phase=phase,valid=valid,statistics_ms=dict(median_ms=value))
        data=[item(a,p,v) for p in ('repeat-1','repeat-2') for a,v in [('previous',.95),('candidate',1.)]]
        self.assertEqual(len(adaptive_pairs(selection,data)),1)
        data[-1]['valid']=False;self.assertFalse(adaptive_pairs(selection,data))
        data[-1]['valid']=True;data[-2]['statistics_ms']['median_ms']=1.01
        self.assertFalse(adaptive_pairs(selection,data))

    def test_bad_timestamps_never_become_stage_times_or_erase_valid_dispatch(self):
        folder=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-boundary-v5-tail-validate-20261027/measurement-validation/702464-z2d_1d'
        plan=(folder/'metadata/plan.txt').read_text();events=json.loads((folder/'profile/trace.json').read_text())['traceEvents']
        good,warning=profile_evidence(plan,events,'z2d_1d');self.assertIsNone(warning)
        bad=copy.deepcopy(events)
        devices=sorted([e for e in bad if e.get('cat')=='HIPOPS'],key=lambda e:int(e['args']['index']))
        # Inject a calibration error into the final two same-stream kernels.
        first,second=devices[-2:];start=int(first['args']['EndNs'])-100000
        second['args']['BeginNs']=str(start)
        second['args']['DurationNs']=str(int(second['args']['EndNs'])-start)
        second['dur']=(int(second['args']['EndNs'])-start)/1000
        result,warning=profile_evidence(plan,bad,'z2d_1d')
        self.assertIn('overlapping',warning)
        self.assertEqual(result['kernel_names'],good['kernel_names'])
        self.assertNotIn('kernels',result)
        self.assertEqual(result['contract']['benchmark_executions'],40)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticContract))
    (RECORD/'host-tests.json').write_text(json.dumps(dict(complete=result.wasSuccessful(),tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors)),indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
