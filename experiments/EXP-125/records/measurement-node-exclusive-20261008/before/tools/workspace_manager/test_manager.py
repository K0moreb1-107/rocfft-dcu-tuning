"""Small synthetic task tests. No compiler, sbatch or GPU execution."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
import uuid
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fft_measurement'))
import common
import manager

class ManagedTasks(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[2]/'.worktree-archives/manager-tests'
        parent.mkdir(parents=True,exist_ok=True)
        self.root=parent/uuid.uuid4().hex;self.root.mkdir()
        def cleanup():
            assert self.root.resolve().parent==parent.resolve()
            shutil.rmtree(self.root)
        self.addCleanup(cleanup)
        self.addCleanup(patch.stopall)
        patch.object(manager,'ROOT',self.root).start()
        self.cfg={'schema_version':1,'experiment':'EXP-999','run_id':'EXP-999-test', 'build':{'build_id':'EXP-999-build'}}

    def test_escape_and_output_root_rejected(self):
        for value in ('../escape',str(self.root)):
            with self.assertRaises(ValueError):manager.inside(value)
        self.assertEqual(manager.inside(self.root,allow_root=True),self.root.resolve())

    def test_placeholder_refused(self):
        with self.assertRaises(ValueError):manager.ident('EXP-999-REPLACE','run')

    def test_preview_never_submits_or_allocates(self):
        with patch.object(manager,'load',return_value=self.cfg),patch.object(manager,'task_plan',return_value={'task':'measure','processes':720}),patch.object(manager,'submit') as submit,patch.object(manager,'allocate') as allocate,patch.object(sys,'argv',['manage.py','measure','--config','fake.json']),contextlib.redirect_stdout(io.StringIO()):
            manager.main();submit.assert_not_called();allocate.assert_not_called()
        self.assertFalse((self.root/'experiments').exists())

    def test_allocator_refuses_reused_run(self):
        p=manager.allocate(self.cfg,'build')
        (p['logs']/'sentinel').write_text('keep')
        with self.assertRaises(ValueError):manager.allocate(self.cfg,'build')
        self.assertEqual((p['logs']/'sentinel').read_text(),'keep')

    def test_allocator_refuses_reused_install(self):
        p=manager.locations(self.cfg,'build');p['install'].mkdir(parents=True)
        with self.assertRaises(ValueError):manager.allocate(self.cfg,'build')
        self.assertFalse(p['run'].exists())

    def test_frozen_reservation_mismatch_refused(self):
        p=manager.allocate(self.cfg,'build');other=copy.deepcopy(self.cfg);other['build']['component']='hipfft'
        with self.assertRaises(ValueError):manager.claim(other,'build')
        self.assertFalse((p['run']/'.execution-lock').exists())

    def test_claim_refuses_evidence_and_double_execution(self):
        p=manager.allocate(self.cfg,'build');(p['run']/'provenance.json').write_text('{}')
        with self.assertRaises(ValueError):manager.claim(self.cfg,'build')
        (p['run']/'provenance.json').unlink();manager.claim(self.cfg,'build')
        with self.assertRaises(ValueError):manager.claim(self.cfg,'build')

    def test_submission_prepares_logs_before_sbatch(self):
        def fake_sbatch(argv,**kwargs):
            logs=manager.locations(self.cfg,'build')['logs']
            self.assertTrue(logs.is_dir())
            self.assertIn('--output='+str(logs/'slurm_%j.out'),argv)
            frozen=Path(argv[-1]);self.assertEqual(json.loads(frozen.read_text()),self.cfg)
            return 'synthetic-job\n'
        with patch.object(manager,'task_plan',return_value={}),patch.object(manager.subprocess,'check_output',side_effect=fake_sbatch),contextlib.redirect_stdout(io.StringIO()):manager.submit('build',self.cfg)

    def test_measure_submission_uses_unified_worker(self):
        def fake_sbatch(argv,**kwargs):
            self.assertEqual(argv[-3:-1],[str(self.root/'jobs/workspace_task.slurm'),'measure'])
            self.assertEqual(json.loads(Path(argv[-1]).read_text()),self.cfg)
            return 'synthetic-job\n'
        with patch.object(manager,'task_plan',return_value={}),patch.object(manager.subprocess,'check_output',side_effect=fake_sbatch),contextlib.redirect_stdout(io.StringIO()):
            manager.submit('measure',self.cfg)
    def test_measure_worker_uses_correct_shared_schedule(self):
        import run
        def inspect_plan(cfg):
            plan=run.plan(cfg)
            self.assertEqual(plan['processes'],720)
            self.assertEqual([e['arm'] for e in plan['schedule'][:6]],
                             ['official','previous','candidate','candidate','previous','official'])
            self.assertEqual([e['arm'] for e in plan['schedule'][6:12]],
                             ['candidate','previous','official','official','previous','candidate'])
        allocation={'SLURM_JOB_ID':'synthetic-job','SLURM_JOB_GPUS':'0','SLURM_JOB_NUM_NODES':'1'}
        with patch.object(manager,'load',return_value=self.cfg),patch.object(common,'manifest',return_value=self.cfg),patch.dict(os.environ,allocation,clear=True),patch.object(sys,'argv',['manage.py','measure','--config','fake','--worker']),patch.object(run,'execute',side_effect=inspect_plan) as execute:
            manager.main()
            execute.assert_called_once_with(self.cfg)
    def test_submission_failure_keeps_evidence(self):
        with patch.object(manager,'task_plan',return_value={}),patch.object(manager.subprocess,'check_output',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):manager.submit('build',self.cfg)
        self.assertTrue((manager.locations(self.cfg,'build')['run']/'submission-failed.json').exists())

    def test_old_registry_entry_not_promoted(self):
        cfg=dict(self.cfg,arms={'official':{'registry_id':'old'},'previous':{},'candidate':{}})
        with patch.object(manager,'registry',return_value={'installations':{'old':{'role':'historical','eligible_formal_arm':False}}}):
            with self.assertRaises(ValueError):manager.measurement(cfg)

    def test_missing_candidate_build_record_refused(self):
        cfg=dict(self.cfg,arms={'official':{},'previous':{},'candidate':{'build_record':str(self.root/'missing.json')}})
        with self.assertRaises(OSError):manager.measurement(cfg)

    def test_incomplete_candidate_record_refused(self):
        p=self.root/'record.json';p.write_text(json.dumps({'complete':False,'component':'rocfft'}))
        cfg=dict(self.cfg,arms={'official':{},'previous':{},'candidate':{'build_record':str(p)}})
        with self.assertRaises(ValueError):manager.measurement(cfg)

    def test_common_paths_are_experiment_scoped(self):
        run,build,logs,cache=common.measurement_paths(self.cfg,self.root)
        self.assertEqual(run,self.root/'experiments/EXP-999/runs/EXP-999-test')
        self.assertEqual(logs,run/'logs')
        self.assertIn('artifacts/build/measurement',build.as_posix());self.assertIn('artifacts/cache',cache.as_posix())

    def test_formal_reservation_once_only(self):
        p=manager.allocate(self.cfg,'measure')
        run,build,logs,cache=common.prepare_measurement_paths(self.cfg,self.root)
        self.assertEqual(run,p['run']);self.assertTrue(logs.is_dir());self.assertTrue(cache.is_dir())
        with self.assertRaises(ValueError):common.prepare_measurement_paths(self.cfg,self.root)

    def test_formal_wrong_reservation_refused(self):
        p=manager.allocate(self.cfg,'validate')
        with self.assertRaises(ValueError):common.prepare_measurement_paths(self.cfg,self.root)
        self.assertFalse(p['build'].exists())

    def test_worker_without_allocation_rejected(self):
        with patch.object(manager,'load',return_value=self.cfg),patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['manage.py','build','--config','fake','--worker']),patch.object(manager,'execute_build') as execute,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):manager.main()
            execute.assert_not_called()

    def test_build_source_commit_drift_rejected(self):
        repo=self.root/'source';source=repo/'projects/rocfft';source.mkdir(parents=True);(source/'CMakeLists.txt').write_text('project(test)')
        cfg=dict(self.cfg,build={'source_repo':str(repo),'source_dir':str(source),'source_commit':'a'*40})
        with patch.object(manager.subprocess,'check_output',return_value='b'*40):
            with self.assertRaises(ValueError):manager.source_identity(cfg)

    def test_build_plan_does_not_reuse_shared_install(self):
        cfg=copy.deepcopy(self.cfg);cfg['build'].update(component='rocfft')
        state={'repo':str(self.root/'source'),'source':str(self.root/'source/projects/rocfft'),'commit':'a'*40,'source_status':'','tracked_state':''}
        with patch.object(manager,'source_identity',return_value=state):plan=manager.build_plan(cfg)
        self.assertIn('/experiments/EXP-999/artifacts/install/EXP-999-build',plan['paths']['install'].replace('\\','/'))
        self.assertIn('rocfft-rtc-gen',plan['commands'][1])
        self.assertIn('-DCMAKE_INSTALL_PREFIX='+plan['paths']['install'],plan['commands'][0])
        self.assertNotIn(str(self.root/'install'),plan['commands'][0])

    def test_build_reserved_path_override_refused(self):
        cfg=copy.deepcopy(self.cfg);cfg['build']['cmake']={'CMAKE_INSTALL_PREFIX':'../outside'}
        with patch.object(manager,'source_identity',return_value={}):
            with self.assertRaises(ValueError):manager.build_plan(cfg)

    def test_queue_configuration_does_not_re_resolve_registry(self):
        base={'install':str(self.root/'version'),'source_repo':str(self.root/'source'),'source_commit':'a'*40,'source_state':'committed source','library_sha256':'b'*64,'build_provenance':'verified synthetic record'}
        cfg=dict(self.cfg,arms={'official':{'registry_id':'official'},'previous':{'registry_id':'previous'},'candidate':dict(base)})
        entries={arm:{'role':arm,'eligible_formal_arm':True,'arm':dict(base)} for arm in ('official','previous')}
        with patch.object(manager,'registry',return_value={'installations':entries}),patch.object(common,'validate_manifest',side_effect=lambda m:m):
            frozen=manager.measurement(cfg)
        self.assertNotIn('registry_id',frozen['arms']['official'])
        with patch.object(manager,'registry',side_effect=AssertionError('must not read mutable registry')),patch.object(common,'validate_manifest',side_effect=lambda m:m):
            self.assertEqual(manager.measurement(frozen),frozen)

if __name__=='__main__':unittest.main()
