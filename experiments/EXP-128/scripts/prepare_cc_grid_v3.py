"""Prepare four disjoint-per-N v3 divisor builds and the standard two-arm timer."""
import hashlib
import json
import runpy
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr

RECORDS=ROOT/'experiments/EXP-128/records/grid-fill-20261027'
CONFIGS=ROOT/'configs/experiments'


def read(path):
    return json.loads(path.read_text())


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def elf_sections(path):
    data=path.read_bytes()
    assert data[:6]==b'\x7fELF\x02\x01'
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    offset,size,count,names_index=header[6],header[11],header[12],header[13]
    assert size==64
    entries=[struct.unpack_from('<IIQQQQIIQQ',data,offset+index*size) for index in range(count)]
    names_entry=entries[names_index]
    names=data[names_entry[4]:names_entry[4]+names_entry[5]]
    result={}
    for entry in entries:
        name=names[entry[0]:].split(b'\0',1)[0].decode()
        if name in ('.text','.rodata'):
            result[name]=hashlib.sha256(data[entry[4]:entry[4]+entry[5]]).hexdigest()
    assert set(result)=={'.text','.rodata'}
    return result


def main():
    matrix=read(RECORDS/'matrix.json')
    assert [len(group) for group in matrix['groups']]==[65,13,5,1]
    coverage=read(ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json')
    native={(row['C'],row['Q']) for row in coverage['geometries']}
    by_n={row['N']:row for row in coverage['public']}
    seen=set()
    for group in matrix['groups']:
        assert len(group)==len({row['N'] for row in group})
        for row in group:
            assert row['N']==2*row['C']*row['Q'] and row['N']>=65536
            assert (row['C'],row['Q']) in native
            assert row['N'] in by_n and row['C']!=by_n[row['N']]['C']
            assert (row['C'],row['Q']) not in seen
            seen.add((row['C'],row['Q']))
    assert len(seen)==84
    helpers=runpy.run_path(str(ROOT/'experiments/EXP-128/scripts/build_cc_grid_v3.py'))
    helpers['export_headers']()
    headers=helpers['HEADERS']
    preflight=dict(complete=False,cells=84,cases=168,processes=336,samples=10080,
        groups=[len(group) for group in matrix['groups']],scope='N>=65536; v3 with controlled static CC divisors',
        production_sources_modified=False,computation_version='v3',source_freeze=False,builds=[])
    output=ROOT/'experiments/EXP-128/artifacts/preflight/grid-fill-v3-20261027'
    output.mkdir(parents=True,exist_ok=True)
    control=output/'v3-unchanged-control.so'
    args,cwd,objects=helpers['link_command'](helpers['BASE_BUILD']/'library/src/CMakeFiles/rocfft.dir/node_factory.cpp.o',control)
    with (output/'unchanged-control-link.log').open('wb') as log:
        subprocess.run(args,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True)
    old_sections=elf_sections(helpers['BASE_INSTALL']/'lib/librocfft.so.0.1')
    assert elf_sections(control)==old_sections, 'old computation objects do not reconstruct the verified v3 code'
    preflight['unchanged_v3_relink']=dict(text_and_rodata_match=True,sections_sha256=old_sections,
        control_library_sha256=hashlib.sha256(control.read_bytes()).hexdigest(),link_command=args)
    for index,group in enumerate(matrix['groups']):
        folder=output/('g%d'%index)
        argv=[mgr.PYTHON,str(ROOT/'experiments/EXP-128/scripts/build_cc_grid_v3.py'),
              '--group',str(index),'--output',str(folder),'--syntax-only']
        with (output/('syntax-g%d.log'%index)).open('wb') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        generated,requested=helpers['patched_source'](group)
        args,cwd,objects=helpers['link_command'](folder/'node_factory.cpp.o',folder/'unused.so')
        preflight['builds'].append(dict(group=index,syntax_check=True,changed_entries=len(requested),
            source_sha256=hashlib.sha256(generated.encode()).hexdigest(),reused_object_count=len(objects),
            reused_objects=objects,link_command=args))
    old=read(ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-rowsimplify-retry1-performance-20261022/preregistration.json')
    ref=old['arms']['baseline']
    assert mgr.common.sha(mgr.inside(ref['install'])/'lib/librocfft.so.0.1')==ref['library_sha256']
    common_inputs=['experiments/EXP-128/scripts/validate_cc_local_rows.py',
        'experiments/EXP-128/records/grid-fill-20261027/matrix.json',
        'tools/fft_measurement/cc_dispatch.py','tools/fft_measurement/cufft261012_contract.py',
        'tools/fft_measurement/sample_contract.py','tools/workspace_manager/validation_finish.py']
    hook=dict(script=str(ROOT/'experiments/EXP-128/scripts/validate_cc_grid_v3.py'),
        sha256=mgr.common.sha(ROOT/'experiments/EXP-128/scripts/validate_cc_grid_v3.py'),
        inputs=[dict(path=str(ROOT/path),sha256=mgr.common.sha(ROOT/path)) for path in common_inputs])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    written=[]
    for index,group in enumerate(matrix['groups']):
        prefix='EXP-128-cc-local-grid-g%d'%index
        series=ROOT/('experiments/EXP-128/records/grid-g%d-20261027'%index)
        series.mkdir(parents=True,exist_ok=True)
        build=dict(schema_version=1,experiment='EXP-128',run_id=prefix+'-build-20261027',
            resources=dict(partition='hx1hdnormal01',cpus=4,time_limit='00:15:00',exclude='a01r4n05'),
            build=dict(component='rocfft',build_id=prefix+'-20261027',source_repo=str(ROOT),source_commit=commit,
                source_dir=str(ROOT/'experiments/EXP-128/scripts/cc_grid_v3_build'),
                cmake=dict(CC_GRID_GROUP=str(index),GPU_TARGETS='gfx936',CMAKE_BUILD_TYPE='Release')),
            scope='Measurement-only v3 divisor relink; exact existing v3 computation objects, static table only.',
            base_v3_commit=helpers['BASE_COMMIT'])
        build_run=ROOT/'experiments/EXP-128/runs'/build['run_id']
        validation=dict(schema_version=1,experiment='EXP-128',run_id=prefix+'-validate-20261027',
            gpu_arch='gfx936',resources=dict(partition='hx1hdnormal01',cpus=8,time_limit='00:30:00',
                node_exclusive=True,exclude='a01r4n05'),build=build['build'],post_build_validation=hook,
            existing_build_validation=dict(build_record=str(build_run/'build-provenance.json'),
                evidence_record='cc-grid-validation.json'),
            validation=dict(profile='cc-v3-controlled-grid-two-checks',matrix=str(RECORDS/'matrix.json'),group=index,
                sample_N=[row['N'] for row in group],smoke_N=[row['N'] for row in group[:2]]))
        measurement=dict(old)
        for key in ('validation_acceptance','queued_submission'):
            measurement.pop(key,None)
        measurement.update(run_id=prefix+'-performance-20261027',
            resources=dict(partition='hx1hdnormal01',cpus=8,time_limit='01:00:00',node_exclusive=True,exclude='a01r4n05'),
            cases=[dict(N=row['N'],func=func) for row in group for func in ('z2d_1d','d2z_1d')],
            arms=dict(baseline=ref,candidate=dict(build_record=str(build_run/'build-provenance.json'))),
            arm_labels=dict(baseline='EXP125默认计划',candidate='行端简化v3指定CC分解'),
            comparison_kind='version_comparison',
            comparison_description='Heatmap blank-cell supplement: EXP125 default plan versus v3 controlled CC geometry. Same old v3 computation objects, only its divisor table differs. Not a default-plan or isolated-fusion comparison.',
            case_scope='Requested heatmap blank cells, group %d; N>=65536; fixed C*Q=N/2; both real directions.'%index,
            acceptance='Every controlled geometry must pass numerical and actual two-kernel v3 dispatch checks before timing. Preserve all 10/30 samples and compare exact EXP125 reference on the same exclusive GPU.',
            coverage_path=str(RECORDS/'matrix.json'),coverage_sha256=mgr.common.sha(RECORDS/'matrix.json'),
            controlled_geometry=dict(group=index,cells=group,matrix_sha256=mgr.common.sha(RECORDS/'matrix.json'),
                base_v3_commit=helpers['BASE_COMMIT'],default_plan=False),
            measurement_conditions=dict(default_plan=False,baseline_default_plan=True,candidate_fixed_CC=True,
                double_precision=True,batch=1,out_of_place=True,dimensions=1))
        for task,cfg in [('build',build),('validate',validation),('performance',measurement)]:
            path=CONFIGS/(prefix+'-'+task+'-20261027.json')
            write(path,cfg)
            written.append(str(path.relative_to(ROOT)))
    preflight.update(complete=True,configs=written,
        maximum_new_storage_bytes=1024**3,headers_bytes=sum(p.stat().st_size for p in headers.rglob('*') if p.is_file()),
        note='Four groups keep unique N per standard timer. Pairs within each job share an exclusive GPU; historical 194 cells remain separate batches.')
    write(RECORDS/'host-preflight.json',preflight)
    print(json.dumps(dict(complete=True,groups=preflight['groups'],cells=84,cases=168,processes=336,samples=10080,
                         production_sources_modified=False,configs=written),ensure_ascii=False))


if __name__=='__main__':
    main()
