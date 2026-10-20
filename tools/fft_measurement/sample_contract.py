"""Versioned single-process event samples; legacy common.py stays immutable."""
import copy
import csv
import json
import math
import re
import statistics

from common import (ARMS, HEADER, OFFICIAL_COMMIT, OFFICIAL_SHA, cases, inside, require)

POLICY = 'FFT-event-samples-single-v2'
SOURCE_SHA = '6d42f1fbf917229262c6bd792994fb44cc20176b8f9a04fbbb8a2d42a29fa08d'
SAMPLE_HEADER = ['func', 'N', 'batch', 'sample_index', 'elapsed_ms']
SOURCE_NAME = 'fft_test_1d_samples.cpp'


def iterations(m):
    value = m.get('event_iterations', 50)
    require(type(value) is int and 0 < value <= 2147483647, 'event_iterations must be a positive int')
    return value


def arms(m):
    selected = m.get('arms', {})
    require(isinstance(selected, dict) and 'candidate' in selected
            and len(selected) >= 2 and set(selected) <= set(ARMS),
            'candidate and at least one declared reference arm required')
    return tuple(arm for arm in ARMS if arm in selected)


def validate_manifest(value):
    m = copy.deepcopy(value)
    require(m.get('policy', POLICY) == POLICY, 'wrong sample policy')
    m['policy'] = POLICY
    m['event_iterations'] = iterations(m)
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
    with open(path, encoding='utf-8') as stream:
        return validate_manifest(json.load(stream))


def schedule(m):
    selected = arms(m)
    result = []
    for case_index, (n, func) in enumerate(cases(m)):
        order = selected if case_index % 2 == 0 else tuple(reversed(selected))
        for slot, arm in enumerate(order, 1):
            result.append(dict(index=len(result), N=n, func=func, round=1, slot=slot, arm=arm))
    return result


def read_samples(path):
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == SAMPLE_HEADER, 'invalid sample CSV header')
        rows = list(reader)
    require(all(set(row) == set(SAMPLE_HEADER) and all(v is not None for v in row.values())
                for row in rows), 'malformed sample CSV')
    return rows


def validate_process(row, samples, n, func, count):
    require(set(row) == set(HEADER), 'invalid process CSV row')
    require(row['func'] == func and int(row['N']) == n, 'case mismatch')
    require(int(row['batch']) == 1 and int(row['iters']) == count
            and int(row['is_warmup']) == 1, 'batch/iterations/warmup mismatch')
    require(row['check'] == 'PASS', 'correctness did not PASS')
    values = {key: float(row[key]) for key in HEADER[5:11] + ['err_a', 'err_b']}
    require(all(math.isfinite(x) for x in values.values()), 'nonfinite process measurement')
    require(values['plan_ms'] >= 0 and values['first_ms'] >= 0, 'negative diagnostic time')
    require(0 <= values['err_a'] < 1e-9, 'strict err_a threshold failed')
    require((0 <= values['err_b'] < 1e-9) if func == 'z2z_1d' else values['err_b'] == -1,
            'strict err_b threshold/sentinel failed')
    require(len(samples) == count, 'missing/extra event samples')
    times = []
    for index, sample in enumerate(samples, 1):
        require(sample['func'] == func and int(sample['N']) == n and int(sample['batch']) == 1,
                'sample case mismatch')
        require(int(sample['sample_index']) == index, 'duplicate/missing/reordered sample index')
        elapsed = float(sample['elapsed_ms'])
        require(math.isfinite(elapsed) and elapsed > 0, 'invalid event sample time')
        times.append(elapsed)
    expected = {'min_ms': min(times), 'mean_ms': statistics.mean(times),
                'max_ms': max(times), 'per_tf_ms': min(times)}
    require(all(math.isclose(values[key], value, rel_tol=1e-12, abs_tol=1e-12)
                for key, value in expected.items()), 'process aggregate differs from raw samples')
    return times


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def statistics_for(values):
    return dict(mean_ms=statistics.mean(values), median_ms=statistics.median(values),
                min_ms=min(values), max_ms=max(values),
                p25_ms=percentile(values, .25), p75_ms=percentile(values, .75))
