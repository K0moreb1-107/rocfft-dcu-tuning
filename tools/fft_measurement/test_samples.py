"""Synthetic sample statistics, integrity, plotting and unified-entry tests; no GPU work."""
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import unittest
import uuid
from unittest.mock import patch

import common
import sample_contract as contract
from summarize_samples import aggregate, report


class Samples(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[2]
        parent = workspace/'.worktree-archives/sample-tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.run = parent/uuid.uuid4().hex
        self.run.mkdir()
        def cleanup():
            assert self.run.resolve().parent == parent.resolve()
            shutil.rmtree(self.run)
        self.addCleanup(cleanup)
        self.ref = workspace/'results/reference/a100/A100_1d_32768_65536_131072_262144_524288_1048576.csv'
        self.m = dict(schema_version=1, policy=contract.POLICY, experiment='EXP-999', run_id='EXP-999-synthetic',
                      gpu_arch='gfx936', acceptance='Synthetic fixture only, not measured performance.',
                      case_scope='Synthetic cases exercise reference matching and real transform sentinels.',
                      cases=[dict(N=65536, func='z2z_1d'), dict(N=69938, func='d2z_1d'), dict(N=69938, func='z2d_1d')],
                      arms={})
        for arm in ('official', 'candidate'):
            self.m['arms'][arm] = dict(install='/public/home/zhangkewei/zr/install-'+arm,
                                      source_repo='/public/home/zhangkewei/zr',
                                      source_commit=common.OFFICIAL_COMMIT if arm == 'official' else 'a'*40,
                                      library_sha256=common.OFFICIAL_SHA if arm == 'official' else 'b'*64,
                                      source_state='Synthetic committed source, not a valid library build.',
                                      build_provenance='Synthetic fixture only; not performance evidence.')
        self.create_run()

    def dump(self, name, value):
        (self.run/name).write_text(json.dumps(value), encoding='utf-8')

    def create_run(self):
        self.dump('preregistration.json', self.m)
        self.gpu = dict(count=1, uuid='1'*32, arch='gfx936', runtime_version=1, driver_version=1)
        self.p = dict(policy=contract.POLICY, source_sha256=contract.SOURCE_SHA, complete=True,
                      event_iterations=contract.iterations(self.m), timing_warmups=3,
                      job_id='synthetic', host='synthetic', gpu=self.gpu,
                      arms={arm:dict(value, actual_library=value['install']+'/lib/librocfft.so.0.1',
                                     binary_sha256='f'*64) for arm, value in self.m['arms'].items()})
        self.dump('provenance.json', self.p)
        self.entries = []
        for planned in contract.schedule(self.m):
            directory = self.run/('p%04d'%planned['index'])
            directory.mkdir(exist_ok=True)
            arm = planned['arm']
            count = contract.iterations(self.m)
            values = ([.03]*(count-1)+[.09] if arm == 'official' else [.02]*(count-1)+[.12])
            if arm == 'previous':
                values = [.025]*count
            row = dict(zip(common.HEADER, [planned['func'], planned['N'], 1, 1, count, 1, 1,
                       min(values), statistics.mean(values), max(values), min(values),
                       'PASS', 1e-12, 1e-12 if planned['func'] == 'z2z_1d' else -1]))
            self.write_csv(directory/'summary.csv', common.HEADER, [row])
            samples = [dict(func=planned['func'], N=planned['N'], batch=1, sample_index=i, elapsed_ms=t)
                       for i, t in enumerate(values, 1)]
            self.write_csv(directory/'samples.csv', contract.SAMPLE_HEADER, samples)
            entry = dict(planned, returncode=0, gpu=self.gpu, job_id='synthetic', host='synthetic',
                         library_sha256=self.m['arms'][arm]['library_sha256'])
            for key, name in (('csv', 'summary.csv'), ('samples', 'samples.csv'),
                              ('stdout', 'stdout.txt'), ('stderr', 'stderr.txt')):
                if name.endswith('.txt'):
                    (directory/name).write_text('Synthetic fixture only.\n', encoding='utf-8')
                entry[key] = (directory/name).relative_to(self.run).as_posix()
                entry[key+'_sha256'] = common.sha(directory/name)
            self.entries.append(entry)
        self.dump('processes.json', self.entries)

    @staticmethod
    def write_csv(path, header, rows):
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

    def change_samples(self, change):
        entry = self.entries[0]
        path = self.run/entry['samples']
        rows = contract.read_samples(path)
        change(rows)
        self.write_csv(path, contract.SAMPLE_HEADER, rows)
        entry['samples_sha256'] = common.sha(path)
        self.dump('processes.json', self.entries)

    def rejected(self):
        with self.assertRaises((ValueError, OSError, KeyError, TypeError)):
            aggregate(self.run, self.ref)

    def test_default_two_arm_schedule_and_source_version(self):
        m = contract.validate_manifest(dict(self.m, policy=contract.POLICY))
        self.assertEqual(m['event_iterations'], 50)
        self.assertEqual(m['timing_source_sha256'], contract.SOURCE_SHA)
        self.assertEqual([e['arm'] for e in contract.schedule(m)],
                         ['official', 'candidate', 'candidate', 'official', 'official', 'candidate'])
        self.assertEqual(len(contract.schedule(m)), 6)

    def test_mean_median_ratios_include_slow_samples(self):
        _, _, rows, samples = aggregate(self.run, self.ref)
        self.assertEqual(len(samples[(65536, 'z2z_1d', 'candidate')]), 50)
        self.assertAlmostEqual(rows[0]['official_mean_ms'], .0312)
        self.assertAlmostEqual(rows[0]['candidate_mean_ms'], .022)
        self.assertAlmostEqual(rows[0]['speedup_official_mean'], .0312/.022)
        self.assertAlmostEqual(rows[0]['speedup_official_median'], 1.5)
        self.assertEqual(rows[0]['candidate_max_ms'], .12)
        self.assertEqual(rows[0]['candidate_p25_ms'], .02)
        self.assertIsNotNone(rows[0]['a100_mean_ms'])
        self.assertIsNone(rows[1]['a100_mean_ms'])
        self.assertNotIn('a100_median_ms', rows[0])

    def test_custom_count_frozen_and_same_for_each_arm(self):
        self.m['event_iterations'] = 100
        self.create_run()
        m, _, rows, samples = aggregate(self.run, self.ref)
        self.assertEqual(contract.iterations(m), 100)
        self.assertTrue(all(len(values) == 100 for values in samples.values()))
        self.assertTrue(all(row['events_per_arm'] == 100 for row in rows))

    def test_optional_previous_arm_one_process_each(self):
        self.m['arms']['previous'] = dict(self.m['arms']['candidate'], library_sha256='c'*64)
        self.create_run()
        _, _, rows, samples = aggregate(self.run, self.ref)
        self.assertEqual(len(samples), 9)
        self.assertAlmostEqual(rows[0]['speedup_previous_median'], 1.25)

    def test_missing_extra_reordered_or_invalid_samples_rejected(self):
        changes = [lambda rows: rows.pop(), lambda rows: rows.append(dict(rows[-1])),
                   lambda rows: rows.reverse(), lambda rows: rows[0].update(sample_index='2'),
                   lambda rows: rows[0].update(elapsed_ms='nan'),
                   lambda rows: rows[0].update(elapsed_ms='0'),
                   lambda rows: rows[0].update(N='65537'),
                   lambda rows: rows[0].update(elapsed_ms='.3')]
        for change in changes:
            with self.subTest(change=change):
                self.create_run()
                self.change_samples(change)
                self.rejected()

    def test_changed_hash_failed_case_incomplete_and_order_rejected(self):
        for change in (lambda: self.entries[0].update(samples_sha256='0'*64),
                       lambda: self.entries[0].update(returncode=1),
                       lambda: self.entries.pop(),
                       lambda: self.entries.reverse(),
                       lambda: self.entries[0].update(gpu=dict(self.gpu, uuid='2'*32))):
            with self.subTest(change=change):
                self.create_run(); change(); self.dump('processes.json', self.entries); self.rejected()
        self.create_run()
        self.p['complete'] = False; self.dump('provenance.json', self.p); self.rejected()

    def test_invalid_manifest_fields_and_stale_source_rejected(self):
        for fields in ({'event_iterations':0}, {'event_iterations':True}, {'event_iterations':1.5},
                       {'timing_source_sha256':'0'*64}, {'policy':'unknown'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                contract.validate_manifest(dict(self.m, **fields))
        m = copy.deepcopy(self.m); m['arms'].pop('official')
        with self.assertRaises(ValueError):
            contract.validate_manifest(m)

    def test_complete_report_and_svg_do_not_change_samples(self):
        before = [(entry['samples'], common.sha(self.run/entry['samples'])) for entry in self.entries]
        report(self.run, self.ref)
        self.assertEqual(len(list((self.run/'plots').glob('*.svg'))), 3)
        first = next((self.run/'plots').glob('*.svg')).read_text(encoding='utf-8')
        self.assertIn('测量序号', first)
        self.assertIn('全部样本的分布', first)
        self.assertEqual(before, [(path, common.sha(self.run/path)) for path, _ in before])
        summary = json.loads((self.run/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['processes'], 6)
        self.assertEqual(summary['policy'], contract.POLICY)
        with self.assertRaises(FileExistsError):
            report(self.run, self.ref)


class Entry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location = Path(__file__).resolve().parents[1]/'workspace_manager/manager.py'
        spec = importlib.util.spec_from_file_location('sample_test_manager', location)
        cls.manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.manager)

    def test_default_new_policy_and_explicit_legacy_dispatch(self):
        self.assertIs(self.manager.measurement_protocol({}), contract)
        self.assertIs(self.manager.measurement_protocol({'policy':common.POLICY}), common)

    def test_legacy_frozen_files_and_sample_source_hash(self):
        here = Path(__file__).resolve().parent
        self.assertEqual(common.sha(here/'fft_test_1d.cpp'), common.SOURCE_SHA)
        self.assertEqual(common.sha(here/contract.SOURCE_NAME), contract.SOURCE_SHA)

    def test_default_worker_uses_new_schedule_without_submitting(self):
        import run_samples
        cfg = {'experiment':'EXP-999', 'run_id':'EXP-999-worker',
               'arms':{'official':{}, 'candidate':{}}}
        allocation = {'SLURM_JOB_ID':'synthetic', 'SLURM_JOB_GPUS':'0,1', 'SLURM_STEP_GPUS':'0'}
        with patch.object(self.manager, 'load', return_value=cfg), \
             patch.object(contract, 'manifest', return_value=cfg), \
             patch.dict(os.environ, allocation, clear=True), \
             patch.object(sys, 'argv', ['manage.py','measure','--config','fake','--worker']), \
             patch.object(run_samples, 'execute') as execute, \
             patch.object(self.manager, 'submit') as submit:
            self.manager.main()
        execute.assert_called_once_with(cfg)
        submit.assert_not_called()
        plan = run_samples.plan(cfg)
        self.assertEqual(plan['processes'], 30)
        self.assertEqual(plan['events_per_case_arm'], 50)
        self.assertEqual(plan['processes_per_case_arm'], 1)

    def test_registered_legacy_report_selects_legacy_module(self):
        parent = Path(__file__).resolve().parents[2]/'.worktree-archives/sample-tests'
        parent.mkdir(parents=True, exist_ok=True)
        root = parent/uuid.uuid4().hex
        cfg = dict(experiment='EXP-999', run_id='EXP-999-legacy-report', policy=contract.POLICY,
                   arms={'official':{}, 'candidate':{}})
        run = root/'experiments/EXP-999/runs/EXP-999-legacy-report'
        run.mkdir(parents=True)
        (run/'preregistration.json').write_text(json.dumps({'policy':common.POLICY}))
        try:
            with patch.object(self.manager, 'ROOT', root), \
                 patch.object(self.manager, 'measurement', return_value=cfg):
                planned = self.manager.task_plan('report', cfg)
            self.assertEqual(Path(planned['command'][1]).name, 'summarize.py')
        finally:
            assert root.resolve().parent == parent.resolve()
            shutil.rmtree(root)


if __name__ == '__main__':
    unittest.main()
