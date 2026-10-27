"""Reject mixed timing versions and corrupt per-process evidence before reporting."""
import copy
import csv
import json
import math
import os
import shutil
import statistics
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import cufft261012_contract as v3
import sample_contract as v2
from common import ROOT
from tools.workspace_manager import manager


def fixture():
    values = [0.021 + i * 0.0001234567 for i in range(30)]
    row = dict(func='d2z_1d', N='131072', is_warmup='1', warmup_times='10', test_times='30')
    row.update({key: '%.6f' % value for key, value in {
        'tmax_ms': max(values), 'tmin_ms': min(values), 'tmean_ms': statistics.mean(values),
        'tmedium_ms': statistics.median(values)}.items()})
    row.update({'time_%d_ms' % i: '%.6f' % value for i, value in enumerate(values, 1)})
    samples = [dict(func='d2z_1d', N='131072', batch='1', sample_index=str(i), elapsed_ms=repr(value))
               for i, value in enumerate(values, 1)]
    check = dict(func='d2z_1d', N='131072', batch='1', check='PASS', err_a='1e-15', err_b='-1')
    return row, samples, check


def synthetic_manifest(selected):
    m = dict(policy=v3.POLICY, experiment='EXP-999', run_id='EXP-999-v3-synthetic',
             gpu_arch='gfx936', acceptance='Synthetic fixture, no measured performance.',
             comparison_description='Explicit stable-version comparison, not a fusion-only ablation.',
             case_scope='One exact A100 match and one case with no A100 reference.',
             cases=[dict(N=131072, func='d2z_1d'), dict(N=69938, func='z2d_1d')],
             arm_labels=dict(baseline='EXP125固定对照', previous='上一轮EXP128',
                             unfused_cc='同CC未融合', candidate='新候选'),
             arms={})
    commits = dict(baseline='1'*40, previous='2'*40, unfused_cc='5'*40, candidate='a'*40)
    libraries = dict(baseline='3'*64, previous='4'*64, unfused_cc='6'*64, candidate='b'*64)
    for arm in selected:
        m['arms'][arm] = dict(install=str(ROOT/('synthetic-'+arm)), source_repo=str(ROOT),
            source_commit=v3.OFFICIAL_COMMIT if arm == 'official' else commits[arm],
            library_sha256=v3.OFFICIAL_SHA if arm == 'official' else libraries[arm],
            source_state='Synthetic committed source only.', build_provenance='Synthetic fixture only.')
    return m


