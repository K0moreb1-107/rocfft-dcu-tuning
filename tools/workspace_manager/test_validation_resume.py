"""Host regressions for resumed acceptance and the final device-path collision."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[2]


def function(path,name,namespace):
    tree=ast.parse(path.read_text())
    node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name]


def require(value,message):
    if not value: raise ValueError(message)


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.check=function(ROOT/'tools/workspace_manager/validation_resume.py','checked_cases',
                            {'mgr':types.SimpleNamespace(require=require)})
        self.coverage={'cases':[{'N':65536,'func':'z2d_1d'}],
                       'controls':[{'N':32768,'func':'d2z_1d'}],'folded':[{'N':65536}]}
        self.model={'cases':1,'configurations':0}
        self.record={'complete':False,'failures':[{'type':'FileNotFoundError',
                     'message':"{'passed_default': 172}"}],
                     'default_cases':[dict(self.coverage['cases'][0],guard={'references':[{}]*14})],
                     'boundary_cases':[{'id':'one','exchange':'direct_scalar','max_error':1e-15}],
                     'controls':self.coverage['controls'],
                     'folded_regressions':[{'N':65536,'load':x} for x in ('registers','lds')],
                     'negative_control':{'expected_returncode':1},'retained_validation_sha256':'proof'}

    def test_complete_saved_coverage(self):
        self.check(self.record,self.coverage,self.model)

    def test_each_missing_stage_rejected(self):
        for key in ('default_cases','boundary_cases','controls','folded_regressions'):
            with self.subTest(stage=key):
                bad=copy.deepcopy(self.record);bad[key]=[]
                with self.assertRaises(ValueError):self.check(bad,self.coverage,self.model)

    def test_failed_accuracy_and_wrong_backend_rejected(self):
        for field,value in [('max_error',1e-9),('max_error',float('nan')),('exchange','direct_complex')]:
            bad=copy.deepcopy(self.record);bad['boundary_cases'][0][field]=value
            with self.assertRaises(ValueError):self.check(bad,self.coverage,self.model)

    def test_other_failure_not_reusable(self):
        bad=copy.deepcopy(self.record);bad['failures'][0]['type']='ValueError'
        with self.assertRaises(ValueError):self.check(bad,self.coverage,self.model)

    def test_guard_and_negative_control_required(self):
        for key in ('guard','negative'):
            bad=copy.deepcopy(self.record)
            if key=='guard':bad['default_cases'][0]['guard']['references']=[]
            else:bad['negative_control']={}
            with self.assertRaises(ValueError):self.check(bad,self.coverage,self.model)


class FinalVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"));self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.lib=self.path/'lib.so';self.lib.write_bytes(b'library')
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        self.gpu={'count':1,'uuid':'0123456789abcdef0123456789abcdef','arch':'gfx936'}
        self.device=self.path/'device_identity'
        self.calls=[]
        def process(argv,**kwargs):
            self.calls.append(argv)
            if argv[0]=='git':return 'tree'
            require(argv==[str(self.device)],'device executable was shadowed')
            return json.dumps(self.gpu)
        self.subprocess=types.SimpleNamespace(check_output=process)
        self.namespace={'mgr':types.SimpleNamespace(require=require,inside=Path,common=types.SimpleNamespace(sha=sha)),
                        'json':json,'subprocess':self.subprocess,'ROOT':self.path,
                        'matching_source_tree':lambda *args:{'tree_sha1':'tree'}}
        self.finish=function(ROOT/'experiments/EXP-127/scripts/validate_cc_all_io.py',
                             'finish_validation',self.namespace)
        self.v={'policy_index':0,'policy':'retained'}
        self.record={'default_cases':[],'boundary_cases':[],'controls':[]}
        self.built={'arm':{'library_sha256':sha(self.lib)}}
        self.model={'cases':0,'configurations':0};self.coverage={'cases':[]}

    def run_finish(self):
        self.finish(self.record,self.v,self.built,{},self.coverage,self.model,self.gpu,{},self.lib,self.device)

    def test_retained_uses_device_executable(self):
        self.run_finish();self.assertTrue(self.record['complete'])
        self.assertEqual(self.calls[-1],[str(self.device)])

    def test_nonretained_identity_data_never_overwrites_device(self):
        sha=self.namespace['mgr'].common.sha
        self.built.update(plan={'source_identity':{},'profile':{'ROCFFT_REAL_PAIR_IO_POLICY':'direct-scalar'}},compiler_version='same')
        prior={'complete':True,'arm':{'install':str(self.path),'source_commit':'commit','library_sha256':sha(self.lib)},
               'plan':{'source_identity':{},'profile':{'ROCFFT_REAL_PAIR_IO_POLICY':'retained'}},'compiler_version':'same'}
        libpath=self.path/'lib/librocfft.so.0.1';libpath.parent.mkdir();libpath.write_bytes(b'library')
        other={'complete':True,'policy':'retained','source_commit':'commit','library_sha256':sha(self.lib),'default_cases':[],'controls':[]}
        checked={'complete':True,'source_commit':'commit','library_sha256':sha(self.lib)}
        for name,value in [('build-provenance.json',prior),('cc-all-io-validation.json',other),('post-build-validation.json',checked),
                           ('identity.json',{'files':{},'fft_subtree':'tree'})]:
            (self.path/name).write_text(json.dumps(value))
        self.v.update(policy_index=2,policy='direct-scalar',retained_build_record=str(self.path/'build-provenance.json'),
                      retained_identity=str(self.path/'identity.json'))
        self.run_finish();self.assertTrue(self.record['complete'])
        self.assertEqual(self.calls[-1],[str(self.device)])

    def test_device_change_rejected(self):
        self.namespace['subprocess'].check_output=lambda *args,**kwargs:json.dumps({'count':2})
        with self.assertRaises(ValueError):self.run_finish()
        self.assertNotIn('complete',self.record)

    def test_library_change_rejected(self):
        self.lib.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_finish()


class QueueGateTests(unittest.TestCase):
    def setUp(self):
        self.resumed={'experiment':'EXP-127','validation_resume':{}}
        self.arm={'library_sha256':'candidate','source_commit':'source'}
        self.measurement={'experiment':'EXP-127','run_id':'actual','arms':{'candidate':self.arm},
                          'resources':{'node_exclusive':True}}
        self.cfg={'experiment':'EXP-127','run_id':'queue',
                  'resources':{'node_exclusive':True,'dependency':'afterok:123'},
                  'validated_measurement':{'resume_config':'resume.json','resume_job_id':'123',
                                           'measurement_config':'measurement.json'}}
        files={'resume.json':self.resumed,'measurement.json':self.measurement,
               str(Path('/run')/'submission.json'):{'job':'123'}}
        mgr=types.SimpleNamespace(require=require,inside=Path,load=lambda p:files[str(p)],
             locations=lambda *args:{'run':Path('/run')},task_plan=lambda *args:{'node_exclusive':True})
        self.call=function(ROOT/'tools/workspace_manager/validation_resume.py','gate',
             {'mgr':mgr,'read':lambda p:files[str(p)],'existing':lambda cfg:(None,{'arm':self.arm}),
              're':__import__('re')})

    def test_pending_resume_preview_allowed(self):
        self.call(self.cfg)

    def test_missing_success_dependency_rejected(self):
        self.cfg['resources']['dependency']='afterany:123'
        with self.assertRaises(ValueError):self.call(self.cfg)

    def test_wrong_candidate_rejected(self):
        self.measurement['arms']['candidate']={'library_sha256':'other'}
        with self.assertRaises(ValueError):self.call(self.cfg)

    def test_wrong_job_rejected(self):
        self.cfg['validated_measurement']['resume_job_id']='124'
        with self.assertRaises(ValueError):self.call(self.cfg)


if __name__=='__main__':unittest.main()
