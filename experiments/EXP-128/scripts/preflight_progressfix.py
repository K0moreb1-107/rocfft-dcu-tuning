"""Host-only persistence/driver regression; device calls are explicitly mocked."""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

ROOT=Path('/public/home/zhangkewei/zr')
HERE=ROOT/'experiments/EXP-128/scripts'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
from tools.workspace_manager import manager as mgr

started=time.monotonic()
record=ROOT/'experiments/EXP-128/records/progressfix-20261021'
record.mkdir(exist_ok=True)
label=sys.argv[1]
assert label.replace('-', '').isalnum()
folder=ROOT/'experiments/EXP-128/artifacts/preflight/progressfix-20261021'/label
folder.mkdir(parents=True)
build_run=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-callbackfix-build-20261021'
built=json.loads((build_run/'build-provenance.json').read_text())
config=json.loads((build_run/'submit-manifest.json').read_text())
gpu=json.loads((build_run/'cc-local-validation.json').read_text())['gpu']
lib=(Path(built['arm']['install'])/'lib/librocfft.so.0.1').resolve()
coverage=json.loads(Path(config['validation']['coverage']).read_text())
by_n={c['N']:c for c in coverage['public']}
real_run=subprocess.run;real_output=subprocess.check_output
script=HERE/'validate_cc_local_fast.py'
old=types.ModuleType('old_validation');old.__file__=str(script)
source=subprocess.check_output(['git','show',built['arm']['source_commit']+':experiments/EXP-128/scripts/validate_cc_local_fast.py'],cwd=ROOT,text=True)
exec(compile(source,str(script),'exec'),old.__dict__)
spec=importlib.util.spec_from_file_location('new_validation',script)
new=importlib.util.module_from_spec(spec);spec.loader.exec_module(new)


def exercise(module,label,fail_at=None):
    run=folder/label;run.mkdir();cache=run/'cache';cache.mkdir()
    cfg=run/'config.json';cfg.write_text(json.dumps(config))
    checks=[]
    def fake_references(n,d,callbacks,scratch,patterns,scales):
        manifest=scratch/'mock-manifest.txt';manifest.write_text('host-only mocked device input\n')
        return manifest,[dict(pattern=p,scale=s) for p in patterns for s in scales]
    def fake_run(argv,**kwargs):
        argv=list(map(str,argv))
        if argv[0].endswith('/hipcc'):
            Path(argv[argv.index('-o')+1]).touch()
            return subprocess.CompletedProcess(argv,0)
        if Path(argv[0]).name=='public-guard':
            n=int(argv[1]);direction=argv[2];mode=argv[4]
            checks.append((n,direction,mode))
            env=kwargs['env'];rtc=Path(env['ROCFFT_LOG_RTC_PATH'])
            if n==65536:
                rtc.write_text('_unique_load_v1' if mode in ('callbacks','load') else 'ordinary input loader')
            else:
                c=by_n[n];roles=(4,5) if direction=='z2d' else (6,7)
                rtc.write_text(' '.join('_cc_local_v1_role%d_C%d_Q%d_'%(role,c['C'],c['Q']) for role in roles))
            Path(env['ROCFFT_LOG_PLAN_PATH']).write_text('host-only mock plan\n')
            kwargs['stdout'].write(b'EVEN_CC_GUARD_PASS mocked\n'*4)
            return subprocess.CompletedProcess(argv,1 if len(checks)==fail_at else 0)
        return real_run(argv,**kwargs)
    def fake_output(argv,**kwargs):
        if Path(str(argv[0])).name=='device-identity':return json.dumps(gpu)
        if str(argv[0])=='ldd':return 'librocfft.so.0 => '+str(lib)+' (0x0)\n'
        return real_output(argv,**kwargs)
    argv=[str(script),'--config',str(cfg),'--build-record',str(build_run/'build-provenance.json'),
        '--run',str(run),'--build',built['plan']['paths']['build'],'--cache',str(cache)]
    error=None
    with patch.object(module.sys,'argv',argv),patch.object(module,'references',fake_references), \
         patch.object(module.subprocess,'run',fake_run),patch.object(module.subprocess,'check_output',fake_output), \
         contextlib.redirect_stdout(io.StringIO()):
        try:module.worker()
        except Exception as exc:error=exc
    return run,json.loads((run/'cc-local-validation.json').read_text()),checks,error


run,old_record,checks,error=exercise(old,'old-reproduction')
assert isinstance(error,FileExistsError) and len(checks)==2 and len(old_record['controls'])==1
run,complete,checks,error=exercise(new,'complete')
assert error is None and complete['complete'] and len(checks)==32
assert len(complete['controls'])==8 and len(complete['public'])==24
assert not list(run.glob('*.tmp'))
run,failed,checks,error=exercise(new,'failure',fail_at=2)
assert error is not None and not failed['complete'] and len(failed['controls'])==1
assert 'guard failed' in failed['failure']['message']
# Exercise the real timeout handler with an already existing progress record.
class Expired:
    pid=123456
    calls=0
    def wait(self,timeout):
        self.calls+=1
        if self.calls==1:raise subprocess.TimeoutExpired('host-only mock worker',timeout)
        return -15
with patch.object(new.sys,'argv',[str(script),'--run',str(run)]), \
     patch.object(new.subprocess,'Popen',return_value=Expired()), \
     patch.object(new.os,'killpg') as killed,contextlib.redirect_stderr(io.StringIO()):
    assert new.main()==1
    assert killed.called
expired=json.loads((run/'cc-local-validation.json').read_text())
assert not expired['complete'] and expired['failure']['type']=='ValidationTimeout'
assert len(expired['controls'])==1 and not list(run.glob('*.tmp'))
summary=dict(complete=True,host_only=True,device_calls_mocked=True,
    tests=['original second-save failure reproduced','all 32 records and final completion saved',
           'injected guard failure preserved','timeout replaced existing progress safely','store-only callback needs no load specialization'],
    elapsed_seconds=time.monotonic()-started,
    actual_device_acceptance=False)
(record/('host-checks-'+label+'.json')).write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
