"""Read active numeric C++ initializers and check every EXP128 coverage entry."""
import copy
import math
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def mapping_body(source):
    # This table contains numeric initializers only, never quoted strings.
    clean = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
    match = re.search(r'NodeFactory::map1DLengthDouble\s*=\s*\{(.*?)^\s*\};',
                      clean, re.S | re.M)
    require(match is not None, 'double-precision decomposition table missing')
    return match.group(1)


def parse_mapping(source):
    body = mapping_body(source)
    pattern = re.compile(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}\s*,?')
    require(not pattern.sub('', body).strip(), 'unsupported decomposition table syntax')
    result = {}
    for match in pattern.finditer(body):
        length, column = map(int, match.groups())
        require(length not in result, 'duplicate active decomposition: %d' % length)
        require(length > 0 and column > 0 and length % column == 0,
                'invalid active decomposition: %d' % length)
        result[length] = column
    require(result, 'empty decomposition table')
    return result


def representative_sizes(public):
    remaining = {('C', x['C']) for x in public} | {('Q', x['Q']) for x in public}
    selected = set()
    while remaining:
        case = max(public, key=lambda x: (len({('C', x['C']), ('Q', x['Q'])} & remaining), x['N']))
        remaining -= {('C', case['C']), ('Q', case['Q'])}
        selected.add(case['N'])
    return selected


def validate_coverage(coverage, mapping):
    cols = {x['length']: x for x in coverage['columns']}
    rows = {x['aligned']['length']: x['aligned'] for x in coverage['rows']}
    require(len(cols) == len(coverage['columns']) and len(rows) == len(coverage['rows']),
            'duplicate native length')
    for cfg in [*cols.values(), *rows.values()]:
        require(math.prod(cfg['factors']) == cfg['length'] and cfg['P'] > 0
                and cfg['ordinary_T'] > 0, 'invalid native configuration')

    def geometry(case):
        n, c, q = (case[key] for key in ('N', 'C', 'Q'))
        require(all(type(x) is int and x > 0 for x in (n, c, q)), 'invalid geometry fields')
        require(n == 2*c*q and 65536 < n <= 1 << 24, 'geometry outside registered scope')
        require(c in cols and q in rows, 'geometry has no native column or row')
        col, row = cols[c], rows[q]
        slots = col['ordinary_T']
        require(q >= slots and c*slots//(2 if col['half_lds'] else 1) >= c,
                'column geometry has insufficient shared storage')
        require(c*slots*16//(2 if col['half_lds'] else 1) <= 65536
                and q*row['ordinary_T']*16 <= 65536, 'native geometry exceeds shared storage')

    native = coverage['geometries']
    for case in native:
        geometry(case)
    native_keys = {(x['C'], x['Q']) for x in native}
    require(len(native_keys) == len(native), 'duplicate internal geometry')
    wanted_native = {(c, q) for c, col in cols.items() for q, row in rows.items()
                     if 65536 < 2*c*q <= 1 << 24 and q >= col['ordinary_T']
                     and c*col['ordinary_T']//(2 if col['half_lds'] else 1) >= c
                     and c*col['ordinary_T']*16//(2 if col['half_lds'] else 1) <= 65536
                     and q*row['ordinary_T']*16 <= 65536}
    require(native_keys == wanted_native, 'native catalogue incomplete')

    public = coverage['public']
    require([x['N'] for x in public] == sorted({x['N'] for x in public}),
            'public cases are empty, duplicate or unordered')
    require(public, 'public coverage missing')
    for case in public:
        geometry(case)
        n, c, q = (case[key] for key in ('N', 'C', 'Q'))
        require(mapping.get(n//2) == c and n//2//c == q,
                'public decomposition differs from active table: %d' % n)
        require((c, q) in native_keys, 'public geometry missing internal coverage')

    preserved = {int(k): v for k, v in coverage['preserved_entries'].items()}
    added = {}
    for case in coverage['added_decompositions']:
        geometry(case)
        key = case['N']//2
        require(key not in added and key not in preserved, 'added decomposition overwrites an entry')
        added[key] = case['C']
        require(case in public, 'added decomposition missing public case')
    require(mapping == (preserved | added), 'preserved or added table entries differ')
    expected = [dict(N=x['N'], func=f) for x in public for f in ('z2d_1d', 'd2z_1d')]
    require(coverage['cases'] == expected, 'measurement cases differ from public validation')
    require(coverage['controls'] == [dict(N=65536, func=f) for f in ('z2d_1d', 'd2z_1d')],
            '64K regression controls differ')
    representatives = representative_sizes(public)
    return dict(complete=True, active_map_entries=len(mapping), preserved_entries=len(preserved),
                added_decompositions=len(added), public_N=len(public), measurement_cases=len(expected),
                native_geometries=len(native), native_columns=len(cols), native_rows=len(rows),
                active_native_rows=len({x['Q'] for x in native}),
                public_columns=len({x['C'] for x in public}), public_rows=len({x['Q'] for x in public}),
                representative_N=sorted(representatives),
                public_validation_records=2*(len(public)+3*len(representatives)))


def correct_coverage(coverage, mapping):
    result = copy.deepcopy(coverage)
    changes = []
    for case in result['public']:
        c = mapping[case['N']//2]
        q = case['N']//2//c
        if (case['C'], case['Q']) != (c, q):
            changes.append(dict(field='public', N=case['N'], before=[case['C'], case['Q']], after=[c, q]))
            case.update(C=c, Q=q)
    for length, old in list(result['preserved_entries'].items()):
        actual = mapping[int(length)]
        if old != actual:
            changes.append(dict(field='preserved_entries', M=int(length), before=old, after=actual))
            result['preserved_entries'][length] = actual
    audit = validate_coverage(result, mapping)
    result['coverage_audit'] = audit
    return result, dict(audit, corrections=changes)
