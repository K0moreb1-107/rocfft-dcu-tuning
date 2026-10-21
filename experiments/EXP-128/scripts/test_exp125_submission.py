"""Regression checks for an existing reference and an independent candidate chain."""
import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
path = Path(__file__).with_name('submit_cc_local_exp125.py')
spec = importlib.util.spec_from_file_location('submit_cc_local_exp125', path)
submission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(submission)


class IndependentSubmission(unittest.TestCase):
    def test_performance_waits_only_for_candidate(self):
        measurement = dict(resources=dict(node_exclusive=True, cpus=8))
        with patch.object(submission.mgr.common, 'sha', return_value='a'*64):
            queue = submission.queue_config(Path('measurement.json'), measurement,
                                             Path('submitted-build.json'), '123456')
        self.assertEqual(queue['resources']['dependency'], 'afterok:123456')
        self.assertEqual(queue['deferred_measurement']['required_success_jobs'], ['123456'])
        self.assertNotIn('reference_builds', queue['deferred_measurement'])
        self.assertTrue(queue['resources']['node_exclusive'])
        self.assertNotIn('dependency', measurement['resources'])

    def test_registered_chain_has_no_off_control(self):
        directory = ROOT/'configs/experiments'
        build = json.loads((directory/'EXP-128-cc-local-exp125-on-build-20261021.json').read_text())
        timing = json.loads((directory/'EXP-128-cc-local-exp125-performance-20261021.json').read_text())
        self.assertNotIn('dependency', build['resources'])
        self.assertNotIn('previous_build_record', build['validation'])
        self.assertEqual(timing['arms']['previous'], {'registry_id': 'EXP-125-pre-memory-i'})
        self.assertIn(build['run_id'], timing['arms']['candidate']['build_record'])
        self.assertEqual(len(timing['cases']), 386)
        self.assertEqual(timing['event_iterations'], 30)
        self.assertEqual(timing['timing_warmups'], 10)
        self.assertNotEqual(timing['comparison_kind'], 'real_boundary_fusion')

    def test_validation_keeps_own_checks_without_reference_gate(self):
        source = Path(__file__).with_name('validate_cc_local.py').read_text()
        tree = ast.parse(source)
        self.assertNotIn('previous_build_record', source)
        self.assertNotIn('unfused control not validated', source)
        calls = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertTrue({'public_case', 'trace_case', 'compile_internal_fixture', 'finish'} <= calls)
        self.assertIn("'native matrix incomplete'", source)
        self.assertIn("'public matrix incomplete'", source)


if __name__ == '__main__':
    unittest.main()
