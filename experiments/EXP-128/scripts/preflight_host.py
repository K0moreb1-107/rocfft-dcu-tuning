from pathlib import Path
import json,sys,subprocess
ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
base=ROOT/'experiments/EXP-128/artifacts/preflight/host-20261021'
base.mkdir(parents=True,exist_ok=True)
cfg={'experiment':'EXP-128','run_id':'EXP-128-host-preflight-20261021','gpu_arch':'gfx936','resources':{'cpus':16},'build':{'build_id':'EXP-128-host-preflight-20261021','source_repo':str(ROOT),'source_dir':str(ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'),'source_commit':'f229a064cfd4a429d7fe06024ab138fe7c544ff7','cmake':{'BUILD_CLIENTS_BENCH':'OFF','CMAKE_EXPORT_COMPILE_COMMANDS':'ON'}}}
plan=mgr.build_plan(cfg)
commands=plan['commands'][:2]
for i,argv in enumerate(commands):
    # Isolate generator preparation from the two queued builds.
    argv=[str(base/'rocfft_build') if a==plan['paths']['build'] else a for a in argv]
    with (base/('step-%d.log'%i)).open('wb') as f:
        r=subprocess.run(argv,env=mgr.environment(base),stdout=f,stderr=subprocess.STDOUT)
    print(json.dumps({'step':i,'returncode':r.returncode,'log':str(base/('step-%d.log'%i))}),flush=True)
    if r.returncode:
        print((base/('step-%d.log'%i)).read_text()[-14000:]);sys.exit(r.returncode)
print('GENERATOR_PREFLIGHT_PASS')

import concurrent.futures,shlex
commands=json.loads((base/'rocfft_build/compile_commands.json').read_text())
names={'tree_node_real.cpp','tree_node.cpp','tree_node_1D.cpp','plan.cpp','assignment_policy.cpp','rtc_stockham_kernel.cpp'}
def check(rec):
    argv=shlex.split(rec['command']);i=argv.index('-o');del argv[i:i+2];argv.remove('-c')
    argv.extend(['-fsyntax-only','--offload-host-only','-ferror-limit=5'])
    path=base/(Path(rec['file']).stem+'-syntax.log')
    with path.open('wb') as f:r=subprocess.run(argv,cwd=rec['directory'],env=mgr.environment(base),stdout=f,stderr=subprocess.STDOUT)
    if r.returncode:print(path.read_text()[-10000:],flush=True)
    return {'file':rec['file'],'returncode':r.returncode,'log':str(path)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:checks=list(pool.map(check,[x for x in commands if Path(x['file']).name in names]))
(base/'host-syntax.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks),flush=True)
assert len(checks)==len(names) and all(x['returncode']==0 for x in checks)
