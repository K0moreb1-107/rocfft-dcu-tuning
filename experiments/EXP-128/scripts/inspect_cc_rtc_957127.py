"""Compare accepted generated code; retain exact sources for offline ISA checks."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('/public/home/zhangkewei/zr')
RUN = ROOT/'experiments/EXP-128/runs/EXP-128-cc-regression-955252-diagnostic-20261022'
OUT = ROOT/'experiments/EXP-128/records/regression-955252-20261022/analysis-957127'
ART = ROOT/'experiments/EXP-128/artifacts/preflight/regression-957127'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    record = json.loads((RUN/'diagnostic-result.json').read_text())
    assert record['complete']
    ART.mkdir(exist_ok=True)
    results = []
    selected = {65536,131072,167042,69938,142688,82134,346112,497664}
    for item in record['traces']:
        rtc = Path(item['folder'])/'metadata/rtc.txt'
        sources = dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',
                                  rtc.read_text(),re.M|re.S))
        kernels = []
        for position,name in enumerate(item['trace']['kernel_names']):
            source = sources.get(name)
            normalized = re.sub(r'_cc_local_v[12]_', '_cc_local_vX_',source) if source else None
            entry = dict(position=position,name=name,available=source is not None,
                source_sha256=sha(source) if source else None,
                version_name_normalized_sha256=sha(normalized) if normalized else None)
            if source and item['N'] in selected:
                path = ART/('%d-%s-%s-stage%d.hip.cpp'%(item['N'],item['func'],item['arm'],position))
                path.write_text('#include <hip/hip_runtime.h>\n'+source)
                entry['offline_source'] = str(path)
            kernels.append(entry)
        results.append(dict(N=item['N'],func=item['func'],arm=item['arm'],kernels=kernels,
                            evidence=str(rtc),sha256=hashlib.sha256(rtc.read_bytes()).hexdigest()))
    by_case = {(item['N'],item['func'],item['arm']):item for item in results}
    comparisons = []
    for item in results:
        if item['arm'] != 'candidate':
            continue
        old = by_case[item['N'],item['func'],'previous']
        same = [a['available'] and b['available'] and
                a['version_name_normalized_sha256'] == b['version_name_normalized_sha256']
                for a,b in zip(item['kernels'],old['kernels'])]
        comparisons.append(dict(N=item['N'],func=item['func'],same_except_version_name=same,
            lengths_equal=len(item['kernels'])==len(old['kernels'])))
    result = dict(complete=True,kind='generated source evidence; not device performance',
                  kernels=results,comparisons=comparisons)
    (OUT/'source-comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(records=len(results),comparisons=len(comparisons),
        both_stages_identical=sum(all(item['same_except_version_name']) for item in comparisons),
        stages_identical=[sum(len(item['same_except_version_name']) > k and item['same_except_version_name'][k]
                              for item in comparisons) for k in range(2)],output=str(OUT/'source-comparison.json')),indent=2))


if __name__ == '__main__':
    main()
