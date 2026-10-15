"""Verify metadata logging never contaminates the profiled process."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch


class DiagnosticRunner(unittest.TestCase):
    def test_profile_is_separate_from_plan_logging_and_keeps_trace(self):
        workspace=Path(__file__).resolve().parents[2]
        path=workspace/'experiments/EXP-127/scripts/diagnose_cc_low_speed.py'
        saved=list(sys.path)
        try:
            spec=importlib.util.spec_from_file_location('cc_diagnostic_test',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        finally:sys.path[:]=saved
        parent=workspace/'.worktree-archives/diagnostic-runner-tests';parent.mkdir(parents=True,exist_ok=True)
        root=parent/uuid.uuid4().hex;root.mkdir()
        def cleanup():
            assert root.resolve().parent==parent.resolve();shutil.rmtree(root)
        self.addCleanup(cleanup)
        args=SimpleNamespace(run=root/'run',cache=root/'cache')
        args.run.mkdir();args.cache.mkdir()
        lib=root/'install/lib/librocfft.so.0.1';lib.parent.mkdir(parents=True);lib.write_bytes(b'synthetic library')
        binary=root/'timer';binary.write_bytes(b'synthetic binary')
        identity=root/'identity';identity.write_bytes(b'synthetic identity')
        gpu=dict(count=1,uuid='a'*32,arch='gfx936')
        cfg=dict(arms=dict(candidate=dict(install=str(lib.parent.parent),library_sha256=module.mgr.common.sha(lib))),
                 diagnostic_program=dict(binary_sha256=module.mgr.common.sha(binary),identity_sha256=module.mgr.common.sha(identity)),
                 expected_boundaries={'120224':{'z2d_1d':'fft_rtc_paired_pre_columns_v2'}})
        calls=[]
        def launch(argv,env,folder,label,timeout=180):
            argv=list(map(str,argv));calls.append((argv,dict(env)))
            if label=='profile':
                (folder/'profile.hipkernel.csv').write_text('Name,Calls,TotalDurationNs\nfft_rtc_paired_pre_columns_v2,41,1234\nfft_rtc_ordinary,41,2345\nTotal,-,3579\n')
            return dict(argv=argv,returncode=0)
        def command(argv,**kwargs):
            return json.dumps(gpu) if argv[0]==str(identity) else 'librocfft.so.0.1 => '+str(lib)+' (0x0)\n'
        entries=[]
        with patch.object(module.mgr,'ROOT',root),patch.object(module,'launch',side_effect=launch),\
             patch.object(module.subprocess,'check_output',side_effect=command),\
             patch.object(module.contract,'read_rows',return_value=[{}]),\
             patch.object(module.contract,'read_check',return_value={'check':'PASS'}),\
             patch.object(module.contract,'read_samples',return_value=[]),\
             patch.object(module.contract,'validate_process'),contextlib.redirect_stdout(io.StringIO()):
            module.profile_case(args,cfg,entries,gpu,{'LD_LIBRARY_PATH':'synthetic'},binary,identity,
                                dict(N=120224,func='z2d_1d',arm='candidate',index=0))
        self.assertTrue(entries[0]['valid'])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][1]['ROCFFT_LAYER'],'40')
        self.assertNotIn('ROCFFT_LAYER',calls[1][1])
        self.assertNotIn('--stats',calls[1][0])
        self.assertIn('--trace-args',calls[1][0])
        self.assertIn('--output-type',calls[1][0])
        self.assertNotEqual(calls[0][1]['FFT_TEST_OUT'],calls[1][1]['FFT_TEST_OUT'])


if __name__=='__main__':unittest.main()
