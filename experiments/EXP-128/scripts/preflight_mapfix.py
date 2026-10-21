"""Independently compile the active table and check the complete existing-build submission."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import unittest

ROOT=Path('/public/home/zhangkewei/zr')
sys.path[:0]=[str(ROOT),str(ROOT/'tools/fft_measurement'),str(Path(__file__).parent)]
from tools.workspace_manager import manager as mgr, revalidate
from audit_cc_coverage import parse_mapping, validate_coverage
from validate_cc_local import compile_internal_fixture


def main():
    cfg=mgr.load(ROOT/'configs/experiments/EXP-128-cc-local-mapfix-validate-20261021.json')
    built,library,command,filename=revalidate.existing(cfg)
    text=subprocess.check_output(['git','-C',built['arm']['source_repo'],'show',
        built['arm']['source_commit']+':rocm-libraries-rocm-7.2.2/projects/rocfft/library/src/node_factory.cpp'],text=True)
    mapping=parse_mapping(text)
    coverage=json.loads(mgr.inside(cfg['validation']['coverage']).read_text())
    audited=validate_coverage(coverage,mapping)
    # Preserve comments in this independent check: the C++ compiler decides
    # which initializers exist, rather than sharing the Python comment parser.
    match=re.search(r'NodeFactory::map1DLengthDouble\s*=\s*\{(.*?)^\s*\};',text,re.S|re.M)
    assert match is not None
    folder=ROOT/'experiments/EXP-128/artifacts/preflight/mapfix-20261021'
    folder.mkdir(parents=True,exist_ok=True)
    source=folder/'table.cpp';binary=folder/'table'
    source.write_text('#include <utility>\n#include <cstdio>\n'
        'int main(){ const std::pair<unsigned long long,unsigned long long> rows[]={\n'
        +match.group(1)+'\n}; for(auto x:rows) std::printf("%llu %llu\\n",x.first,x.second); }\n')
    compiler=shutil.which('g++')
    compile_command=([compiler,'-std=c++17','-O0',str(source),'-o',str(binary)] if compiler else
        [mgr.DTK+'/bin/hipcc','--offload-host-only','-std=c++17','-O0',str(source),'-o',str(binary)])
    compiled=subprocess.run(compile_command,text=True,capture_output=True,check=True)
    (folder/'compile.stdout').write_text(compiled.stdout)
    (folder/'compile.stderr').write_text(compiled.stderr)
    pairs=[tuple(map(int,line.split())) for line in subprocess.check_output([str(binary)],text=True).splitlines()]
    mgr.require(len(pairs)==len(mapping) and dict(pairs)==mapping,'compiler and Python table extraction differ')
    cache=folder/'cache'; cache.mkdir(exist_ok=True)
    internal=compile_internal_fixture(mgr.inside(built['plan']['paths']['build']),
        mgr.inside(cfg['build']['source_dir']),Path(__file__).with_name('cc_local_pipeline_guard.cpp'),
        folder/'internal-fixture-check',mgr.environment(cache),folder/'internal-fixture-link')
    tests=['test_coverage_audit','tools.workspace_manager.test_revalidate',
           'tools.workspace_manager.test_source_identity','tools.workspace_manager.test_validation_resume',
           'tools.workspace_manager.test_manager','test_cufft261012']
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(tests))
    preview=mgr.task_plan('validate',cfg)
    mgr.require(preview['rebuild_required'] is False and not any('--dependency' in x for x in preview['submission_command']),
                'validation unexpectedly requires a rebuild or preceding task')
    measurement=mgr.load(ROOT/'configs/experiments/EXP-128-cc-local-mapfix-performance-20261021.json')
    mgr.require(measurement['arms']['candidate']==built['arm'],'measurement library differs')
    mgr.require(measurement['cases']==coverage['cases'] and
                measurement['arms']['previous']==dict(registry_id='EXP-125-pre-memory-i'),
                'measurement coverage or reference differs')
    measurement_preview=mgr.task_plan('measure',measurement)
    record=dict(complete=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        compiled_table_matches=True,compiler_command=compile_command,compiler_entries=len(pairs),
        internal_fixture_link=internal,
        audit=audited,reused_build_job='951534',candidate=built['arm'],
        validation_preview=preview,measurement_preview=measurement_preview,
        free_disk_GiB=shutil.disk_usage(ROOT).free/2**30,
        source_state_policy='No source freeze, workspace-state comparison or FFT build.')
    path=ROOT/'experiments/EXP-128/records/coverage-mapfix-20261021/host-checks.json'
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(complete=record['complete'],tests_run=result.testsRun,compiler_entries=len(pairs),
        audit=audited,reused_build_job='951534',candidate_library_sha256=built['arm']['library_sha256'],
        validation_submission=preview['submission_command'],formal_processes=measurement_preview['processes'],
        free_disk_GiB=record['free_disk_GiB']),ensure_ascii=False,indent=2))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':
    main()
