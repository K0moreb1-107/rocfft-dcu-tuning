"""Four-arm timing cannot start until both independent libraries are accepted."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from tools.workspace_manager import manager as mgr, revalidate
from tools.workspace_manager import test_pending_build_validation as fixtures


class DualRevalidation(unittest.TestCase):
    setUp=fixtures.PendingBuildValidation.setUp
    dump=fixtures.PendingBuildValidation.dump
    complete_build=fixtures.PendingBuildValidation.complete_build
    def four_arm_fixture(self):
        self.vp['run'].mkdir(parents=True)
        self.dump(self.vp['run']/'submit-manifest.json', self.cfg)
        self.dump(self.vp['run']/'submission.json', dict(job='10002'))
        off_build = copy.deepcopy(self.build)
        off_build['run_id'] = 'off-build'
        off_build['build']['build_id'] = 'off-install'
        off_build['build']['source_commit'] = 'c'*40
        bp = mgr.locations(off_build, 'build')
        bp['run'].mkdir(parents=True)
        self.dump(bp['run']/'submit-manifest.json', off_build)
        self.dump(bp['run']/'submission.json', dict(job='10003'))
        off = copy.deepcopy(self.cfg)
        off.update(run_id='off-validation', build=copy.deepcopy(off_build['build']))
        off['resources']['dependency'] = 'afterok:10003'
        off['existing_build_validation']['build_record'] = str(bp['run']/'build-provenance.json')
        off['pending_build_validation'] = dict(build_config=str(bp['run']/'submit-manifest.json'),
            build_config_sha256=mgr.common.sha(bp['run']/'submit-manifest.json'), build_job_id='10003')
        vp = mgr.locations(off, 'validate'); vp['run'].mkdir(parents=True)
        self.dump(vp['run']/'submit-manifest.json', off)
        self.dump(vp['run']/'submission.json', dict(job='10004'))
        refs = {}
        for name in ('baseline','previous'):
            library = self.root/('ref-'+name)/'lib/librocfft.so.0.1'
            library.parent.mkdir(parents=True); library.write_bytes(name.encode())
            refs[name] = dict(install=str(library.parents[1]), source_repo=str(self.root),
                source_commit='d'*40, source_state='Known reference',
                library_sha256=mgr.common.sha(library), build_provenance=str(library.parents[1]/'record.json'))
        m = dict(schema_version=1, experiment='EXP-999', run_id='four-arm-performance',
            policy='FFT-event-cufft261012-single-v3', timing_source_sha256='f'*64,
            case_scope='Two synthetic cases, four independent arms.',
            resources=dict(cpus=4,node_exclusive=True), timing_warmups=10,event_iterations=30,
            cases=[dict(N=65536,func=f) for f in ('z2d_1d','d2z_1d')],
            arms=dict(refs,unfused_cc=dict(build_record=off['existing_build_validation']['build_record']),
                candidate=dict(build_record=self.cfg['existing_build_validation']['build_record'])))
        mp = self.root/'four-arm.json';self.dump(mp,m)
        queue = dict(schema_version=1,experiment='EXP-999',run_id='four-arm-queue',gpu_arch='gfx936',
            resources=dict(m['resources'],dependency='afterok:10002:10004'),
            revalidated_measurement=dict(validation_config=str(self.vp['run']/'submit-manifest.json'),
                validation_job_id='10002',measurement_config=str(mp),measurement_config_sha256=mgr.common.sha(mp),
                reference_validations=dict(unfused_cc=dict(validation_config=str(vp['run']/'submit-manifest.json'),
                    validation_job_id='10004'))))
        class Protocol:
            POLICY = 'FFT-event-cufft261012-single-v3'
            SOURCE_SHA = 'f'*64
            WARMUPS = 10
            arms = staticmethod(lambda cfg: ('baseline','previous','unfused_cc','candidate'))
            iterations = staticmethod(lambda cfg: 30)
            schedule = staticmethod(lambda cfg: list(range(8)))
        self.off_cfg,self.off_bp,self.off_vp,self.measure,self.queue,self.protocol=off,bp,vp,m,queue,Protocol

    def complete_off_build(self):
        bp=self.off_bp
        bp['build'].mkdir(parents=True);(bp['build']/'CMakeCache.txt').write_text('OFF\n')
        lib=bp['install']/'lib/librocfft.so.0.1';lib.parent.mkdir(parents=True);lib.write_bytes(b'off library')
        self.off_built=dict(complete=True,component='rocfft',experiment='EXP-999',job_id='10003',
            plan=dict(paths={k:str(v) for k,v in bp.items()},post_build_validation_command=None,
                source_identity=dict(repo=str(self.root),source=str(self.root/'rocfft'),commit='e'*40,requested_commit='c'*40)),
            arm=dict(install=str(bp['install']),source_repo=str(self.root),source_commit='e'*40,
                source_state='Actual identity',library_sha256=mgr.common.sha(lib),
                build_provenance=str(bp['run']/'build-provenance.json')))
        self.dump(bp['run']/'build-provenance.json',self.off_built)

    def test_dual_preview_tracks_each_pending_identity(self):
        self.four_arm_fixture()
        with patch.object(mgr,'measurement_protocol',return_value=self.protocol):
            planned=revalidate.plan('measure',self.queue)
            self.assertEqual(planned['processes'],8)
            self.assertEqual(planned['event_samples'],240)
            self.assertIsNone(planned['pending_candidate']['library_sha256'])
            self.assertIsNone(planned['pending_reference_arms']['unfused_cc']['library_sha256'])
            self.complete_build()
            planned=revalidate.plan('measure',self.queue)
            self.assertEqual(planned['pending_candidate']['library_sha256'],self.built['arm']['library_sha256'])
            self.assertIsNone(planned['pending_reference_arms']['unfused_cc']['library_sha256'])
            self.complete_off_build()
            with patch.object(mgr,'measurement',side_effect=AssertionError('resolved before acceptance')):
                planned=revalidate.plan('measure',self.queue)
            self.assertTrue(planned['pending_acceptance'])
            self.assertEqual(planned['pending_reference_arms']['unfused_cc']['library_sha256'],self.off_built['arm']['library_sha256'])

    def test_both_exact_success_dependencies_are_required(self):
        self.four_arm_fixture()
        with patch.object(mgr,'measurement_protocol',return_value=self.protocol):
            changed=copy.deepcopy(self.queue);changed['resources']['dependency']='afterok:10004:10002'
            revalidate.plan('measure',changed)
            for dep in ('afterok:10002','afterok:10004','afterok:10002:10004:10005',
                        'afterok:10002:10002','afterany:10002:10004'):
                changed=copy.deepcopy(self.queue);changed['resources']['dependency']=dep
                with self.subTest(dep=dep),self.assertRaisesRegex(ValueError,'every pending arm'):
                    revalidate.plan('measure',changed)
            changed=copy.deepcopy(self.queue)
            changed['revalidated_measurement']['reference_validations']['unfused_cc']['validation_job_id']='10005'
            with self.assertRaisesRegex(ValueError,'receipt'):revalidate.plan('measure',changed)

    def test_failed_reference_acceptance_prevents_resolution_allocation_and_worker(self):
        self.four_arm_fixture();self.complete_build();self.complete_off_build()
        q=mgr.locations(self.queue,'measure');q['run'].mkdir(parents=True)
        with patch.object(mgr,'measurement_protocol',return_value=self.protocol), \
             patch.object(mgr,'claim',return_value=q),patch.object(mgr,'allocate') as allocate, \
             patch.object(mgr,'measurement') as resolve, \
             patch.object(revalidate,'verify_acceptance',side_effect=[dict(job_id='10002'),ValueError('OFF rejected')]), \
             patch.dict(sys.modules,run_cufft261012=SimpleNamespace(POLICY=self.protocol.POLICY,execute=Mock())):
            with self.assertRaisesRegex(ValueError,'OFF rejected'):revalidate.measure(self.queue)
            resolve.assert_not_called();allocate.assert_not_called()
            sys.modules['run_cufft261012'].execute.assert_not_called()
        self.assertFalse(json.loads((q['run']/'completion.json').read_text())['complete'])

    def test_both_acceptances_precede_resolution_and_execution(self):
        self.four_arm_fixture();self.complete_build();self.complete_off_build()
        q=mgr.locations(self.queue,'measure');q['run'].mkdir(parents=True)
        for name in ('submission.json','submission-command.json'):self.dump(q['run']/name,{})
        p=mgr.locations(self.measure,'measure');p['run'].mkdir(parents=True)
        ordered=[]
        def accept(vp,built,command,filename,job):
            ordered.append(job);return dict(job_id=job,library_sha256=built['arm']['library_sha256'])
        def resolve(m):
            self.assertEqual(ordered,['10002','10004'])
            concrete=copy.deepcopy(m)
            concrete['arms']['candidate']=self.built['arm'];concrete['arms']['unfused_cc']=self.off_built['arm']
            return concrete
        worker=Mock()
        with patch.object(mgr,'measurement_protocol',return_value=self.protocol), \
             patch.object(mgr,'claim',return_value=q),patch.object(mgr,'allocate',return_value=p), \
             patch.object(mgr,'measurement',side_effect=resolve),patch.object(revalidate,'verify_acceptance',side_effect=accept), \
             patch.dict(sys.modules,run_cufft261012=SimpleNamespace(POLICY=self.protocol.POLICY,execute=worker)):
            revalidate.measure(self.queue)
        sent=worker.call_args.args[0]
        self.assertEqual(set(sent['validation_acceptances']),{'candidate','unfused_cc'})
        self.assertEqual(sent['arms']['unfused_cc'],self.off_built['arm'])
        self.assertTrue(json.loads((q['run']/'completion.json').read_text())['complete'])


if __name__=='__main__':unittest.main()
