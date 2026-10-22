"""Pure readers for trace windows and raw counter blocks; no GPU execution."""
import hashlib
import re
import statistics

from cc_dispatch import inspect_dispatch


def index(event):
    return int(event['args']['index'])


def duration_us(event):
    args = event['args']
    ns = int(args['EndNs']) - int(args['BeginNs'])
    assert ns == int(args['DurationNs']) and ns >= 0, 'inconsistent raw device timestamp'
    assert abs(float(event['dur']) - ns/1000) < .001, 'trace unit differs from raw nanoseconds'
    return ns/1000


def stats(values):
    ordered = sorted(values)
    def percentile(p):
        at = (len(ordered)-1)*p
        left = int(at)
        return ordered[left]+(ordered[min(left+1,len(ordered)-1)]-ordered[left])*(at-left)
    return dict(median=statistics.median(values),p25=percentile(.25),p75=percentile(.75),
                min=min(values),max=max(values))


def trace_evidence(plan, events, func):
    first, contract = inspect_dispatch(plan, events, func)
    names = [event['name'] for event in first]
    timers = sorted((event for event in events if event.get('cat') == 'HIP'
                     and event.get('name') == 'hipEventRecord'),key=index)
    device = sorted((event for event in events if event.get('cat') == 'HIPOPS'),key=index)
    groups = [[event for event in device if index(start) < index(event) < index(stop)]
              for start,stop in zip(timers[::2],timers[1::2])]
    measured = groups[10:]
    assert len(measured) == 30 and all([event['name'] for event in group] == names for group in measured)
    columns = [[duration_us(group[position]) for group in measured] for position in range(len(names))]
    sums = [sum(duration_us(event) for event in group) for group in measured]
    spans = [(int(group[-1]['args']['EndNs'])-int(group[0]['args']['BeginNs']))/1000 for group in measured]
    gaps = [span-total for span,total in zip(spans,sums)]
    assert all(gap >= -.001 for gap in gaps), 'overlapping default-stream kernel spans'
    return dict(contract=contract,kernel_names=names,
        kernels=[dict(position=position,name=name,samples_us=values,stats_us=stats(values))
                 for position,(name,values) in enumerate(zip(names,columns))],
        window_kernel_sum_us=stats(sums),window_device_span_us=stats(spans),
        window_gap_us=stats(gaps),window_samples_us=[dict(kernel_sum=total,span=span,gap=gap)
                                                   for total,span,gap in zip(sums,spans,gaps)],
        interpretation='Only final 30 actual event windows. Diagnostic instrumentation, not formal performance.')


def actual_sources(text, names):
    sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S))
    return {name:dict(available=name in sources,
        sha256=hashlib.sha256(sources[name].encode()).hexdigest() if name in sources else None)
        for name in names}


def pmc_blocks(text):
    blocks = []
    for match in re.finditer(r'kernel-name:\s*"([^"\n]+)"\s*\n(.*?)(?=\n\s*kernel-name:|\Z)',text,re.S):
        fields = {}
        for line in match.group(2).splitlines():
            parts = re.split(r'\s{2,}',line.strip(),maxsplit=1)
            if len(parts) == 2:
                fields[parts[0]] = parts[1]
        blocks.append(dict(name=match.group(1),fields=fields))
    return blocks


def select_pmc_windows(blocks, names):
    """Discard setup and correctness by the full sequence, never just a repeated name."""
    selected = [block for block in blocks if block['name'] in names]
    width = len(names)
    # Correctness can use callback variants with different names; only the
    # subsequent 40 ordinary executions have the benchmark's exact sequence.
    assert 40*width <= len(selected) <= 41*width, 'counter dispatch count differs from real v3 loop'
    benchmark = selected[-40*width:]
    assert [block['name'] for block in benchmark] == names*40, 'counter dispatch order differs from real v3 loop'
    return [benchmark[start:start+width] for start in range(10*width,40*width,width)]
