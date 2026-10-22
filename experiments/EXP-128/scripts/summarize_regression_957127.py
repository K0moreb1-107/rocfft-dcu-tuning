"""Summarize accepted raw diagnostic counters without relabelling their units."""
import hashlib
import json
from pathlib import Path
import re

from cc_regression_evidence import stats

ROOT = Path('/public/home/zhangkewei/zr')
RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-regression-955252-diagnostic-20261022'
OUT = ROOT/'experiments/EXP-128/records/regression-955252-20261022/analysis-957127'
SKIP = {'kernel dispatch index','dispatch queue id','dispatch queue index','gpu id',
        'process id','thread id','signal handle'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field_stats(values):
    parsed = [re.fullmatch(r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)(.*)',value)
              for value in values]
    if all(parsed) and len({match[2] for match in parsed}) == 1:
        return dict(unit=parsed[0][2],**stats([float(match[1]) for match in parsed]))
    return dict(raw_values=sorted(set(values)))


def main():
    record = json.loads((RUN/'diagnostic-result.json').read_text())
    assert record['complete'] and not record['failures']
    assert len(record['traces']) == 300 and len(record['pmc']) == 196
    traces = {(item['N'],item['func'],item['arm']):item for item in record['traces']}
    counters = []
    for item in record['pmc']:
        path = Path(item['folder'])/'measured-counter-windows.json'
        data = json.loads(path.read_text())
        windows = data['windows']
        trace = traces[item['N'],item['func'],item['arm']]['trace']
        names = trace['kernel_names']
        assert len(windows) == 30 and all([block['name'] for block in window] == names for window in windows)
        kernels = []
        for position,name in enumerate(names):
            keys = set(windows[0][position]['fields'])-SKIP
            assert all(keys <= window[position]['fields'].keys() for window in windows)
            kernels.append(dict(position=position,name=name,
                fields={key:field_stats([window[position]['fields'][key] for window in windows])
                        for key in sorted(keys)}))
        counters.append(dict(N=item['N'],func=item['func'],arm=item['arm'],mode=item['mode'],
            kernels=kernels,evidence=str(path),sha256=digest(path),export_type=item['export_type']))
    plan_notes = []
    for item in record['traces']:
        path = Path(item['folder'])/'metadata/plan.txt'
        text = path.read_text()
        grids = re.findall(r'GridParams\n(.*?)End GridParams',text,re.S)
        assert grids
        width = len(item['trace']['kernel_names'])
        occupancies = list(map(int,re.findall(r'Kernel occupancy:\s*(\d+)',text)))
        assert len(occupancies) >= 40*width
        assert occupancies[-40*width:] == occupancies[-width:]*40
        # Keep the final, already verified actual timing geometry; no setup/check plans.
        plan_notes.append(dict(N=item['N'],func=item['func'],arm=item['arm'],
            geometry=grids[-1].strip(),maximum_active_workgroups=occupancies[-width:],
            evidence=str(path),sha256=digest(path),
            schemes=sorted(set(re.findall(r'CS_[A-Z0-9_]+',text)))))
    result = dict(complete=True,formal=False,source_run='957127',
        source_record_sha256=digest(RUN/'diagnostic-result.json'),
        unit_policy='Raw SDK units retained; trace durations are microseconds. Counter kernel time is rounded and instrumented.',
        pmc=counters,plans=plan_notes)
    OUT.mkdir(exist_ok=True)
    (OUT/'counter-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=True,counter_processes=len(counters),plan_records=len(plan_notes),
        output=str(OUT/'counter-summary.json'),bytes=(OUT/'counter-summary.json').stat().st_size),indent=2))


if __name__ == '__main__':
    main()
