"""Submit the reviewed registration once, record its receipt, and stop without polling."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr
from register_ablation_957127 import ABLATION, CONFIG, RUN_ID, read, save


def commit(paths, message):
    subprocess.run(['git', 'add', '--', *map(str, paths)], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '--only', '-m', message, '--', *map(str, paths)],
                   cwd=ROOT, check=True)


def main():
    registration = read(ABLATION/'registration.json')
    preview = read(ABLATION/'preview.json')
    run = Path('experiments/EXP-128/runs')/RUN_ID
    mgr.require(not (ROOT/run).exists(), 'run already reserved; inspect its receipt before retrying')
    mgr.require(preview['submission_command'] == registration['submission_command'], 'preview differs')
    commit([CONFIG, Path('experiments/EXP-128/scripts/submit_ablation_957127.py')]
           + [ABLATION/name for name in ('preview-process.json', 'preview.json', 'registration.json')],
           'EXP128: register controlled ablation diagnostic and reviewed unified preview')
    proc = subprocess.run(registration['submit'], cwd=ROOT, capture_output=True, text=True, timeout=120)
    save(ABLATION/'submission-process.json', dict(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr))
    mgr.require(proc.returncode == 0, 'submission failed: '+proc.stderr[-2000:])
    receipt = read(run/'submission.json')
    mgr.require(receipt['argv'] == registration['submission_command'], 'submitted command differs')
    record = dict(job=receipt['job'], run=str(ROOT/run), config=str(ROOT/CONFIG),
                  cases=20, clean_timing_processes=79, metadata_processes=16,
                  processes=95, timing_samples=2370, formal_samples=0,
                  tool_source_commit=registration['tool_source_commit'],
                  status='Submitted; no scheduler or result polling after receipt.',
                  argv=receipt['argv'])
    save(ABLATION/'submission.json', record)
    commit([ABLATION/'submission-process.json', ABLATION/'submission.json'],
           'EXP128: record controlled ablation submission receipt')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