class VersionAndEvidence(unittest.TestCase):
    def test_three_experimental_arms_are_v3_only(self):
        m = synthetic_manifest(('baseline', 'previous', 'candidate'))
        checked = v3.validate_manifest(m)
        self.assertEqual(v3.arms(checked), ('baseline', 'previous', 'candidate'))
        self.assertNotIn('official', checked['arms'])
        self.assertEqual(manager.common.ARMS, ('official', 'previous', 'candidate'))
        legacy = copy.deepcopy(m); legacy['policy'] = v2.POLICY
        with self.assertRaises(ValueError): v2.validate_manifest(legacy)
        with self.assertRaises(ValueError): v2.arms(legacy)
        with self.assertRaises(ValueError): manager.common.validate_manifest(m)

    def test_three_arms_remain_adjacent_and_reverse_per_case(self):
        m = synthetic_manifest(('candidate', 'previous', 'baseline'))
        entries = v3.schedule(m)
        self.assertEqual([r['arm'] for r in entries],
                         ['baseline', 'previous', 'candidate', 'candidate', 'previous', 'baseline'])
        self.assertEqual([r['index'] for r in entries], list(range(6)))
        for index, case in enumerate(m['cases']):
            group = entries[index*3:index*3+3]
            self.assertTrue(all(r['N'] == case['N'] and r['func'] == case['func'] for r in group))
            self.assertEqual({r['slot'] for r in group}, {1, 2, 3})

    def test_official_identity_stays_fixed_with_extra_reference(self):
        m = synthetic_manifest(('official', 'baseline', 'previous', 'candidate'))
        v3.validate_manifest(m)
        for field, value in [('source_commit', 'a'*40), ('library_sha256', 'b'*64)]:
            changed = copy.deepcopy(m); changed['arms']['official'][field] = value
            with self.assertRaises(ValueError): v3.validate_manifest(changed)

    def test_four_experimental_arms_are_adjacent_and_legacy_rejects_new_role(self):
        m = synthetic_manifest(('candidate','unfused_cc','previous','baseline'))
        checked = v3.validate_manifest(m)
        self.assertEqual(v3.arms(checked), ('baseline','previous','unfused_cc','candidate'))
        entries = v3.schedule(checked)
        self.assertEqual([x['arm'] for x in entries],
                         ['baseline','previous','unfused_cc','candidate',
                          'candidate','unfused_cc','previous','baseline'])
        for i, case in enumerate(m['cases']):
            self.assertTrue(all(x['N']==case['N'] and x['func']==case['func']
                                for x in entries[4*i:4*i+4]))
        legacy = synthetic_manifest(('unfused_cc','candidate'))
        legacy['policy'] = v2.POLICY
        with self.assertRaises(ValueError): v2.arms(legacy)

    def test_dispatch_and_legacy_defaults(self):
        self.assertIs(manager.measurement_protocol({}), v3)
        self.assertIs(manager.measurement_protocol({'policy': v2.POLICY}), v2)
        self.assertIs(manager.measurement_protocol({'policy': manager.common.POLICY}), manager.common)
        with self.assertRaises(ValueError): manager.measurement_protocol({'policy': 'unknown'})
        self.assertEqual(v3.iterations({}), 30)
        self.assertEqual(v2.iterations({}), 50)

    def test_default_worker_uses_v3_without_submitting(self):
        import run_cufft261012 as worker
        cfg = dict(experiment='EXP-999', run_id='EXP-999-worker', arms={'official': {}, 'candidate': {}})
        allocation = dict(SLURM_JOB_ID='synthetic', SLURM_JOB_GPUS='0,1', SLURM_STEP_GPUS='0')
        with patch.object(manager, 'load', return_value=cfg), \
             patch.object(v3, 'manifest', return_value=cfg), \
             patch.dict(os.environ, allocation, clear=True), \
             patch.object(sys, 'argv', ['manage.py', 'measure', '--config', 'fake', '--worker']), \
             patch.object(worker, 'execute') as execute, patch.object(manager, 'submit') as submit:
            manager.main()
        execute.assert_called_once_with(cfg)
        submit.assert_not_called()
        self.assertEqual(worker.plan(cfg)['events_per_case_arm'], 30)

    def test_mixed_count_rejected(self):
        for count in (0, 29, 31, 50, True, '30'):
            with self.assertRaises(ValueError): v3.iterations({'event_iterations': count})

    def test_valid_lossless_and_rounded_evidence(self):
        row, samples, check = fixture()
        result = v3.validate_process(row, samples, check, 131072, 'd2z_1d', 30)
        self.assertEqual(result, [float(r['elapsed_ms']) for r in samples])

    def test_timing_condition_corruption(self):
        for key, value in [('warmup_times', '3'), ('test_times', '50'), ('is_warmup', '0'),
                           ('N', '131073'), ('func', 'z2d_1d'), ('tmedium_ms', '0.9'),
                           ('time_1_ms', '-1')]:
            row, samples, check = fixture(); row[key] = value
            with self.assertRaises(ValueError): v3.validate_process(row, samples, check, 131072, 'd2z_1d', 30)

    def test_sample_loss_reorder_and_nonfinite(self):
        mutations = [lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[-1])),
                     lambda rows: rows.reverse(), lambda rows: rows[0].update(sample_index='2')]
        mutations += [lambda rows, value=value: rows[0].update(elapsed_ms=value) for value in ('nan', 'inf', '0', '-1')]
        for mutate in mutations:
            row, samples, check = fixture(); mutate(samples)
            with self.assertRaises(ValueError): v3.validate_process(row, samples, check, 131072, 'd2z_1d', 30)

    def test_numerical_guard(self):
        for key, value in [('check', 'FAIL'), ('err_a', 'nan'), ('err_a', '1e-9'),
                           ('err_a', '-1'), ('err_b', '0'), ('batch', '2')]:
            row, samples, check = fixture(); check[key] = value
            with self.assertRaises(ValueError): v3.validate_process(row, samples, check, 131072, 'd2z_1d', 30)

    def test_frozen_sources_and_origin_loop(self):
        here = Path(__file__).resolve().parent
        for name, digest in v3.SOURCE_FILES.items(): self.assertEqual(v3.sha(here/name), digest)
        origin = ROOT/'results/reference/a100/test_fft_261012/test_fft/src/fft_test_1d.cu'
        self.assertEqual(v3.sha(origin), v3.ORIGIN_SHA)
        original = origin.read_text(encoding='utf-8')
        ported = (here/v3.SOURCE_NAME).read_text(encoding='utf-8')
        def loop(text):
            return text[text.index('template <typename TestFn>'):text.index('TimingStats calculateStats')]
        self.assertEqual(loop(original).replace('CHECK_CUDA', 'CHECK_HIP').replace('cuda', 'hip'), loop(ported))
        self.assertNotIn('first_ms', ported)
        self.assertNotIn('i % 1024', ported)

    def test_explicit_default_reference_is_pinned(self):
        m = v3.freeze_reference({})
        reference = copy.deepcopy(m['a100_reference'])
        self.assertEqual(len(v3.reference(m)), 981)
        with patch.object(v3.json, 'loads', side_effect=AssertionError('mutable latest read')):
            self.assertEqual(v3.freeze_reference(m)['a100_reference'], reference)
        for key in ('median_table_sha256', 'source_sha256', 'manifest_sha256'):
            changed = copy.deepcopy(m); changed['a100_reference'][key] = '0' * 64
            with self.assertRaises(ValueError): v3.reference(changed)

    def test_complete_report_uses_lossless_medians_and_keeps_all_samples(self):
        self.exercise_complete_report(('official', 'candidate'))

    def test_complete_three_arm_report_has_both_median_ratios_and_plots(self):
        self.exercise_complete_report(('baseline', 'previous', 'candidate'))

    def test_complete_four_arm_report_has_unfused_ratio_and_four_plots_series(self):
        self.exercise_complete_report(('baseline','previous','unfused_cc','candidate'))

    def exercise_complete_report(self, selected):
        from summarize_cufft261012 import report
        parent = Path(__file__).resolve().parents[2]/'.worktree-archives/sample-tests'
        parent.mkdir(parents=True, exist_ok=True)
        run = parent/uuid.uuid4().hex; run.mkdir()
        def cleanup():
            assert run.resolve().parent == parent.resolve()
            shutil.rmtree(run)
        self.addCleanup(cleanup)
        m = synthetic_manifest(selected)
        m = v3.validate_manifest(v3.freeze_reference(m))
        def dump(name, value): (run/name).write_text(json.dumps(value), encoding='utf-8')
        def write_csv(path, header, rows):
            with path.open('w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=header); writer.writeheader(); writer.writerows(rows)
        gpu = dict(count=1, uuid='1'*32, arch='gfx936')
        p = dict(policy=v3.POLICY, source_sha256=v3.SOURCE_SHA, source_files_sha256=v3.SOURCE_FILES,
                 timing_origin_sha256=v3.ORIGIN_SHA, complete=True, event_iterations=30, timing_warmups=10,
                 job_id='synthetic', host='synthetic', gpu=gpu,
                 arms={a: dict(v, actual_library=v['install']+'/lib/librocfft.so.0.1', binary_sha256='f'*64)
                       for a, v in m['arms'].items()})
        entries = []
        for item in v3.schedule(m):
            directory = run/('p%04d'%item['index']); directory.mkdir()
            medians = dict(official=.03, baseline=.04, previous=.03, unfused_cc=.05, candidate=.02)
            outliers = dict(official=.09, baseline=.11, previous=.09, unfused_cc=.13, candidate=.12)
            values = [medians[item['arm']]]*29+[outliers[item['arm']]]
            row, samples, check = fixture()
            for record in [row, check, *samples]: record.update(N=str(item['N']), func=item['func'])
            row.update({k:'%.6f'%v for k,v in dict(tmax_ms=max(values), tmin_ms=min(values),
                       tmean_ms=statistics.mean(values), tmedium_ms=statistics.median(values)).items()})
            row.update({'time_%d_ms'%i:'%.6f'%v for i,v in enumerate(values,1)})
            for sample,value in zip(samples,values): sample['elapsed_ms']=repr(value)
            write_csv(directory/'summary.csv',v3.HEADER,[row])
            write_csv(directory/'samples.csv',v2.SAMPLE_HEADER,samples)
            write_csv(directory/'check.csv',v3.CHECK_HEADER,[check])
            entry=dict(item,returncode=0,gpu=gpu,job_id='synthetic',host='synthetic',
                       library_sha256=m['arms'][item['arm']]['library_sha256'])
            for key,name in [('csv','summary.csv'),('samples','samples.csv'),('correctness','check.csv'),
                             ('stdout','stdout.txt'),('stderr','stderr.txt')]:
                path=directory/name
                if name.endswith('.txt'): path.write_text('Synthetic fixture.\n')
                entry[key]=path.relative_to(run).as_posix();entry[key+'_sha256']=v3.sha(path)
            entries.append(entry)
        dump('preregistration.json',m);dump('provenance.json',p);dump('processes.json',entries)
        before=[v3.sha(run/e['samples']) for e in entries]
        with patch.dict(os.environ, {'MPLCONFIGDIR': str(run/'plots/matplotlib-cache')}):
            rows=report(run)
        for arm in selected:
            if arm != 'candidate':
                self.assertTrue(all(r['speedup_'+arm+'_median']==medians[arm]/medians['candidate'] for r in rows))
        self.assertTrue(all(not k.startswith('speedup_') or k.endswith('_median') for r in rows for k in r))
        self.assertIsNotNone(rows[0]['a100_median_ms']);self.assertIsNone(rows[1]['a100_median_ms'])
        self.assertEqual(before,[v3.sha(run/e['samples']) for e in entries])
        self.assertEqual(len(list((run/'plots').glob('*.svg'))),2)
        self.assertIn('十次预热', (run/'comparison.md').read_text(encoding='utf-8'))
        self.assertIn(m['comparison_description'], (run/'comparison.md').read_text(encoding='utf-8'))
        if 'baseline' in selected:
            summary = json.loads((run/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['processes'], 2*len(selected))
            self.assertEqual(summary['events_per_arm'], 30)
            self.assertEqual(summary['timing_warmups'], 10)
            self.assertTrue(all(r['speedup_baseline_median'] == 2.0
                                and r['speedup_previous_median'] == 1.5 for r in summary['rows']))
            markdown = (run/'comparison.md').read_text(encoding='utf-8')
            self.assertIn('baseline＝EXP125固定对照', markdown)
            self.assertIn('对上一轮EXP128加速比', markdown)
            svg = next((run/'plots').glob('*.svg')).read_text(encoding='utf-8')
            for label in ('EXP125固定对照', '上一轮EXP128', '新候选'):
                self.assertIn(label, svg)
            if 'unfused_cc' in selected:
                self.assertTrue(all(r['speedup_unfused_cc_median']==2.5 for r in summary['rows']))
                self.assertIn('同CC未融合', svg)
            entries[0]['returncode'] = 1
            dump('processes.json', entries)
            from summarize_cufft261012 import aggregate
            with self.assertRaises(ValueError): aggregate(run)
            entries[0]['returncode'] = 0
            entries[0]['library_sha256'] = m['arms']['previous']['library_sha256']
            dump('processes.json', entries)
            with self.assertRaises(ValueError): aggregate(run)


if __name__ == '__main__': unittest.main()
