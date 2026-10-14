"""Managed TRTRT correctness and default-plan evidence; never a timing driver."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/public/home/zhangkewei/zr')
ROLES = ('_real_pre_transpose_v1', '_real_post_transpose_v1',
         '_real_pre_rows_v1', '_real_post_rows_v1')
REAL_PROCESSING = ('CS_KERNEL_R_TO_CMPLX', 'CS_KERNEL_CMPLX_TO_R')
META = re.compile(r'EXP127 TRTRT boundary role=(pre|post)_(transpose|rows)_v1 '
                  r'real_N=(\d+) axis=(\d+) span=(\d+) orig_tpb=(\d+) '
                  r'paired_tpb=(\d+) scratch_bytes=(\d+)')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer_list(value):
    return tuple(int(x) for x in re.findall(r'\d+', value or ''))


def detailed_nodes(text):
    matches = list(re.finditer(r'(?m)^([ \t]*)scheme: (CS_[A-Z0-9_]+)', text))
    result = []
    fields = ('dimension', 'batch', 'length', 'direction', 'large1D', 'lengthBlue',
              'largeTwdBase', 'largeTwdSteps', 'workgroup_size', 'trans_per_block',
              'radices', 'iStrides', 'oStrides', 'iDist', 'oDist', 'outputLength')
    for i, match in enumerate(matches):
        block = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
        values = {key: next(iter(re.findall(r'(?m)^\s*'+key+r': ([^\r\n]+)', block)), None)
                  for key in fields}
        result.append(dict(scheme=match.group(2), indent=len(match.group(1)), block=block,
                           **values))
    return result


def outer_tree(text, m):
    nodes = detailed_nodes(text)
    start = next((i for i, n in enumerate(nodes)
                  if n['scheme'] == 'CS_L1D_TRTRT' and integer_list(n['length']) == (m,)), None)
    require(start is not None, 'missing outer half-length TRTRT tree')
    end = next((i for i in range(start+1, len(nodes))
                if nodes[i]['indent'] <= nodes[start]['indent']), len(nodes))
    root, descendants = nodes[start], nodes[start+1:end]
    children = [n for n in descendants if n['indent'] == root['indent']+4]
    require(children, 'outer TRTRT has no children')
    return root, descendants, children


def metadata(text):
    # A guard prints each retained plan many times. Repeated equal descriptors
    # are expected; different descriptors in one size/direction are not.
    records = {tuple(m.groups()) for m in META.finditer(text)}
    require(len(records) == 1, 'missing or inconsistent TRTRT boundary descriptor')
    side, kind, *numbers = next(iter(records))
    return dict(side=side, kind=kind, **dict(zip(
        ('N', 'axis', 'span', 'orig_tpb', 'paired_tpb', 'scratch_bytes'), map(int, numbers))))


def core_names(text):
    pattern = r'\bfft_rtc\w*_len_(\d+)_factors_([0-9_]+)_wgs_(\d+)_tpt_(\d+)\w*\b'
    records = set()
    for match in re.finditer(pattern, text):
        name = match.group(0)
        if not any(s in name for s in ('_sbrr', '_sbcc', '_sbrc', '_sbcr')):
            continue
        records.add((int(match.group(1)), integer_list(match.group(2)), int(match.group(4)),
                     '_halfLds' in name,
                     next(s for s in ('sbrr', 'sbcc', 'sbrc', 'sbcr') if '_'+s in name)))
    return sorted(records)


def default_rows_configs(source):
    # Source identity is checked against the committed build before this
    # import. The default pool table supplies TPT/half_lds when an unchanged
    # parent row kernel was precompiled and has no RTC source in the log.
    sys.path.insert(0, str(source/'library/src/device'))
    path = source/'library/src/device/kernels/configs/config_sbrr.py'
    spec = importlib.util.spec_from_file_location('frozen_default_rows_configs', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {}
    for kernel in module.sbrr_kernels:
        if not getattr(kernel, 'double_precision', True) or getattr(kernel, 'lds_size_bytes', 65536) > 65536:
            continue
        if kernel.length in result:
            continue
        half = getattr(kernel, 'half_lds', True) and len(kernel.factors) > 1
        if hasattr(kernel, 'half_lds_precision'):
            half = 'dp' in kernel.half_lds_precision
        result[kernel.length] = dict(factors=tuple(kernel.factors), TPT=kernel.threads_per_transform,
                                     half_lds=half)
    return result, {str(path): file_sha(path)}


def outer_rows(descendants, a, b):
    root_indent = min(n['indent'] for n in descendants)
    children = [n for n in descendants if n['indent'] == root_indent]
    phase = [i for i, n in enumerate(children)
             if n['scheme'] == 'CS_KERNEL_TRANSPOSE' and integer_list(n['large1D']) == (a*b,)]
    require(len(phase) == 1, 'missing unique outer T2 while locating row cores')
    left = [n for n in children[:phase[0]] if n['scheme'] != 'CS_KERNEL_TRANSPOSE']
    right = [n for n in children[phase[0]+1:] if n['scheme'] != 'CS_KERNEL_TRANSPOSE']
    require(len(left) == len(right) == 1, 'outer TRTRT row cores are ambiguous')
    return {id(left[0]): (b, a), id(right[0]): (a, b)}


def normalized_outer_row(node, span, axis):
    lengths, batch = integer_list(node['length']), integer_list(node['batch'])
    require((lengths == (span, axis) and batch == (1,))
            or (lengths == (span,) and batch == (axis,)),
            'outer row is not the registered logical span/axis')
    # Preserve row labels for pair ownership. The parent ordinary RR may fold
    # the same row axis into batch; this normalization is only for the two
    # actual outer RR children identified around T2, never recursive leaves.
    return '%d %d' % (span, axis), '1'


def computational_nodes(descendants):
    root_indent = min(n['indent'] for n in descendants)
    return [n for n in descendants if not (n['indent'] == root_indent
            and n['scheme'] == 'CS_KERNEL_TRANSPOSE' and not integer_list(n['large1D']))]


def computational_signature(descendants, a, b):
    # The first and last outer transpose may disappear through existing TR/RT.
    # T2, including its phase, remains part of this signature. All recursive
    # children and their actual fusion comments remain part of the comparison.
    row_views = outer_rows(descendants, a, b)
    keys = ('scheme', 'dimension', 'batch', 'length', 'direction', 'large1D',
            'largeTwdBase', 'largeTwdSteps', 'lengthBlue', 'radices')
    result = []
    for n in computational_nodes(descendants):
        values = dict((key, (n.get(key) or '').strip()) for key in keys)
        if id(n) in row_views and n['scheme'] == 'CS_KERNEL_STOCKHAM':
            values['length'], values['batch'] = normalized_outer_row(n, *row_views[id(n)])
        result.append(values)
    return result


def core_evidence(old_nodes, nodes, before_rtc, after_rtc, configs):
    schemes = {'CS_KERNEL_STOCKHAM': 'sbrr', 'CS_KERNEL_STOCKHAM_PP': 'sbrr',
               'CS_KERNEL_STOCKHAM_BLOCK_CC': 'sbcc', 'CS_KERNEL_STOCKHAM_PP_BLOCK_CC': 'sbcc',
               'CS_KERNEL_STOCKHAM_BLOCK_RC': 'sbrc', 'CS_KERNEL_STOCKHAM_BLOCK_CR': 'sbcr',
               'CS_KERNEL_STOCKHAM_TRANSPOSE_XY_Z': 'sbrc',
               'CS_KERNEL_STOCKHAM_TRANSPOSE_Z_XY': 'sbrc'}
    old = [n for n in computational_nodes(old_nodes) if n['scheme'] in schemes]
    new = [n for n in computational_nodes(nodes) if n['scheme'] in schemes]
    require(len(old) == len(new) and new, 'missing actual computation leaves')
    identities = set()
    rows = []
    for previous, current in zip(old, new):
        length = integer_list(current['length'])[0]
        factors = integer_list(current['radices'])
        require(factors and factors == integer_list(previous['radices'])
                and previous['scheme'] == current['scheme'], 'computation leaf changed')
        values = [integer_list(n[key]) for n in (previous, current)
                  for key in ('workgroup_size', 'trans_per_block')]
        require(all(len(x) == 1 and x[0] > 0 for x in values), 'missing actual launch geometry')
        (old_wgs,), (old_tpb,), (wgs,), (tpb,) = values
        role = META.search(current['block'])
        if role and role.group(2) == 'rows':
            info = metadata(current['block'])
            require(old_tpb == info['orig_tpb'] and tpb == info['paired_tpb'],
                    'paired slot adjustment differs from original actual kernel')
        else:
            require((old_wgs, old_tpb) == (wgs, tpb), 'unchanged core launch geometry changed')
        kind = schemes[current['scheme']]
        key = (length, factors, kind)
        identities.add(key)
        entry = dict(length=length, factors=factors, kind=kind, old_wgs=old_wgs,
                     old_tpb=old_tpb, wgs=wgs, tpb=tpb)
        if kind == 'sbrr':
            require(length in configs and configs[length]['factors'] == factors,
                    'row core differs from frozen default pool configuration')
            entry.update(configs[length], TPT_evidence='committed default pool table; actual plan radices/geometry')
            if role:
                require(wgs == tpb*entry['TPT'] and old_wgs >= old_tpb*entry['TPT'],
                        'paired workgroup does not retain default core TPT')
        rows.append(entry)
    # Filter out callback helper FFTs outside the half-length computation.
    # Static dimension, stride and placement affect I/O specialization, not
    # this core identity. A new Rows source must not require an old AOT source.
    visible = []
    for text in (before_rtc, after_rtc):
        records = [x for x in core_names(text) if (x[0], x[1], x[4]) in identities]
        for record in records:
            if record[4] == 'sbrr':
                configured = configs[record[0]]
                require(record[1:4] == (configured['factors'], configured['TPT'], configured['half_lds']),
                        'visible RTC row factors/TPT/half_lds differ from default core')
        visible.append(records)
    old_nonrows = [x for x in visible[0] if x[4] != 'sbrr']
    new_nonrows = [x for x in visible[1] if x[4] != 'sbrr']
    require(old_nonrows == new_nonrows, 'recursive non-row RTC core configuration changed')
    return dict(leaves=rows, before_visible=visible[0], after_visible=visible[1])


def check_target_writes(nodes):
    for node in nodes:
        if not node['scheme'].startswith('CS_KERNEL_'):
            continue
        outputs = re.findall(r'(?m)^\s*OB_[A-Z_]+\s*->\s*(OB_[A-Z_]+)', node['block'])
        require(len(outputs) == 1 and outputs[0] != 'OB_USER_IN',
                'new real target computation writes user input')


def fusion_marks(descendants, a, b):
    marks = []
    root_indent = min(n['indent'] for n in descendants)
    row_views = outer_rows(descendants, a, b)
    for n in descendants:
        for side in ('TR', 'RT'):
            if side+'FuseShim: fused ' in n['block']:
                logical_length = integer_list(n['length'])
                if id(n) in row_views and n['scheme'] == 'CS_KERNEL_STOCKHAM':
                    logical_length = integer_list(normalized_outer_row(n, *row_views[id(n)])[0])
                marks.append((n['indent']-root_indent, side, n['scheme'], logical_length))
    return marks


def check_trtrt(before, after, before_rtc, after_rtc, row, direction, configs):
    n, a, b = row['N'], row['A'], row['B']
    m = n//2
    _, old_nodes, old_children = outer_tree(before, m)
    _, nodes, children = outer_tree(after, m)
    info = metadata(after)
    side = 'pre' if direction == 'z2d' else 'post'
    axis, span = (a, b) if side == 'pre' else (b, a)
    require(info['N'] == n and (info['side'], info['axis'], info['span']) == (side, axis, span),
            'wrong real boundary view')
    tr = any('TRFuseShim: fused ' in x['block'] for x in children)
    rt = any('RTFuseShim: fused ' in x['block'] for x in children)
    recursive = any(x['scheme'] not in ('CS_KERNEL_TRANSPOSE', 'CS_KERNEL_STOCKHAM') for x in children)
    actual_family = 'TRTRT-recursive-R1' if recursive else 'TRTRT-TR%d-RT%d' % (tr, rt)
    require(actual_family == row['group'], 'actual candidate family differs from preregistration: '+actual_family)
    require(tr == row['TR_scheme_predicate'] and rt == row['RT_scheme_predicate'],
            'eligible outer TR/RT was lost or resource classification changed')
    expected_kind = 'rows' if (tr if side == 'pre' else rt) else 'transpose'
    require(info['kind'] == expected_kind, 'wrong boundary backend for actual outer fusion')
    phase_nodes = [x for x in children if x['scheme'] == 'CS_KERNEL_TRANSPOSE' and integer_list(x['large1D']) == (m,)]
    require(len(phase_nodes) == 1, 'outer T2 phase transpose was removed or changed')
    require(computational_signature(old_nodes, a, b) == computational_signature(nodes, a, b),
            'core decomposition, factors, phase, or recursive path changed')
    old_marks, marks = fusion_marks(old_nodes, a, b), fusion_marks(nodes, a, b)
    require(all(marks.count(x) >= old_marks.count(x) for x in set(old_marks)),
            'an existing outer or recursive fusion was removed')
    cores = core_evidence(old_nodes, nodes, before_rtc, after_rtc, configs)
    check_target_writes(nodes)
    role = '_real_'+side+'_'+expected_kind+'_v1'
    names = sorted({x for x in re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', after_rtc) if role in x})
    require(names and role in after, 'new boundary was not compiled with its registered identity')
    active = [x for x in children if META.search(x['block'])]
    require(len(active) == 1 and active[0] is (children[0] if side == 'pre' else children[-1]),
            'real boundary leaked into a recursive child or wrong outer leaf')
    if expected_kind == 'transpose':
        require(info['orig_tpb'] == info['paired_tpb'] == 0 and info['scratch_bytes'] == 33792,
                'wrong paired-transpose resource registration')
        require(active[0]['scheme'] == 'CS_KERNEL_TRANSPOSE' and not integer_list(active[0]['large1D']),
                'boundary transpose has a cross-stage phase')
    else:
        original, paired = info['orig_tpb'], info['paired_tpb']
        require(original >= 4 and paired == original-original%2 and paired >= 4,
                'unregistered odd-slot reduction')
        require(info['scratch_bytes'] == 16*paired*(span+1), 'wrong full complex exchange capacity')
        require(integer_list(active[0]['trans_per_block']) == (paired,), 'launch slot count disagrees with descriptor')
        matching = core_names('\n'.join(names))
        require(len(matching) == 1 and matching[0][0] == span and matching[0][4] == 'sbrr',
                'ambiguous or wrong compiled boundary core')
        configured = configs[span]
        require(matching[0][1:4] == (configured['factors'], configured['TPT'], configured['half_lds']),
                'compiled boundary core differs from frozen default core')
        require(integer_list(active[0]['workgroup_size']) == (paired*configured['TPT'],),
                'launch workgroup differs from exact paired kernel key')
    return dict(actual_group=actual_family, metadata=info, before_actual_fusions=old_marks,
                after_actual_fusions=marks, core_configuration=cores, kernel_names=names)


def check_fallback(before, after, row):
    n, a, b = row['N'], row['A'], row['B']
    _, old, _ = outer_tree(before, n//2)
    _, new, children = outer_tree(after, n//2)
    require(not any(role in after for role in ROLES) and not META.search(after),
            'capacity fallback has an active new boundary')
    pre = row['direction'] == 'z2d'
    real_processing = 'CS_KERNEL_CMPLX_TO_R' if pre else 'CS_KERNEL_R_TO_CMPLX'
    fused_side = 'TR' if pre else 'RT'
    span, axis = (b, a) if pre else (a, b)
    require(real_processing in after, 'capacity fallback lost ordinary real processing')
    require(computational_signature(old, a, b) == computational_signature(new, a, b),
            'capacity fallback changed computation or phase')
    old_marks, marks = fusion_marks(old, a, b), fusion_marks(new, a, b)
    require(old_marks == marks and any(fused_side+'FuseShim: fused ' in x['block'] for x in children),
            'capacity fallback lost existing '+fused_side+' fusion')
    selected = children[0] if pre else children[-1]
    require(selected['scheme'] == 'CS_KERNEL_STOCKHAM', 'capacity fallback selected a different boundary kind')
    normalized_outer_row(selected, span, axis)
    require(span == 1024 and integer_list(selected['trans_per_block']) == (4,)
            and integer_list(selected['workgroup_size']) == (256,)
            and integer_list(selected['radices']) == (16, 16, 4),
            'capacity fallback did not exercise the registered 1024 core')
    require(row['required_scratch_bytes'] == 16*4*(span+1) > row['shared_limit_bytes'],
            'capacity fallback registration does not exceed the shared limit')
    return dict(actual_group='TRTRT-capacity-fallback', required_scratch_bytes=row['required_scratch_bytes'],
                actual_fusions=marks, ordinary_real_processing=real_processing)


def check_guard_output(case, refs, role=None):
    stdout = (case/'stdout.txt').read_text()
    count = len(refs)
    require(stdout.count('REAL_BOUNDARY_GUARD_PASS') == count
            and 'REAL_BOUNDARY_ALL_PASS cases=%d' % count in stdout, 'incomplete independent reference matrix')
    profile = (case/'profile.txt').read_text()
    schemes = re.findall(r'CS_KERNEL_[A-Z0-9_]+', profile)
    require(not any(s.startswith(REAL_PROCESSING) for s in schemes), 'independent real pre/postprocessing executed')
    if role:
        rtc = (case/'rtc.txt').read_text()
        require(role in rtc, 'compiled boundary identity missing')
        require(len(schemes) and len(schemes) % (2*count) == 0, 'inconsistent executed transform kernel count')
    return {p: file_sha(case/p) for p in ('stdout.txt', 'stderr.txt', 'plan.txt', 'rtc.txt', 'profile.txt')}


def file_sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    sys.path.insert(0, str(ROOT))
    from tools.workspace_manager import manager as mgr
    old_path = ROOT/'experiments/EXP-127/scripts/validate_bluestein_boundary.py'
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'build-record', 'run', 'build', 'cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    cfg = mgr.load(args.config)
    built = json.loads(mgr.inside(args.build_record).read_text())
    require(built['complete'] and built['arm']['source_commit'] == cfg['build']['source_commit'], 'build identity mismatch')
    require(mgr.source_identity(cfg) == built['plan']['source_identity'], 'source changed')
    mgr.validation_hook(cfg)
    coverage = json.loads(mgr.inside(cfg['validation']['coverage']).read_text())
    require(len(coverage['sizes']) == 25 and len(coverage['families']) == 5, 'incomplete TRTRT registration')
    require(file_sha(old_path) == coverage['frozen_helpers'][str(old_path.relative_to(ROOT))], 'frozen reference driver changed')
    spec = importlib.util.spec_from_file_location('frozen_blue_validation', old_path)
    blue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(blue)
    run = mgr.inside(args.run)
    build = mgr.inside(args.build)/'validation'
    build.mkdir()
    scratch = mgr.inside(args.cache)/'reference'
    scratch.mkdir()
    env = mgr.environment(mgr.inside(args.cache))
    install = mgr.inside(built['arm']['install'])
    lib = install/'lib/librocfft.so.0.1'
    digest = built['arm']['library_sha256']
    env.update(LD_PRELOAD=str(lib), LD_LIBRARY_PATH=str(install/'lib')+':'+env['LD_LIBRARY_PATH'])
    source = ROOT/'rocm-libraries-rocm-7.2.2/projects/rocfft'
    configs, config_sources = default_rows_configs(source)
    require(mgr.inside(cfg['validation']['guard_source']) == ROOT/'experiments/EXP-127/scripts/real_boundary_guard.cpp',
            'reference guard differs from frozen helper')
    identity, frozen, guard = (build/name for name in ('device_identity', 'fft_test_1d', 'real_boundary_guard'))
    require(file_sha(ROOT/'tools/fft_measurement/fft_test_1d.cpp') == mgr.common.SOURCE_SHA, 'frozen quick tool changed')
    for name, sha in coverage['frozen_helpers'].items():
        require(file_sha(ROOT/name) == sha, 'frozen helper changed: '+name)
    commands = [
        [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++17', ROOT/'tools/fft_measurement/device_identity.cpp', '-o', identity],
        [mgr.DTK+'/bin/hipcc', '-O3', '-std=c++17', ROOT/'tools/fft_measurement/fft_test_1d.cpp',
         '-I'+str(install/'include'), '-L'+str(install/'lib'), '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-o', frozen],
        [mgr.DTK+'/bin/hipcc', '-O2', '-std=c++17', '--offload-arch=gfx936', cfg['validation']['guard_source'],
         '-I'+str(install/'include'), '-I'+str(source/'shared'), '-L'+str(install/'lib'),
         '-Wl,-rpath,'+str(install/'lib'), '-lrocfft', '-o', guard]]
    # The manager writes ordinary JSON without a custom Path serializer.
    commands = [list(map(str, command)) for command in commands]
    for i, command in enumerate(commands):
        with (run/'logs'/('tr-validate-compile-%d.txt' % i)).open('xb') as out:
            subprocess.run(list(map(str, command)), env=env, stdout=out, stderr=subprocess.STDOUT, check=True)
    gpu = json.loads(subprocess.check_output([str(identity)], env=env, text=True))
    require(gpu['count'] == 1 and gpu['arch'].split(':')[0] == 'gfx936', 'wrong GPU profile')
    require(re.fullmatch('[0-9a-f]{32}', gpu['uuid']) and int(gpu['uuid'], 16), 'wrong GPU UUID')
    binaries = {str(p): file_sha(p) for p in (identity, frozen, guard)}
    for binary in (frozen, guard):
        linked = subprocess.check_output(['ldd', str(binary)], env=env, text=True)
        loaded = [mgr.inside(line.strip().split('=>')[-1].strip().split(' ')[0])
                  for line in linked.splitlines() if 'librocfft.so' in line]
        require('not found' not in linked and len(set(loaded)) == 1 and loaded[0] == lib, 'wrong candidate linkage')
        (run/'logs'/(binary.name+'-ldd.txt')).write_text(linked)
    previous = coverage['previous_arm']
    require(previous == cfg['validation']['matched_previous'], 'matched parent identity differs from preregistration')
    previous_lib = mgr.inside(previous['install'])/'lib/librocfft.so.0.1'
    require(file_sha(previous_lib) == previous['library_sha256'], 'previous library changed')
    previous_build = json.loads(mgr.inside(previous['build_provenance']).read_text())
    require(previous_build['complete'] and previous_build['arm'] == previous,
            'previous six-field identity differs from original build provenance')
    previous_env = dict(env, LD_PRELOAD=str(previous_lib),
                        LD_LIBRARY_PATH=str(previous_lib.parent)+':'+env['LD_LIBRARY_PATH'])
    previous_cache = mgr.inside(args.cache)/'previous-rtc'
    previous_cache.mkdir()
    previous_env.update(mgr.environment(previous_cache))
    previous_env.update(LD_PRELOAD=str(previous_lib), LD_LIBRARY_PATH=str(previous_lib.parent)+':'+env['LD_LIBRARY_PATH'])
    record = dict(complete=False, formal=False, job_id=os.environ['SLURM_JOB_ID'], gpu=gpu,
        allocation=mgr.common.single_gpu_allocation(os.environ), source_commit=built['arm']['source_commit'],
        library_sha256=digest, matched_previous=previous, binaries=binaries, compile_commands=commands,
        default_rows_configuration_sources=config_sources, numpy_version=blue.np.__version__,
        default_path_only=True, quick_checks=[], matched_plans=[], guard_groups=[], blue_guard_groups=[],
        complex_guard_groups=[], scope_checks=[], fallback_plan_checks=[], fallback_scope_checks=[],
        failures=[], families={},
        reference='Frozen full-length NumPy recipe, binary hashes, seven patterns and two scales',
        start=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def audit():
        require(file_sha(lib) == digest and file_sha(previous_lib) == previous['library_sha256'], 'library changed')
        require(all(file_sha(p) == sha for p, sha in binaries.items()), 'validator binary changed')
        require(all(file_sha(p) == sha for p, sha in config_sources.items()), 'default core configuration changed')
        require(json.loads(subprocess.check_output([str(identity)], env=env, text=True)) == gpu, 'device changed')

    def logged_env(case, base=env, layer='45'):
        return dict(base, ROCFFT_LAYER=layer, ROCFFT_LOG_TRACE_PATH=str(case/'trace.txt'),
            ROCFFT_LOG_PLAN_PATH=str(case/'plan.txt'), ROCFFT_LOG_RTC_PATH=str(case/'rtc.txt'),
            ROCFFT_LOG_PROFILE_PATH=str(case/'profile.txt'), FFT_TEST_OUT=str(case))

    def plan_text(case):
        return (case/'plan.txt').read_text()+(case/'stdout.txt').read_text()

    def guarded(n, direction, kind, comparison=None):
        for callbacks in (False, True):
            audit()
            case = run/'guards'/kind/str(n)/direction/('callbacks' if callbacks else 'plain')
            reference_dir = scratch/kind/str(n)/direction/('callbacks' if callbacks else 'plain')
            reference_dir.mkdir(parents=True)
            reference_list, refs = blue.references(n, direction, callbacks, reference_dir)
            require(len(refs) == 14, 'frozen seven-pattern/two-scale reference matrix changed')
            try:
                blue.run_logged([guard, n, direction, reference_list, 'callbacks' if callbacks else 'plain'], logged_env(case), case)
                plan, rtc = plan_text(case), (case/'rtc.txt').read_text()
                details = {}
                role = None
                if kind == 'trtrt':
                    row = coverage['sizes'][str(n)]
                    details = check_trtrt(comparison[0], plan, comparison[1], rtc, row, direction, configs)
                    role = '_real_'+('pre' if direction == 'z2d' else 'post')+'_'+details['metadata']['kind']+'_v1'
                elif kind == 'blue':
                    role = '_real_pre_blue_v1' if direction == 'z2d' else '_real_post_blue_v1'
                    require(role in plan and role in rtc and not any(r in plan for r in ROLES), 'Bluestein boundary regression')
                    require(blue.convolution_signature(comparison[0]) == blue.convolution_signature(plan), 'inner Bluestein plan changed')
                    schemes = re.findall(r'CS_KERNEL_[A-Z0-9_]+', (case/'profile.txt').read_text())
                    require(all(schemes.count(s) == 2*len(refs) for s in
                                ('CS_KERNEL_PAD_MUL', 'CS_KERNEL_RES_MUL', 'CS_KERNEL_FFT_MUL')),
                            'ordinary Bluestein stages not executed')
                else:
                    require(not any(r in plan for r in ROLES), 'TRTRT boundary leaked into complex plan')
                    require('Fused chirp + padding w/ fwd FFT' in plan, 'complex fused-convolution regression absent')
                evidence = check_guard_output(case, refs, role)
                entry = dict(N=n, direction=direction, callbacks=callbacks, check='PASS',
                             references=refs, executions=2*len(refs), evidence_sha256=evidence, **details)
                record[{'trtrt': 'guard_groups', 'blue': 'blue_guard_groups', 'complex': 'complex_guard_groups'}[kind]].append(entry)
            except (subprocess.CalledProcessError, ValueError) as error:
                record['failures'].append(dict(stage='guard', kind=kind, N=n, direction=direction,
                                              callbacks=callbacks, error=str(error), evidence=str(case)))

    try:
        for item in coverage['quick_cases']:
            n, func = item['N'], item['func']
            case = run/'quick'/('%d_%s' % (n, func))
            audit()
            try:
                blue.run_logged([frozen, n, 1, func, 1], logged_env(case), case)
                rows = mgr.common.read_rows(case/'fft_test_1d.csv')
                require(len(rows) == 1, 'wrong quick row count')
                mgr.common.validate_row(rows[0], n, func)
                text = plan_text(case)
                if item['kind'] not in ('trtrt',):
                    require(not any(role in text for role in ROLES), 'TRTRT role leaked outside targets')
                if item['kind'] == 'blue':
                    role = '_real_pre_blue_v1' if func == 'z2d_1d' else '_real_post_blue_v1'
                    require(role in text, 'retained Bluestein real boundary missing')
                record['quick_checks'].append(dict(item, check='PASS', csv_sha256=file_sha(case/'fft_test_1d.csv')))
            except (subprocess.CalledProcessError, ValueError) as error:
                record['failures'].append(dict(stage='quick', case=item, error=str(error), evidence=str(case)))
        require(not record['failures'], 'quick failures; retained evidence must be reviewed')
        for kind, sizes in (('trtrt', coverage['sizes']), ('blue', coverage['blue_regression_sizes']),
                            ('fallback', coverage['fallback_sizes'])):
            for n_text in sizes:
                n = int(n_text)
                directions = (sizes[n_text]['direction'],) if kind == 'fallback' else ('d2z', 'z2d')
                for direction in directions:
                    audit()
                    before_case = run/'matched-previous'/kind/str(n)/direction
                    blue.run_logged([frozen, n, 1, direction+'_1d', 1], logged_env(before_case, previous_env), before_case)
                    previous_rows = mgr.common.read_rows(before_case/'fft_test_1d.csv')
                    require(len(previous_rows) == 1, 'wrong previous quick row count')
                    mgr.common.validate_row(previous_rows[0], n, direction+'_1d')
                    after_case = run/'quick'/('%d_%s_1d' % (n, direction))
                    before, after = plan_text(before_case), plan_text(after_case)
                    before_rtc, after_rtc = (before_case/'rtc.txt').read_text(), (after_case/'rtc.txt').read_text()
                    if kind == 'trtrt':
                        details = check_trtrt(before, after, before_rtc, after_rtc, coverage['sizes'][str(n)], direction, configs)
                    elif kind == 'fallback':
                        details = check_fallback(before, after, sizes[n_text])
                    else:
                        require(blue.convolution_signature(before) == blue.convolution_signature(after), 'inner Bluestein plan changed')
                        details = dict(inner_plan='PASS')
                    record['matched_plans'].append(dict(N=n, direction=direction, kind=kind, check='PASS',
                        before_sha256=file_sha(before_case/'plan.txt'), after_sha256=file_sha(after_case/'plan.txt'), **details))
                    if kind == 'fallback':
                        record['fallback_plan_checks'].append(record['matched_plans'][-1])
                    else:
                        guarded(n, direction, kind, (before, before_rtc))
        for n in coverage['fused_complex_controls']:
            for direction in ('cforward', 'cinverse'):
                guarded(n, direction, 'complex')
        for item in coverage['scope_cases']:
            mode, direction, n = item['mode'], item['direction'], item['N']
            case = run/'scope'/mode/(str(n) if n is not None else 'original')/direction
            audit()
            try:
                blue.run_logged([guard, 'scope', mode, direction]+([n] if n is not None else []), logged_env(case), case)
                text = plan_text(case)
                require('REAL_BOUNDARY_SCOPE_PASS' in text, 'scope validation incomplete')
                stdout = (case/'stdout.txt').read_text()
                require(('plan_only=1' if item['plan_only'] else 'plan_only=0') in stdout,
                        'scope execution/plan-only classification differs from registration')
                require(not any(role in text for role in ROLES) and not META.search(text), 'TRTRT boundary leaked outside scope')
                require('_real_pre_blue_v1' not in text and '_real_post_blue_v1' not in text, 'Bluestein role leaked outside scope')
                if mode.startswith('offset'):
                    require(not any(role in text for role in ('real IO:', 'EXP126 pair backend=',
                        'EXP125 local real', 'EXP125 real post:')), 'retained pair role leaked into offsets')
                if item.get('origin') == 'TRTRT-capacity-fallback':
                    if mode == 'small':
                        previous_case = run/'matched-previous'/'fallback'/str(n)/direction
                        check_fallback(plan_text(previous_case), text, coverage['fallback_sizes'][str(n)])
                        profile = (case/'profile.txt').read_text()
                        expected_processing = 'CS_KERNEL_CMPLX_TO_R' if direction == 'z2d' else 'CS_KERNEL_R_TO_CMPLX'
                        require(expected_processing in profile, 'capacity fallback real processing did not execute')
                    else:
                        require('SCOPE_CALLBACK_VISITS' in stdout, 'capacity fallback callback coverage missing')
                record['scope_checks'].append(dict(item, check='PASS', evidence_sha256={p: file_sha(case/p)
                    for p in ('stdout.txt', 'stderr.txt', 'plan.txt')}))
                if item.get('origin') == 'TRTRT-capacity-fallback':
                    record['fallback_scope_checks'].append(record['scope_checks'][-1])
            except (subprocess.CalledProcessError, ValueError) as error:
                record['failures'].append(dict(item, stage='scope', error=str(error), evidence=str(case)))
        require(not record['failures'], 'independent correctness, scope or actual-fusion failures')
        for family, sizes in coverage['families'].items():
            require(len(sizes) == len(set(sizes)) == 5, 'five distinct sizes per family required')
            for n in sizes:
                groups = [x for x in record['guard_groups'] if x['N'] == n]
                require(len(groups) == 4 and all(x['actual_group'] == family for x in groups), 'actual family coverage incomplete')
            record['families'][family] = dict(sizes=sizes, actual_fusion='PASS')
        expected = coverage['expected_counts']
        for name in ('quick_checks', 'matched_plans', 'guard_groups', 'blue_guard_groups', 'complex_guard_groups',
                     'scope_checks', 'fallback_plan_checks', 'fallback_scope_checks'):
            require(len(record[name]) == expected[name], 'incomplete '+name)
        groups = {'trtrt': record['guard_groups'], 'blue': record['blue_guard_groups'],
                  'complex': record['complex_guard_groups']}
        for kind, rows in groups.items():
            require(sum(len(row['references']) for row in rows) == coverage['expected_references'][kind]
                    and sum(row['executions'] for row in rows) == coverage['expected_executions'][kind],
                    'incomplete independent references/executions for '+kind)
        require(sum(row['plan_only'] for row in record['scope_checks']) == coverage['expected_scope_plan_only']
                and sum(not row['plan_only'] for row in record['scope_checks']) == coverage['expected_scope_executions'],
                'scope plan/execution coverage incomplete')
        audit()
        require(mgr.source_identity(cfg) == built['plan']['source_identity'], 'source changed during validation')
        record['complete'] = True
    finally:
        record['end'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        mgr.dumps(run/'trtrt-boundary-validation.json', record)
    print(run/'trtrt-boundary-validation.json')


if __name__ == '__main__':
    main()
