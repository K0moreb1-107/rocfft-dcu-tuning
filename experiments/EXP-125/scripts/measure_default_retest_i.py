#!/usr/bin/env python3
"""One formal 720-process measurement of unchanged EXP125 using default paths."""
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT / 'tools/workspace_manager'))
import manager as mgr
import run as formal_run
import summarize


def formal_schedule():
    entries = []
    for n in mgr.common.SIZES:
        for function in mgr.common.FUNCS:
            for round_no in range(1, 9):
                order = (('official', 'previous', 'candidate', 'candidate', 'previous', 'official')
                         if round_no % 2 else
                         ('candidate', 'previous', 'official', 'official', 'previous', 'candidate'))
                for slot, arm in enumerate(order, 1):
                    entries.append(dict(index=len(entries), N=n, func=function,
                                        round=round_no, slot=slot, arm=arm))
    return entries


def audit(cfg):
    for name, digest in cfg['required_file_sha256'].items():
        mgr.require(mgr.common.sha(mgr.inside(name)) == digest, 'frozen file changed: ' + name)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    identity = cfg['candidate_identity']
    mgr.require(git('rev-parse', 'HEAD') == identity['source_commit'], 'source commit changed')
    mgr.require(git('branch', '--show-current') == identity['branch'], 'source branch changed')
    mgr.require(not git('status', '--porcelain', '--untracked-files=all', '--',
                        'rocm-libraries-rocm-7.2.2/projects/rocfft'), 'FFT source changed')
    mgr.require(not any(k.startswith('ROCFFT_') and k not in
                        ('ROCFFT_RTC_CACHE_READ_DISABLE', 'ROCFFT_RTC_CACHE_WRITE_DISABLE')
                        for k in os.environ), 'default path requires no ROCFFT overrides')
    mgr.require(tuple(mgr.common.SIZES) == (65536, 131072, 262144, 524288, 1048576)
                and tuple(mgr.common.FUNCS) == ('z2z_1d', 'd2z_1d', 'z2d_1d'),
                'measurement matrix changed')


def main():
    cfg = mgr.load(Path(sys.argv[1]))
    mgr.require(os.environ.get('SLURM_JOB_ID') and os.environ.get('SLURM_JOB_GPUS')
                and len(os.environ['SLURM_JOB_GPUS'].split(',')) == 1,
                'one GPU allocation required')
    mgr.require(os.environ.get('SLURM_JOB_NUM_NODES', '1') == '1', 'one node required')
    audit(cfg)
    # Apply the prescribed order in this worker and its aggregator only.
    mgr.common.schedule = formal_schedule
    formal_run.schedule = formal_schedule
    summarize.schedule = formal_schedule
    formal_run.execute(mgr.common.validate_manifest(cfg))
    audit(cfg)


if __name__ == '__main__':
    main()
