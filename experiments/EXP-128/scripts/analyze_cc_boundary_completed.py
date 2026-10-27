"""Audit the complete 194-N matrix assembled from two explicit, non-overlapping allocations."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path[:0]=[str(ROOT),str(ROOT/'tools/fft_measurement'),str(ROOT/'experiments/EXP-128/scripts')]
import cufft261012_contract as contract
from summarize_cufft261012 import aggregate
from analyze_cc_rows_results import order_effect,summarize
from tools.workspace_manager import manager as mgr,revalidate

FIRST=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-boundary-v5-performance-20261027'
TAIL=ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-unfused-phasefix-performance-20261027'
PREFIX=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/inspection-983952'
REPAIR=ROOT/'experiments/EXP-128/records/unfused-phasefix-20261027'
OUT=ROOT/'experiments/EXP-128/records/boundary-v5-20261027/results-983952-984725'
ARMS=('baseline','previous','unfused_cc','candidate')


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def csv_file(name,rows,fields=None):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    prefix_audit=read(PREFIX/'audit.json');prefix_rows=read(PREFIX/'valid-four-arm-cases.json')
    assert prefix_audit['audit_complete'] and not prefix_audit['full_matrix_accepted']
    assert prefix_audit['complete_four_arm_cases']==len(prefix_rows)==368
    # The prefix was audited against every raw file in the preceding inspection.
    # Verify that audit and exported samples still match their committed evidence.
    prior_commit='41d089bda2a138dc8fbfc74a8c876ce6e88197ed'
    for file in (PREFIX/'audit.json',PREFIX/'valid-four-arm-cases.json'):
        blob=subprocess.check_output(['git','show',prior_commit+':'+str(file.relative_to(ROOT))],cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest()==sha(file)
    for relative,digest in prefix_audit['evidence_sha256'].items():assert sha(ROOT/relative)==digest
    original=contract.manifest(FIRST/'preregistration.json')
    first_prov=read(FIRST/'provenance.json');assert first_prov['complete'] is False
    m,p,tail_rows,samples=aggregate(TAIL)
    assert tail_rows==read(TAIL/'summary.json')['rows']
    assert len(tail_rows)==20 and len(samples)==80 and sum(map(len,samples.values()))==2400
    assert contract.arms(m)==contract.arms(original)==ARMS
    assert m['a100_reference']==original['a100_reference']
    for arm in ('baseline','previous','candidate'):assert m['arms'][arm]==original['arms'][arm]
    assert p['job_id']=='984725'
    repair=read(REPAIR/'phase-selector-model.json')
    assert repair['complete'] and repair['original_368_cases_unchanged']
    repaired={x['N'] for x in repair['affected']}
    assert not repaired&{r['N'] for r in prefix_rows}
    catalog={x['N']:x for x in repair['catalog']}
    validation={}
    for arm,prefix,job,count in [('candidate','boundary-v5-tail','984724',6),
                                ('unfused_cc','unfused-phasefix','984723',40)]:
        folder=ROOT/'experiments/EXP-128/runs'/('EXP-128-cc-local-'+prefix+'-validate-20261027')
        cfg=mgr.load(folder/'submit-manifest.json');built,lib,cmd,name=revalidate.existing(cfg)
        acceptance=revalidate.verify_acceptance(mgr.locations(cfg,'validate'),built,cmd,name,job)
        assert acceptance==m['validation_acceptances'][arm]
        evidence=read(folder/name)
        assert evidence['complete'] and not evidence['failures']
        assert len(evidence['numerical'])==len(evidence['dispatch'])==count
        assert all(x['check']['check']=='PASS' for x in evidence['numerical'])
        for d in evidence['dispatch']:
            if arm=='candidate':
                roles=(4,5) if d['func']=='z2d_1d' else (6,7)
                assert len(d['actual_names'])==2
                assert all('_cc_local_v5_role%d_C%d_Q%d_'%(role,d['C'],d['Q']) in name
                           for role,name in zip(roles,d['actual_names']))
            else:
                assert len(d['actual_names'])==3
                assert (d['column_phase']['base'],d['column_phase']['steps'])==(catalog[d['N']]['base'],catalog[d['N']]['steps'])
                if d['N'] in repaired:assert d['column_phase']['original_selection_failed'] and d['column_phase']['base']==8 and d['column_phase']['steps']==3
        validation[arm]=dict(acceptance=acceptance,cases=count,seconds=evidence['elapsed_seconds'])
    coverage=read(ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json')
    geometry={x['N']:x for x in coverage['public']}
    matrix=[line.split() for line in (ROOT/'experiments/EXP-128/artifacts/preflight/unified-20261021/native-matrix.txt').read_text().splitlines()]
    native={(int(f[1]),int(f[2])):f for f in matrix}
    tail_export=[]
    for old in tail_rows:
        n,func=old['N'],old['func'];c,q=geometry[n]['C'],geometry[n]['Q']
        row=dict(N=n,type=func.removesuffix('_1d'),C=c,Q=q,power_of_two=n&(n-1)==0)
        effects={}
        for arm in ARMS:
            for stat in ('median','p25','p75'):row[arm+('_us' if stat=='median' else '_'+stat+'_us')]=old[arm+'_'+stat+'_ms']*1000
            effects[arm]=order_effect(samples[n,func,arm])
        for ref in ARMS[:-1]:
            row['speedup_'+ref]=row[ref+'_us']/row['candidate_us']
            row['overlap_'+ref]=not(row[ref+'_p25_us']>row['candidate_p75_us'] or row['candidate_p25_us']>row[ref+'_p75_us'])
            row['order_effect_'+ref]=effects[ref]['flag'] or effects['candidate']['flag']
            row['assessment_'+ref]=('差异不明确' if row['overlap_'+ref] or row['order_effect_'+ref]
                                   else '更快' if row['speedup_'+ref]>1 else '更慢')
        row['a100_us']=old['a100_median_ms']*1000 if old['a100_median_ms'] is not None else None
        row['a100_performance_percent']=old['a100_performance_median_percent']
        tail_export.append(dict(row,samples_us={a:[v*1000 for v in samples[n,func,a]] for a in ARMS},order_effect_details=effects))
    key=lambda r:(r['N'],r['type'])
    prefix_keys=set(map(key,prefix_rows));tail_keys=set(map(key,tail_export))
    assert not prefix_keys&tail_keys
    assert tail_keys=={(x['N'],x['type']) for x in prefix_audit['missing_cases']}
    assert prefix_keys|tail_keys=={(n,func.removesuffix('_1d')) for n,func in mgr.common.cases(original)}
    exported=[];rows=[]
    for source,job,prov,manifest in [(prefix_rows,'983952',first_prov,original),(tail_export,'984725',p,m)]:
        for old in source:
            r=dict(old,measurement_job=job,host=prov['host'],gpu_uuid=prov['gpu']['uuid'],
                   unfused_library_sha256=manifest['arms']['unfused_cc']['library_sha256'])
            f=native[r['C'],r['Q']];block_rows=int(f[8])
            r['output_changed']=r['type']=='z2d' and r['C']%2==block_rows%2==r['C']%block_rows==0
            r['input_changed']=r['type']=='d2z'
            for a in ARMS:
                assert len(r['samples_us'][a])==30
                assert abs(statistics.median(r['samples_us'][a])-r[a+'_us'])<1e-10
            rows.append({k:v for k,v in r.items() if k not in ('samples_us','order_effect_details')})
            exported.append(r)
    exported.sort(key=key);rows.sort(key=key)
    assert len(rows)==388 and len({x['N'] for x in rows})==194
    assert sum(x['output_changed'] for x in rows)==60
    stats={func:{ref:summarize([r for r in rows if r['type']==func],ref) for ref in ARMS[:-1]} for func in ('z2d','d2z')}
    groups=[]
    for dimension,get in [('全部',lambda r:'all'),('列长',lambda r:r['C']),('行长',lambda r:r['Q']),
                           ('二次幂',lambda r:r['power_of_two']),('批次',lambda r:r['measurement_job']),
                           ('本轮行端改动',lambda r:r['input_changed'] or r['output_changed'])]:
        for value in sorted({get(r) for r in rows},key=str):
            for func in ('z2d','d2z'):
                selected=[r for r in rows if r['type']==func and get(r)==value]
                if not selected:continue
                for ref in ARMS[:-1]:groups.append(dict(dimension=dimension,value=value,type=func,reference=ref,**summarize(selected,ref)))
    entries=read(TAIL/'processes.json');checks=[dict(measurement_job='984725',arm=e['arm'],**contract.read_check(TAIL/e['correctness'])) for e in entries]
    old_entries=read(FIRST/'processes.json')
    # Select the complete original groups, not the two abandoned 702464 processes.
    for e in old_entries:
        if (e['N'],e['func'].removesuffix('_1d')) not in prefix_keys:continue
        assert e['returncode']==0
        check=contract.read_check(FIRST/e['correctness'])
        assert check['check']=='PASS'
        checks.append(dict(measurement_job='983952',arm=e['arm'],**check))
    assert len(checks)==1552 and all(c['check']=='PASS' and float(c['err_a'])<1e-9 for c in checks)
    segments={}
    for job,prov,manifest,count in [('983952',first_prov,original,368),('984725',p,m,20)]:
        segments[job]=dict(host=prov['host'],gpu=prov['gpu'],start=prov['start'],end=prov['end'],
            complete_cases_used=count,processes_used=count*4,source_run_complete=prov['complete'],
            arms={a:{k:manifest['arms'][a][k] for k in ('install','source_commit','library_sha256')} for a in ARMS})
    audit=dict(complete=True,full_matrix_covered=True,segmented_measurement=True,single_allocation=False,
        N=194,cases=388,processes_used=1552,samples_used=46560,timing_warmups=10,event_iterations=30,
        policy=contract.POLICY,segments=segments,validation=validation,
        max_numerical_error=max(float(c['err_a']) for c in checks),all=stats,
        output_changed={ref:summarize([r for r in rows if r['output_changed']],ref) for ref in ARMS[:-1]},
        input_changed={ref:summarize([r for r in rows if r['input_changed']],ref) for ref in ARMS[:-1]},
        repaired_N=sorted(repaired),original_failed_run_preserved=True,
        merge_policy='Exactly one four-arm group per case; ratios only within its own allocation. Original abandoned partial group retained but superseded by the complete tail group. Two OFF identities are explicit.',
        evidence_sha256={str(f.relative_to(ROOT)):sha(f) for f in (PREFIX/'audit.json',PREFIX/'valid-four-arm-cases.json',
            FIRST/'preregistration.json',FIRST/'provenance.json',FIRST/'processes.json',TAIL/'preregistration.json',
            TAIL/'provenance.json',TAIL/'processes.json',TAIL/'summary.json',REPAIR/'phase-selector-model.json')})
    write('audit-and-statistics.json',audit);write('all-samples-and-statistics.json',exported)
    csv_file('全部尺寸.csv',rows);csv_file('类型汇总.csv',groups);csv_file('独立正确性表.csv',checks)
    for ref in ARMS[:-1]:
        bad=sorted([r for r in rows if r['speedup_'+ref]<.95],key=lambda r:r['speedup_'+ref])
        csv_file('低于095-'+ref+'.csv',bad,list(rows[0]))
    with (OUT/'原始逐次样本.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['measurement_job','N','type','arm','sample_index','elapsed_us'])
        for r in exported:
            for a in ARMS:w.writerows((r['measurement_job'],r['N'],r['type'],a,i,v) for i,v in enumerate(r['samples_us'][a],1))
    print(json.dumps(dict(complete=True,N=194,cases=388,samples=46560,all=stats,output_changed=audit['output_changed'],
        repaired_N=audit['repaired_N'],powers_of_two=[r for r in rows if r['power_of_two']],max_error=audit['max_numerical_error']),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
