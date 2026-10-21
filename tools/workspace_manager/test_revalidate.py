"""Existing artifacts stay intact; incomplete or mismatched acceptance cannot start timing."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.workspace_manager import manager as mgr, revalidate


class ExistingBuildValidation(unittest.TestCase):
    def setUp(self):
        parent=mgr.ROOT/'.worktree-archives/manager-tests'; parent.mkdir(parents=True, exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        patched=patch.object(mgr, 'ROOT', self.root); patched.start(); self.addCleanup(patched.stop)
        self.exp=self.root/'experiments/EXP-999'
        artifact=self.exp/'artifacts/build/original'; artifact.mkdir(parents=True)
        (artifact/'CMakeCache.txt').write_text('Original build metadata.\n')
        install=self.exp/'artifacts/install/original'; (install/'lib').mkdir(parents=True)
        self.library=install/'lib/librocfft.so.0.1'; self.library.write_bytes(b'original installed library')
        self.old=self.exp/'runs/original'; self.old.mkdir(parents=True)
        self.built=dict(complete=True, experiment='EXP-999', component='rocfft',
            plan=dict(paths=dict(build=str(artifact))), arm=dict(install=str(install),
                source_repo=str(self.root), source_commit='a'*40,
                library_sha256=mgr.common.sha(self.library), source_state='Synthetic original build identity.',
                build_provenance=str(self.old/'build-provenance.json')))
        self.dump(self.old/'build-provenance.json', self.built)
        self.dump(self.old/'post-build-validation.json', dict(complete=False))
        script=self.exp/'scripts/validator.py'; script.parent.mkdir(); script.write_text('# synthetic full validation\n')
        self.cfg=dict(schema_version=1, experiment='EXP-999', run_id='fresh-validation', gpu_arch='gfx936',
            resources=dict(cpus=8), build=dict(component='rocfft', build_id='original'),
            post_build_validation=dict(script=str(script), sha256=mgr.common.sha(script), inputs=[]),
            existing_build_validation=dict(build_record=str(self.old/'build-provenance.json'),
                evidence_record='evidence.json', isolated_helpers=True))
        self.paths=mgr.locations(self.cfg, 'validate')
        self.paths['logs'].mkdir(parents=True)
        self.dump(self.paths['run']/'submit-manifest.json', self.cfg)
        self.dump(self.paths['run']/'submission.json', dict(job='12345'))

    def dump(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def accepted(self):
        command=revalidate.existing(self.cfg)[2]
        gpu=dict(count=1, uuid='1'*32, arch='gfx936')
        evidence=dict(complete=True, source_commit=self.built['arm']['source_commit'],
                      library_sha256=self.built['arm']['library_sha256'], gpu=gpu)
        self.dump(self.paths['run']/'evidence.json', evidence)
        (self.paths['logs']/'post-build-validation.txt').write_text('Full validation passed.\n')
        accepted=dict(evidence, job_id='12345', command=command,
            evidence_sha256=mgr.common.sha(self.paths['run']/'evidence.json'),
            log_sha256=mgr.common.sha(self.paths['logs']/'post-build-validation.txt'))
        self.dump(self.paths['run']/'post-build-validation.json', accepted)
        return command, evidence, accepted

    def test_preview_reuses_build_and_keeps_helpers_in_new_run(self):
        with patch.object(mgr, 'build_plan', side_effect=AssertionError('FFT rebuild invoked')):
            planned=mgr.task_plan('validate', self.cfg)
        self.assertFalse(planned['rebuild_required'])
        command=planned['validation_command']
        self.assertEqual(command[command.index('--build-record')+1], str(self.old/'build-provenance.json'))
        self.assertEqual(command[command.index('--build')+1], self.built['plan']['paths']['build'])
        self.assertEqual(command[command.index('--helpers')+1], str(self.paths['build']))
        self.assertNotEqual(str(self.paths['build']), self.built['plan']['paths']['build'])
        self.assertEqual(self.library.read_bytes(), b'original installed library')

    def test_wrong_installed_library_rejected(self):
        self.library.write_bytes(b'wrong library')
        with self.assertRaises(ValueError): revalidate.existing(self.cfg)

    def test_complete_new_acceptance_is_required(self):
        command, evidence, accepted=self.accepted()
        result=revalidate.verify_acceptance(self.paths, self.built, command, 'evidence.json', '12345')
        self.assertEqual(result['library_sha256'], self.built['arm']['library_sha256'])
        self.assertFalse(json.loads((self.old/'post-build-validation.json').read_text())['complete'])
        for field, value in [('complete',False), ('source_commit','b'*40), ('library_sha256','0'*64),
                             ('job_id','54321'), ('command',['another script']), ('gpu',dict(count=2))]:
            changed=dict(accepted); changed[field]=value
            self.dump(self.paths['run']/'post-build-validation.json', changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                revalidate.verify_acceptance(self.paths, self.built, command, 'evidence.json', '12345')

    def test_changed_evidence_or_log_rejected(self):
        command, evidence, accepted=self.accepted()
        (self.paths['logs']/'post-build-validation.txt').write_text('different log')
        with self.assertRaises(ValueError):
            revalidate.verify_acceptance(self.paths, self.built, command, 'evidence.json', '12345')
        command, evidence, accepted=self.accepted()
        evidence['complete']=False; self.dump(self.paths['run']/'evidence.json', evidence)
        with self.assertRaises(ValueError):
            revalidate.verify_acceptance(self.paths, self.built, command, 'evidence.json', '12345')

    def test_incomplete_acceptance_cannot_start_formal_worker(self):
        command, evidence, accepted=self.accepted()
        accepted['complete']=False; self.dump(self.paths['run']/'post-build-validation.json', accepted)
        qrun=self.exp/'runs/queue'; qrun.mkdir()
        planned=dict(paths=dict(run=str(self.exp/'runs/performance')))
        cfg=dict(revalidated_measurement=dict(validation_job_id='12345'))
        with patch.object(revalidate, 'gate', return_value=(self.cfg,self.paths,self.built,command,'evidence.json',planned)), \
             patch.object(mgr, 'claim', return_value=dict(run=qrun)), \
             patch.object(mgr, 'allocate') as allocate:
            with self.assertRaises(ValueError): revalidate.measure(cfg)
        allocate.assert_not_called()
        self.assertFalse(json.loads((qrun/'completion.json').read_text())['complete'])

    def test_gate_requires_actual_validation_receipt_and_single_dependency(self):
        measurement=dict(schema_version=1, experiment='EXP-999', run_id='performance',
                         policy='FFT-event-cufft261012-single-v3',
                         resources=dict(cpus=8,node_exclusive=True), arms=dict(candidate=self.built['arm']))
        mpath=self.root/'measurement.json'; self.dump(mpath,measurement)
        queue=dict(schema_version=1, experiment='EXP-999', run_id='queue',
            resources=dict(measurement['resources'],dependency='afterok:12345'),
            revalidated_measurement=dict(validation_config=str(self.paths['run']/'submit-manifest.json'),
                validation_job_id='12345',measurement_config=str(mpath),
                measurement_config_sha256=mgr.common.sha(mpath)))
        planned=dict(node_exclusive=True, resolved_preregistration=measurement)
        with patch.object(mgr, 'task_plan', return_value=planned):
            revalidate.gate(queue)
            for dependency in ('afterok:54321', 'afterok:12345:54321', 'afterany:12345'):
                changed=copy.deepcopy(queue); changed['resources']['dependency']=dependency
                with self.subTest(dependency=dependency), self.assertRaises(ValueError): revalidate.gate(changed)
            changed=copy.deepcopy(queue); changed['revalidated_measurement']['validation_job_id']='54321'
            with self.assertRaises(ValueError): revalidate.gate(changed)
            measurement['run_id']='changed-after-submission'; self.dump(mpath,measurement)
            with self.assertRaisesRegex(ValueError,'measurement configuration differs'):
                revalidate.gate(queue)


if __name__ == '__main__':
    unittest.main()
