"""Audit each controlled CC cell against its original timer and actual v3 dispatch."""
import csv
import hashlib
import json
import runpy
import sys
from pathlib import Path

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools/fft_measurement'))
from summarize_cufft261012 import aggregate
from cufft261012_contract import read_check
from tools.workspace_manager import manager as mgr, revalidate

FOLDER=ROOT/'experiments/EXP-128/records/grid-fill-20261027'
OUT=FOLDER/'results'
HELPERS=runpy.run_path(str(ROOT/'experiments/EXP-128/scripts/analyze_cc_rows_results.py'))
order_effect,summarize=HELPERS['order_effect'],HELPERS['summarize']
builder=runpy.run_path(str(ROOT/'experiments/EXP-128/scripts/build_cc_grid_v3.py'))


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_csv(name,rows):
    with (OUT/name).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    state=read(FOLDER/'submission-state.json')
    matrix=read(FOLDER/'matrix.json')
    assert state['complete'] and len(state['receipts'])==12
    original_path=ROOT/'experiments/EXP-128/records/rowsimplify-retry1-20261022/results-960099/all-samples-and-statistics.json'
    assert mgr.common.sha(original_path)==matrix['original_data_sha256']
    original=read(original_path)
    assert len(original)==388
    original_keys={(row['C'],row['Q'],row['type']) for row in original}
    expected_keys={(row['C'],row['Q'],func) for group in matrix['groups'] for row in group for func in ('z2d','d2z')}
    assert len(expected_keys)==168 and not (original_keys & expected_keys)
    rows,exported,groups,checks,raw=[],[],[],[],[]
    evidence=[]
    for index,cells in enumerate(matrix['groups']):
        receipt=state['receipts']
        queue=Path(receipt['g%d-performance'%index]['run'])
        completion=read(queue/'completion.json')
        assert completion['complete']
        run=Path(completion['measurement_run'])
        manifest,provenance,reported,samples=aggregate(run)
        assert reported==read(run/'summary.json')['rows']
        assert len(reported)==2*len(cells) and len(samples)==4*len(cells)
        assert sum(map(len,samples.values()))==120*len(cells)
        assert set(provenance['arms'])=={'baseline','candidate'}
        assert provenance['job_id']==receipt['g%d-performance'%index]['job'].split(';')[0]
        assert provenance['arms']['baseline']['library_sha256']=='243849fd7f03849ce5d8378ae36324b9607f8c53e4b964e3e95dad859b86a677'
        validation=Path(receipt['g%d-validation'%index]['run'])
        cfg=mgr.load(validation/'submit-manifest.json')
        built,library,command,filename=revalidate.existing(cfg)
        acceptance=revalidate.verify_acceptance(mgr.locations(cfg,'validate'),built,command,filename,
                                                receipt['g%d-validation'%index]['job'].split(';')[0])
        assert acceptance==manifest['validation_acceptance']
        accepted=read(validation/filename)
        assert accepted['complete'] and not accepted['failures']
        assert accepted['profile']=='cc-v3-controlled-grid-two-checks'
        assert accepted['matrix_sha256']==mgr.common.sha(FOLDER/'matrix.json')
        assert accepted['gpu']['count']==1 and accepted['gpu']['arch'].split(':')[0]=='gfx936'
        assert len(accepted['numerical'])==len(accepted['dispatch'])==2*len(cells)
        by_n={cell['N']:cell for cell in cells}
        for entry in accepted['dispatch']:
            expected=by_n[entry['N']]
            assert entry['C']==expected['C'] and entry['Q']==expected['Q']
            roles=(4,5) if entry['func']=='z2d_1d' else (6,7)
            assert len(entry['actual_names'])==2
            assert all('_cc_local_v3_role%d_C%d_Q%d_'%(role,entry['C'],entry['Q']) in name
                       for role,name in zip(roles,entry['actual_names']))
            if entry['func']=='d2z_1d':
                assert entry['actual_names'][1].endswith('_reg')
        assert {(e['N'],e['func']) for e in accepted['dispatch']}=={(c['N'],f) for c in cells for f in ('z2d_1d','d2z_1d')}
        data,identity,divisors=builder['controlled_library'](cells)
        assert hashlib.sha256(data).hexdigest()==built['arm']['library_sha256']
        origin=read(Path(built['arm']['install'])/'grid-build.json')
        assert origin['all_executable_bytes_identical'] and origin['all_bytes_outside_table_identical']
        assert origin['library_sha256']==built['arm']['library_sha256']
        for entry in read(run/'processes.json'):
            check=read_check(run/entry['correctness'])
            checks.append(dict(group=index,arm=entry['arm'],**check))
        for item in reported:
            n,func=item['N'],item['func']
            geometry=by_n[n]
            row=dict(N=n,type=func.removesuffix('_1d'),C=geometry['C'],Q=geometry['Q'],group=index,
                     source_kind='controlled',source_job=provenance['job_id'],host=provenance['host'],
                     power_of_two=(n & (n-1))==0)
            effects={}
            for arm in ('baseline','candidate'):
                for stat,key in [('median','us'),('p25','p25_us'),('p75','p75_us')]:
                    row[arm+'_'+key]=1000*item[arm+'_'+stat+'_ms']
                effects[arm]=order_effect(samples[n,func,arm])
            row['speedup_baseline']=row['baseline_us']/row['candidate_us']
            row['reduction_baseline_percent']=100*(1-row['candidate_us']/row['baseline_us'])
            row['overlap_baseline']=not (row['baseline_p25_us']>row['candidate_p75_us']
                                         or row['candidate_p25_us']>row['baseline_p75_us'])
            row['order_effect_baseline']=effects['baseline']['flag'] or effects['candidate']['flag']
            row['assessment_baseline']='差异不明确' if row['overlap_baseline'] or row['order_effect_baseline'] else (
                '更快' if row['speedup_baseline']>1 else '更慢')
            rows.append(row)
            exported.append(dict(row,samples_us={arm:[v*1000 for v in samples[n,func,arm]]
                                for arm in ('baseline','candidate')},order_effect_details=effects))
            for arm in ('baseline','candidate'):
                raw.extend(dict(group=index,N=n,type=func.removesuffix('_1d'),C=geometry['C'],Q=geometry['Q'],
                                arm=arm,sample_index=i,elapsed_ms=v)
                           for i,v in enumerate(samples[n,func,arm],1))
        selected=[row for row in rows if row['group']==index]
        groups.append(dict(group=index,cells=len(cells),cases=len(reported),processes=len(samples),
            samples=sum(map(len,samples.values())),performance_job=provenance['job_id'],
            validation_job=acceptance['job_id'],host=provenance['host'],gpu=provenance['gpu'],
            validation_gpu=accepted['gpu'],first=provenance['start'],last=provenance['end'],
            validation_seconds=accepted['elapsed_seconds'],arms=provenance['arms'],
            by_direction={f:summarize([r for r in selected if r['type']==f],'baseline') for f in ('z2d','d2z')}))
        for path in [run/'preregistration.json',run/'provenance.json',run/'summary.json',run/'processes.json',
                     validation/filename,validation/'post-build-validation.json',Path(built['arm']['build_provenance'])]:
            evidence.append(dict(path=str(path),sha256=mgr.common.sha(path)))
    assert {(r['C'],r['Q'],r['type']) for r in rows}==expected_keys
    assert len(rows)==168 and len(checks)==336 and len(raw)==10080
    assert all(check['check']=='PASS' for check in checks)
    max_error=max(max(float(check['err_a']),float(check['err_b'])) for check in checks)
    assert max_error<1e-9
    combined_keys=original_keys|expected_keys
    assert len(combined_keys)==556
    assert {(c,q,f) for c in matrix['C'] for q in matrix['Q'] if 2*c*q>=65536 for f in ('z2d','d2z')}==combined_keys
    audit=dict(complete=True,new_cells=84,new_cases=168,new_processes=336,new_samples=10080,
        validation_numerical_cases=168,validation_dispatch_cases=168,max_numerical_error=max_error,
        total_cells_per_direction=278,outside_scope_cells_per_direction=283,original_cells_per_direction=194,
        original_data_sha256=mgr.common.sha(original_path),matrix_sha256=mgr.common.sha(FOLDER/'matrix.json'),
        by_direction={f:summarize([r for r in rows if r['type']==f],'baseline') for f in ('z2d','d2z')},
        groups=groups,evidence=evidence,
        interpretation='EXP125 default versus controlled v3 CC geometry, paired within each performance job; cells span different batches and GPUs. Not isolated fusion gains or one fixed-GPU decomposition ranking.')
    write('audit-and-statistics.json',audit)
    write('supplement-samples-and-statistics.json',exported)
    write_csv('补测84格双向结果.csv',rows)
    write_csv('独立正确性表.csv',checks)
    write_csv('原始逐次样本.csv',raw)
    print(json.dumps({k:audit[k] for k in ['complete','new_cells','new_cases','new_processes','new_samples',
        'validation_numerical_cases','validation_dispatch_cases','max_numerical_error','by_direction']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
