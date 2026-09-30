"""Scientific aggregation/schedule rejection tests; synthetic data, no GPU calls."""
import copy
import csv
import json
import math
import os
import tempfile
import unittest
import uuid
from collections import Counter
from pathlib import Path
from common import ARMS, FUNCS, HEADER, OFFICIAL_COMMIT, OFFICIAL_SHA, POLICY, SIZES, SOURCE_SHA, manifest, reference, schedule, sha
from summarize import aggregate

class Contract(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            # Windows sandbox-created mode-0700 TemporaryDirectory can deny
            # the restricted token. Use inherited workspace permissions.
            self.run = Path(os.environ['TEMP']) / ('fft-' + uuid.uuid4().hex)
            self.run.mkdir()
        else:
            self.tmp = tempfile.TemporaryDirectory()
            self.addCleanup(self.tmp.cleanup)
            self.run = Path(self.tmp.name)
        self.ref = Path(__file__).resolve().parents[2] / 'results/reference/a100/A100_1d_32768_65536_131072_262144_524288_1048576.csv'
        # Shared reference location when installed at zr/tools/fft_measurement.
        m = dict(policy=POLICY, experiment='EXP-999', run_id='EXP-999-synthetic', gpu_arch='gfx936', acceptance='Synthetic example requires all correctness checks and explicit manual assessment.', arms={})
        for arm in ARMS:
            m['arms'][arm] = dict(install='/public/home/zhangkewei/zr/install-'+arm, source_repo='/public/home/zhangkewei/zr', source_state='clean tracked source at declared build commit', build_provenance='Synthetic fixture; not valid GPU performance evidence.', source_commit=OFFICIAL_COMMIT if arm=='official' else 'a'*40, library_sha256=OFFICIAL_SHA if arm=='official' else ('b' if arm=='previous' else 'c')*64)
        self.m=m
        self.dump('preregistration.json',m)
        self.gpu=dict(count=1,uuid='1'*32,arch='gfx936',runtime_version=70200000,driver_version=70200000)
        self.p=dict(policy=POLICY, source_sha256=SOURCE_SHA, complete=True, job_id='synthetic', host='synthetic',gpu=self.gpu,arms={a:dict(m['arms'][a],actual_library='/public/home/zhangkewei/zr/install-'+a+'/lib/librocfft.so.0.1',binary_sha256='f'*64) for a in ARMS})
        self.dump('provenance.json',self.p)
        entries=[]
        for planned in schedule():
            arm=planned['arm']; index=planned['index']; func=planned['func']
            directory=self.run/('p%04d'%index);directory.mkdir()
            # Last process per arm/case is intentionally extreme: it must remain in arithmetic mean.
            ordinal=sum(1 for e in entries if (e['N'],e['func'],e['arm'])==(planned['N'],func,arm))
            mean={'official':4.,'previous':3.,'candidate':2.}[arm] + (16 if ordinal==15 else 0)
            row=dict(zip(HEADER,[func,planned['N'],1,1,50,1,1,1,mean,mean+1,1,'PASS',1e-12,1e-12 if func=='z2z_1d' else -1]))
            with (directory/'data.csv').open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=HEADER);w.writeheader();w.writerow(row)
            for filename in ('stdout.txt','stderr.txt'):(directory/filename).write_text('synthetic\n',encoding='utf-8')
            e=dict(planned,returncode=0,gpu=self.gpu,job_id='synthetic',host='synthetic',library_sha256=m['arms'][arm]['library_sha256'])
            for key,name in (('csv','data.csv'),('stdout','stdout.txt'),('stderr','stderr.txt')):
                e[key]=str((directory/name).relative_to(self.run));e[key+'_sha256']=sha(directory/name)
            entries.append(e)
        self.entries=entries
        self.dump('processes.json',entries)
    def dump(self,name,data):
        (self.run/name).write_text(json.dumps(data),encoding='utf-8')
    def rejected(self):
        with self.assertRaises((ValueError, OSError, KeyError, TypeError)):
            aggregate(self.run,self.ref)
    def change_row(self,key,value):
        e=self.entries[0]; p=self.run/e['csv']
        with p.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
        rows[0][key]=value
        with p.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=HEADER);w.writeheader();w.writerows(rows)
        e['csv_sha256']=sha(p);self.dump('processes.json',self.entries)
    def test_schedule_pairwise_balance_and_counts(self):
        s=schedule();self.assertEqual(len(s),720)
        self.assertTrue(all(v==16 for v in Counter((e['N'],e['func'],e['arm']) for e in s).values()))
        for start in range(0,720,6):
            block=[x['arm'] for x in s[start:start+6]]
            for a,b in (('official','previous'),('official','candidate'),('previous','candidate')):
                pair=[v for v in block if v in (a,b)]
                self.assertIn(pair,([a,b,b,a],[b,a,a,b]))
        self.assertNotIn(32768,[e['N'] for e in s])
    def test_formula_all16_including_outlier(self):
        _,_,rows=aggregate(self.run,self.ref)
        self.assertEqual(len(rows),15)
        ref=reference(self.ref)
        for r in rows:
            self.assertEqual(r['candidate_mean_ms'],3.)
            self.assertEqual(r['previous_mean_ms'],4.)
            self.assertEqual(r['official_mean_ms'],5.)
            self.assertAlmostEqual(r['speedup_previous'],4/3)
            self.assertAlmostEqual(r['speedup_official'],5/3)
            self.assertAlmostEqual(r['a100_performance_percent'],ref[(r['N'],r['func'])]/3*100)
            self.assertEqual(r['candidate_process_median_ms'],2.)
    def test_missing_process(self):
        self.dump('processes.json',self.entries[:-1]);self.rejected()
    def test_wrong_order(self):
        self.entries[0],self.entries[1]=self.entries[1],self.entries[0];self.dump('processes.json',self.entries);self.rejected()
    def test_gpu_change(self):
        self.entries[0]['gpu']=dict(self.gpu,uuid='2'*32);self.dump('processes.json',self.entries);self.rejected()
    def test_job_change(self):
        self.entries[0]['job_id']='other';self.dump('processes.json',self.entries);self.rejected()
    def test_nonzero_exit(self):
        self.entries[0]['returncode']=1;self.dump('processes.json',self.entries);self.rejected()
    def test_hash_change(self):
        (self.run/self.entries[0]['csv']).write_text('corrupt',encoding='utf-8');self.rejected()
    def test_fail(self):self.change_row('check','FAIL');self.rejected()
    def test_iterations(self):self.change_row('iters','51');self.rejected()
    def test_batch(self):self.change_row('batch','2');self.rejected()
    def test_nan(self):self.change_row('mean_ms','nan');self.rejected()
    def test_strict_error(self):self.change_row('err_a','1e-9');self.rejected()
    def test_wrong_case(self):self.change_row('N','32768');self.rejected()
    def test_incomplete(self):
        self.p['complete']=False;self.dump('provenance.json',self.p);self.rejected()
    def test_reference_modified(self):
        bad=self.run/'badref.csv';bad.write_bytes(self.ref.read_bytes()+b'\n')
        with self.assertRaises(ValueError):aggregate(self.run,bad)
    def test_library_mismatch(self):
        self.entries[0]['library_sha256']='d'*64;self.dump('processes.json',self.entries);self.rejected()
    def test_requires_preregistration(self):
        self.m['acceptance']='REPLACE';self.dump('preregistration.json',self.m);self.rejected()

if __name__=='__main__': unittest.main()
