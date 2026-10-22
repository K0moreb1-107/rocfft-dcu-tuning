"""Check whether explicit true thread bounds change copied RTC code generation."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re

from isa_cc_957127 import compile_one, RECORD, ART


def main():
    originals = json.loads((RECORD/'isa-summary.json').read_text())['kernels']
    prototypes = json.loads((RECORD/'prototype-summary.json').read_text())['kernels']
    selected = [x for x in originals if x['arm']=='candidate' and (
        x['N']==167042 or (x['N']==65536 and x['func']=='d2z_1d' and x['position']==1) or
        (x['N']==82134 and x['position']==1) or (x['N']==497664 and x['position']==0))]
    selected += [x for x in prototypes if x['N']==167042]
    tasks = []
    for item in selected:
        source = Path(item['offline_source']).read_text()
        wgs = int(re.search(r'_wgs_(\d+)_',item['name'])[1])
        start = source.index('{',source.index('extern "C" __global__'))+1
        source = source[:start]+f'\n__builtin_assume(threadIdx.x < {wgs});\n'+source[start:]
        variant = item.get('variant','original')+'_bounded'
        path = ART/('%d-%s-stage%d-%s.hip.cpp'%(item['N'],item['func'],item['position'],variant))
        path.write_text(source)
        tasks.append(dict(N=item['N'],func=item['func'],arm=item['arm'],position=item['position'],
                          name=item['name'],variant=variant,offline_source=str(path)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(compile_one,tasks))
    (RECORD/'bounded-summary.json').write_text(json.dumps(dict(complete=True,device_execution=False,
        precondition='The actual dispatched x dimension never exceeds the generated workgroup size. '
                     'This holds for the accepted CC launches; not an assumption about arbitrary external kernels.',
        kernels=result),ensure_ascii=False,indent=2)+'\n')
    print('BOUNDED',len(result),flush=True)


if __name__ == '__main__':
    main()
