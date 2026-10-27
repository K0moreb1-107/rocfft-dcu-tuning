"""Reuse numerical/actual CC checks and verify the range-safe phase parameters."""
import json
from pathlib import Path
import re
import sys

ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT/'experiments/EXP-128/scripts'))
import validate_cc_local_boundary as boundary
from tools.workspace_manager import manager as mgr

MODEL=ROOT/'experiments/EXP-128/records/unfused-phasefix-20261027/phase-selector-model.json'


def column_phase(column,expected):
    match=re.search(r'_twdbase(\d+)_(\d+)step',column)
    mgr.require(match and tuple(map(int,match.groups()))==(expected['base'],expected['steps']),
                'actual column phase parameters differ: '+column)
    return dict(base=expected['base'],steps=expected['steps'],
        original_selection_failed=expected['old']['status']=='ERROR')


def main():
    proof=json.loads(MODEL.read_text());mgr.require(proof['complete'],'phase preflight incomplete')
    expected={x['N']:x for x in proof['catalog']}
    trace=boundary.trace_case
    def checked(binary,case,func,env,folder,fused):
        mgr.require(not fused,'phase-fix validation is for the unfused control')
        numerical,dispatch=trace(binary,case,func,env,folder,fused)
        column=dispatch['actual_names'][1 if func=='z2d_1d' else 0]
        e=expected[case['N']]
        dispatch['column_phase']=column_phase(column,e)
        return numerical,dispatch
    boundary.trace_case=checked
    boundary.main()


if __name__=='__main__':main()
