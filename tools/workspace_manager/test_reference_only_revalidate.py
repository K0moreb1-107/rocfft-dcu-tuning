"""An accepted candidate may wait only for its new experimental reference."""
import copy
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.workspace_manager import manager as mgr, revalidate
from tools.workspace_manager.test_dual_revalidate import DualRevalidation


class ReferenceOnlyRevalidation(unittest.TestCase):
    setUp = DualRevalidation.setUp
    dump = DualRevalidation.dump
    four_arm_fixture = DualRevalidation.four_arm_fixture
    complete_off_build = DualRevalidation.complete_off_build

    def fixture(self):
        self.four_arm_fixture()
        accepted = copy.deepcopy(self.measure['arms']['previous'])
        accepted_check = dict(job_id='9000', library_sha256=accepted['library_sha256'])
        self.measure['arms'] = dict(previous=self.measure['arms']['unfused_cc'], candidate=accepted)
        self.measure['validation_acceptance'] = accepted_check
        self.measure['validation_acceptances'] = dict(candidate=accepted_check)
        spec = self.queue['revalidated_measurement']
        old = spec.pop('reference_validations')['unfused_cc']
        spec.update(old, validation_arm='previous')
        self.queue['resources']['dependency'] = 'afterok:10004'
        self.dump(self.root/'four-arm.json', self.measure)
        spec['measurement_config_sha256'] = mgr.common.sha(self.root/'four-arm.json')
        self.protocol.arms = staticmethod(lambda cfg: ('previous', 'candidate'))
        self.protocol.schedule = staticmethod(lambda cfg: list(range(4)))

    def test_reference_only_preview_preserves_candidate_and_ratio_direction(self):
        self.fixture()
        with patch.object(mgr, 'measurement_protocol', return_value=self.protocol):
            p = revalidate.plan('measure', self.queue)
            self.assertEqual(p['validation_arm'], 'previous')
            self.assertEqual(p['processes'], 4)
            self.assertIsNone(p['pending_candidate'])
            self.assertIsNone(p['pending_validation_arm']['library_sha256'])
            self.assertEqual(p['reference_arms']['candidate'], self.measure['arms']['candidate'])
            self.complete_off_build()
            p = revalidate.plan('measure', self.queue)
            self.assertEqual(p['pending_validation_arm']['library_sha256'], self.off_built['arm']['library_sha256'])

    def test_only_new_reference_validation_dependency_is_accepted(self):
        self.fixture()
        with patch.object(mgr, 'measurement_protocol', return_value=self.protocol):
            revalidate.plan('measure', self.queue)
            for dep in ('afterok:9000:10004', 'afterok:9000', 'afterany:10004'):
                cfg = copy.deepcopy(self.queue)
                cfg['resources']['dependency'] = dep
                with self.subTest(dep=dep), self.assertRaisesRegex(ValueError, 'every pending arm'):
                    revalidate.plan('measure', cfg)

    def test_changed_existing_candidate_is_rejected(self):
        self.fixture()
        (self.root/'ref-previous/lib/librocfft.so.0.1').write_bytes(b'changed candidate')
        with patch.object(mgr, 'measurement_protocol', return_value=self.protocol):
            with self.assertRaisesRegex(ValueError, 'reference library differs'):
                revalidate.plan('measure', self.queue)

    def test_success_keeps_both_acceptances_and_off_over_on_arms(self):
        self.fixture()
        self.complete_off_build()
        q = mgr.locations(self.queue, 'measure')
        q['run'].mkdir(parents=True)
        for name in ('submission.json', 'submission-command.json'):
            self.dump(q['run']/name, {})
        p = mgr.locations(self.measure, 'measure')
        p['run'].mkdir(parents=True)
        worker = Mock()
        accepted = dict(job_id='10004', library_sha256=self.off_built['arm']['library_sha256'])

        def resolve(m):
            m = copy.deepcopy(m)
            m['arms']['previous'] = self.off_built['arm']
            return m

        with patch.object(mgr, 'measurement_protocol', return_value=self.protocol), \
             patch.object(mgr, 'claim', return_value=q), \
             patch.object(mgr, 'allocate', return_value=p), \
             patch.object(mgr, 'measurement', side_effect=resolve), \
             patch.object(revalidate, 'verify_acceptance', return_value=accepted), \
             patch.dict(sys.modules, run_cufft261012=SimpleNamespace(POLICY=self.protocol.POLICY, execute=worker)):
            revalidate.measure(self.queue)
        sent = worker.call_args.args[0]
        self.assertEqual(sent['arms']['candidate'], self.measure['arms']['candidate'])
        self.assertEqual(sent['arms']['previous'], self.off_built['arm'])
        self.assertEqual(sent['validation_acceptance']['job_id'], '9000')
        self.assertEqual(sent['validation_acceptances']['previous']['job_id'], '10004')
        self.assertEqual(sent['queued_submission']['validation_job_ids'], dict(candidate='9000', previous='10004'))
        self.assertTrue(json.loads((q['run']/'completion.json').read_text())['complete'])


if __name__ == '__main__':
    unittest.main()
