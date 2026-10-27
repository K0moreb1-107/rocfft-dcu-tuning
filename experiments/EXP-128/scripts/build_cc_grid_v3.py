"""Relink v3 objects, replacing only its static double-precision CC divisor table."""
import argparse
import hashlib
import io
import json
import re
import shlex
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path('/public/home/zhangkewei/zr')
BASE_COMMIT = '8da0abb02ae6f5591e448d3e10adef8919aae40f'
BASE_SHA = 'f97365bba962f3be72a1336b67b5d4d6a93dd8d63f2500172730f639bb5cf3ea'
PREFIX = 'rocm-libraries-rocm-7.2.2/projects/rocfft/'
BASE_BUILD = ROOT/'experiments/EXP-128/artifacts/build/EXP-128-cc-local-rowsimplify-20261022'
BASE_INSTALL = ROOT/'experiments/EXP-128/artifacts/install/EXP-128-cc-local-rowsimplify-20261022'
RECORDS = ROOT/'experiments/EXP-128/records/grid-fill-20261027'
HEADERS = ROOT/'experiments/EXP-128/artifacts/source/cc-grid-v3-headers-20261027'
TABLE = re.compile(r'(NodeFactory::Map1DLength const NodeFactory::map1DLengthDouble\s*=\s*\{)(.*?)(\n\};)',re.S)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def source():
    return subprocess.check_output(['git','show',BASE_COMMIT+':'+PREFIX+'library/src/node_factory.cpp'],cwd=ROOT).decode()


