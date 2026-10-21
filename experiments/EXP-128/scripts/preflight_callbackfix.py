"""Host-only generator compilation and generated-code regression comparison."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
from tools.workspace_manager import manager as mgr
s = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
b = ROOT/'experiments/EXP-128/artifacts/preflight/host-20261021'
build = b/'rocfft_build'
phase = sys.argv[1]
assert phase in ('before', 'after')
r = ROOT/'experiments/EXP-128/records/callbackfix-20261021'
a = ROOT/'experiments/EXP-128/artifacts/preflight/callbackfix-20261021'/phase
a.mkdir(parents=True, exist_ok=True)
env = mgr.environment(a)
start = time.monotonic()

def run(argv, label):
    with (a/(label+'.log')).open('wb') as out:
        proc = subprocess.run(list(map(str, argv)), env=env, cwd=ROOT,
                              stdout=out, stderr=subprocess.STDOUT, timeout=240)
    print(label, proc.returncode, flush=True)
    if proc.returncode:
        print((a/(label+'.log')).read_text()[-10000:], flush=True)
        sys.exit(proc.returncode)

if phase == 'after':
    run(['cmake', '--build', build, '--target', 'rocfft-rtc-gen', 'rocfft-rtc-common',
         'generator', '-j16'], 'generator')
incs = [s/'library/src/include', s/'library/include', build/'include',
        build/'include/rocfft', Path(mgr.DTK)/'hip/include']
objects = list((build/'library/src/CMakeFiles/rocfft-rtc-gen.dir').rglob('*.o'))
objects += list((build/'library/src/CMakeFiles/rocfft-rtc-common.dir').rglob('*.o'))
objects += list((build/'library/src/device/generator/CMakeFiles/generator.dir').rglob('*.o'))
for name, manifest in [
    ('cc_local_generate', ROOT/'experiments/EXP-128/records/implementation-20261021/generation-matrix.txt'),
    ('cc_legacy_generate', r/'legacy-generation-matrix.txt')]:
    src = ROOT/'experiments/EXP-128/scripts'/(name+'.cpp')
    run([mgr.DTK+'/bin/hipcc', '--offload-host-only', '-std=c++17', '-D__HIP_PLATFORM_AMD__',
         '-DROCFFT_STATIC_LIB', *['-I'+str(x) for x in incs], '-c', src,
         '-o', a/(name+'.o')], name+'-compile')
    run([mgr.DTK+'/bin/hipcc', a/(name+'.o'), *objects, '-L'+mgr.DTK+'/lib',
         '-lamdhip64', '-lpthread', '-ldl', '-lstdc++fs', '-o', a/name], name+'-link')
    out = a/name; generated = a/(name+'-source'); generated.mkdir()
    run([out, manifest, generated], name+'-generate')

hashes = {str(p.relative_to(a)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in a.glob('*-source/*.cpp')}
summary = dict(phase=phase, files=len(hashes), sha256=hashes,
               elapsed_seconds=time.monotonic()-start)
if phase == 'after':
    before = json.loads((r/'host-before.json').read_text())['sha256']
    assert hashes.keys() == before.keys()
    changed = [name for name, value in hashes.items() if before[name] != value]
    expected = {'cc_legacy_generate-source/%d-1-%d-1.cpp'%(n, load)
                for n in (65536, 131072, 262144, 524288, 1048576) for load in (0, 1)}
    assert set(changed) == expected, changed
    def syntax(name):
        path = a/name
        log = path.with_suffix('.syntax.log')
        with log.open('wb') as out:
            p = subprocess.run([mgr.DTK+'/bin/hipcc', '--offload-arch=gfx936', '-mcumode',
                '-std=c++17', '-include', 'hip/hip_runtime.h', '-fsyntax-only', '-ferror-limit=4',
                '-DROCFFT_CALLBACKS_ENABLED', str(path)], env=env, stdout=out,
                stderr=subprocess.STDOUT, timeout=90)
        return dict(file=name, returncode=p.returncode,
                    errors=[x for x in log.read_text().splitlines() if 'error:' in x])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        checks = list(pool.map(syntax, sorted(changed)))
    summary.update(changed=changed, syntax=checks,
                   elapsed_seconds=time.monotonic()-start)
    assert all(x['returncode'] == 0 for x in checks), checks
    summary['unchanged'] = dict(new_adapter_sources=96, legacy_other_sources=30)
(r/('host-'+phase+'.json')).write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('sha256', 'syntax')}, indent=2))
