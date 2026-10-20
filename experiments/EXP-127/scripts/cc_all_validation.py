"""Pure identity checks shared by the CC validation harness and its tests."""
from pathlib import PurePosixPath
import re


def inspect_callback_sources(generated, expected, func):
    role={'z2d_1d':'paired_pre_columns', 'd2z_1d':'generic_paired_post'}[func]
    family=re.compile('_'+role+r'_v[0-9]+_C')
    marker=family.search(expected['name'])
    if marker is None:
        raise ValueError('expected generic boundary identity missing')
    suffix=expected['name'][marker.start():]
    names=[name for name in generated if family.search(name)]
    if not names or not any('_CB_' in name for name in names):
        raise ValueError('missing callback boundary source')
    geometry='_factors_'+'_'.join(map(str,expected['factors']))+'_wgs_'+str(expected['W'])+'_tpt_'+str(expected['P'])+'_'
    if any(not name.endswith(suffix) or geometry not in name for name in names):
        raise ValueError('guard compiled a different boundary backend')
    return names


def matching_source_tree(previous, current, read_tree):
    """Allow a harness-only commit change; require the entire build source tree."""
    if any(previous[key]!=current[key] for key in ('repo','source')):
        raise ValueError('retained source location differs')
    if previous['source_status'] or current['source_status']:
        raise ValueError('retained or current FFT source is dirty')
    repo=PurePosixPath(current['repo']);source=PurePosixPath(current['source'])
    if not repo.is_absolute() or not source.is_relative_to(repo):
        raise ValueError('FFT source is outside the source repository')
    subtree=source.relative_to(repo).as_posix()
    trees=[]
    for item in (previous,current):
        if not re.fullmatch('[0-9a-f]{40}',item['commit']):
            raise ValueError('invalid retained source commit')
        tree=read_tree(item['commit'],subtree)
        if not re.fullmatch('[0-9a-f]{40}',tree):
            raise ValueError('invalid FFT source tree identity')
        trees.append(tree)
    if trees[0]!=trees[1]:
        raise ValueError('retained FFT source tree differs')
    return dict(previous_commit=previous['commit'],current_commit=current['commit'],
                source_subtree=subtree,tree_sha1=trees[0])
