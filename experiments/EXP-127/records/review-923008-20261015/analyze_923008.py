import collections
import csv
import hashlib
import json
import re
import statistics
from pathlib import Path

WORK=Path(__file__).resolve().parent
OUT=WORK/'review-923008'
RAW=OUT/'raw'
record=json.loads((RAW/'diagnostic-result.json').read_text())
config=json.loads((RAW/'preregistration.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(p):return list(csv.DictReader(p.open(encoding='utf-8',newline='')))
def summary(values):
    q=statistics.quantiles(values,n=4,method='inclusive')
    return dict(median=statistics.median(values),q1=q[0],q3=q[2],min=min(values),max=max(values),
                first10=statistics.median(values[:10]),last10=statistics.median(values[-10:]))

assert record['complete'] and record['pmc_complete'] and not record['formal']
assert config==json.loads((RAW/'submit-manifest.json').read_text())
assert record['gpu']==config['diagnostic_program']['gpu']
validation=json.loads((RAW/'diagnostic-validation.json').read_text())
assert validation['complete'] and validation['log_sha256']==sha(RAW/'logs/diagnostic.txt')
report=dict(job='923008',formal=False,gpu=record['gpu'],checks=[],profiles=[],pmc=[])
errors=[]
for item in record['profiles']:
    folder=RAW/'profiles'/('%04d_%d_%s_%s'%(item['index'],item['N'],item['func'],item['arm']))
    for name,digest in item['files'].items():assert sha(folder/name)==digest,name
    assert item['valid']
    trace=json.loads((folder/'profile.json').read_text())['traceEvents']
    kernels=sorted([e for e in trace if e.get('cat')=='HIPOPS' and e.get('ph')=='X'],
                   key=lambda e:int(e['args']['BeginNs']))
    for e in kernels:
        assert int(e['args']['EndNs'])-int(e['args']['BeginNs'])==int(e['args']['DurationNs'])
    sums=collections.defaultdict(int)
    counts=collections.Counter()
    for e in kernels:
        counts[e['name']]+=1;sums[e['name']]+=int(e['args']['DurationNs'])
    expected=collections.defaultdict(int)
    for row in item['all_kernel_rows']:
        if row['Name']!='Total':expected[row['Name']]+=int(row['Calls'])
    assert dict(counts)==dict(expected),(folder,'summary counts')
    # Summary exporters can round/truncate subnanosecond source times by one ns.
    for name,count in expected.items():
        stated=sum(int(r['TotalDurationNs']) for r in item['all_kernel_rows'] if r['Name']==name)
        assert abs(sums[name]-stated)<=count,(name,sums[name],stated)
    transform=[e for e in kernels if re.match(r'(fft_rtc_|transpose_rtc_|c2r_even_pre|r2c_even_post)',e['name'])]
    assert len(transform)%41==0
    leaf_count=len(transform)//41
    groups=[transform[i*leaf_count:(i+1)*leaf_count] for i in range(41)]
    signature=[(e['name'],re.sub(r'f=0x[0-9a-f]+','f=FUNCTION',e['args']['args'])) for e in groups[0]]
    for g in groups:
        assert [(e['name'],re.sub(r'f=0x[0-9a-f]+','f=FUNCTION',e['args']['args'])) for e in g]==signature
        assert all(int(b['args']['BeginNs'])>=int(a['args']['EndNs']) for a,b in zip(g,g[1:]))
    if item['arm']=='candidate':
        assert leaf_count==2
        assert config['expected_boundaries'][str(item['N'])][item['func']] in [e['name'] for e in groups[0]]
        assert not any(re.search(r'(c2r_even_pre|r2c_even_post)',e['name']) for e in transform)
    api=sorted([e for e in trace if e.get('cat')=='HIP' and e.get('name')=='hipEventRecord'],
               key=lambda e:int(e['args']['index']))
    assert len(api)==80,(folder,len(api))
    # Correlation indices put each kernel launch inside its actual event pair;
    # this independently verifies correctness / warmup / measured partitioning.
    assert max(int(e['args']['index']) for e in groups[0])<int(api[0]['args']['index'])
    for i,g in enumerate(groups[1:]):
        start=int(api[2*i]['args']['index']);end=int(api[2*i+1]['args']['index'])
        assert all(start<int(e['args']['index'])<end for e in g),(folder,i)
    samples=table(folder/'harness/fft_test_1d.samples.csv')
    check=table(folder/'harness/fft_test_1d.check.csv')
    assert len(samples)==30 and len(check)==1
    assert check[0]['check']=='PASS'
    errors.append(float(check[0]['err_a']))
    sample_us=[float(s['elapsed_ms'])*1000 for s in samples]
    plan=(folder/'metadata/plan.txt').read_text()
    grids=re.findall(r'GridParams\n(.*?)End GridParams',plan,re.S)
    assert len(grids)==41 and len(set(grids))==1
    occupancies=list(map(int,re.findall(r'Kernel occupancy: (\d+)',plan.rsplit('End GridParams',1)[-1])))
    assert len(occupancies)==leaf_count,(folder,occupancies,leaf_count)
    measures=groups[11:]
    per_call_sums=[sum(int(e['args']['DurationNs']) for e in g)/1000 for g in measures]
    per_call_spans=[(int(g[-1]['args']['EndNs'])-int(g[0]['args']['BeginNs']))/1000 for g in measures]
    per_call_gaps=[span-total for span,total in zip(per_call_spans,per_call_sums)]
    leaves=[]
    for i,e in enumerate(groups[0]):
        values=[int(g[i]['args']['DurationNs'])/1000 for g in measures]
        leaves.append(dict(ordinal=i+1,name=e['name'],launch=e['args']['args'],
            occupancy_max_blocks_per_sm=occupancies[i],durations_us=values,**summary(values)))
    report['profiles'].append(dict(N=item['N'],func=item['func'],arm=item['arm'],folder=str(folder),
        leaf_count=leaf_count,transform_calls=41,measured_calls=30,correctness=check[0],
        grid=grids[0].strip().splitlines(),leaves=leaves,
        kernel_sum_us=summary(per_call_sums),kernel_span_us=summary(per_call_spans),
        inter_kernel_gap_us=summary(per_call_gaps),instrumented_event_us=summary(sample_us),
        per_call_sum_us=per_call_sums,per_call_span_us=per_call_spans,
        interpretation='All 41 transforms retained; diagnostic medians use positions 11..40 (zero based). Profiling-only; not formal performance.'))

for item in record['pmc']:
    folder=RAW/'pmc'/('%04d_%d_%s_%s'%(item['index'],item['N'],item['func'],item['arm']))
    for name,digest in item['files'].items():assert sha(folder/name)==digest,name
    text=(folder/'pmc.txt').read_text()
    chunks=re.split(r'^kernel-name:',text,flags=re.M)[1:]
    assert len(chunks)==41,(folder,len(chunks))
    metrics=[];names=[]
    for i,chunk in enumerate(chunks):
        names.append(chunk.splitlines()[0].strip('"'))
        row={}
        for line in chunk.splitlines()[1:]:
            m=re.match(r'^\s+(.+?)\s{2,}(.+?)\s*$',line)
            if m:
                key,value=m.groups();number=re.match(r'^([-+]?\d+(?:\.\d+)?)(.*)$',value)
                if number and not value.startswith('0x'):row[key]=float(number.group(1))
        assert int(row['kernel dispatch index'])==i
        metrics.append(row)
    expected=config['expected_boundaries'][str(item['N'])][item['func']]
    assert set(names)=={expected},(folder,set(names),expected)
    common=set.intersection(*(set(m) for m in metrics))
    medians={k:summary([m[k] for m in metrics[11:]]) for k in sorted(common)
             if k not in ('process id','thread id','kernel dispatch index','dispatch queue index')}
    report['pmc'].append(dict(N=item['N'],func=item['func'],kernel=expected,dispatches=41,
                               measured_dispatches=30,medians=medians,all_metrics=metrics))
report['max_profile_error']=max(errors)
all_checks=[]
for p in RAW.rglob('fft_test_1d.check.csv'):
    rows=table(p);assert len(rows)==1 and rows[0]['check']=='PASS'
    assert float(rows[0]['err_a'])<1e-9
    all_checks.append(dict(path=str(p.relative_to(RAW)),**rows[0]))
assert len(all_checks)==52
report['correctness_processes']=len(all_checks)
report['max_error_all_processes']=max(float(r['err_a']) for r in all_checks)
report['correctness_records']=all_checks
by_case=collections.defaultdict(dict)
for p in report['profiles']:by_case[(p['N'],p['func'])][p['arm']]=p
report['shared_kernel_source_checks']=[]
for (n,func),arms in by_case.items():
    blocks={}
    for arm,p in arms.items():
        text=(Path(p['folder'])/'metadata/rtc.txt').read_text()
        blocks[arm]=dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S))
    names={p['name'] for p in arms['official']['leaves']}&{p['name'] for p in arms['candidate']['leaves']}
    for name in names:
        digests={arm:hashlib.sha256(v[name].encode()).hexdigest() for arm,v in blocks.items()}
        report['shared_kernel_source_checks'].append(dict(N=n,func=func,name=name,digests=digests,
                                                            equal=len(set(digests.values()))==1))
report['checks']=['All preregistered inputs match recorded checksums','24 profile traces valid',
    '12 current cases execute exactly 2 registered fused leaves per transform',
    'Trace and CSV names/calls/durations agree','41 identical transform sequences each',
    '80 event-record calls and 30 retained samples per process','Metadata geometry repeats 41 times',
    '4 PMC targets each match the registered kernel and have 41 dispatch records']
(OUT/'verified-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
for p in report['profiles']:
    print(p['N'],p['func'],p['arm'],'leaves',p['leaf_count'],'sum',p['kernel_sum_us']['median'],
          'span',p['kernel_span_us']['median'],'gaps',p['inter_kernel_gap_us']['median'],
          'event',p['instrumented_event_us']['median'],
          'stages',[(l['median'],l['occupancy_max_blocks_per_sm']) for l in p['leaves']])
for p in report['pmc']:
    print('PMC',p['N'],p['func'],{k:v['median'] for k,v in p['medians'].items()})
print('max_error',report['max_profile_error'])
