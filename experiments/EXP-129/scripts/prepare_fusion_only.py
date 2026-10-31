"""Register same-source fusion ON/OFF timing; optionally submit its three dependent jobs."""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'tools/fft_measurement'), str(ROOT/'experiments/EXP-129/scripts')]
from tools.workspace_manager import manager as mgr, revalidate
import cufft261012_contract as protocol
from validate_fusion_off import validate_names

RECORD = ROOT/'experiments/EXP-129/records/fusion-only-20261031'
CONFIGS = ROOT/'configs/experiments'
OFF = 'EXP-129-fusion-off'
PAIR = 'EXP-129-fusion-only'
DATE = '20261031'
STABLE = '842b98916033e212ca9fe0e327381e6d33eb8080'
ON_RUN = ROOT/'experiments/EXP-129/runs/EXP-129-stable-scale-fix-build-20261030'
ON_VALID = ROOT/'experiments/EXP-129/runs/EXP-129-stable-scale-fix-validate-20261030'
ORIGIN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-local-v6-official-performance-20261029/preregistration.json'


def read(p):
    return json.loads(p.read_text())


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def commit(paths, message):
    args = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(['git', 'add', '--', *args], cwd=ROOT, capture_output=True, check=True)
    p = subprocess.run(['git', 'commit', '--only', '-m', message, '--', *args],
                       cwd=ROOT, capture_output=True, text=True)
    mgr.require(p.returncode == 0, p.stdout+p.stderr)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def paths():
    return [CONFIGS/(name+'.json') for name in
        (OFF+'-build-'+DATE, OFF+'-validate-'+DATE, PAIR+'-performance-'+DATE, PAIR+'-queue-'+DATE)]


