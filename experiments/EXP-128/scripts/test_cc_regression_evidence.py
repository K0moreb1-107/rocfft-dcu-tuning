"""Test trace/counter readers with accepted device records and boundary ambiguities."""
import copy
import json
from pathlib import Path
import unittest

from cc_regression_evidence import trace_evidence, actual_sources, pmc_blocks, select_pmc_windows

ROOT = Path('/public/home/zhangkewei/zr')
RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-phasefix-validate-20261022/measurement-validation'


class CounterWindows(unittest.TestCase):
    def blocks(self, names):
        return [dict(name=name,fields={'ordinal':str(i)}) for i,name in enumerate(names)]

    def test_skip_correctness_and_ten_warmups(self):
        names = ['column','row']
        selected = select_pmc_windows(self.blocks(names*41),names)
        self.assertEqual(len(selected),30)
        self.assertEqual(selected[0][0]['fields']['ordinal'],'22')
        self.assertEqual(selected[-1][-1]['fields']['ordinal'],'81')

    def test_callback_correctness_names_can_differ(self):
        names = ['column','row']
        blocks = self.blocks(['column-callback','row-callback']+names*40)
        selected = select_pmc_windows(blocks,names)
        self.assertEqual(selected[0][0]['fields']['ordinal'],'22')
        partial = self.blocks(['column-callback','row']+names*40)
        self.assertEqual(select_pmc_windows(partial,names)[0][0]['fields']['ordinal'],'22')

    def test_duplicate_kernel_names_preserve_positions(self):
        names = ['transpose','fft','transpose']
        windows = select_pmc_windows(self.blocks(names*41),names)
        self.assertEqual(windows[0][0]['fields']['ordinal'],'33')
        self.assertEqual(windows[0][2]['fields']['ordinal'],'35')

    def test_truncated_or_reordered_trace_rejected(self):
        names = ['column','row']
        for blocks in (self.blocks(names*39),self.blocks(names*39+['row','column'])):
            with self.assertRaises(AssertionError):
                select_pmc_windows(blocks,names)

    def test_raw_counter_units_are_not_reinterpreted(self):
        text = 'kernel-name:"row"\n vgpr count       167\n L1 cache unit is stalled      1.25(%)\n'
        blocks = pmc_blocks(text)
        self.assertEqual(blocks[0]['fields']['vgpr count'],'167')
        self.assertEqual(blocks[0]['fields']['L1 cache unit is stalled'],'1.25(%)')


class AcceptedTraces(unittest.TestCase):
    def test_actual_timeline_units_windows_and_sources(self):
        for n in (65536,69938,167042,142688):
            for func in ('z2d_1d','d2z_1d'):
                with self.subTest(N=n,func=func):
                    folder = RUN/(str(n)+'-'+func)
                    events = json.loads((folder/'profile/trace.json').read_text())['traceEvents']
                    plan = (folder/'metadata/plan.txt').read_text()
                    record = trace_evidence(plan,events,func)
                    self.assertEqual(len(record['kernels']),2)
                    self.assertTrue(all(len(item['samples_us']) == 30 for item in record['kernels']))
                    self.assertTrue(all(item['stats_us']['median'] > 0 for item in record['kernels']))
                    sources = actual_sources((folder/'metadata/rtc.txt').read_text(),record['kernel_names'])
                    self.assertTrue(all(item['available'] for item in sources.values()))
                    changed = copy.deepcopy(events)
                    next(event for event in changed if event.get('cat') == 'HIPOPS')['dur'] *= 1000
                    # Change a timed device event, not initialization or correctness.
                    for event in changed:
                        if event.get('cat') == 'HIPOPS' and event['name'] == record['kernel_names'][0]:
                            event['dur'] *= 1000
                    with self.assertRaises(AssertionError):
                        trace_evidence(plan,changed,func)


if __name__ == '__main__':
    unittest.main()
