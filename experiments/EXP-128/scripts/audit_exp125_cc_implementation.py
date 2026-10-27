"""Offline comparison of accepted RTC texts; never runs a device or edits FFT sources."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/EXP-128/scripts'))
from tools.workspace_manager import manager as mgr
from isa_cc_957127 import analyze_isa

RECORD = ROOT / 'experiments/EXP-128/records/exp125-fusion-audit-20261027'
ART = ROOT / 'experiments/EXP-128/artifacts/preflight/exp125-fusion-audit-20261027'
NS = {65536, 131072, 262144, 524288, 1048576}
OLD_RUN = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-regression-955252-diagnostic-20261022'
V3_RUN = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-rowsimplify-retry1-validate-20261022'
V4_RUN = ROOT / 'experiments/EXP-128/runs/EXP-128-cc-local-grouped-validate-20261026'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sources(log):
    text = log.read_text()
    return dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$', text, re.M | re.S))


def capture(version, n, func, log, names=None):
    entries = sources(log)
    if names is None:
        entries = {k: v for k, v in entries.items() if k.startswith('fft_rtc_') and '_CB' not in k}
        names = sorted(entries, key=lambda s: 0 if '_sbcc_' in s else 1)
    assert len(names) == 2, (version, n, func, names)
    result = []
    for position, name in enumerate(names):
        raw = entries[name]
        p = ART / f'{version}-{n}-{func}-{position}.hip.cpp'
        p.write_text('#include <hip/hip_runtime.h>\n' + raw)
        result.append(dict(version=version, N=n, func=func, position=position,
                           name=name, source=str(p), source_sha256=sha(raw.encode()),
                           source_normalized_sha256=sha(re.sub(r'_cc_local_v[234]_', '_cc_local_vX_', raw).rstrip('\n').encode()),
                           evidence=str(log), evidence_sha256=sha(log.read_bytes())))
    return result


def compile_one(item):
    src = Path(item['source'])
    asm = src.with_suffix('.s')
    cmd = [mgr.DTK + '/bin/hipcc', '-O3', '-std=c++14', '--offload-arch=gfx936',
           '--cuda-device-only', '-S', '-mcumode', str(src), '-o', str(asm)]
    p = subprocess.run(cmd, env=mgr.environment(ART), capture_output=True, text=True, timeout=150)
    src.with_suffix('.compile.err').write_text(p.stderr)
    if p.returncode:
        return dict(item, complete=False, returncode=p.returncode, error=p.stderr[-2000:])
    text = asm.read_text()
    lines = text.splitlines()
    barriers = [i for i, s in enumerate(lines) if re.match(r'\s*s_barrier\b', s)]
    first = barriers[0] if barriers else len(lines)
    extra = dict(
        static_wait_all_before_first_barrier=sum('s_waitcnt vmcnt(0)' in s for s in lines[:first]),
        wait_all_total=sum('s_waitcnt vmcnt(0)' in s for s in lines),
        after_last_barrier_instructions=Counter(re.findall(r'^\s*((?:s_|v_|ds_|global_)[a-z0-9_]+)', '\n'.join(lines[barriers[-1] + 1:]), re.M)) if barriers else {},
    )
    info = analyze_isa(text)
    print('COMPILED', item['version'], item['N'], item['func'], item['position'], flush=True)
    return dict(item, complete=True, command=cmd, assembly=str(asm), assembly_sha256=sha(asm.read_bytes()),
                **info, **extra)


def main():
    RECORD.mkdir(exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    old = json.loads((OLD_RUN / 'diagnostic-result.json').read_text())
    assert old['complete']
    tasks = []
    for x in old['traces']:
        if x['N'] in NS and x['arm'] == 'baseline':
            tasks += capture('exp125', x['N'], x['func'], Path(x['folder']) / 'metadata/rtc.txt', x['trace']['kernel_names'])
    assert len(tasks) == 20, len(tasks)
    for version, run in [('v3', V3_RUN), ('v4', V4_RUN)]:
        gate = json.loads((run / 'post-build-validation.json').read_text())
        assert gate.get('complete'), (version, list(gate))
        for n in sorted(NS):
            for func in ['z2d_1d', 'd2z_1d']:
                log = run / 'measurement-validation' / f'{n}-{func}' / 'metadata/rtc.txt'
                if log.exists():
                    tasks += capture(version, n, func, log)
    # The v3 validation predates the 262144 representative; use its accepted diagnostic log.
    diag = json.loads((ROOT / 'experiments/EXP-128/runs/EXP-128-cc-rows-v3-regression-diagnostic-20261023/diagnostic-result.json').read_text())
    known = {(x['version'], x['N'], x['func']) for x in tasks}
    for x in diag['traces']:
        key = ('v3', x['N'], x['func'])
        if x['N'] in NS and x['arm'] == 'candidate' and key not in known:
            tasks += capture('v3', x['N'], x['func'], Path(x['folder']) / 'metadata/rtc.txt')
            known.add(key)
    assert sum(x['version'] == 'v4' for x in tasks) == 20
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(compile_one, tasks))
    failures = [x for x in rows if not x['complete']]
    by_key = {(x['version'], x['N'], x['func'], x['position']): x for x in rows}
    comparisons = []
    for x in rows:
        if x['version'] != 'v4':
            continue
        y = by_key.get(('v3', x['N'], x['func'], x['position']))
        if y:
            same = x['source_normalized_sha256'] == y['source_normalized_sha256']
            comparisons.append(dict(N=x['N'], func=x['func'], position=x['position'], v3_v4_same_except_version=same))
            if x['func'] == 'z2d_1d' or x['position'] == 0:
                assert same, (x['N'], x['func'], x['position'])
    result = dict(complete=not failures, device_execution=False, exact_logged_sources=True,
                  policy='Offline static ISA; not device execution counts, timings, or occupancy measurements.',
                  kernels=rows, comparisons=comparisons, failures=failures)
    out = RECORD / 'exact-rtc-static-comparison.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(complete=not failures, kernels=len(rows), comparisons=len(comparisons), output=str(out))))
    assert not failures


if __name__ == '__main__':
    main()
