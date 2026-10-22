"""Read accepted traces and compile their actual row sources; no device execution."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
from cc_regression_evidence import trace_evidence

BASE = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-phasefix-validate-20261022/measurement-validation'
OUT = ROOT/'experiments/EXP-128/artifacts/preflight/regression-955252-20261022'
RECORD = ROOT/'experiments/EXP-128/records/regression-955252-20261022'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    RECORD.mkdir(parents=True,exist_ok=True)
    traces = []
    for n in (65536,69938,167042,142688):
        for func in ('z2d_1d','d2z_1d'):
            folder = BASE/(str(n)+'-'+func)
            trace = trace_evidence((folder/'metadata/plan.txt').read_text(),
                json.loads((folder/'profile/trace.json').read_text())['traceEvents'],func)
            traces.append(dict(N=n,func=func,metadata_logging_enabled=True,
                source='accepted validation trace, not an independent performance diagnosis',
                kernels=[dict(name=x['name'],**x['stats_us']) for x in trace['kernels']]))
    tasks = [(92480,'z2d_1d',5),(167042,'z2d_1d',5),(167042,'d2z_1d',7),
             (142688,'z2d_1d',5),(142688,'d2z_1d',7)]
    def compile_one(task):
        n,func,role = task
        folder = BASE/(str(n)+'-'+func)
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
            (folder/'metadata/rtc.txt').read_text(),re.M|re.S))
        name,source = next((name,source) for name,source in sources.items()
            if '_cc_local_v2_role'+str(role)+'_' in name and not re.search(r'_(CB|CBr2c|CBc2r)_',name))
        stem = OUT/('%d-%s-role%d'%(n,func,role))
        cpp = stem.with_suffix('.hip.cpp')
        cpp.write_text('#include <hip/hip_runtime.h>\n'+source)
        bundle = stem.with_suffix('.bundle')
        device = stem.with_suffix('.hsaco')
        command = [mgr.DTK+'/bin/hipcc','-O3','-std=c++14','--genco','--offload-arch=gfx936',
                   '-mcumode',str(cpp),'-o',str(bundle)]
        def run(command,label):
            proc = subprocess.run(command,env=mgr.environment(OUT),capture_output=True,text=True,timeout=120)
            stem.with_suffix('.'+label+'.out').write_text(proc.stdout)
            stem.with_suffix('.'+label+'.err').write_text(proc.stderr)
            if proc.returncode:
                raise RuntimeError(str(command)+': '+proc.stderr[-3000:])
            return proc.stdout
        run(command,'compile')
        run([mgr.DTK+'/llvm/bin/clang-offload-bundler','--unbundle','--type=o',
             '--targets=hipv4-amdgcn-amd-amdhsa--gfx936','--input='+str(bundle),
             '--output='+str(device)],'unbundle')
        notes = run([mgr.DTK+'/llvm/bin/llvm-readelf','--notes',str(device)],'notes')
        keys = ('vgpr_count','vgpr_spill_count','private_segment_fixed_size','group_segment_fixed_size','sgpr_count')
        resources = {key:int(re.search(r'\.'+key+r':\s*(\d+)',notes).group(1)) for key in keys}
        bundle.unlink()
        return dict(N=n,func=func,role=role,name=name,command=command,resources=resources,
                    source=str(cpp),code_object=str(device))
    with ThreadPoolExecutor(max_workers=2) as pool:
        resources = list(pool.map(compile_one,tasks))
    result = dict(complete=True,device_execution=False,validation_trace_samples=traces,offline_compilation=resources,
        limitation='Offline compilation of actual accepted RTC text; loaded device resources still require new counters. Validation traces included metadata/occupancy logging and cannot replace new clean diagnostic traces.')
    (RECORD/'host-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=True,traces=traces,resources=[dict(N=x['N'],func=x['func'],role=x['role'],
                         resources=x['resources']) for x in resources]),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