def parse_table(text):
    match = TABLE.search(text)
    assert match and not TABLE.search(text,match.end())
    clean = re.sub(r'/\*.*?\*/|//[^\n]*','',match.group(2),flags=re.S)
    pairs = [(int(a),int(b)) for a,b in re.findall(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}',clean)]
    remainder = re.sub(r'\{\s*\d+\s*,\s*\d+\s*\}','',clean)
    assert not remainder.replace(',','').strip() and len(pairs)==len(dict(pairs))
    return match,dict(pairs)


def patched_source(group):
    original = source()
    match,table = parse_table(original)
    requested = {row['N']//2:row['C'] for row in group}
    assert len(requested)==len(group) and requested.keys() <= table.keys()
    assert all(table[m]!=c for m,c in requested.items())
    replacement = dict(table)
    replacement.update(requested)
    body = '\n    // Measurement-only CC divisors; all computation objects remain v3.\n'
    body += ',\n'.join('    {%d, %d}'%(m,c) for m,c in sorted(replacement.items()))
    result = original[:match.start(2)]+body+original[match.end(2):]
    new_match,new_table = parse_table(result)
    assert new_table.keys()==table.keys()
    assert {m:c for m,c in new_table.items() if table[m]!=c}==requested
    assert original[:match.start(2)]==result[:new_match.start(2)]
    assert original[match.end(2):]==result[new_match.end(2):]
    return result,requested


def export_headers():
    if HEADERS.exists():
        return
    HEADERS.mkdir(parents=True)
    paths = [PREFIX+p for p in ('library/src/include','library/include','library/src/device/generator','shared')]
    raw = subprocess.check_output(['git','archive',BASE_COMMIT,'--',*paths],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive.getmembers():
            assert member.name.startswith(PREFIX) or member.isdir()
            if member.isdir():
                continue
            assert member.isfile() and member.name.startswith(PREFIX)
            relative = member.name[len(PREFIX):]
            target = (HEADERS/relative).resolve()
            assert target.is_relative_to(HEADERS.resolve())
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())


def compile_command(factory, output):
    entries = json.loads((BASE_BUILD/'compile_commands.json').read_text())
    found = [entry for entry in entries if entry['file'].endswith('/node_factory.cpp')]
    assert len(found)==1
    entry = found[0]
    args = shlex.split(entry['command'])
    original_prefix = str(ROOT/PREFIX)
    original_prefix = original_prefix.rstrip('/')+'/'
    converted=[]
    for arg in args:
        if arg==entry['file']:
            arg=str(factory)
        elif arg.startswith('-I'+original_prefix):
            arg='-I'+str(HEADERS/arg[len('-I'+original_prefix):])
        converted.append(arg)
    converted[converted.index('-o')+1]=str(output)
    # Preserve the relative shared/ includes of node_factory.cpp.
    converted.extend(['-iquote',str(HEADERS/'library/src')])
    return converted,Path(entry['directory'])


def link_command(factory_object, library):
    link_path=BASE_BUILD/'library/src/CMakeFiles/rocfft.dir/link.txt'
    original=shlex.split(link_path.read_text())
    cwd=BASE_BUILD/'library/src'
    args=list(original)
    args[args.index('-o')+1]=str(library)
    replaced=0
    inputs={}
    for index,arg in enumerate(args):
        if arg.endswith('.o'):
            path=(cwd/arg).resolve()
            assert path.is_relative_to(ROOT) and path.is_file(),str(path)
            if arg=='CMakeFiles/rocfft.dir/node_factory.cpp.o':
                args[index]=str(factory_object)
                replaced+=1
            else:
                inputs[str(path.relative_to(ROOT))]=sha(path)
    assert replaced==1 and len(inputs)>40
    return args,cwd,inputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group',type=int,required=True,choices=range(4))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--syntax-only',action='store_true')
    a=parser.parse_args()
    output=a.output.resolve()
    assert output.is_relative_to(ROOT)
    output.mkdir(parents=True,exist_ok=True)
    assert sha(BASE_INSTALL/'lib/librocfft.so.0.1')==BASE_SHA
    matrix=json.loads((RECORDS/'matrix.json').read_text())
    group=matrix['groups'][a.group]
    generated,requested=patched_source(group)
    export_headers()
    factory=output/'node_factory.cpp'
    factory.write_text(generated,encoding='utf-8')
    object_path=output/'node_factory.cpp.o'
    compile_args,cwd=compile_command(factory,object_path)
    if a.syntax_only:
        del compile_args[compile_args.index('-o'):compile_args.index('-o')+2]
        compile_args.remove('-c')
        compile_args.append('-fsyntax-only')
    subprocess.run(compile_args,cwd=cwd,check=True)
    record=dict(group=a.group,cases=len(group),base_commit=BASE_COMMIT,base_library_sha256=BASE_SHA,
        matrix_sha256=sha(RECORDS/'matrix.json'),only_static_divisor_table_changed=True,
        changed_divisors=requested,source_sha256=sha(factory),compile_command=compile_args,
        compiler_command_source_sha256=sha(BASE_BUILD/'compile_commands.json'),
        headers={str(p.relative_to(HEADERS)):sha(p) for p in HEADERS.rglob('*') if p.is_file()})
    if not a.syntax_only:
        install=output/'grid-install'
        libdir=install/'lib'
        libdir.mkdir(parents=True)
        library=libdir/'librocfft.so.0.1'
        link_args,link_cwd,inputs=link_command(object_path,library)
        subprocess.run(link_args,cwd=link_cwd,check=True)
        for name in ('librocfft.so.0','librocfft.so'):
            (libdir/name).symlink_to('librocfft.so.0.1')
        for relative in ('include','lib/rocfft','share/doc/rocfft'):
            target=install/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(BASE_INSTALL/relative,target,symlinks=True)
        record.update(reused_objects=inputs,link_command=link_args,
                      library_sha256=sha(library),new_factory_object_sha256=sha(object_path))
        write(install/'grid-build.json',record)
    write(output/'grid-relink.json',dict(record,syntax_only=a.syntax_only,complete=True))
    print(json.dumps(dict(complete=True,group=a.group,cells=len(group),syntax_only=a.syntax_only,
                         reused_computation_objects=len(record.get('reused_objects',{})))))


if __name__=='__main__':
    main()
