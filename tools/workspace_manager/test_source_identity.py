"""Real Git regressions for build dependency identity; no compiler or GPU."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manager


class BuildSourceIdentity(unittest.TestCase):
    def setUp(self):
        parent = manager.ROOT / '.worktree-archives/manager-tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='source-identity-', dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'projects/rocfft'
        self.source.mkdir(parents=True)
        self.files = {
            'projects/rocfft/CMakeLists.txt': 'project(identity_regression)\n',
            'projects/rocfft/kernel.cpp': 'int kernel = 1;\n',
            'AGENTS.md': 'Instructions\n',
            'docs/cleanup.md': 'Cleanup record\n',
            'VkFFT/state.txt': 'Unrelated source\n',
            'manage.py': '# entrypoint\n',
            'jobs/workspace_task.slurm': '# managed job\n',
            'tools/workspace_manager/manager.py': '# task manager\n',
            'tools/fft_measurement/common.py': '# shared task helpers\n',
            'experiments/EXP-999/validator.py': '# validation implementation\n',
            'experiments/EXP-999/input.json': '{"case": 1}\n',
        }
        for name, text in self.files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Identity Regression', '-c', 'user.email=identity@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'initial')
        self.cfg = {'build': {'source_repo': str(self.root), 'source_dir': str(self.source),
                              'source_commit': self.git('rev-parse', 'HEAD')},
                    'post_build_validation': {'script': str(self.root/'experiments/EXP-999/validator.py'),
                                              'sha256': 'unused-in-this-hash-regression',
                                              'inputs': [{'path': str(self.root/'experiments/EXP-999/input.json'),
                                                          'sha256': 'unused-in-this-hash-regression'}]}}
        self.patcher = patch.object(manager, 'ROOT', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True,
                                       env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).strip()

    def change(self, name):
        path = self.root / name
        original = path.read_text()
        path.write_text(original + '# changed\n')
        return path, original

    def test_unrelated_docs_and_other_source_do_not_change_build_identity(self):
        before = manager.source_identity(self.cfg)
        audit_before = manager.repository_tracked_state(self.root)
        for name in ('AGENTS.md', 'docs/cleanup.md', 'VkFFT/state.txt'):
            self.change(name)
        self.assertEqual(manager.source_identity(self.cfg), before)
        self.assertNotEqual(manager.repository_tracked_state(self.root), audit_before)

    def test_dirty_or_untracked_fft_source_does_not_block(self):
        path, original = self.change('projects/rocfft/kernel.cpp')
        self.assertEqual(manager.source_identity(self.cfg)['commit'], self.cfg['build']['source_commit'])
        path.write_text(original)
        (self.source/'new_kernel.cpp').write_text('int another = 2;\n')
        self.assertEqual(manager.source_identity(self.cfg)['commit'], self.cfg['build']['source_commit'])

    def test_changed_management_and_validation_inputs_change_identity(self):
        before = manager.source_identity(self.cfg)
        names = ('manage.py', 'jobs/workspace_task.slurm', 'tools/workspace_manager/manager.py',
                 'tools/fft_measurement/common.py', 'experiments/EXP-999/validator.py',
                 'experiments/EXP-999/input.json')
        for name in names:
            with self.subTest(path=name):
                path, original = self.change(name)
                self.assertNotEqual(manager.source_identity(self.cfg), before)
                path.write_text(original)
                self.assertEqual(manager.source_identity(self.cfg), before)

    def test_added_management_module_changes_identity(self):
        before = manager.source_identity(self.cfg)
        (self.root/'tools/workspace_manager/new_dependency.py').write_text('# new dependency\n')
        self.assertNotEqual(manager.source_identity(self.cfg), before)

    def test_recorded_task_inputs_do_not_lock_validation_files(self):
        self.cfg['build']['task_input_sha256'] = manager.build_input_identity(self.cfg)
        manager.source_identity(self.cfg)
        self.change('experiments/EXP-999/input.json')
        state=manager.source_identity(self.cfg)
        self.assertNotEqual(state['task_input_sha256'], self.cfg['build']['task_input_sha256'])

    def test_requested_and_actual_commit_are_both_recorded(self):
        self.cfg['build']['source_commit'] = '0' * 40
        state=manager.source_identity(self.cfg)
        self.assertEqual(state['requested_commit'],'0'*40)
        self.assertEqual(state['commit'],self.git('rev-parse','HEAD'))


if __name__ == '__main__':
    unittest.main()
