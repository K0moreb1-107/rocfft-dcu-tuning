"""Publish the fully accepted EXP129 source locally, preserving both ordered histories."""
from pathlib import Path
import copy
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path('/public/home/zhangkewei/zr')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/EXP-129/scripts')]
from submit_gate_simplification import read, write, commit

RECORD = ROOT/'experiments/EXP-129/records/stable-promotion-20261031'
AUDIT = ROOT/'experiments/EXP-129/records/stable-scale-fix-20261030/results-1004433'
SOURCE = 'rocm-libraries-rocm-7.2.2/projects/rocfft'
BRANCH = 'exp-129-gate-simplification'
TAG = 'stable-main-exp129-cc-generic-clean-20261031'
OLD_MAIN = '697f6f0a8a3ffa9dd255d911b488856722f4e839'
BUILD_SOURCE = '842b98916033e212ca9fe0e327381e6d33eb8080'


def git(*args, raw=False, input=None):
    result = subprocess.run(['git', *args], cwd=ROOT, input=input, capture_output=True,
        text=not raw, timeout=180, check=True)
    return result.stdout if raw else result.stdout.strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert git('branch', '--show-current') == BRANCH
    assert git('rev-parse', 'main') == OLD_MAIN
    assert not git('tag', '--list', TAG)
    assert not git('diff', '--cached', '--name-only'), 'preserve any preexisting staged changes'
    review = read(AUDIT/'audit.json')
    assert review['complete'] and review['formal_acceptance_complete']
    assert review['candidate']['source_commit'] == BUILD_SOURCE
    arm = review['candidate']
    assert sha(Path(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256']
    source_tree = git('rev-parse', BUILD_SOURCE+':'+SOURCE)
    assert git('rev-parse', 'HEAD:'+SOURCE) == source_tree
    old_tags = git('show-ref', '--tags', '-d')
    gitlink = git('rev-parse', 'HEAD:VkFFT')
    assert git('rev-parse', 'main:VkFFT') == gitlink
    initial_head = git('rev-parse', 'HEAD')
    RECORD.mkdir(parents=True, exist_ok=False)
    before = RECORD/'before'
    before.mkdir()
    for name in ('AGENTS.md', 'configs/installations.json'):
        path = before/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT/name).read_bytes())
    write(before/'git-refs.json', dict(main=OLD_MAIN, experiment_head=initial_head, tags=old_tags))
    missing = git('-c', 'core.quotepath=false', 'diff', '--name-only', '--diff-filter=D', 'main', 'HEAD').splitlines()
    historical = [name for name in missing if name.startswith(('configs/experiments/',
        'experiments/EXP-125/records/', 'experiments/EXP-126/records/', 'experiments/EXP-126/scripts/'))]
    assert all(name.startswith(SOURCE+'/') for name in set(missing)-set(historical))
    preserved_local_changes = []
    for name in historical:
        path = ROOT/name
        content = git('show', 'main:'+name, raw=True)
        if path.exists():
            if path.read_bytes() != content:
                preserved_local_changes.append(name)
        else:
            assert path.resolve().is_relative_to(ROOT)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if git('ls-tree', 'main', '--', name).split()[0] == '100755':
                path.chmod(path.stat().st_mode | 0o111)
    registry_path = ROOT/'configs/installations.json'
    registry = read(registry_path)
    old_stable = copy.deepcopy(registry['stable_source'])
    identifier = Path(arm['install']).name
    previous = registry['aliases']['previous']
    registry['stable_source_history'].append(old_stable)
    registry['installations'][previous]['superseded_as_default_previous_on'] = '2026-10-31'
    registry['installations'][identifier] = dict(path=str(Path(arm['install']).relative_to(ROOT)),
        role='previous', eligible_formal_arm=True, compatibility=False, arm=arm,
        source_identity='已通过完整公开接口验收的EXP129通用CC融合、门控精简与旧后端退役源码',
        stable_tag=TAG, approved='2026-10-31', approval_record=str((RECORD/'promotion.json').relative_to(ROOT)),
        validation_job='1004431', formal_performance_job='1004433',
        cmake=dict(ROCFFT_CC_REAL_FUSION='ON'),
        known_limitations='性能用逐次样本中位数；保留全部逐项差异。相对EXP125少数尺寸仍有退化，'
            '本次发布不把计划变化带来的版本收益归因为纯前后处理融合收益。')
    registry['aliases']['previous'] = identifier
    registry['updated'] = '2026-10-31'
    registry['stable_source'] = dict(branch='main', worktree=str(ROOT), source_anchor=BUILD_SOURCE,
        tag=TAG, retained_kernel_source=BUILD_SOURCE, rocfft_source_tree=source_tree,
        previous_binary_registry_id=identifier, management_tools_commit=BUILD_SOURCE,
        binary_equivalence='稳定标签的rocFFT源码子树与构建1004430的实际源码子树一致；安装库保留原始构建身份。',
        approved='2026-10-31', approval_record=str((RECORD/'promotion.json').relative_to(ROOT)))
    write(registry_path, registry)
    agents_path = ROOT/'AGENTS.md'
    original_agents = agents_path.read_text()
    start, end = original_agents.index('## 当前有效版本'), original_agents.index('## 历史材料')
    current = ('## 当前有效版本\n\n稳定分支：main\n稳定工作区：'+str(ROOT)
        +'\n保留源码引用：EXP-129 '+BUILD_SOURCE+'\n有效标签：'+TAG
        +'\n已批准的稳定安装：'+str(Path(arm['install']).relative_to(ROOT))
        +'（ROCFFT_CC_REAL_FUSION=ON）\n完整验证：1004431；性能：1004433，原始10／30、中位数。'
        +'\n晋升记录：'+str((RECORD/'promotion.json').relative_to(ROOT))
        +'\n用户批准当前通用CC版本为稳定版；逐项性能差异按记录保留。\n\n')
    agents_path.write_text(original_agents[:start]+current+original_agents[end:])
    assert agents_path.read_text().split('## 当前有效版本')[0] == original_agents[:start]
    assert agents_path.read_text().split('## 历史材料', 1)[1] == original_agents[end+len('## 历史材料'):]
    promotion = dict(approved=True, date='2026-10-31', stable_branch='main', stable_tag=TAG,
        experiment_branch=BRANCH, previous_stable_main=OLD_MAIN, source_commit=BUILD_SOURCE,
        repair_implementation_commit='bd3988d566549e90951f005b230faf4f65fe092f',
        source_tree=source_tree, candidate_arm=arm, full_validation_job='1004431', performance_job='1004433',
        full_audit=str((AUDIT/'audit.json').relative_to(ROOT)), full_audit_sha256=sha(AUDIT/'audit.json'),
        numerical_and_actual_paths=401, main_guard_groups=320, main_guard_reference_cases=3840,
        smoke_reference_cases=32, formal_performance_cases=393, formal_samples=35370,
        performance_summary=review['summary'], prior_stable_source=old_stable,
        historical_files_retained_from_main=len(historical), historical_local_changes_preserved=preserved_local_changes,
        main_history_resolution='Keep the validated candidate production tree and current tools; restore historical '
            'records/configurations missing only because EXP129 started from EXP125. Record both parents, then fast-forward main.',
        old_tags_preserved=True, source_branch_switch=False, worktrees_created=False, automation=False,
        cloud_push_authorized=True, cloud_push_receipt='push-result.json')
    write(RECORD/'promotion.json', promotion)
    write(RECORD/'historical-files.json', dict(retained=historical, local_changes_preserved=preserved_local_changes,
        intentionally_not_restored=sorted(set(missing)-set(historical))))
    (RECORD/'稳定版本说明.md').write_text('# EXP129通用CC融合稳定版\n\n'
        +'标签：'+TAG+'。稳定分支：main。\n\n'
        +'一维、双精度、批量一、非原位、偶数N≥65536的通用CC前后处理融合；精简门控，退役EXP125专用后端。'
        +'完整验证包含数值、实际路径、内存、回调、边界及缩放。401项数值／路径、3840个扩展参考用例和32个冒烟参考用例全部通过。\n\n'
        +'正式性能393组合、三版本1179进程、35370样本齐全。相对清理前EXP129，z2d和d2z的逐组合加速比中位数均为1.000；'
        +'相对EXP125保留版分别为1.260827和1.286293。后两项包含计划差异，不代表纯融合收益；少数尺寸的退化与分布漂移均保留。\n\n'
        +'已验证计算源码：'+BUILD_SOURCE+'；安装库校验值：'+arm['library_sha256']+'。\n\n'
        +'完整验收及逐项性能见../stable-scale-fix-20261030/results-1004433/结果核对.md。'
        +'云端推送状态及最终提交号见push-result.json；旧标签与历史保留。\n')
    direction = ROOT/'VKFFT_ROCFFT_OPTIMIZATION_DIRECTIONS.md'
    with direction.open('a') as stream:
        stream.write('\n\n### EXP129：完整验收通过并晋升稳定版本（2026-10-31）\n\n'
            '构建1004430、完整验证1004431、性能1004433成功。401项数值／实际路径、320组3840个扩展参考用例、'
            '8组32个缩放冒烟用例全部通过，临时参考数组已清理。393组合1179进程35370个原始10／30样本完整，'
            '同卡三版对照。逐组合加速比中位数：对清理前EXP129，z2d/d2z均1.000；对EXP125保留版，'
            'z2d=1.260827，d2z=1.286293。逐项退化及漂移保留，不声称版本差异为纯融合收益。'
            '用户已授权服务器稳定分支、新标签及云端推送。新标签'+TAG+'，保留旧标签和两条历史；'
            '发布计算树与实际构建'+BUILD_SOURCE+'一致。验收记录：'+str(AUDIT.relative_to(ROOT))
            +'；发布记录：'+str(RECORD.relative_to(ROOT))+'。\n')
    paths = [agents_path, registry_path, direction, RECORD, AUDIT,
        ROOT/'experiments/EXP-129/scripts/audit_stable_release_results.py',
        ROOT/'experiments/EXP-129/scripts/push_stable_release.py', Path(__file__)]
    commit(paths, 'EXP129：完整验收通用CC融合并登记新稳定版本')
    accepted_head = git('rev-parse', 'HEAD')
    # Restage exact historical blobs without overwriting local historical edits.
    git('restore', '--source=main', '--staged', '--', *historical)
    tree = git('write-tree')
    merge = git('commit-tree', tree, '-p', accepted_head, '-p', OLD_MAIN,
        '-m', '合并稳定历史，保留完整验收的EXP129通用CC源码与当前测量规则')
    assert git('rev-parse', merge+':'+SOURCE) == source_tree
    assert git('rev-parse', merge+':VkFFT') == gitlink
    git('merge-base', '--is-ancestor', OLD_MAIN, merge)
    transaction = ('start\nupdate refs/heads/'+BRANCH+' '+merge+' '+accepted_head
        +'\nupdate refs/heads/main '+merge+' '+OLD_MAIN+'\nprepare\ncommit\n')
    git('update-ref', '--stdin', input=transaction)
    git('tag', '-a', TAG, merge, '-m', 'EXP129通用CC前后处理融合稳定版：完整数值、路径、内存、回调、边界及性能验收通过')
    assert git('rev-parse', 'HEAD') == git('rev-parse', 'main') == git('rev-parse', TAG+'^{}') == merge
    assert not git('diff', '--cached', '--name-only')
    assert set(old_tags.splitlines()).issubset(set(git('show-ref', '--tags', '-d').splitlines()))
    assert git('branch', '--show-current') == BRANCH
    assert sha(Path(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256']
    result = dict(local_promotion_complete=True, stable_commit=merge, stable_tag=TAG,
        tag_object=git('rev-parse', TAG), stable_branch='main', experiment_branch=BRANCH,
        checked_out_branch=BRANCH, build_source_commit=BUILD_SOURCE, source_tree=source_tree,
        source_subtree_identical_to_accepted_build=True, old_tags_unchanged=True,
        historical_records_retained=len(historical), manual_agents_rules_preserved=True,
        unrelated_vkfft_changes_preserved=True, new_gpu_jobs_submitted=False, cloud_push_done=False)
    write(RECORD/'commit-result.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
