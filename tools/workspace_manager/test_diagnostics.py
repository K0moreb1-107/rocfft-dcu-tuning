"""Diagnostic registration and unified dispatch gates; no jobs or GPU work."""
import contextlib
import copy
import hashlib
import io
import os
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from unittest.mock import patch

from tools.workspace_manager import diagnostics
from tools.workspace_manager import manager as mgr


class Diagnostics(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[2]/'.worktree-archives/diagnostic-tests'
        parent.mkdir(parents=True,exist_ok=True)
        self.root=parent/uuid.uuid4().hex;self.root.mkdir()
        def cleanup():
            assert self.root.resolve().parent==parent.resolve();shutil.rmtree(self.root)
        self.addCleanup(cleanup)
        self.addCleanup(patch.stopall)
        patch.object(mgr,'ROOT',self.root).start()
        self.paths=['manage.py','jobs/workspace_task.slurm','tools/workspace_manager/manager.py',
                    'tools/workspace_manager/diagnostics.py','experiments/EXP-999/scripts/diagnose.py']
        for name in self.paths:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Synthetic '+name+'\n')
        script=self.root/self.paths[-1]
        self.cfg=dict(schema_version=1,experiment='EXP-999',run_id='EXP-999-diagnostic',
            resources=dict(node_exclusive=True),diagnostic=dict(script=str(script),
                sha256=mgr.common.sha(script),tool_source_commit='a'*40,reason='Synthetic diagnostic gate, never a real measurement.',
                inputs=[dict(path=str(self.root/n),sha256=mgr.common.sha(self.root/n)) for n in self.paths[:-1]]))
        def git_blob(argv,**kwargs):
            name=argv[-1].split(':',1)[1];return (self.root/name).read_bytes()
        patch.object(diagnostics.subprocess,'check_output',side_effect=git_blob).start()

    def test_frozen_command_and_output_paths(self):
        argv=diagnostics.command(self.cfg)
        self.assertEqual(argv[:2],[mgr.PYTHON,str(self.root/self.paths[-1])])
        self.assertIn('/artifacts/build/diagnostics/',argv[argv.index('--build')+1])
        self.assertFalse((self.root/'experiments/EXP-999/runs').exists())

    def test_changed_script_and_changed_committed_blob_rejected(self):
        (self.root/self.paths[-1]).write_text('changed')
        with self.assertRaises(ValueError):diagnostics.command(self.cfg)
        self.cfg['diagnostic']['sha256']=mgr.common.sha(self.root/self.paths[-1])
        with patch.object(diagnostics.subprocess,'check_output',return_value=b'foreign source'):
            with self.assertRaises(ValueError):diagnostics.command(self.cfg)

    def test_missing_entry_duplicate_extra_and_escape_rejected(self):
        for mutate in (lambda d:d['inputs'].pop(),lambda d:d['inputs'].append(copy.deepcopy(d['inputs'][0])),
                       lambda d:d.update(extra=True),lambda d:d.update(script=str(self.root/'outside.py'))):
            cfg=copy.deepcopy(self.cfg);mutate(cfg['diagnostic'])
            with self.assertRaises((ValueError,OSError)):diagnostics.command(cfg)

    def test_diagnostic_submission_is_exclusive_and_keeps_worker(self):
        argv=mgr.submission_command('diagnose',self.cfg)
        self.assertIn('--exclusive',argv)
        self.assertEqual(argv[-2],'diagnose')
        self.assertNotIn('--exclusive',mgr.submission_command('validate',self.cfg))

    def test_diagnostic_preview_does_not_submit(self):
        with patch.object(mgr,'load',return_value=self.cfg),patch.object(diagnostics,'plan',return_value={'formal':False}) as plan,\
             patch.object(mgr,'submit') as submit,patch.object(sys,'argv',['manage.py','diagnose','--config','fake']),\
             contextlib.redirect_stdout(io.StringIO()):
            mgr.main()
        plan.assert_called_once_with(self.cfg);submit.assert_not_called()

    def test_worker_dispatch_keeps_formal_runner_separate(self):
        allocation=dict(SLURM_JOB_ID='synthetic',SLURM_JOB_GPUS='0,1',SLURM_STEP_GPUS='0')
        with patch.object(mgr,'load',return_value=self.cfg),patch.object(diagnostics,'execute') as execute,\
             patch.dict(os.environ,allocation,clear=True),patch.object(sys,'argv',['manage.py','diagnose','--config','fake','--worker']):
            mgr.main()
        execute.assert_called_once_with(self.cfg)


if __name__=='__main__':unittest.main()