def prepare():
    RECORD.mkdir(parents=True, exist_ok=True)
    bp, vp, mp, qp = paths()
    mgr.require(not any(p.exists() for p in (bp, vp, mp, qp)), 'already registered; inspect saved receipt')
    mgr.require(read(RECORD/'management-preflight.json')['returncode'] == 0, 'host management tests failed')
    free = shutil.disk_usage(ROOT).free
    mgr.require(free > 4*1024**3, 'less than 4 GiB build/storage headroom')
    cfg = read(ON_VALID/'submit-manifest.json')
    on, library, command, filename = revalidate.existing(cfg)
    acceptance = revalidate.verify_acceptance(mgr.locations(cfg, 'validate'), on, command, filename, '1004431')
    mgr.require(on['arm']['source_commit'] == STABLE and on['arm']['library_sha256'] ==
        '974f5a4f1acfd471b751849277a8a949b2c4e59466b907ea9078ee4fb65ae0b3', 'not accepted current stable ON')
    coverage = ROOT/'experiments/EXP-128/records/unified-20261021/coverage.json'
    public = read(coverage)['public']
    origin = read(ORIGIN)
    cases = origin['cases']
    ns = {x['N'] for x in public}
    mgr.require(len(public) == len(ns) == 194 and len(cases) == 388 and
        {(x['N'], x['func']) for x in cases} == {(n, f) for n in ns for f in ('z2d_1d', 'd2z_1d')},
        'image matrix differs')
    factory = Path(cfg['build']['source_dir'])/'library/src/node_factory.cpp'
    cpp = factory.read_text()
    block = cpp.split('NodeFactory::Map1DLength const NodeFactory::map1DLengthDouble = {', 1)[1].split('};', 1)[0]
    table = {int(a): int(b) for a, b in re.findall(r'^\s*\{(\d+),\s*(\d+)\}', block, re.M)}
    mgr.require('ROCFFT_CC_REAL_FUSION' not in cpp, 'CC plan unexpectedly depends on fusion switch')
    mgr.require(all(table.get(x['N']//2) == x['C'] and x['N'] == 2*x['C']*x['Q'] for x in public),
                'current default CC geometry differs from image')
    sample = [65536,65856,67200,67760,68600,70000,70304,71344,71680,72250,73008,73728,74088,
              75000,75264,76832,77760,80000,81120,82944,83006,84000,86528,90000,100000,100352,
              102400,105000,118098,129472,131072,131712,133100,138424,170368,262144,524288,
              702464,769318,913066,1048576,2097152,2725888]
    model_path = ROOT/'experiments/EXP-128/records/row-cost-reduction-20261027/mapping-model.json'
    model = {x['N']: x for x in read(model_path)['cases']}
    selected = [model[n] for n in sample]
    features = lambda x: {('C', x['C']), ('QTR', x['Q'], x['T'], x['R']),
                          ('tail', x['Q'], bool(x['C'] % x['R'])),
                          ('parity', x['C'] % 2, x['Q'] % 2)}
    required = set.union(*(features(x) for x in model.values()))
    covered = set.union(*(features(x) for x in selected))
    mgr.require(required <= covered and set(sample) <= ns, 'representative type coverage incomplete')
    for func in ('z2d_1d', 'd2z_1d'):
        fft = ['fft_len_128_dp_sbcc_test', 'fft_len_256_dp_sbrc_test']
        names = ['c2r_even_pre_test']+fft if func == 'z2d_1d' else fft+['r2c_even_post_test']
        validate_names(names, 128, 256, func)
        for bad in (names[:2], [s.replace('_len_128_', '_len_64_') for s in names]):
            try:
                validate_names(bad, 128, 256, func)
            except ValueError:
                pass
            else:
                raise ValueError('bad OFF path was accepted')
    build = read(CONFIGS/'EXP-129-stable-scale-fix-build-20261030.json')
    build.update(run_id=OFF+'-build-'+DATE, starting_stable_commit=STABLE,
                 starting_stable_tag='stable-main-exp129-cc-generic-clean-20261031',
                 acceptance='Build the accepted stable production source with only real CC fusion disabled; validate separately.',
                 reference_policy='Reuse accepted stable ON installation; no ON build or new ON validation job.')
    build['build'].update(build_id=OFF+'-'+DATE, source_commit=STABLE)
    build['build']['cmake']['ROCFFT_CC_REAL_FUSION'] = 'OFF'
    build.pop('post_build_validation', None)
    plan = mgr.build_plan(build)
    before = on['plan']['commands'][0]
    after = plan['commands'][0]
    old_flags = {s.split('=', 1)[0]: s.split('=', 1)[1] for s in before if s.startswith('-D')}
    new_flags = {s.split('=', 1)[0]: s.split('=', 1)[1] for s in after if s.startswith('-D')}
    diff = {k: [old_flags.get(k), new_flags.get(k)] for k in set(old_flags)|set(new_flags)
            if old_flags.get(k) != new_flags.get(k)}
    mgr.require(set(diff) == {'-DCMAKE_INSTALL_PREFIX', '-DROCFFT_CC_REAL_FUSION'}
                and diff['-DROCFFT_CC_REAL_FUSION'] == ['ON', 'OFF'], 'unexpected build option difference: '+str(diff))
    validate = copy.deepcopy(build)
    validate.update(run_id=OFF+'-validate-'+DATE,
        resources=dict(partition='hx1hdnormal01', cpus=8, time_limit='01:00:00',
                       node_exclusive=True, exclude='a01r4n05'),
        acceptance='Numerical correctness and actual independent pre/post plus two native CC stages only.')
    script = ROOT/'experiments/EXP-129/scripts/validate_fusion_off.py'
    inputs = [coverage, ROOT/'experiments/EXP-129/scripts/cc_dispatch.py',
              ROOT/'experiments/EXP-129/scripts/gate_validation_support.py']
    validate['post_build_validation'] = dict(script=str(script), sha256=mgr.common.sha(script),
        inputs=[dict(path=str(p), sha256=mgr.common.sha(p)) for p in inputs])
    validate['validation'] = dict(profile='fusion-off-two-checks', coverage=str(coverage),
        coverage_sha256=mgr.common.sha(coverage), sample_N=sample, smoke_N=[65536,702464],
        scope='Default OFF numerical/path representatives: every C,Q,T/R, tail and parity; old powers and historical phase-capacity failures.')
    # Validation-hook inputs are experiment-local; keep the shared historical matrix as a recorded copy.
    coverage_copy = RECORD/'coverage.json'
    shutil.copyfile(coverage, coverage_copy)
    validate['validation']['coverage'] = str(coverage_copy)
    validate['post_build_validation']['inputs'][0]['path'] = str(coverage_copy)
    validate['existing_build_validation'] = dict(build_record=str(mgr.locations(build, 'build')['run']/'build-provenance.json'),
                                               evidence_record='fusion-off-validation.json', isolated_helpers=False)
    measure = copy.deepcopy(origin)
    for key in ('queued_submission', 'revalidated_measurement', 'deferred_measurement', 'installations_sha256'):
        measure.pop(key, None)
    measure.update(experiment='EXP-129', run_id=PAIR+'-performance-'+DATE,
        resources=dict(partition='hx1hdnormal01', cpus=8, time_limit='02:00:00',
                       node_exclusive=True, exclude='a01r4n05'),
        arms=dict(previous=dict(build_record=validate['existing_build_validation']['build_record']), candidate=on['arm']),
        arm_labels=dict(previous='EXP129同源未融合', candidate='EXP129稳定融合'),
        comparison_kind='real_boundary_fusion',
        comparison_description='Same accepted EXP129 production source and native CC decomposition; only ROCFFT_CC_REAL_FUSION OFF versus ON. Complete transform events include layout, endpoint, pairing and synchronization costs.',
        validation_acceptance=acceptance, validation_acceptances=dict(candidate=acceptance),
        coverage_path=str(coverage_copy), coverage_sha256=mgr.common.sha(coverage_copy),
        case_scope='Image 194 default N, both real directions, even N>=65536 through 2725888; no supplement geometries or z2z.',
        acceptance='OFF must pass independent numerical and actual three-stage CC validation; accepted stable ON is reused. Use all original 10/30 samples and OFF/ON median ratios only.')
    measure['measurement_conditions'] = dict(precision='double', batch=1, placement='out-of-place',
        dimensions=1, load_path='default', callbacks='none', scale_factor=1.,
        reference='Same-source OFF and stable ON on one exclusive gfx936; adjacent alternating processes.',
        fusion_cost='All implementation costs needed for fusion, including any added endpoint transforms and layout/resource changes, are part of its net event time.')
    measure['source_state_policy'] = 'Record actual source/library identities; do not freeze or compare source changes during build.'
    schedule = protocol.schedule(measure)
    mgr.require(protocol.arms(measure) == ('previous','candidate') and len(schedule) == 776,
                'wrong pair or process count')
    for i in range(388):
        pair = schedule[2*i:2*i+2]
        mgr.require({p['arm'] for p in pair} == {'previous','candidate'} and
                    len({(p['N'],p['func']) for p in pair}) == 1, 'pair not adjacent')
    write(bp, build); write(vp, validate); write(mp, measure)
    proof = dict(complete=True, approved_source=STABLE, accepted_ON=on['arm'], accepted_ON_validation=acceptance,
        build_option_differences=diff, same_CC_cases=388, performance_N=194,
        performance_cases=388, processes=776, formal_samples=23280, timing_warmups=10,
        samples_per_process=30, representative_N=sample, numerical_path_checks=86,
        representative_rule='Cover all C; all Q/T/R; full/tail groups per Q; all C/Q parity; force legacy powers, maximum N and prior OFF phase failures.',
        geometry_feature_count=len(required), all_geometry_features_covered=True,
        no_ON_rebuild=True, no_new_ON_validation=True, no_source_freeze=True, free_bytes=free,
        management_tests=read(RECORD/'management-preflight.json'), stop_after_submission=True)
    write(RECORD/'host-preflight.json', proof)
    (RECORD/'方案与口径.md').write_text('''# EXP129同源融合净收益测量

复用842b9891稳定生产源码对应的融合安装；新建OFF库，仅改变ROCFFT_CC_REAL_FUSION。保留N/2算法、194个N的CC列长及行长、编译器、其余构建参数和各版默认加载路径。记录实际构建提交与最终库身份，不冻结或检查构建期间源码变化。

仅做数值和实际路径检查：OFF为独立前／后处理加两段普通CC；ON复用1004431验收。代表集43个N覆盖列长、行长／线程配置、尾组及奇偶类型，同时包含旧二次幂和三种历史相位容量失败。正式计时程序会对全部388组合、每版逐项进行窗口外数值校验。

性能两版同一独占显卡、相邻交替，每组合每版一个进程，10次预热、30次计时，共776进程、23280样本。加速比＝OFF中位数／ON中位数，使用原始计时程序；所有融合必要的布局、端点、配对、同步与资源变化计入净成本。保留全部样本、散点和顺序图，区间重叠或漂移标差异不明确。

统一入口提交纯构建→独立验证→性能队列。验证显式依赖新OFF构建成功；性能仅依赖新OFF验证成功，稳定ON验收直接复用。管理入口新增validation_arm配置，默认候选行为不变，本次previous为OFF、candidate为ON，保持正确加速比方向。提交后立即停止，不检查队列或结果、不创建定时任务。
''')
    files = [bp, vp, mp, coverage_copy, RECORD/'host-preflight.json', RECORD/'management-preflight.json',
        RECORD/'方案与口径.md', Path(__file__), script, ROOT/'tools/workspace_manager/revalidate.py',
        ROOT/'tools/workspace_manager/pending_build_validation.py',
        ROOT/'tools/workspace_manager/test_reference_only_revalidate.py']
    revision = commit(files, 'Register EXP129 same-source real fusion ON OFF measurement and reference-only validation gate')
    write(RECORD/'registration.json', dict(revision=revision, build_config=str(bp),
        validation_config=str(vp), measurement_config=str(mp), status='registered; not submitted'))
    print(json.dumps(dict(revision=revision, processes=776, formal_samples=23280, representative_N=len(sample))))


def submit():
    mgr.require(read(RECORD/'host-preflight.json')['complete'], 'preflight required')
    bp, vp, mp, qp = paths()
    receipt_file, preview_file = RECORD/'submission.json', RECORD/'submission-previews.json'
    receipts = read(receipt_file).get('receipts', {}) if receipt_file.exists() else {}
    previews = read(preview_file) if preview_file.exists() else {}

    def send(task, config, name):
        if name not in receipts:
            command = [mgr.PYTHON, str(ROOT/'manage.py'), task, '--config', str(config)]
            previews[name] = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
            if name == 'performance':
                p = previews[name]
                mgr.require(p['validation_arm'] == 'previous' and p['processes'] == 776
                            and p['event_samples'] == 23280 and p['pending_candidate'] is None,
                            'wrong performance gate preview')
                mgr.require(p['reference_arms']['candidate']['library_sha256'] ==
                    '974f5a4f1acfd471b751849277a8a949b2c4e59466b907ea9078ee4fb65ae0b3',
                    'performance candidate is not stable ON')
            write(preview_file, previews)
            receipts[name] = json.loads(subprocess.check_output(command+['--execute'], cwd=ROOT, text=True))
            write(receipt_file, dict(receipts=receipts, inspection='not performed; await user request', automation=False))
            print('SUBMITTED', name, receipts[name]['job'], flush=True)
        return receipts[name]

    built = send('build', bp, 'build')
    bj = built['job'].split(';')[0]
    if 'validation' not in receipts:
        manifest = Path(built['run'])/'submit-manifest.json'
        v = read(vp)
        v['build'] = read(manifest)['build']
        v['pending_build_validation'] = dict(build_config=str(manifest),
            build_config_sha256=mgr.common.sha(manifest), build_job_id=bj)
        v['resources']['dependency'] = 'afterok:'+bj
        write(vp, v)
        commit([vp], 'Require successful EXP129 OFF pure build before numerical and CC-path validation')
    checked = send('validate', vp, 'validation')
    vj = checked['job'].split(';')[0]
    if 'performance' not in receipts:
        m = read(mp)
        queue = dict(schema_version=1, experiment='EXP-129', run_id=PAIR+'-queue-'+DATE, gpu_arch='gfx936',
            resources=dict(m['resources'], dependency='afterok:'+vj),
            revalidated_measurement=dict(validation_arm='previous',
                validation_config=str(Path(checked['run'])/'submit-manifest.json'), validation_job_id=vj,
                measurement_config=str(mp), measurement_config_sha256=mgr.common.sha(mp)))
        write(qp, queue)
        commit([qp], 'Require only new OFF validation for same-source OFF ON timing')
    perf = send('measure', qp, 'performance')
    summary = dict(build_job=bj, validation_job=vj, performance_job=perf['job'].split(';')[0],
        measurement_run=str(ROOT/'experiments/EXP-129/runs'/(PAIR+'-performance-'+DATE)),
        sizes=194, cases=388, processes=776, formal_samples=23280, references_rebuilt=False,
        comparison='same-source OFF / ON medians', inspection='not performed; await user request', automation=False)
    write(RECORD/'submission-summary.json', summary)
    commit([bp,vp,mp,qp,receipt_file,preview_file,RECORD/'submission-summary.json',RECORD/'registration.json'],
           'Record EXP129 same-source fusion measurement submission receipts')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    if parser.parse_args().submit:
        submit()
    else:
        prepare()
