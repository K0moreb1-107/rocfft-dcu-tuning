"""Replay saved device traces and reject incomplete or altered dispatch evidence."""
import copy
import json
import os
from pathlib import Path
import re
import unittest

from cc_all_dispatch import inspect_dispatch


class DispatchReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['CC_ALL_REPLAY_ROOT'])
        case = cls.root / 'controls/101088_z2z_1d'
        cls.plan = (case / 'metadata/plan.txt').read_text()
        cls.events = json.loads((case / 'profile/trace.json').read_text())['traceEvents']

    def check(self, plan=None, events=None, func='z2z_1d'):
        return inspect_dispatch(self.plan if plan is None else plan,
                                self.events if events is None else events, func)

    def timed_indices(self):
        records = sorted((e for e in self.events if e.get('cat') == 'HIP'
                          and e['name'] == 'hipEventRecord'), key=lambda e: e['args']['index'])
        start, stop = records[:2]
        return [e['args']['index'] for e in self.events if e.get('cat') == 'HIPOPS'
                and start['args']['index'] < e['args']['index'] < stop['args']['index']]

    def test_replay_all_available_cases(self):
        files = sorted(self.root.glob('*/**/profile/trace.json'))
        self.assertGreaterEqual(len(files), 3)
        for file in files:
            case = file.parent.parent
            func = ('d2z_1d' if case.name.endswith('_0') else 'z2d_1d') if case.parent.name == 'default' else case.name.split('_', 1)[1]
            with self.subTest(case=str(case.relative_to(self.root))):
                selected, proof = inspect_dispatch((case / 'metadata/plan.txt').read_text(),
                    json.loads(file.read_text())['traceEvents'], func)
                self.assertEqual(proof['benchmark_executions'], 40)
                self.assertEqual(proof['samples'], 30)
                self.assertEqual(proof['checked_kernel_dispatches'], 40 * len(selected))

    def test_shared_transpose_and_inverse_are_separate(self):
        selected, proof = self.check()
        self.assertEqual(len(selected), 5)
        self.assertEqual(sum(e['name'] == 'transpose_rtc_tile32x32_dim2_dp_CI_CI' for e in selected), 2)
        self.assertFalse(any('_back_' in e['name'] for e in selected))
        self.assertEqual(proof['plan_executions'], 43)
        self.assertEqual(proof['correctness_executions'], 3)

    def test_opposite_correctness_geometry_may_differ(self):
        blocks = list(re.finditer(r'GridParams\n(.*?)End GridParams', self.plan, re.S))
        block = blocks[2]
        changed = block.group(0).replace('dy_lds bytes 0', 'dy_lds bytes 16', 1)
        self.check(plan=self.plan[:block.start()] + changed + self.plan[block.end():])

    def test_kernel_name_frequency_does_not_select_dispatch(self):
        events = copy.deepcopy(self.events)
        for event in events:
            if event.get('cat') == 'HIPOPS':
                event['name'] = 'bluestein_multiply_copy_shared_name'
        selected, proof = self.check(events=events)
        self.assertEqual(len(selected), 5)
        self.assertEqual(proof['checked_kernel_dispatches'], 200)

    def test_missing_device_dispatch_rejected(self):
        index = self.timed_indices()[0]
        events = [e for e in self.events if not (e.get('cat') == 'HIPOPS' and e['args']['index'] == index)]
        with self.assertRaisesRegex(ValueError, 'incomplete actual'):
            self.check(events=events)

    def test_missing_host_dispatch_rejected(self):
        index = self.timed_indices()[0]
        events = [e for e in self.events if not (e.get('cat') == 'HIP' and e['args']['index'] == index)]
        with self.assertRaisesRegex(ValueError, 'incomplete actual'):
            self.check(events=events)

    def test_reordered_kernel_sequence_rejected(self):
        events = copy.deepcopy(self.events)
        next(e for e in events if e.get('cat') == 'HIPOPS' and e['args']['index'] == self.timed_indices()[0])['name'] = 'wrong_kernel'
        with self.assertRaisesRegex(ValueError, 'execution sequence'):
            self.check(events=events)

    def test_changed_launch_geometry_rejected(self):
        events = copy.deepcopy(self.events)
        index = self.timed_indices()[0]
        for event in events:
            if event.get('cat') in ('HIP', 'HIPOPS') and event['args']['index'] == index:
                event['args']['args'] = re.sub(r'gridDimX=\d+', 'gridDimX=999', event['args']['args'])
        with self.assertRaisesRegex(ValueError, 'differs from plan geometry'):
            self.check(events=events)

    def test_changed_plan_geometry_rejected(self):
        start = self.plan.rindex('\nGridParams\n') + 1
        changed = self.plan[start:].replace('dy_lds bytes 0', 'dy_lds bytes 16', 1)
        with self.assertRaisesRegex(ValueError, 'benchmark plan geometry changed'):
            self.check(plan=self.plan[:start] + changed)

    def test_wrong_plan_execution_count_rejected(self):
        changed = re.sub(r'GridParams\n.*?End GridParams', '', self.plan, count=2, flags=re.S)
        with self.assertRaisesRegex(ValueError, 'plan execution count'):
            self.check(plan=changed)

    def test_missing_elapsed_read_rejected(self):
        events = copy.deepcopy(self.events)
        events.remove(next(e for e in events if e.get('cat') == 'HIP' and e['name'] == 'hipEventElapsedTime'))
        with self.assertRaisesRegex(ValueError, 'incomplete benchmark event loop'):
            self.check(events=events)

    def test_wrong_synchronization_event_rejected(self):
        events = copy.deepcopy(self.events)
        event = next(e for e in events if e.get('cat') == 'HIP' and e['name'] == 'hipEventSynchronize')
        event['args']['args'] = 'hipEventSynchronize(event=0xbad)'
        with self.assertRaisesRegex(ValueError, 'synchronization'):
            self.check(events=events)

    def test_dispatch_outside_event_windows_rejected(self):
        events = copy.deepcopy(self.events)
        event = copy.deepcopy(next(e for e in events if e.get('cat') == 'HIPOPS'))
        event['args']['index'] = 999999
        events.append(event)
        with self.assertRaisesRegex(ValueError, 'outside benchmark windows'):
            self.check(events=events)

    def test_duplicate_device_correlation_rejected(self):
        events = copy.deepcopy(self.events)
        events.append(copy.deepcopy(next(e for e in events if e.get('cat') == 'HIPOPS')))
        with self.assertRaisesRegex(ValueError, 'duplicate device'):
            self.check(events=events)

    def test_nondefault_stream_rejected(self):
        events = copy.deepcopy(self.events)
        event = next(e for e in events if e.get('cat') == 'HIP' and e['name'] == 'hipEventRecord')
        event['args']['args'] = event['args']['args'].replace('stream=0', 'stream=1')
        with self.assertRaisesRegex(ValueError, 'event or stream changed'):
            self.check(events=events)


if __name__ == '__main__':
    unittest.main(verbosity=2)
