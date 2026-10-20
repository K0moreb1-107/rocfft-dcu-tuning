"""Supplied 2026-10-12 timing semantics, separately versioned from v1/v2."""
import copy
import csv
import json
import math
import re
import statistics
from pathlib import Path
from common import ROOT, OFFICIAL_COMMIT, OFFICIAL_SHA, cases, inside, require, sha
from sample_contract import arms, schedule, read_samples, percentile, statistics_for

POLICY = 'FFT-event-cufft261012-single-v3'
SOURCE_NAME = 'fft_test_1d_cufft261012.cpp'
SUPPORT_NAME = 'rocfft_measurement_support_v3.h'
SOURCE_SHA = 'b28fe276cf55c917c621820da9d0686289936434edbbb8bb25c40f89d28af771'
SUPPORT_SHA = '1c6bad63705e794472606ae9a106c60878d4fcf69112af9fbe5dd51be28499d6'
ORIGIN_SHA = 'f48f52127a94e682da854cb4036ffbbaf150bd2de18753c3f0c8f426916e6f35'
SOURCE_FILES = {SOURCE_NAME: SOURCE_SHA, SUPPORT_NAME: SUPPORT_SHA}
WARMUPS = 10
EVENTS = 30
CHECK_HEADER = ['func', 'N', 'batch', 'check', 'err_a', 'err_b']
HEADER = ['func', 'N', 'is_warmup', 'warmup_times', 'test_times',
          'tmax_ms', 'tmin_ms', 'tmean_ms', 'tmedium_ms'] + ['time_%d_ms' % i for i in range(1, EVENTS + 1)]

def iterations(m):
    require(type(m.get('event_iterations', EVENTS)) is int and m.get('event_iterations', EVENTS) == EVENTS,
            'this frozen source requires exactly 30 measurements')
    return EVENTS

def validate_manifest(value):
    m = copy.deepcopy(value)
    require(m.get('policy', POLICY) == POLICY, 'wrong sample policy')
    m['policy'] = POLICY
    m['event_iterations'] = iterations(m)
    require(m.get('timing_warmups', WARMUPS) == WARMUPS, 'warmup version mismatch')
    m['timing_warmups'] = WARMUPS
    require(m.get('timing_support_sha256', SUPPORT_SHA) == SUPPORT_SHA, 'support version mismatch')
    m['timing_support_sha256'] = SUPPORT_SHA
    require(m.get('timing_source_sha256', SOURCE_SHA) == SOURCE_SHA, 'timing source version mismatch')
    m['timing_source_sha256'] = SOURCE_SHA
    require(re.fullmatch(r'EXP-\d{3,}', m.get('experiment', '')) is not None, 'explicit EXP identifier required')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', m.get('run_id', '')) is not None, 'invalid run_id')
    require(isinstance(m.get('acceptance'), str) and len(m['acceptance'].strip()) >= 10
            and 'REPLACE' not in m['acceptance'], 'preregister experiment-specific acceptance')
    require(m.get('gpu_arch') == 'gfx936', 'register another profile for other hardware')
    for arm in arms(m):
        a = m['arms'][arm]
        for field, length in (('source_commit', 40), ('library_sha256', 64)):
            require(re.fullmatch('[0-9a-f]{%d}' % length, a.get(field, '')) is not None,
                    arm + ': invalid ' + field)
        for field in ('install', 'source_repo'):
            inside(a[field])
        for field in ('source_state', 'build_provenance'):
            require(isinstance(a.get(field), str) and len(a[field].strip()) >= 10
                    and 'REPLACE' not in a[field], arm + ': explicit ' + field + ' required')
    if 'official' in m['arms']:
        a = m['arms']['official']
        require(a['source_commit'] == OFFICIAL_COMMIT and a['library_sha256'] == OFFICIAL_SHA,
                'official source/library is fixed')
    cases(m)
    return m



def manifest(path):
    return validate_manifest(json.loads(Path(path).read_text(encoding='utf-8')))

def read_rows(path, header=HEADER):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == header, 'invalid versioned CSV header: ' + str(path))
        rows = list(reader)
    require(all(set(row) == set(header) and all(v is not None for v in row.values()) for row in rows), 'malformed CSV')
    return rows

