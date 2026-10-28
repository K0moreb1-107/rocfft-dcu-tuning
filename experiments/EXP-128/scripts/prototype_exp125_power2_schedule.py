"""Restore only the EXP125 phase-load order in copied V6 RTC sources; CPU only."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path.insert(0, str(ROOT / 'experiments/EXP-128/scripts'))
import audit_exp125_cc_implementation as audit

RECORD = ROOT / 'experiments/EXP-128/records/exp125-power2-recheck-20261028'
ART = ROOT / 'experiments/EXP-128/artifacts/preflight/exp125-power2-recheck-20261028/schedule-prototypes'


def transform(raw, q):
    a = raw.index('// load global into registers\n')
    b = raw.index('// calc the thread_in_device', a)
    body = raw[a:b]
    indices = re.findall(r'cc_pre_j = ([^;]+);\ncc_pre_phase = [^;]+;', body)
    assert len(indices) == 4, indices
    expression = 'cc_pre_phase = cc_pre_j == 0 ? scalar_type{0,0} : cc_real_twiddles[cc_pre_j];'
    assert body.count(expression) == 4
    if q == 512:
        preload = '\n'.join(f'const scalar_type audit_phase_{i} = cc_real_twiddles[{index}];'
                            for i, index in enumerate(indices)) + '\n'
        first = body.index('cc_pre_j = ')
        body = body[:first] + preload + body[first:]
        for i in range(4):
            body = body.replace(expression, f'cc_pre_phase = audit_phase_{i};', 1)
    elif q == 256:
        # EXP125's register variant loads the phase inside the ordinary pair,
        # after p and q. Packed endpoints and all addresses remain V6's.
        body = body.replace(expression + '\n', '')
        call = 'cc_pre_pair<scalar_type>(cc_pre_p,cc_pre_q,cc_pre_phase,cc_pre_own,cc_pre_other);'
        assert body.count(call) == 4
        body = body.replace(call, 'cc_pre_phase = cc_real_twiddles[cc_pre_j];\n' + call)
    else:
        raise AssertionError(q)
    return raw[:a] + body + raw[b:]


def main():
    ART.mkdir(parents=True, exist_ok=True)
    data = json.loads((RECORD / 'current-vs-exp125-static.json').read_text())
    cases = []
    for x in data['kernels']:
        if x['version'] == 'exp125' or x['position'] != 1:
            continue
        q = int(re.search(r'_Q(\d+)_', x['name'])[1])
        src = Path(x['source'])
        raw = src.read_text()
        modified = transform(raw, q)
        assert modified[:modified.index('// load global into registers\n')] == raw[:raw.index('// load global into registers\n')]
        assert modified[modified.index('// calc the thread_in_device'):] == raw[raw.index('// calc the thread_in_device'):]
        dest = ART / f"schedule-{x['N']}.hip.cpp"
        dest.write_text(modified)
        cases.append(dict(version='old_phase_order_only', N=x['N'], func='z2d_1d', position=1,
                          name=x['name'], source=str(dest), original=str(src),
                          original_sha256=audit.sha(src.read_bytes()),
                          source_sha256=audit.sha(dest.read_bytes()), Q=q))
    assert len(cases) == 5
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(audit.compile_one, cases))
    result = dict(complete=all(x['complete'] for x in rows), device_execution=False,
                  production_source_modified=False,
                  changes='Only phase-load ordering in copied V6 rows; addresses, packed endpoints, arithmetic, shuffles, FFT and output stay unchanged. No performance or device-correctness claim.',
                  kernels=rows)
    out = RECORD / 'phase-order-prototypes.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for x in rows:
        print(json.dumps(dict(N=x['N'], Q=x['Q'], resources=x.get('resources'),
                              counts=x.get('static_instruction_groups'))))
    assert result['complete']


if __name__ == '__main__':
    main()
