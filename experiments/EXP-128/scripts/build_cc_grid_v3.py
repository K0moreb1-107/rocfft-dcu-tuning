"""Create controlled v3 copies by changing only source-derived divisor data."""
import argparse, hashlib, json, re, shutil, struct, subprocess
from pathlib import Path
ROOT=Path('/public/home/zhangkewei/zr')
BASE_COMMIT='8da0abb02ae6f5591e448d3e10adef8919aae40f'
BASE_SHA='f97365bba962f3be72a1336b67b5d4d6a93dd8d63f2500172730f639bb5cf3ea'
PREFIX='rocm-libraries-rocm-7.2.2/projects/rocfft/'
BASE_INSTALL=ROOT/'experiments/EXP-128/artifacts/install/EXP-128-cc-local-rowsimplify-20261022'
RECORDS=ROOT/'experiments/EXP-128/records/grid-fill-20261027'
TABLE=re.compile(r'NodeFactory::Map1DLength const NodeFactory::map1DLengthDouble\s*=\s*\{(.*?)\n\};',re.S)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def source_table():
    source=subprocess.check_output(['git','show',BASE_COMMIT+':'+PREFIX+'library/src/node_factory.cpp'],cwd=ROOT).decode()
    match=TABLE.search(source)
    assert match and not TABLE.search(source,match.end())
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',match.group(1),flags=re.S)
    pairs=[(int(a),int(b)) for a,b in re.findall(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}',clean)]
    remainder=re.sub(r'\{\s*\d+\s*,\s*\d+\s*\}','',clean)
    assert not remainder.replace(',','').strip() and len(pairs)==len(dict(pairs))
    return pairs
def sections(data):
    assert data[:6]==b'\x7fELF\x02\x01'
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    assert h[11]==64
    entries=[struct.unpack_from('<IIQQQQIIQQ',data,h[6]+i*h[11]) for i in range(h[12])]
    names=entries[h[13]];names=data[names[4]:names[4]+names[5]]
    result={}
    for i,e in enumerate(entries):
        name=names[e[0]:].split(b'\0',1)[0].decode()
        result[name]=dict(index=i,type=e[1],flags=e[2],offset=e[4],size=e[5],link=e[6],entry_size=e[9])
    return result,entries
def map_symbol(data):
    section,entries=sections(data);s=section['.symtab']
    names=entries[s['link']];names=data[names[4]:names[4]+names[5]]
    found=[]
    for offset in range(s['offset'],s['offset']+s['size'],s['entry_size']):
        e=struct.unpack_from('<IBBHQQ',data,offset);name=names[e[0]:].split(b'\0',1)[0]
        if b'map1DLengthDouble' in name:
            assert e[1]&15==1 and e[5]>0
            found.append(dict(name=name.decode(),value=e[4],size=e[5]))
    assert len(found)==1
    return found[0]
def controlled_library(group):
    data=(BASE_INSTALL/'lib/librocfft.so.0.1').read_bytes()
    assert hashlib.sha256(data).hexdigest()==BASE_SHA
    pairs=source_table();table=dict(pairs)
    requested={r['N']//2:r['C'] for r in group}
    assert len(requested)==len(group) and requested.keys()<=table.keys()
    assert all(table[m]!=c for m,c in requested.items())
    original=b''.join(struct.pack('<QQ',m,c) for m,c in pairs)
    assert data.count(original)==1, 'exact source table must occur once'
    offset=data.index(original);section,_=sections(data);rodata=section['.rodata']
    assert rodata['type']==1 and rodata['flags']&2 and not rodata['flags']&5
    assert rodata['offset']<=offset and offset+len(original)<=rodata['offset']+rodata['size']
    replacement=b''.join(struct.pack('<QQ',m,requested.get(m,c)) for m,c in pairs)
    result=data[:offset]+replacement+data[offset+len(original):]
    assert len(result)==len(data)
    allowed=set()
    for i,(m,c) in enumerate(pairs):
        if m in requested:allowed.update(range(offset+16*i+8,offset+16*i+16))
    changed=[i for i,(a,b) in enumerate(zip(data,result)) if a!=b]
    assert changed and set(changed)<=allowed
    code=section['.text']
    assert result[code['offset']:code['offset']+code['size']]==data[code['offset']:code['offset']+code['size']]
    assert result[:offset]==data[:offset] and result[offset+len(original):]==data[offset+len(original):]
    expected=dict(table);expected.update(requested)
    return result,dict(base_commit=BASE_COMMIT,base_library_sha256=BASE_SHA,
        only_static_divisor_table_changed=True,all_executable_bytes_identical=True,
        all_bytes_outside_table_identical=True,table_offset=offset,table_bytes=len(original),
        changed_byte_count=len(changed),changed_divisors=requested,map_symbol=map_symbol(data),
        text_sha256=hashlib.sha256(data[code['offset']:code['offset']+code['size']]).hexdigest(),
        source_table_sha256=hashlib.sha256(original).hexdigest(),
        binary_edit_scope='Read-only divisor values only; ELF build-id retained, identity uses full SHA256.'),expected
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--group',type=int,required=True,choices=range(4));p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();output=a.output.resolve();assert output.is_relative_to(ROOT)
    output.mkdir(parents=True,exist_ok=True);matrix=json.loads((RECORDS/'matrix.json').read_text());group=matrix['groups'][a.group]
    data,record,expected=controlled_library(group)
    install=output/'grid-install';libdir=install/'lib';libdir.mkdir(parents=True,exist_ok=True)
    library=libdir/'librocfft.so.0.1';library.write_bytes(data)
    for name in ('librocfft.so.0','librocfft.so'):
        link=libdir/name
        if link.is_symlink():assert link.readlink()==Path('librocfft.so.0.1')
        else:
            assert not link.exists();link.symlink_to('librocfft.so.0.1')
    for relative in ('include','lib/rocfft','share/doc/rocfft'):
        target=install/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(BASE_INSTALL/relative,target,symlinks=True,dirs_exist_ok=True)
    record.update(complete=True,group=a.group,cases=len(group),matrix_sha256=sha(RECORDS/'matrix.json'),library_sha256=sha(library))
    write(install/'grid-build.json',record);write(output/'grid-build.json',record)
    print(json.dumps(dict(complete=True,group=a.group,cells=len(group),changed_bytes=record['changed_byte_count'],executable_bytes_identical=True)))
if __name__=='__main__':main()
