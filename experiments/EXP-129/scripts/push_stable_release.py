"""Push the accepted stable branch and immutable release tag atomically."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts')]
from submit_gate_simplification import read, write

RECORD = ROOT/'experiments/EXP-129/records/stable-promotion-20261031'


def git(*args, timeout=90):
    process = subprocess.run(['git', *args], cwd=ROOT, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'),
        capture_output=True, text=True, timeout=timeout, check=True)
    return process.stdout.strip(), process.stderr


def refs(*names):
    output, _ = git('ls-remote', 'origin', *names)
    return {line.split()[1]: line.split()[0] for line in output.splitlines()}


def main():
    local = read(RECORD/'commit-result.json')
    assert local['local_promotion_complete']
    commit, tag, branch = local['stable_commit'], local['stable_tag'], local['experiment_branch']
    assert git('rev-parse', 'main')[0] == git('rev-parse', branch)[0] == commit
    assert git('rev-parse', tag+'^{}')[0] == commit
    names = ['refs/heads/main', 'refs/heads/'+branch, 'refs/tags/'+tag]
    before = refs(*names)
    old = read(RECORD/'promotion.json')['previous_stable_main']
    assert before['refs/heads/main'] == old and 'refs/tags/'+tag not in before
    git('merge-base', '--is-ancestor', old, commit)
    output, error = git('push', '--atomic', 'origin', *(name+':'+name for name in names), timeout=1200)
    after = refs(*names, 'refs/tags/'+tag+'^{}')
    assert after['refs/heads/main'] == after['refs/heads/'+branch] == after['refs/tags/'+tag+'^{}'] == commit
    assert after['refs/tags/'+tag] == local['tag_object']
    assert git('rev-parse', 'origin/main')[0] == commit
    result = dict(cloud_push_done=True, stable_commit=commit, stable_tag=tag,
        stable_branch='main', experiment_branch=branch,
        cloud_repository='https://github.com/K0moreb1-107/rocfft-dcu-tuning',
        remote_refs=after, remote_refs_before=before, push_stdout=output, push_stderr=error,
        source_subtree_identical_to_accepted_build=local['source_subtree_identical_to_accepted_build'],
        old_tags_unchanged=local['old_tags_unchanged'], force_push=False,
        full_validation_job='1004431', performance_job='1004433', new_gpu_jobs_submitted=False)
    write(RECORD/'push-result.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
