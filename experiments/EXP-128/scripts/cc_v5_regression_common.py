"""Pure selection, exact row restoration, and safe separation of profiler timestamp evidence."""
import re


def key(row):return row['N'],row.get('func',row.get('type','')+'_1d')


def select(rows):
    chosen={}
    def add(row,refs,reason):
        k=(row['N'],row['type']+'_1d')
        x=chosen.setdefault(k,dict(N=k[0],func=k[1],C=row['C'],Q=row['Q'],
            ratios={a:row['speedup_'+a] for a in ('previous','unfused_cc')},
            assessments={a:row['assessment_'+a] for a in ('previous','unfused_cc')},
            row_changed=row['input_changed'] or row['output_changed'],references=[],reasons=[]))
        for ref in refs:
            if ref not in x['references']:x['references'].append(ref)
        if reason not in x['reasons']:x['reasons'].append(reason)
    for r in rows:
        refs=[a for a in ('previous','unfused_cc') if r['speedup_'+a]<1]
        if refs:add(r,refs,'every original median ratio below one')
    controls=[]
    for ref in ('previous','unfused_cc'):
        families=sorted({(r['type'],r['Q']) for r in rows if r['speedup_'+ref]<.95
                         and (ref=='unfused_cc' or r['input_changed'] or r['output_changed'])})
        for func,q in families:
            pool=sorted([r for r in rows if r['type']==func and r['Q']==q and r['speedup_'+ref]>1.02],key=lambda r:r['N'])
            picked=[]
            for r in ([pool[0],pool[-1]] if pool else []):
                if r['N'] in [x['N'] for x in picked]:continue
                picked.append(r);reason='same-row positive control for '+ref
                add(r,[ref],reason);controls.append(dict(N=r['N'],func=func+'_1d',Q=q,reference=ref))
    cases=sorted(chosen.values(),key=lambda x:(x['N'],x['func']))
    schedule=[];detailed=[];ablations=[]
    for i,x in enumerate(cases):
        refs=sorted(x['references']);names=refs+['candidate']
        if i%2:names.reverse()
        for arm in names:schedule.append(dict(index=len(schedule),N=x['N'],func=x['func'],arm=arm))
        detail=[a for a in refs if x['ratios'][a]<.95 or 'same-row positive control for '+a in x['reasons']]
        if detail:
            for arm in detail+['candidate']:detailed.append(dict(index=len(detailed),N=x['N'],func=x['func'],arm=arm))
        if x['ratios']['previous']<.95 and x['row_changed']:
            ablations.append(dict(N=x['N'],func=x['func'],variant='restore_v4_output' if x['func']=='z2d_1d' else 'restore_v4_input',reason='all changed-row severe v4 comparisons'))
    # One positive case from each changed row family makes the intervention a type comparison.
    families={(x['func'],x['Q']) for x in cases if x['ratios']['previous']<.95 and x['row_changed']}
    for func,q in sorted(families):
        pool=[x for x in cases if x['func']==func and x['Q']==q and 'same-row positive control for previous' in x['reasons']]
        if pool:
            x=pool[0];ablations.append(dict(N=x['N'],func=func,
                variant='restore_v4_output' if func=='z2d_1d' else 'restore_v4_input',reason='matched changed-type positive control'))
    return dict(formal=False,original_below_one=dict(previous=sum(r['speedup_previous']<1 for r in rows),
        unfused_cc=sum(r['speedup_unfused_cc']<1 for r in rows)),
        original_below_095=dict(previous=sum(r['speedup_previous']<.95 for r in rows),unfused_cc=sum(r['speedup_unfused_cc']<.95 for r in rows)),
        cases=cases,controls=controls,clean_schedule=schedule,mandatory_detailed=detailed,ablations=ablations,
        adaptive_rule='Add a previously non-detailed pair if both clean repeats have ratio<0.98. This threshold schedules instrumentation; it is not a significance verdict.')


def restore_row(current,previous,variant):
    older=previous.replace('_cc_local_v4_','_cc_local_v5_')
    entry=lambda t:re.search(r'extern "C" __global__.*? void ([^(]+)\((.*?)\) \{',t,re.S).groups()
    assert entry(current)==entry(older),'row ABI or native geometry differs'
    register=lambda t:re.search(r'scalar_type R\[\d+\]',t[t.index('extern "C" __global__'):])[0]
    assert register(current)==register(older),'native register allocation differs'
    if variant=='identity':return current
    if variant=='restore_v4_input':
        start,end='// load global into registers\n','// calc the thread_in_device'
        a,b=current.index(start),current.index(end,current.index(start))
        x,y=older.index(start),older.index(end,older.index(start))
        restored=current[:a]+older[x:y]+current[b:]
    elif variant=='restore_v4_output':
        marker='// call a post-store from registers to lds (if necessary)'
        a=current.index('if(direct_store_from_reg) {',current.index(marker))
        b=older.index('if(direct_store_from_reg) {',older.index(marker))
        restored=current[:a]+older[b:]
    else:raise ValueError('unknown row intervention')
    assert restored==older,'intervention changed more than the sole v5 row region'
    return restored


def rtc_sources(text):
    # The logger adds exactly one newline outside the submitted source.
    return {name:source[:-1] for name,source in re.findall(
        r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S)}


def adaptive_pairs(selection,timings):
    by={(x['N'],x['func'],x['arm'],x['phase']):x for x in timings if x['valid']}
    out=[]
    for x in selection['cases']:
        for ref in x['references']:
            if x['ratios'][ref]<.95 or 'same-row positive control for '+ref in x['reasons']:continue
            values=[]
            for repeat in ('repeat-1','repeat-2'):
                a=by.get((x['N'],x['func'],ref,repeat));b=by.get((x['N'],x['func'],'candidate',repeat))
                if a and b:values.append(a['statistics_ms']['median_ms']/b['statistics_ms']['median_ms'])
            if len(values)==2 and max(values)<.98:out.append(dict(N=x['N'],func=x['func'],reference=ref,ratios=values))
    return out


def profile_evidence(plan,events,func):
    from cc_dispatch import inspect_dispatch
    from cc_regression_evidence import trace_evidence
    launches,checked=inspect_dispatch(plan,events,func)
    fallback=dict(kernel_names=[x['name'] for x in launches],contract=checked)
    try:return trace_evidence(plan,events,func),None
    except (AssertionError,ValueError,KeyError) as error:return fallback,str(error)
