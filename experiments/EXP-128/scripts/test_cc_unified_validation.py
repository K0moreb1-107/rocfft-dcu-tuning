"""Host-only validation control-flow tests; no device acceptance implied."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import validate_cc_local_unified as validation


class ValidationFlow(unittest.TestCase):
    def test_failed_check_is_reported_before_missing_timings(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder/'fft_test_1d.check.csv').write_text(
                'func,N,batch,check,err_a,err_b\nd2z_1d,65536,1,FAIL,1,-1\n')
            with self.assertRaises(validation.CaseError) as caught:
                validation.read_numerical_outputs(folder, 65536, 'd2z_1d', 2)
            self.assertEqual(caught.exception.stage, 'numerical')
            self.assertEqual(caught.exception.returncode, 2)
            self.assertIn('correctness check failed', str(caught.exception))
            self.assertNotIn('No such file', str(caught.exception))

    def test_profiler_child_failure_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder/'fft_test_1d.check.csv').write_text(
                'func,N,batch,check,err_a,err_b\nd2z_1d,65536,1,PASS,0,-1\n')
            with self.assertRaises(validation.CaseError) as caught:
                validation.read_numerical_outputs(folder, 65536, 'd2z_1d', 3)
            self.assertEqual(caught.exception.stage, 'trace')
            self.assertEqual(caught.exception.returncode, 3)

    def exercise(self, failures=()):
        record = dict(numerical=[],dispatch=[],failures=[])
        attempted,saved = [],[]
        def operation(n,func):
            attempted.append((n,func))
            if (n,func) in failures:
                raise validation.CaseError('injected','simulated nonzero exit',17)
            return dict(N=n,func=func,check='PASS'),dict(N=n,func=func)
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                validation.check_cases(record,[65536,69938,92480,142688],[65536,69938],
                                       operation,lambda:saved.append(len(attempted)))
                error = None
            except Exception as failure:
                error = failure
        return record,attempted,saved,error

    def test_success_records_every_case(self):
        record,attempted,saved,error = self.exercise()
        self.assertIsNone(error)
        self.assertEqual(len(record['numerical']),8)
        self.assertEqual(len(record['dispatch']),8)
        self.assertEqual(saved,list(range(1,9)))

    def test_smoke_failure_stops(self):
        record,attempted,saved,error = self.exercise({(65536,'d2z_1d')})
        self.assertIsNotNone(error)
        self.assertEqual(attempted,[(65536,'z2d_1d'),(65536,'d2z_1d')])
        self.assertEqual(record['failures'][0]['returncode'],17)
        self.assertTrue(record['failures'][0]['smoke'])

    def test_main_failures_all_reported(self):
        record,attempted,saved,error = self.exercise({(92480,'z2d_1d'),(142688,'d2z_1d')})
        self.assertIsNotNone(error)
        self.assertEqual(len(attempted),8)
        self.assertEqual([(x['N'],x['func']) for x in record['failures']],
                         [(92480,'z2d_1d'),(142688,'d2z_1d')])
        self.assertTrue(all(x['stage']=='injected' and x['returncode']==17
                            for x in record['failures']))
        self.assertEqual(len(record['numerical']),6)
        self.assertEqual(len(saved),8)


if __name__ == '__main__':
    unittest.main()
