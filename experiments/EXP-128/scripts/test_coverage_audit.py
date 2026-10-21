"""Reject comment-derived maps and inconsistent entries anywhere in the coverage manifest."""
import copy
import json
from pathlib import Path
import unittest

from audit_cc_coverage import parse_mapping, correct_coverage, validate_coverage

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/node_factory.cpp'
if not SOURCE.exists():
    SOURCE = ROOT/'library/src/node_factory.cpp'


class CoverageAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping = parse_mapping(SOURCE.read_text(encoding='utf-8'))
        cls.original = json.loads((ROOT/'experiments/EXP-128/records/implementation-20261021/coverage.json').read_text())
        cls.corrected, cls.audit = correct_coverage(cls.original, cls.mapping)

    def test_comments_cannot_replace_an_active_entry(self):
        source = '''NodeFactory::map1DLengthDouble = {
            {65536, 256}, // {65536, 64}
            /* {131072, 64}, */ {131072, 256},
        };'''
        self.assertEqual(parse_mapping(source), {65536: 256, 131072: 256})

    def test_duplicate_or_unsupported_active_entries_are_rejected(self):
        for body in ('{65536,256},{65536,64}', '{65536, 0}', '{65536, 3}',
                     '{65536,256},SOME_MACRO', '{65536,256}, trailing'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_mapping('NodeFactory::map1DLengthDouble = {\n'+body+'\n};')

    def test_real_correction_preserves_all_measurement_sizes_and_internal_cases(self):
        self.assertEqual(self.audit['corrections'], [
            dict(field='public', N=131072, before=[64,1024], after=[256,256]),
            dict(field='preserved_entries', M=65536, before=64, after=256)])
        for key in ('cases', 'geometries', 'controls', 'added_decompositions', 'columns', 'rows'):
            self.assertEqual(self.original[key], self.corrected[key])
        self.assertEqual(next(x for x in self.original['public'] if x['N']==131072)['C'], 64)
        self.assertEqual(self.audit['active_map_entries'], 222)
        self.assertEqual(self.audit['native_geometries'], 279)
        self.assertEqual(self.audit['public_N'], 193)

    def test_wrong_entries_in_each_manifest_section_are_rejected(self):
        mutations = [lambda c: c['public'][0].update(C=343, Q=96),
                     lambda c: c['preserved_entries'].update({'65536':64}),
                     lambda c: c['added_decompositions'].pop(),
                     lambda c: c['cases'].pop(),
                     lambda c: c['controls'].pop(),
                     lambda c: c['geometries'].pop(),
                     lambda c: c['columns'][0].update(factors=[1]),
                     lambda c: c['public'].append(copy.deepcopy(c['public'][0]))]
        for index, mutate in enumerate(mutations):
            with self.subTest(section=index):
                changed=copy.deepcopy(self.corrected); mutate(changed)
                with self.assertRaises(ValueError): validate_coverage(changed, self.mapping)


if __name__ == '__main__':
    unittest.main()
