"""Correlate the frozen v3 event loop with its actual kernel dispatches."""
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _index(event):
    return int(event['args']['index'])


def _argument(event, name):
    match = re.search(r'\b' + name + r'=([^,)]+)', event['args']['args'])
    require(match is not None, 'missing trace argument: ' + name)
    return match.group(1).strip()


def _launch_geometry(event):
    fields = ('gridDimX', 'gridDimY', 'gridDimZ', 'blockDimX',
              'blockDimY', 'blockDimZ', 'sharedMemBytes')
    values = tuple(int(_argument(event, field)) for field in fields)
    require(all(value > 0 for value in values[:6]) and values[6] >= 0,
            'invalid actual launch geometry')
    require(_argument(event, 'stream') in ('0', '0x0'), 'nondefault benchmark stream')
    return values


def _plan_grid(text):
    rows = text.strip().splitlines()
    pattern = r'\s*b\[(\d+),(\d+),(\d+)\] wgs\[(\d+),(\d+),(\d+)\], dy_lds bytes (\d+)\s*'
    matches = [re.fullmatch(pattern, row) for row in rows]
    require(rows and all(matches), 'invalid plan launch geometry')
    return tuple(tuple(map(int, match.groups())) for match in matches)


def inspect_dispatch(plan, events, func, warmups=10, samples=30):
    """Return one target execution after checking every warmup/sample window.

    The real checks execute once. z2z checks execute forward twice and inverse
    once before the event loop. None of those calls belongs to a timing window.
    Reused kernel names (e.g. two transposes per FFT) never identify a window.
    """
    require((warmups, samples) == (10, 30), 'unsupported frozen v3 event loop')
    checks = {'z2z_1d': 3, 'd2z_1d': 1, 'z2d_1d': 1}
    require(func in checks, 'unknown transform type')
    rounds = warmups + samples
    grids = [_plan_grid(block) for block in
             re.findall(r'GridParams\n(.*?)End GridParams', plan, re.S)]
    require(len(grids) == rounds + checks[func], 'plan execution count differs from v3 helper')
    geometry = grids[-1]
    require(all(grid == geometry for grid in grids[-rounds:]), 'benchmark plan geometry changed')

    all_apis = [e for e in events if e.get('cat') == 'HIP']
    timers = [e for e in all_apis if e['name'] == 'hipEventRecord']
    threads = {(e['args']['pid'], e['args']['tid']) for e in timers}
    require(len(threads) == 1, 'benchmark timer thread changed')
    # hipprof indexes APIs per host thread; RTC compiler workers restart at 1.
    apis = sorted((e for e in all_apis if (e['args']['pid'], e['args']['tid']) in threads), key=_index)
    by_index = {_index(e): e for e in apis}
    require(len(by_index) == len(apis), 'duplicate host API correlation index')
    require(len({e['args']['pid'] for e in apis}) == 1, 'multiple benchmark processes')
    records = [e for e in apis if e['name'] == 'hipEventRecord']
    syncs = [e for e in apis if e['name'] == 'hipEventSynchronize']
    elapsed = [e for e in apis if e['name'] == 'hipEventElapsedTime']
    require(len(records) == 2 * rounds and len(syncs) == rounds
            and len(elapsed) == samples, 'incomplete benchmark event loop')
    handles = tuple(_argument(e, 'event') for e in records[:2])
    require(handles[0] != handles[1], 'benchmark start and stop events alias')

    device = sorted((e for e in events if e.get('cat') == 'HIPOPS'), key=_index)
    require(len({_index(e) for e in device}) == len(device), 'duplicate device correlation index')
    groups = []
    for iteration in range(rounds):
        start, stop = records[2 * iteration:2 * iteration + 2]
        upper = _index(records[2 * iteration + 2]) if iteration + 1 < rounds else float('inf')
        require(tuple(_argument(e, 'event') for e in (start, stop)) == handles
                and all(_argument(e, 'stream') in ('0', '0x0') for e in (start, stop)),
                'benchmark event or stream changed')
        sync = syncs[iteration]
        require(_index(stop) < _index(sync) < upper
                and _argument(sync, 'event') == handles[1], 'wrong benchmark synchronization')
        reads = [e for e in elapsed if _index(stop) < _index(e) < upper]
        require(len(reads) == int(iteration >= warmups), 'sample read in wrong benchmark iteration')
        for read in reads:
            require(_index(sync) < _index(read)
                    and _argument(read, 'start') == handles[0]
                    and _argument(read, 'stop') == handles[1], 'wrong benchmark elapsed-time events')
        group = [e for e in device if _index(start) < _index(e) < _index(stop)]
        launches = [e for e in apis if _index(start) < _index(e) < _index(stop)
                    and 'LaunchKernel' in e['name']]
        require(len(group) == len(geometry)
                and [_index(e) for e in group] == [_index(e) for e in launches],
                'incomplete actual benchmark dispatch')
        for kernel, host in zip(group, launches):
            require(kernel['args']['pid'] == host['args']['pid']
                    and kernel['args']['args'] == host['args']['args']
                    and int(host['args']['state']) == 0, 'kernel/API correlation failed')
        require(tuple(_launch_geometry(e) for e in group) == geometry,
                'actual dispatch differs from plan geometry')
        groups.append(group)

    names = [e['name'] for e in groups[0]]
    require(all([e['name'] for e in group] == names for group in groups),
            'benchmark execution sequence changed')
    # Only prelude setup/correctness may execute outside the event loop. The
    # opposite-direction correctness FFT must never become the target sequence.
    selected = {_index(e) for group in groups for e in group}
    require(all(_index(e) < _index(records[0]) or _index(e) in selected
                for e in device), 'unexpected dispatch outside benchmark windows')
    return groups[0], dict(plan_executions=len(grids), correctness_executions=checks[func],
                          warmups=warmups, samples=samples, benchmark_executions=rounds,
                          kernels_per_execution=len(geometry),
                          checked_kernel_dispatches=sum(map(len, groups)))
