"""Verify v3 divisor data and register the existing standard 10/30 entry."""
import json, runpy, subprocess, sys
from pathlib import Path
ROOT=Path('/public/home/zhangkewei/zr');sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
RECORDS=ROOT/'experiments/EXP-128/records/grid-fill-20261027'
CONFIGS=ROOT/'configs/experiments'
def read(path):return json.loads(path.read_text())
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    matrix=read(RECORDS/'matrix.json');assert [len(g) for g in matrix['groups']]==[65,13,5,1]
    coverage=read(ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json')
    native={(r['C'],r['Q']) for r in coverage['geometries']};by_n={r['N']:r for r in coverage['public']};seen=set()
    for group in matrix['groups']:
        assert len(group)==len({r['N'] for r in group})
        for r in group:
            assert r['N']==2*r['C']*r['Q'] and r['N']>=65536 and (r['C'],r['Q']) in native
            assert r['N'] in by_n and r['C']!=by_n[r['N']]['C'] and (r['C'],r['Q']) not in seen
            seen.add((r['C'],r['Q']))
    assert len(seen)==84
    helper=runpy.run_path(str(ROOT/'experiments/EXP-128/scripts/build_cc_grid_v3.py'))
    output=ROOT/'experiments/EXP-128/artifacts/preflight/grid-fill-v3-table-20261027';output.mkdir(parents=True,exist_ok=True)
    (output/'cache/tmp').mkdir(parents=True,exist_ok=True)
    env=mgr.environment(output/'cache');probe=output/'probe-cc-map'
    command=[mgr.DTK+'/bin/hipcc','-O2','-std=c++17',str(ROOT/'experiments/EXP-128/scripts/probe_cc_grid_map.cpp'),'-ldl','-o',str(probe)]
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
    (output/'compile-probe.log').write_text(result.stdout+result.stderr);assert result.returncode==0
    preflight=dict(complete=False,cells=84,cases=168,processes=336,samples=10080,groups=[len(g) for g in matrix['groups']],
        production_sources_modified=False,computation_version='v3',source_freeze=False,builds=[],
        method='Verified v3 ELF copies; only source-derived read-only divisor values change.',
        probe_compile_command=command,probe_sha256=mgr.common.sha(probe))
    old=helper['BASE_INSTALL']/'lib/librocfft.so.0.1';original_table=dict(helper['source_table']());symbol=helper['map_symbol'](old.read_bytes())
    def inspect(library,expected):
        args=[str(probe),str(library),str(symbol['value']),*('%d:%d'%(m,c) for m,c in sorted(expected.items()))]
        result=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True)
        assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
        parsed=json.loads(result.stdout);assert parsed['complete'] and parsed['entries']==len(expected)
        return dict(command=args,result=parsed)
    preflight['original_runtime_table']=inspect(old,original_table)
    for index,group in enumerate(matrix['groups']):
        folder=output/('g%d'%index)
        subprocess.run([mgr.PYTHON,str(ROOT/'experiments/EXP-128/scripts/build_cc_grid_v3.py'),'--group',str(index),'--output',str(folder)],cwd=ROOT,env=env,capture_output=True,check=True)
        _,identity,expected=helper['controlled_library'](group);library=folder/'grid-install/lib/librocfft.so.0.1'
        loaded=inspect(library,expected)
        assert mgr.common.sha(library)==read(folder/'grid-build.json')['library_sha256']
        preflight['builds'].append(dict(group=index,cells=len(group),identity=identity,library_sha256=mgr.common.sha(library),runtime_table=loaded))
    wrong=dict(original_table);first=next(iter(wrong));wrong[first]+=1
    negative=subprocess.run([str(probe),str(old),str(symbol['value']),*('%d:%d'%(m,c) for m,c in sorted(wrong.items()))],cwd=ROOT,env=env,capture_output=True,text=True)
    assert negative.returncode==6 and 'divisor mismatch' in negative.stderr
    preflight['incorrect_table_rejected']=True
    old_cfg=read(ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-rowsimplify-retry1-performance-20261022/preregistration.json')
    ref=old_cfg['arms']['baseline'];assert mgr.common.sha(mgr.inside(ref['install'])/'lib/librocfft.so.0.1')==ref['library_sha256']
    inputs=['experiments/EXP-128/scripts/validate_cc_local_rows.py','experiments/EXP-128/records/grid-fill-20261027/matrix.json','experiments/EXP-128/scripts/cc_dispatch.py']
    hook=dict(script=str(ROOT/'experiments/EXP-128/scripts/validate_cc_grid_v3.py'),sha256=mgr.common.sha(ROOT/'experiments/EXP-128/scripts/validate_cc_grid_v3.py'),inputs=[dict(path=str(ROOT/p),sha256=mgr.common.sha(ROOT/p)) for p in inputs])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();written=[]
    for index,group in enumerate(matrix['groups']):
        prefix='EXP-128-cc-local-grid-g%d'%index
        (ROOT/('experiments/EXP-128/records/grid-g%d-20261027'%index)).mkdir(parents=True,exist_ok=True)
        build=dict(schema_version=1,experiment='EXP-128',run_id=prefix+'-build-20261027',
            resources=dict(partition='hx1hdnormal01',cpus=2,time_limit='00:10:00',exclude='a01r4n05'),
            build=dict(component='rocfft',build_id=prefix+'-20261027',source_repo=str(ROOT),source_commit=commit,source_dir=str(ROOT/'experiments/EXP-128/scripts/cc_grid_v3_build'),cmake=dict(CC_GRID_GROUP=str(index),GPU_TARGETS='gfx936',CMAKE_BUILD_TYPE='Release')),
            scope='Measurement-only v3 divisor data copy; executable and embedded generator bytes preserved.',base_v3_commit=helper['BASE_COMMIT'])
        build_run=ROOT/'experiments/EXP-128/runs'/build['run_id']
        validation=dict(schema_version=1,experiment='EXP-128',run_id=prefix+'-validate-20261027',gpu_arch='gfx936',resources=dict(partition='hx1hdnormal01',cpus=8,time_limit='00:30:00',node_exclusive=True,exclude='a01r4n05'),build=build['build'],post_build_validation=hook,existing_build_validation=dict(build_record=str(build_run/'build-provenance.json'),evidence_record='cc-grid-validation.json'),validation=dict(profile='cc-v3-controlled-grid-two-checks',matrix=str(RECORDS/'matrix.json'),group=index,sample_N=[r['N'] for r in group],smoke_N=[r['N'] for r in group[:2]]))
        measurement=dict(old_cfg)
        for key in ('validation_acceptance','queued_submission'):measurement.pop(key,None)
        measurement.update(run_id=prefix+'-performance-20261027',resources=dict(partition='hx1hdnormal01',cpus=8,time_limit='01:00:00',node_exclusive=True,exclude='a01r4n05'),cases=[dict(N=r['N'],func=f) for r in group for f in ('z2d_1d','d2z_1d')],arms=dict(baseline=ref,candidate=dict(build_record=str(build_run/'build-provenance.json'))),arm_labels=dict(baseline='EXP125默认计划',candidate='行端简化v3指定CC分解'),comparison_kind='version_comparison',comparison_description='Heatmap supplement: EXP125 default plan versus v3 controlled CC geometry. Only divisor data differs from verified v3. Not a default-plan or isolated-fusion comparison.',case_scope='Requested heatmap blanks, group %d; N>=65536; fixed C*Q=N/2; both real directions.'%index,acceptance='Each controlled geometry passes numerical and actual two-kernel v3 dispatch checks before timing. Preserve all 10/30 samples; exact EXP125 reference on the same exclusive GPU.',coverage_path=str(RECORDS/'matrix.json'),coverage_sha256=mgr.common.sha(RECORDS/'matrix.json'),controlled_geometry=dict(group=index,cells=group,matrix_sha256=mgr.common.sha(RECORDS/'matrix.json'),base_v3_commit=helper['BASE_COMMIT'],default_plan=False),measurement_conditions=dict(default_plan=False,baseline_default_plan=True,candidate_fixed_CC=True,double_precision=True,batch=1,out_of_place=True,dimensions=1))
        for task,cfg in [('build',build),('validate',validation),('performance',measurement)]:
            path=CONFIGS/(prefix+'-'+task+'-20261027.json')
            if task=='validate':mgr.validation_hook(cfg)
            write(path,cfg);written.append(str(path.relative_to(ROOT)))
    preflight.update(complete=True,configs=written,maximum_new_storage_bytes=1024**3)
    write(RECORDS/'host-preflight.json',preflight)
    print(json.dumps(dict(complete=True,groups=preflight['groups'],cells=84,cases=168,processes=336,samples=10080,executable_bytes_identical=True,loaded_divisor_tables_checked=5,configs=written),ensure_ascii=False))
if __name__=='__main__':main()
