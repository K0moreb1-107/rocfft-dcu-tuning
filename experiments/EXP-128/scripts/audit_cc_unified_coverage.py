"""Audit the inclusive 64K CC catalogue without altering historical coverage."""
import math

from audit_cc_coverage import parse_mapping, require


def native_catalog(coverage):
    columns = {x['length']: x for x in coverage['columns']}
    rows = {x['aligned']['length']: x['aligned'] for x in coverage['rows']}
    require(len(columns) == len(coverage['columns']) and len(rows) == len(coverage['rows']),
            'duplicate native configuration')
    for spec in [*columns.values(), *rows.values()]:
        require(spec['P'] > 0 and spec['ordinary_T'] > 0
                and all(x > 0 for x in spec['factors'])
                and math.prod(spec['factors']) == spec['length'], 'invalid native configuration')
    result = []
    for c, col in columns.items():
        for q, row in rows.items():
            slots = col['ordinary_T']
            if (65536 <= 2*c*q <= 1 << 24 and q >= slots
                    and c*slots//(2 if col['half_lds'] else 1) >= c
                    and c*slots*16//(2 if col['half_lds'] else 1) <= 65536
                    and q*row['ordinary_T']*16 <= 65536):
                result.append(dict(N=2*c*q, C=c, Q=q))
    return sorted(result, key=lambda x: (x['C'], x['Q']))


def validate_coverage(coverage, mapping):
    expected_native = native_catalog(coverage)
    require(coverage['geometries'] == expected_native, 'native catalogue incomplete or unordered')
    native = {(x['C'], x['Q']) for x in expected_native}
    public = coverage['public']
    require(public and [x['N'] for x in public] == sorted({x['N'] for x in public}),
            'public sizes missing, duplicated or unordered')
    for case in public:
        n, c, q = (case[x] for x in ('N', 'C', 'Q'))
        require(type(n) is int and n == 2*c*q and 65536 <= n <= 1 << 24,
                'public case outside scope')
        require((c, q) in native and mapping.get(n//2) == c,
                'public case differs from native support or active decomposition: '+str(n))
    require(public[0] == dict(N=65536, C=128, Q=256), '64K must use the generic CC default')
    preserved = {int(k): v for k, v in coverage['preserved_entries'].items()}
    additions = {x['N']//2: x['C'] for x in coverage['added_decompositions']}
    require(len(additions) == len(coverage['added_decompositions'])
            and not preserved.keys() & additions.keys(), 'mapping additions overlap')
    require(mapping == (preserved | additions), 'existing decomposition table changed')
    expected = [dict(N=x['N'], func=f) for x in public for f in ('z2d_1d', 'd2z_1d')]
    require(coverage['cases'] == expected and coverage['controls'] == [],
            'cases differ or 64K still registered as a legacy control')
    return dict(complete=True, public_N=len(public), measurement_cases=len(expected),
                native_geometries=len(native), native_columns=len(coverage['columns']),
                native_rows=len(coverage['rows']), active_map_entries=len(mapping),
                minimum_N=public[0]['N'], maximum_N=public[-1]['N'], expected_cc_local_version=2)