def read_check(path):
    rows = read_rows(path, CHECK_HEADER)
    require(len(rows) == 1, 'one correctness record required')
    return rows[0]

def validate_process(row, samples, check, n, func, count):
    require(set(row) == set(HEADER) and count == EVENTS, 'wrong v3 process schema/count')
    require(row['func'] == check['func'] == func and int(row['N']) == int(check['N']) == n, 'case mismatch')
    require(row['is_warmup'] == '1' and row['warmup_times'] == str(WARMUPS)
            and row['test_times'] == str(EVENTS) and check['batch'] == '1', 'conditions mismatch')
    a, b = float(check['err_a']), float(check['err_b'])
    require(check['check'] == 'PASS' and math.isfinite(a) and math.isfinite(b) and 0 <= a < 1e-9,
            'strict numerical correctness failed')
    require((0 <= b < 1e-9) if func == 'z2z_1d' else b == -1, 'strict secondary correctness failed')
    require(len(samples) == EVENTS, 'missing/extra samples')
    values = []
    for index, sample in enumerate(samples, 1):
        require(sample['func'] == func and int(sample['N']) == n and sample['batch'] == '1'
                and int(sample['sample_index']) == index, 'sample identity/order mismatch')
        value = float(sample['elapsed_ms'])
        require(math.isfinite(value) and value > 0, 'nonpositive/nonfinite sample')
        require(math.isclose(float(row['time_%d_ms' % index]), value, rel_tol=0, abs_tol=0.500001e-6),
                'wide sample differs from lossless sample')
        values.append(value)
    expected = {'tmax_ms': max(values), 'tmin_ms': min(values),
                'tmean_ms': statistics.mean(values), 'tmedium_ms': statistics.median(values)}
    for key, value in expected.items():
        actual = float(row[key])
        require(math.isfinite(actual) and actual > 0
                and math.isclose(actual, value, rel_tol=0, abs_tol=0.500001e-6), 'aggregate differs from samples')
    return values

def freeze_reference(m):
    """Resolve the latest reference once, before queueing; never follow it in a worker."""
    m = copy.deepcopy(m)
    if 'a100_reference' not in m:
        latest = json.loads((ROOT/'results/reference/a100/latest.json').read_text(encoding='utf-8'))
        path = inside(latest['manifest'])
        require(sha(path) == latest['manifest_sha256'], 'latest A100 manifest changed')
        dataset = json.loads(path.read_text(encoding='utf-8'))
        directory = inside(dataset['dataset_dir'])
        m['a100_reference'] = dict(dataset=dataset['dataset_id'], manifest=str(path), manifest_sha256=sha(path),
            median_table=str(directory/'medians.csv'),
            median_table_sha256=dataset['supplemental_files']['medians.csv']['sha256'],
            source=str(directory/dataset['program_source']), source_sha256=ORIGIN_SHA,
            warmups=WARMUPS, event_iterations=EVENTS, input_pattern='linear_index_real_imaginary_zero',
            comparison='cross_device_reference', source_binary_correspondence_verified=False)
    reference(m)
    return m

def reference(m):
    record = m.get('a100_reference')
    require(isinstance(record, dict), 'freeze the explicit A100 reference before execution')
    for path, digest in (('manifest', 'manifest_sha256'), ('median_table', 'median_table_sha256'), ('source', 'source_sha256')):
        require(sha(inside(record[path])) == record[digest], 'A100 reference changed: ' + path)
    require(record['source_sha256'] == ORIGIN_SHA and record['warmups'] == WARMUPS
            and record['event_iterations'] == EVENTS and record['input_pattern'] == 'linear_index_real_imaginary_zero',
            'A100 timing/input version differs')
    result = {}
    with inside(record['median_table']).open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (int(row['N']), row['func'])
            require(key not in result and row['batch'] == '1' and row['warmup_times'] == str(WARMUPS)
                    and row['test_times'] == str(EVENTS), 'A100 row mismatch')
            value = float(row['median_ms'])
            require(math.isfinite(value) and value > 0, 'invalid A100 median')
            result[key] = value
    return result
