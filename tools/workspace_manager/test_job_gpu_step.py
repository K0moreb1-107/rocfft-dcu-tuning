"""Execute the job script with a simulated scheduler and the real GPU admission check."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

# Use the production admission function without importing measurement workers.
WORKER = r"""import ast, json, os, re, sys
source = open(os.environ['TEST_COMMON_SOURCE']).read()
node = next(x for x in ast.parse(source).body if isinstance(x, ast.FunctionDef) and x.name == 'single_gpu_allocation')
def require(value, message):
    if not value: raise ValueError(message)
exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual GPU admission>', 'exec'))
print(json.dumps({'args': sys.argv[1:], 'allocation': single_gpu_allocation(os.environ)}))
"""

SRUN = r"""import json, os, subprocess, sys
args = sys.argv[1:]
index = next(i for i, arg in enumerate(args) if not arg.startswith('--'))
options, command = args[:index], args[index:]
assert '--gres=dcu:1' in options
assert '--ntasks=1' in options and '--nodes=1' in options and '--exclusive' in options
with open(os.environ['TEST_CAPTURE'], 'w') as stream:
    json.dump({'options': options, 'command': command}, stream)
env = dict(os.environ)
env['SLURM_STEP_GPUS'] = '0,1' if env.get('TEST_BAD_STEP') else env['SLURM_JOB_GPUS'].split(',')[-1]
env['ROCR_VISIBLE_DEVICES'] = env['SLURM_STEP_GPUS']
raise SystemExit(subprocess.call(command, env=env))
"""


@unittest.skipUnless(shutil.which('bash') and os.name=='posix', 'job script requires a POSIX shell')
class JobGpuStep(unittest.TestCase):
    def execute_script(self, task, job_gpus='0,1,2,3,4,5,6,7', bad_step=False,
                       cpus='8', previous_script=False):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temporary:
            root=Path(temporary)
            text=(ROOT/'jobs/workspace_task.slurm').read_text()
            assignment='ROOT=/public/home/zhangkewei/zr'
            self.assertEqual(text.count(assignment),1)
            text=text.replace(assignment,'ROOT='+shlex.quote(str(root)))
            if previous_script:
                text=text.replace(' || "${1:-}" == validate','')
            job=root/'job.sh';job.write_text(text)
            (root/'manage.py').write_text(WORKER)
            stub=root/'srun';stub.write_text('#!'+sys.executable+'\n'+SRUN);stub.chmod(0o700)
            config=root/'registered-config.json';config.write_text('{}')
            capture=root/'capture.json'
            env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],
                     SLURM_JOB_ID='99999',SLURM_JOB_NUM_NODES='1',SLURM_JOB_GPUS=job_gpus,
                     TEST_CAPTURE=str(capture),TEST_COMMON_SOURCE=str(ROOT/'tools/fft_measurement/common.py'))
            for name in ('SLURM_STEP_GPUS','SLURM_CPUS_PER_TASK','TEST_BAD_STEP'):
                env.pop(name,None)
            if cpus is not None:env['SLURM_CPUS_PER_TASK']=cpus
            if bad_step:env['TEST_BAD_STEP']='1'
            process=subprocess.run(['bash',str(job),task,str(config)],env=env,
                                   capture_output=True,text=True,timeout=20)
            trace=json.loads(capture.read_text()) if capture.exists() else None
            result=json.loads(process.stdout) if process.returncode==0 else None
            if result:
                self.assertEqual(result['args'],[task,'--config',str(config),'--worker'])
            return process,result,trace

    def assert_step(self,task,job_gpus):
        process,result,trace=self.execute_script(task,job_gpus)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIsNotNone(trace)
        self.assertIn('--cpus-per-task=8',trace['options'])
        self.assertEqual(result['allocation'],{'allocation_gpu':job_gpus,
                         'step_gpu':job_gpus.split(',')[-1], 'measurement_gpu':job_gpus.split(',')[-1]})

    def test_validate_exclusive_eight_gpu_allocation(self):
        self.assert_step('validate','0,1,2,3,4,5,6,7')

    def test_validate_ordinary_one_gpu_allocation(self):
        self.assert_step('validate','3')

    def test_measure_and_diagnose_keep_single_gpu_steps(self):
        for task in ('measure','diagnose'):
            with self.subTest(task=task):self.assert_step(task,'0,1,2,3,4,5,6,7')

    def test_build_retains_direct_single_gpu_execution(self):
        process,result,trace=self.execute_script('build','3')
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIsNone(trace)
        self.assertEqual(result['allocation']['measurement_gpu'],'3')

    def test_bad_step_does_not_weaken_single_gpu_check(self):
        process,_,trace=self.execute_script('validate',bad_step=True)
        self.assertNotEqual(process.returncode,0)
        self.assertIsNotNone(trace)
        self.assertIn('exactly one GPU',process.stderr)

    def test_missing_cpu_request_rejected(self):
        process,_,trace=self.execute_script('validate',cpus=None)
        self.assertNotEqual(process.returncode,0)
        self.assertIsNone(trace)
        self.assertIn('CPU request missing',process.stderr)

    def test_previous_script_reproduces_admission_failure(self):
        process,_,trace=self.execute_script('validate',previous_script=True)
        self.assertNotEqual(process.returncode,0)
        self.assertIsNone(trace)
        self.assertIn('exactly one GPU',process.stderr)


if __name__=='__main__':unittest.main()
