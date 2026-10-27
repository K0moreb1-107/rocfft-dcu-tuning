"""Read completed diagnostic windows, preserving raw units and source identities."""
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path('/public/home/zhangkewei/zr')
RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-v5-regression-diagnostic-20261027'
OUT = ROOT/'experiments/EXP-128/records/v5-regression-20261027/results-985072'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stat(values):
    ordered=sorted(values)
    def quantile(p):
        at=(len(ordered)-1)*p; left=int(at)
        return ordered[left]+(ordered[min(left+1,len(ordered)-1)]-ordered[left])*(at-left)
    return dict(median=statistics.median(values),p25=quantile(.25),p75=quantile(.75),
                minimum=min(values),maximum=max(values))


def numeric(text):
    match=re.fullmatch(r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)(\([^()]*\))?',text)
    return (float(match[1]),match[2] or '') if match else None


def main():
    result=json.loads((RUN/'diagnostic-result.json').read_text())
    assert result['complete'] and not result['failures']
    OUT.mkdir(parents=True,exist_ok=True)
    summaries=[]
    totals={'shared memory operation','number of L2 cache read requests','size of L2 cache read',
            'number of L2 cache write requests','size of L2 cache write'}
    for entry in result['pmc']:
        assert entry['valid']
        path=Path(entry['folder'])/'measured-counter-windows.json'
        assert path.resolve().is_relative_to(RUN)
        raw=json.loads(path.read_text()); windows=raw['windows']; assert len(windows)==30
        names=[block['name'] for block in windows[0]]
        assert all([b['name'] for b in window]==names for window in windows)
        item={k:entry[k] for k in ('N','func','arm','mode','valid')}
        item.update(variant=entry.get('variant','original'),raw_path=str(path),raw_sha256=digest(path),
                    stages=[],summed_fields={})
        for index,name in enumerate(names):
            fields={}; keys=set(windows[0][index]['fields'])
            assert all(set(window[index]['fields'])==keys for window in windows)
            for key in sorted(keys):
                values=[numeric(window[index]['fields'][key]) for window in windows]
                if any(x is None for x in values):continue
                assert len({x[1] for x in values})==1
                fields[key]=dict(unit=values[0][1],**stat([x[0] for x in values]))
            item['stages'].append(dict(position=index,name=name,fields=fields))
        for key in sorted(totals):
            if not all(key in block['fields'] for window in windows for block in window):continue
            values=[[numeric(block['fields'][key]) for block in window] for window in windows]
            assert all(x is not None for group in values for x in group)
            assert len({x[1] for group in values for x in group})==1
            item['summed_fields'][key]=dict(unit=values[0][0][1],**stat([sum(x[0] for x in group) for group in values]))
        summaries.append(item)
    value=dict(complete=True,job_id='985072',formal=False,source_sha256=digest(RUN/'diagnostic-result.json'),
        unit_policy='SDK raw names and units retained. Stalls are percentages, not wait cycles. L2 traffic is not HBM traffic.',
        entries=summaries)
    (OUT/'pmc-summary.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    checks=[]
    for kind in ('timing','traces','pmc','interventions','anchors'):
        for entry in result[kind]:
            for key in ('check','metadata_check','profile_check'):
                if key in entry:checks.append(float(entry[key]['err_a']))
    acceptance=dict(complete=True,job_id='985072',host=result['host'],gpu=result['gpu'],
        counts={key:len(result[key]) for key in ('timing','traces','pmc','interventions','anchors','source_comparisons')},
        numerical_checks=len(checks),maximum_error=max(checks),failures=result['failures'],
        timestamp_warnings=result['timestamp_warnings'],
        all_requested_workflows_attempted=result['all_requested_workflows_attempted'],
        original_result_sha256=digest(RUN/'diagnostic-result.json'),
        counter_summary_sha256=digest(OUT/'pmc-summary.json'))
    (OUT/'evidence-acceptance.json').write_text(json.dumps(acceptance,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(acceptance,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
