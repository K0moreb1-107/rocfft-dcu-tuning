"""Separate build, validation and measurement keep real identities and dependencies."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.workspace_manager import manager as mgr, pending_build_validation as pending, revalidate


class PendingBuildValidation(unittest.TestCase):
    def setUp(self):
        parent = mgr.ROOT/'experiments/EXP-128/artifacts/preflight/pending-entry-tests'
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        changing_root = patch.object(mgr, 'ROOT', self.root)
        changing_root.start()
        self.addCleanup(changing_root.stop)
        self.build = dict(schema_version=1, experiment='EXP-999', run_id='pure-build', gpu_arch='gfx936',
            resources=dict(cpus=4), build=dict(component='rocfft', build_id='new-install',
                source_repo=str(self.root), source_dir=str(self.root/'rocfft'), source_commit='a'*40))
        self.bp = mgr.locations(self.build, 'build')
        self.bp['run'].mkdir(parents=True)
        self.dump(self.bp['run']/'submit-manifest.json', self.build)
        self.dump(self.bp['run']/'submission.json', dict(job='10001;cluster'))
        script = self.root/'experiments/EXP-999/scripts/check.py'
        script.parent.mkdir(parents=True)
        script.write_text('# synthetic numerical and path validation\n')
        self.cfg = dict(schema_version=1, experiment='EXP-999', run_id='independent-validation',
            gpu_arch='gfx936', resources=dict(cpus=4, dependency='afterok:10001'),
            build=copy.deepcopy(self.build['build']),
            post_build_validation=dict(script=str(script), sha256=mgr.common.sha(script), inputs=[]),
            existing_build_validation=dict(build_record=str(self.bp['run']/'build-provenance.json'),
                                           evidence_record='cc-local-validation.json', isolated_helpers=False),
            pending_build_validation=dict(build_config=str(self.bp['run']/'submit-manifest.json'),
                build_config_sha256=mgr.common.sha(self.bp['run']/'submit-manifest.json'), build_job_id='10001'))
        self.vp = mgr.locations(self.cfg, 'validate')

    def dump(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def complete_build(self):
        self.bp['build'].mkdir(parents=True)
        (self.bp['build']/'CMakeCache.txt').write_text('native build settings\n')
        library = self.bp['install']/'lib/librocfft.so.0.1'
        library.parent.mkdir(parents=True)
        library.write_bytes(b'new, actual installed FFT library')
        self.built = dict(complete=True, component='rocfft', experiment='EXP-999', job_id='10001',
            plan=dict(paths={k: str(v) for k, v in self.bp.items()}, post_build_validation_command=None,
                source_identity=dict(repo=str(self.root), source=str(self.root/'rocfft'),
                                     commit='b'*40, requested_commit='a'*40)),
            arm=dict(install=str(self.bp['install']), source_repo=str(self.root), source_commit='b'*40,
                     source_state='Recorded actual starting identity; no workspace freeze.',
                     library_sha256=mgr.common.sha(library),
                     build_provenance=str(self.bp['run']/'build-provenance.json')))
        self.dump(self.bp['run']/'build-provenance.json', self.built)
        return library

    def test_preview_before_build_has_no_invented_hash_and_preserves_dependency(self):
        with patch.object(mgr, 'build_plan', side_effect=AssertionError('unexpected rebuild')):
            planned = mgr.task_plan('validate', self.cfg)
        self.assertTrue(planned['pending_build'])
        self.assertIsNone(planned['library_sha256'])
        self.assertEqual(planned['source_commit'], 'a'*40)
        self.assertEqual(planned['library'], str(self.bp['install']/'lib/librocfft.so.0.1'))
        self.assertIn('--dependency=afterok:10001', planned['submission_command'])
        self.assertFalse((self.bp['run']/'build-provenance.json').exists())
        self.assertFalse(self.vp['run'].exists())

    def test_explicit_pure_build_receipt_and_dependency_are_required(self):
        for dependency in ('afterany:10001', 'afterok:99999', 'afterok:10001:99999', None):
            changed = copy.deepcopy(self.cfg)
            changed['resources']['dependency'] = dependency
            with self.subTest(dependency=dependency), self.assertRaises(ValueError):
                revalidate.plan('validate', changed)
        changed = copy.deepcopy(self.cfg)
        changed.pop('pending_build_validation')
        with self.assertRaises(FileNotFoundError):
            revalidate.plan('validate', changed)
        changed = copy.deepcopy(self.cfg)
        changed['pending_build_validation']['build_job_id'] = '10002'
        with self.assertRaisesRegex(ValueError, 'receipt'):
            revalidate.plan('validate', changed)

    def test_runtime_requires_complete_build_before_claim_or_validator(self):
        with patch.object(mgr, 'claim') as claim, patch.object(revalidate.subprocess, 'run') as run:
            with self.assertRaises(FileNotFoundError):
                revalidate.validate(self.cfg)
            claim.assert_not_called()
            run.assert_not_called()
        self.complete_build()
        self.built['complete'] = False
        self.dump(self.bp['run']/'build-provenance.json', self.built)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            revalidate.existing(self.cfg)

    def test_actual_identity_mismatch_rejected_without_source_state_comparison(self):
        library = self.complete_build()
        # An actual starting commit may differ from the requested commit, per user policy.
        self.assertEqual(revalidate.existing(self.cfg)[0]['arm']['source_commit'], 'b'*40)
        for field, value in [('install', str(self.root/'wrong-install')),
                             ('source_repo', str(self.root/'wrong-repo')),
                             ('source_commit', 'c'*40)]:
            changed = copy.deepcopy(self.built)
            changed['arm'][field] = value
            self.dump(self.bp['run']/'build-provenance.json', changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'identity differs'):
                revalidate.existing(self.cfg)
        changed = copy.deepcopy(self.built)
        changed['plan']['source_identity']['requested_commit'] = 'c'*40
        self.dump(self.bp['run']/'build-provenance.json', changed)
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            revalidate.existing(self.cfg)
        self.dump(self.bp['run']/'build-provenance.json', self.built)
        library.write_bytes(b'another installed library')
        with self.assertRaisesRegex(ValueError, 'library differs'):
            revalidate.existing(self.cfg)

    def test_runtime_bridges_actual_build_to_independent_acceptance(self):
        self.complete_build()
        self.vp['logs'].mkdir(parents=True)
        self.dump(self.vp['run']/'submit-manifest.json', self.cfg)
        self.dump(self.vp['run']/'submission.json', dict(job='10002'))
        self.dump(self.vp['run']/'.reservation.json', dict(task='validate', manifest=self.cfg))
        gpu = dict(count=1, arch='gfx936', uuid='1'*32)

        def validator(command, **kwargs):
            self.assertEqual(command[command.index('--build-record')+1], str(self.bp['run']/'build-provenance.json'))
            self.assertEqual(command[command.index('--build')+1], str(self.bp['build']))
            self.assertEqual(command[command.index('--run')+1], str(self.vp['run']))
            kwargs['stdout'].write(b'numerical and intended path passed\n')
            self.dump(self.vp['run']/'cc-local-validation.json', dict(complete=True,
                source_commit=self.built['arm']['source_commit'], library_sha256=self.built['arm']['library_sha256'], gpu=gpu))

        with patch.dict(os.environ, SLURM_JOB_ID='10002'), \
             patch.object(mgr, 'environment', return_value={}), \
             patch.object(revalidate.subprocess, 'run', side_effect=validator):
            revalidate.validate(self.cfg)
        accepted = json.loads((self.vp['run']/'post-build-validation.json').read_text())
        self.assertTrue(accepted['complete'])
        self.assertFalse(accepted['rebuild_required'])
        self.assertEqual(accepted['source_commit'], 'b'*40)
        command = revalidate.existing(self.cfg)[2]
        proof = revalidate.verify_acceptance(self.vp, self.built, command, 'cc-local-validation.json', '10002')
        self.assertEqual(proof['library_sha256'], self.built['arm']['library_sha256'])

    def test_pending_measurement_preview_and_actual_resolution(self):
        self.vp['run'].mkdir(parents=True)
        self.dump(self.vp['run']/'submit-manifest.json', self.cfg)
        self.dump(self.vp['run']/'submission.json', dict(job='10002'))
        refs = {}
        for name in ('baseline', 'previous'):
            install = self.root/('ref-'+name)
            library = install/'lib/librocfft.so.0.1'
            library.parent.mkdir(parents=True)
            library.write_bytes(name.encode())
            refs[name] = dict(install=str(install), source_repo=str(self.root), source_commit='d'*40,
                             source_state='Known tested reference.', library_sha256=mgr.common.sha(library),
                             build_provenance=str(install/'record.json'))
        measurement = dict(schema_version=1, experiment='EXP-999', run_id='formal-measurement',
            policy='FFT-event-cufft261012-single-v3', timing_source_sha256='f'*64,
            case_scope='Two explicitly registered synthetic validation cases.',
            event_iterations=30, timing_warmups=10, resources=dict(cpus=4, node_exclusive=True),
            cases=[dict(N=65536, func='z2d_1d'), dict(N=65536, func='d2z_1d')],
            arms=dict(refs, candidate=dict(build_record=self.cfg['existing_build_validation']['build_record'])))
        mpath = self.root/'measurement.json'
        self.dump(mpath, measurement)
        queue = dict(schema_version=1, experiment='EXP-999', run_id='formal-queue', gpu_arch='gfx936',
            resources=dict(measurement['resources'], dependency='afterok:10002'),
            revalidated_measurement=dict(validation_config=str(self.vp['run']/'submit-manifest.json'),
                validation_job_id='10002', measurement_config=str(mpath),
                measurement_config_sha256=mgr.common.sha(mpath)))

        class Protocol:
            POLICY = 'FFT-event-cufft261012-single-v3'
            SOURCE_SHA = 'f'*64
            WARMUPS = 10
            arms = staticmethod(lambda cfg: ('baseline', 'previous', 'candidate'))
            iterations = staticmethod(lambda cfg: 30)
            schedule = staticmethod(lambda cfg: list(range(6)))

        with patch.object(mgr, 'measurement_protocol', return_value=Protocol):
            planned = revalidate.plan('measure', queue)
        self.assertTrue(planned['pending_acceptance'])
        self.assertEqual(planned['processes'], 6)
        self.assertEqual(set(planned['reference_arms']), {'baseline', 'previous'})
        self.assertIsNone(planned['pending_candidate']['library_sha256'])
        self.assertIn('--dependency=afterok:10002', planned['submission_command'])
        with patch.object(mgr, 'measurement_protocol', return_value=Protocol):
            changed = copy.deepcopy(measurement)
            changed['arms']['candidate'] = refs['previous']
            with self.assertRaisesRegex(ValueError, 'another pending candidate'):
                pending.measurement_preview(changed, {}, self.cfg)
        self.complete_build()
        concrete = copy.deepcopy(measurement)
        concrete['arms']['candidate'] = self.built['arm']
        with patch.object(mgr, 'measurement', return_value=concrete) as resolve, \
             patch.object(mgr, 'task_plan', return_value=dict(node_exclusive=True, resolved_preregistration=concrete)):
            result = revalidate.gate(queue)
        resolve.assert_called_once()
        self.assertFalse(result[2].get('pending', False))
        self.assertEqual(result[-1]['resolved_preregistration']['arms']['candidate']['library_sha256'],
                         self.built['arm']['library_sha256'])

    def test_pending_preview_keeps_the_fixed_official_identity(self):
        library = self.root/'reference/lib/librocfft.so.0.1'
        library.parent.mkdir(parents=True)
        library.write_bytes(b'official fixed test identity')
        reference = dict(install=str(library.parents[1]), source_repo=str(self.root), source_commit='d'*40,
                         source_state='Fixed reference', library_sha256=mgr.common.sha(library),
                         build_provenance=str(self.root/'official-build.json'))
        cfg = dict(schema_version=1, experiment='EXP-999', run_id='formal-preview',
            policy='FFT-event-cufft261012-single-v3', timing_source_sha256='f'*64,
            case_scope='Registered official and pending candidate test.', resources=dict(node_exclusive=True),
            cases=[dict(N=65536, func='z2d_1d')],
            arms=dict(official=reference, candidate=dict(build_record=self.cfg['existing_build_validation']['build_record'])))

        class Protocol:
            SOURCE_SHA = 'f'*64
            OFFICIAL_COMMIT = 'e'*40
            OFFICIAL_SHA = mgr.common.sha(library)
            WARMUPS = 10
            arms = staticmethod(lambda cfg: ('official', 'candidate'))
            iterations = staticmethod(lambda cfg: 30)
            schedule = staticmethod(lambda cfg: [0, 1])

        built = pending.resolve(self.cfg, allow_pending=True)
        with patch.object(mgr, 'measurement_protocol', return_value=Protocol):
            with self.assertRaisesRegex(ValueError, 'fixed official identity'):
                pending.measurement_preview(cfg, built, self.cfg)
            cfg['arms']['official']['source_commit'] = Protocol.OFFICIAL_COMMIT
            planned = pending.measurement_preview(cfg, built, self.cfg)
        self.assertIsNone(planned['pending_candidate']['library_sha256'])
        self.assertEqual(planned['reference_arms']['official']['source_commit'], Protocol.OFFICIAL_COMMIT)


if __name__ == '__main__':
    unittest.main()
