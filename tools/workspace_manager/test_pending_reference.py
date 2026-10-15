"""Synthetic corruption and dependency checks for same-experiment build pairs."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.workspace_manager import deferred, manager as mgr


class PendingReference(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.addCleanup(patch.stopall)
        patch.object(mgr,'ROOT',self.root).start()
        patch.object(mgr,'validation_hook',return_value=['frozen-validator']).start()
        self.b=dict(schema_version=1,experiment='EXP-999',run_id='off-build',
            build=dict(component='rocfft',build_id='off',source_commit='a'*40),
            post_build_validation={'script':'validator'})
        self.bp=mgr.locations(self.b,'build');self.bp['run'].mkdir(parents=True)
        self.manifest=self.bp['run']/'submit-manifest.json';self.write(self.manifest,self.b)
        self.write(self.bp['run']/'submission.json',{'job':'1001'})
        self.entry=dict(build_config=str(self.manifest),build_config_sha256=mgr.common.sha(self.manifest),build_job_id='1001')
        self.cfg=dict(schema_version=1,experiment='EXP-999',run_id='queue',deferred_measurement=dict(
            reference_builds={'previous':self.entry},required_success_jobs=['1001','1002']))
        self.m=dict(schema_version=1,experiment='EXP-999',run_id='measure',arms={
            'previous':{'build_record':str(self.bp['run']/'build-provenance.json')},'candidate':{}})

    def write(self,path,data):path.write_text(json.dumps(data),encoding='utf-8')
    def refreeze(self):
        self.write(self.manifest,self.b);self.entry['build_config_sha256']=mgr.common.sha(self.manifest)
    def check(self):return deferred.reference_inputs(self.cfg,self.m)

    def test_exact_submitted_reference_allowed(self):
        result=self.check();self.assertEqual(set(result),{'previous'})
        self.assertEqual(result['previous'][2],self.bp)
    def test_absent_references_preserves_old_flow(self):
        self.cfg['deferred_measurement'].pop('reference_builds');self.assertEqual(self.check(),{})
    def test_official_cannot_be_pending_reference(self):
        self.cfg['deferred_measurement']['reference_builds']={'official':self.entry}
        with self.assertRaisesRegex(ValueError,'experimental previous'):self.check()
    def test_changed_reference_manifest_rejected(self):
        self.manifest.write_text(self.manifest.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'queued input changed'):self.check()
    def test_cross_experiment_reference_rejected(self):
        self.b['experiment']='EXP-998';self.refreeze()
        with self.assertRaisesRegex(ValueError,'experiment mismatch'):self.check()
    def test_original_config_cannot_replace_submitted_manifest(self):
        p=self.root/'original.json';self.write(p,self.b)
        self.entry.update(build_config=str(p),build_config_sha256=mgr.common.sha(p))
        with self.assertRaisesRegex(ValueError,'submitted reference'):self.check()
    def test_reference_arm_must_match_exact_build(self):
        self.m['arms']['previous']['build_record']+='-other'
        with self.assertRaisesRegex(ValueError,'select exactly'):self.check()
    def test_reference_job_receipt_must_match(self):
        self.entry['build_job_id']='1003'
        with self.assertRaisesRegex(ValueError,'job mismatch'):self.check()
    def test_reference_success_dependency_required(self):
        self.cfg['deferred_measurement']['required_success_jobs']=['1002']
        with self.assertRaisesRegex(ValueError,'reference dependency'):self.check()
    def test_reference_requires_post_build_validation(self):
        self.b.pop('post_build_validation');self.refreeze()
        with self.assertRaisesRegex(ValueError,'validation required'):self.check()
    def test_wrong_component_rejected(self):
        self.b['build']['component']='hipfft';self.refreeze()
        with self.assertRaisesRegex(ValueError,'validation required'):self.check()

    def test_failed_reference_prevents_any_formal_identity_resolution(self):
        queue=mgr.locations(self.cfg,'measure')['run'];queue.mkdir(parents=True)
        self.write(queue/'.reservation.json',{'task':'measure','manifest':self.cfg})
        self.write(queue/'submit-manifest.json',self.cfg)
        with patch.object(deferred,'inputs',return_value=(self.m,self.b,self.bp,['frozen-validator'])),\
             patch.object(deferred,'reference_inputs',return_value={'previous':(self.entry,self.b,self.bp,['frozen-validator'])}),\
             patch.object(deferred,'validate_build',side_effect=[{'library_sha256':'c'*64},ValueError('reference failed')]),\
             patch.object(mgr,'measurement') as formal:
            with self.assertRaisesRegex(ValueError,'reference failed'):deferred.execute(self.cfg)
            formal.assert_not_called()
        self.assertFalse(json.loads((queue/'execution-failed.json').read_text())['complete'])

    def manager_fixture(self):
        lib=self.root/'install/lib/librocfft.so.0.1';lib.parent.mkdir(parents=True);lib.write_bytes(b'frozen synthetic library')
        arm=dict(install=str(lib.parents[1]),source_repo=str(self.root),source_commit='a'*40,
                 source_state='frozen synthetic source state',library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),
                 build_provenance=str(self.bp['run']/'build-provenance.json'))
        build=dict(complete=True,experiment='EXP-999',component='rocfft',arm=arm,
                   plan={'post_build_validation_command':['frozen-validator']})
        self.write(self.bp['run']/'build-provenance.json',build)
        self.write(self.bp['run']/'post-build-validation.json',dict(complete=True,source_commit=arm['source_commit'],
            library_sha256=arm['library_sha256'],command=['frozen-validator']))
        protocol=SimpleNamespace(arms=lambda cfg:tuple(cfg['arms']),validate_manifest=lambda cfg:cfg)
        return arm,build,protocol

    def test_completed_same_experiment_reference_can_resolve(self):
        arm,_,protocol=self.manager_fixture()
        with patch.object(mgr,'measurement_protocol',return_value=protocol):resolved=mgr.measurement(self.m)
        self.assertEqual(resolved['arms']['previous']['library_sha256'],arm['library_sha256'])
        self.assertNotIn('build_record',resolved['arms']['previous'])
    def test_incomplete_reference_validation_cannot_resolve(self):
        _,_,protocol=self.manager_fixture();p=self.bp['run']/'post-build-validation.json';d=json.loads(p.read_text());d['complete']=False;self.write(p,d)
        with patch.object(mgr,'measurement_protocol',return_value=protocol):
            with self.assertRaisesRegex(ValueError,'validation incomplete'):mgr.measurement(self.m)
    def test_build_record_cannot_replace_fixed_official(self):
        _,_,protocol=self.manager_fixture();cfg=copy.deepcopy(self.m);cfg['arms']['official']=cfg['arms'].pop('previous')
        with patch.object(mgr,'measurement_protocol',return_value=protocol):
            with self.assertRaisesRegex(ValueError,'fixed official'):mgr.measurement(cfg)


if __name__=='__main__':unittest.main()
