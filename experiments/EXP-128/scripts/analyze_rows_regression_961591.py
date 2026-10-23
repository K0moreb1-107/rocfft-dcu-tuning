"""Preserve valid diagnostic evidence and the rejected trace; never relabel as formal timing."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import statistics

ROOT = Path('/public/home/zhangkewei/zr')
RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-rows-v3-regression-diagnostic-20261023'
RECORD = ROOT/'experiments/EXP-128/records/rows-v3-regression-20261023'
OUT = RECORD/'results-961591'
SKIP = {'kernel dispatch index','dispatch queue id','dispatch queue index','gpu id',
        'process id','thread id','signal handle'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    ordered = sorted(values)
    def percentile(p):
        at=(len(ordered)-1)*p; left=int(at)
        return ordered[left]+(ordered[min(left+1,len(ordered)-1)]-ordered[left])*(at-left)
    return dict(median=statistics.median(values),p25=percentile(.25),p75=percentile(.75),
                min=min(values),max=max(values))


def field_stats(values):
    parsed = [re.fullmatch(r'([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)(.*)',value)
              for value in values]
    if all(parsed) and len({match[2] for match in parsed}) == 1:
        return dict(unit=parsed[0][2],**stats([float(match[1]) for match in parsed]))
    return dict(raw_values=sorted(set(values)))


def sources(path):
    return {name:source[:-1] for name,source in re.findall(
        r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',path.read_text(),re.M|re.S)}


def main():
    record=json.loads((RUN/'diagnostic-result.json').read_text())
    select=json.loads((RECORD/'selection.json').read_text())
    host=json.loads((RECORD/'host-evidence.json').read_text())
    assert {k:len(record[k]) for k in ('timing','traces','pmc','ablations','anchors')} == dict(
        timing=162,traces=114,pmc=114,ablations=33,anchors=30)
    assert len(record['failures']) == 1
    assert record['failures'][0]['N'] == 1280000 and record['failures'][0]['stage'] == 'traces'
    assert all(x['valid'] for key in ('timing','pmc','ablations','anchors') for x in record[key])
    selected={(x['N'],x['func']):x for x in select['cases']}
    traces={(x['N'],x['func'],x['arm']):x for x in record['traces']}
    severe=[(x['N'],x['func']) for x in select['cases'] if any('24 ratios' in t for t in x['reasons'])]
    assert len(severe)==24 and all(traces[n,f,a]['valid'] for n,f in severe for a in ('previous','candidate'))
    counters=[]
    for item in record['pmc']:
        path=Path(item['folder'])/'measured-counter-windows.json'
        data=json.loads(path.read_text()); windows=data['windows']
        names=traces[item['N'],item['func'],item['arm']]['trace']['kernel_names']
        assert len(windows)==30 and all([b['name'] for b in w]==names for w in windows)
        kernels=[]
        for position,name in enumerate(names):
            keys=set(windows[0][position]['fields'])-SKIP
            assert all(keys==set(w[position]['fields'])-SKIP for w in windows)
            kernels.append(dict(position=position,name=name,fields={
                key:field_stats([w[position]['fields'][key] for w in windows]) for key in sorted(keys)}))
        counters.append(dict(N=item['N'],func=item['func'],arm=item['arm'],mode=item['mode'],
            variant=item.get('variant','original'),kernels=kernels,evidence=str(path),
            sha256=digest(path),export_type=item['export_type']))
    native={(x['N'],x['func'],x['arm']):x for x in host['kernels']}
    plans=[]; source_checks=[]; anomalies=[]
    for item in record['traces']:
        folder=Path(item['folder']); path=folder/'metadata/plan.txt'
        text=path.read_text(); grids=re.findall(r'GridParams\n(.*?)End GridParams',text,re.S)
        occupancies=list(map(int,re.findall(r'Kernel occupancy:\s*(\d+)',text)))
        assert grids and len(occupancies)>=80 and occupancies[-80:]==occupancies[-2:]*40
        plans.append(dict(N=item['N'],func=item['func'],arm=item['arm'],
            geometry=grids[-1].strip(),maximum_active_workgroups=occupancies[-2:],
            evidence=str(path),sha256=digest(path)))
        actual=sources(folder/'metadata/rtc.txt')
        if item['valid']:
            name=item['trace']['kernel_names'][1]
            generated=Path(native[item['N'],item['func'],item['arm']]['generated_source'])
            src=generated.read_text(); runtime=actual[name]
            equal=src==runtime
            source_checks.append(dict(N=item['N'],func=item['func'],arm=item['arm'],name=name,
                runtime_source_sha256=hashlib.sha256(runtime.encode()).hexdigest(),
                native_source_sha256=digest(generated),equal=equal,
                diff=[] if equal else list(difflib.unified_diff(src.splitlines(),runtime.splitlines()))[:80]))
        else:
            events=json.loads((folder/'profile/trace.json').read_text())['traceEvents']
            idx=lambda e:int(e['args']['index'])
            timers=sorted((e for e in events if e.get('cat')=='HIP' and e.get('name')=='hipEventRecord'),key=idx)
            device=sorted((e for e in events if e.get('cat')=='HIPOPS'),key=idx)
            groups=[[e for e in device if idx(a)<idx(e)<idx(b)] for a,b in zip(timers[::2],timers[1::2])]
            bad=[]
            for number,group in enumerate(groups[10:]):
                assert len(group)==2
                gap=int(group[1]['args']['BeginNs'])-int(group[0]['args']['EndNs'])
                if gap<0:
                    bad.append(dict(sample=number,gap_ns=gap,kernels=group))
            anomalies.append(dict(N=item['N'],func=item['func'],arm=item['arm'],bad_samples=bad,
                all_windows=len(groups),evidence=str(folder/'profile/trace.json')))
    # Compare the actually loaded column source, including the rejected trace's metadata.
    column_checks=[]
    for (n,f),selection in selected.items():
        old=traces[n,f,'previous']; new=traces[n,f,'candidate']
        oldsrc=sources(Path(old['folder'])/'metadata/rtc.txt')
        newsrc=sources(Path(new['folder'])/'metadata/rtc.txt')
        role=4 if f=='z2d_1d' else 6
        checks=[]
        for name,source in newsrc.items():
            if '_cc_local_v3_role%d_'%role not in name: continue
            oldname=name.replace('_cc_local_v3_','_cc_local_v2_')
            assert oldname in oldsrc
            checks.append(dict(name=name,equal=source==oldsrc[oldname].replace('_cc_local_v2_','_cc_local_v3_')))
        assert checks
        column_checks.append(dict(N=n,func=f,checks=checks,equal=all(x['equal'] for x in checks)))
    assert all(x['equal'] for x in column_checks)
    # Every completed transform, including the two incompatible export attempts, retains its exit.
    commands=[]
    for path in RUN.rglob('*-command.json'):
        if path.name=='submission-command.json': continue
        item=json.loads(path.read_text())
        if isinstance(item,dict) and 'returncode' in item:
            commands.append(dict(path=str(path),returncode=item['returncode'],command=item['command']))
    assert len(commands)==569 and all(x['returncode']==0 for x in commands)
    result=dict(complete=False,analysis_complete=True,formal=False,source_run='961591',
        source_record_sha256=digest(RUN/'diagnostic-result.json'),gpu=record['gpu'],host=record['host'],
        counts={k:len(record[k]) for k in ('timing','traces','pmc','ablations','anchors')},
        accepted_severe_cases=24,rejected_records=record['failures'],processes=commands,
        timing=record['timing'],traces=record['traces'],ablations=record['ablations'],anchors=record['anchors'],
        counters=counters,plans=plans,runtime_source_checks=source_checks,column_source_checks=column_checks,
        timestamp_anomalies=anomalies,selection=select,
        unit_policy='Raw SDK field names and units retained. Counter time is instrumented; clean timing and HIP trace stay separate.')
    OUT.mkdir(exist_ok=True)
    output=OUT/'diagnostic-evidence-summary.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(analysis_complete=True,run_complete=False,severe_valid=24,valid_traces=113,
        counters=len(counters),actual_source_equal=sum(x['equal'] for x in source_checks),
        actual_source_checked=len(source_checks),all_column_sources_equal=True,processes=len(commands),
        output=str(output),bytes=output.stat().st_size),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
