"""Audit the measured prefix of a failed run without accepting an incomplete formal matrix."""
import csv
import json
from pathlib import Path
import statistics
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path[:0]=[str(ROOT),str(ROOT/'tools/fft_measurement'),str(ROOT/'experiments/EXP-128/scripts')]
import cufft261012_contract as contract
from tools.workspace_manager import manager as mgr,revalidate
from analyze_cc_rows_results import order_effect,summarize

RUN=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-boundary-v5-performance-20261027'
RECORD=ROOT/'experiments/EXP-128/records/boundary-v5-20261027'
OUT=RECORD/'inspection-983952'


def read(p):return json.loads(p.read_text())
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def csv_file(name,rows):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    m=contract.manifest(RUN/'preregistration.json');p=read(RUN/'provenance.json')
    arms=contract.arms(m);expected=contract.schedule(m);entries=read(RUN/'processes.json')
    assert arms==('baseline','previous','unfused_cc','candidate')
    assert p['complete'] is False and p['policy']==contract.POLICY and p['source_sha256']==contract.SOURCE_SHA
    assert p['source_files_sha256']==contract.SOURCE_FILES and p['timing_origin_sha256']==contract.ORIGIN_SHA
    assert p['event_iterations']==30 and p['timing_warmups']==10
    assert p['job_id']=='983952' and p['gpu']['count']==1 and p['gpu']['arch'].split(':')[0]=='gfx936'
    assert set(p['arms'])==set(arms)
    for arm in arms:
        assert p['arms'][arm]['library_sha256']==m['arms'][arm]['library_sha256']
        assert p['arms'][arm]['source_commit']==m['arms'][arm]['source_commit']
        assert mgr.common.sha(mgr.inside(p['arms'][arm]['actual_library']))==m['arms'][arm]['library_sha256']
    accepts={}
    for arm,prefix,job,count in [('candidate','boundary-v5','983949',60),('unfused_cc','unfused-cc','983951',24)]:
        vp=ROOT/'experiments/EXP-128/runs'/('EXP-128-cc-local-'+prefix+'-validate-20261027')
        cfg=mgr.load(vp/'submit-manifest.json');built,lib,command,filename=revalidate.existing(cfg)
        accepted=revalidate.verify_acceptance(mgr.locations(cfg,'validate'),built,command,filename,job)
        assert accepted==m['validation_acceptances'][arm]
        evidence=read(vp/filename)
        assert evidence['complete'] and not evidence['failures']
        assert len(evidence['numerical'])==len(evidence['dispatch'])==count
        assert all(x['check']['check']=='PASS' for x in evidence['numerical'])
        accepts[arm]=dict(acceptance=accepted,cases=count,seconds=evidence['elapsed_seconds'])
    values={};checks=[];failures=[];seen=set()
    assert 0<len(entries)<len(expected)
    for e,item in zip(entries,expected):
        assert all(e.get(k)==v for k,v in item.items())
        assert e['gpu']==p['gpu'] and e['host']==p['host'] and e['job_id']==p['job_id']
        assert e['library_sha256']==m['arms'][item['arm']]['library_sha256']
        for key in ('csv','samples','correctness','stdout','stderr'):
            path=(RUN/e[key]).resolve();assert RUN in path.parents and path not in seen;seen.add(path)
            if path.exists():assert mgr.common.sha(path)==e[key+'_sha256']
            else:assert e['returncode']!=0 and key in ('csv','samples','correctness')
        if e['returncode']:
            failures.append(dict(index=e['index'],N=e['N'],type=e['func'].removesuffix('_1d'),arm=e['arm'],
                returncode=e['returncode'],stderr=(RUN/e['stderr']).read_text(),stage='plan creation',
                source_location='tools/fft_measurement/rocfft_measurement_support_v3.h:134-141'))
            continue
        rows=contract.read_rows(RUN/e['csv']);assert len(rows)==1
        check=contract.read_check(RUN/e['correctness'])
        v=contract.validate_process(rows[0],contract.read_samples(RUN/e['samples']),check,item['N'],item['func'],30)
        key=(item['N'],item['func'],item['arm']);assert key not in values;values[key]=v
        checks.append(dict(index=e['index'],arm=e['arm'],**check))
    assert len(failures)==1 and failures[0]['index']==entries[-1]['index']
    coverage=read(ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json')
    geometry={x['N']:x for x in coverage['public']}
    a100=contract.reference(m);full=[];exported=[];missing=[]
    for n,func in mgr.common.cases(m):
        present=[a for a in arms if (n,func,a) in values]
        if len(present)!=len(arms):
            missing.append(dict(N=n,type=func.removesuffix('_1d'),present=present,
                missing=[a for a in arms if a not in present]));continue
        row=dict(N=n,type=func.removesuffix('_1d'),C=geometry[n]['C'],Q=geometry[n]['Q'],
            power_of_two=n&(n-1)==0)
        effects={}
        for arm in arms:
            v=values[n,func,arm];stats=contract.statistics_for(v)
            for stat in ('median','p25','p75'):row[arm+('_us' if stat=='median' else '_'+stat+'_us')]=stats[stat+'_ms']*1000
            effects[arm]=order_effect(v)
        for ref in arms[:-1]:
            row['speedup_'+ref]=row[ref+'_us']/row['candidate_us']
            row['overlap_'+ref]=not(row[ref+'_p25_us']>row['candidate_p75_us'] or row['candidate_p25_us']>row[ref+'_p75_us'])
            row['order_effect_'+ref]=effects[ref]['flag'] or effects['candidate']['flag']
            row['assessment_'+ref]=('差异不明确' if row['overlap_'+ref] or row['order_effect_'+ref]
                else '更快' if row['speedup_'+ref]>1 else '更慢')
        row['a100_us']=a100.get((n,func),0)*1000 or None
        row['a100_performance_percent']=100*row['a100_us']/row['candidate_us'] if row['a100_us'] else None
        full.append(row)
        exported.append(dict(row,samples_us={a:[v*1000 for v in values[n,func,a]] for a in arms},order_effect_details=effects))
    all_stats={func:{ref:summarize([x for x in full if x['type']==func],ref) for ref in arms[:-1]} for func in ('z2d','d2z')}
    audit=dict(audit_complete=True,formal=False,full_matrix_accepted=False,job_id=p['job_id'],
        run_complete=False,host=p['host'],gpu=p['gpu'],start=p['start'],end=p['end'],
        expected_processes=len(expected),attempted_processes=len(entries),successful_processes=len(values),
        successful_samples=sum(map(len,values.values())),complete_four_arm_cases=len(full),
        complete_N=len({x['N'] for x in full}),complete_four_arm_samples=len(full)*4*30,
        expected_cases=len(mgr.common.cases(m)),missing_cases=missing,failures=failures,
        max_successful_numerical_error=max(float(x['err_a']) for x in checks),validation=accepts,
        arms={a:{k:m['arms'][a][k] for k in ('install','source_commit','library_sha256')} for a in arms},
        descriptive_partial_statistics=all_stats,
        limitation='Only complete four-arm cases in the measured prefix. Failed/unmeasured cases remain missing; no full-matrix acceptance or performance claim.',
        evidence_sha256={str(f.relative_to(ROOT)):mgr.common.sha(f) for f in (RUN/'preregistration.json',RUN/'provenance.json',RUN/'processes.json')})
    write('audit.json',audit);write('valid-four-arm-cases.json',exported)
    csv_file('已完成四版组合.csv',full);csv_file('独立正确性表.csv',checks)
    for ref in arms[:-1]:
        bad=sorted([r for r in full if r['speedup_'+ref]<.95],key=lambda r:r['speedup_'+ref])
        if bad:csv_file('低于095-'+ref+'.csv',bad)
    print(json.dumps(dict(expected_cases=audit['expected_cases'],complete_cases=len(full),complete_N=audit['complete_N'],
        successful_processes=len(values),missing=missing,failures=failures,max_error=audit['max_successful_numerical_error'],
        statistics=all_stats,powers_of_two=[r for r in full if r['power_of_two']]),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
