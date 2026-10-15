"""Exercise the actual final-report expression without building or using a GPU."""
import ast
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path('/public/home/zhangkewei/zr')
SCRIPT=ROOT/'experiments/EXP-127/scripts/validate_cc_fusion_ab.py'
PRIOR='59f93beacd40fa23b3932382fd4f6a2bdac5c32a'


def reporting(source,record,fused):
    tree=ast.parse(source);scope=dict(json=json,record=record,fused=fused)
    helper=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='completion_summary'),None)
    if helper:
        exec(compile(ast.Module(body=[helper],type_ignores=[]),str(SCRIPT),'exec'),scope)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    outputs=[n for n in ast.walk(main) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
             and isinstance(n.value.func,ast.Name) and n.value.func.id=='print']
    assert len(outputs)==1
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        exec(compile(ast.Module(body=outputs,type_ignores=[]),str(SCRIPT),'exec'),scope)
    return json.loads(stream.getvalue())


class Reporting(unittest.TestCase):
    def setUp(self):
        self.record=dict(cases=[{}]*24,guards=[{}]*48,controls=[{}]*18)

    def test_original_failure_is_reproduced(self):
        source=subprocess.check_output(['git','-C',str(ROOT),'show',
            PRIOR+':experiments/EXP-127/scripts/validate_cc_fusion_ab.py'],text=True)
        with self.assertRaisesRegex(TypeError,'flush'):
            reporting(source,self.record,False)

    def test_both_fusion_modes_serialize_and_print(self):
        for fused in (False,True):
            with self.subTest(fused=fused):
                result=reporting(SCRIPT.read_text(),self.record,fused)
                self.assertEqual(result,dict(complete=True,fusion_enabled=fused,cases=24,
                    independent_references=672,executions=1344))

    def test_folded_regressions_are_in_reference_totals(self):
        self.record['folded_load_regressions']=[dict(guards=[{},{}]) for _ in range(10)]
        result=reporting(SCRIPT.read_text(),self.record,True)
        self.assertEqual(result['independent_references'],952)
        self.assertEqual(result['executions'],1904)

    def test_result_output_precedes_complete_flag(self):
        tree=ast.parse(SCRIPT.read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        guarded=next(n for n in main.body if isinstance(n,ast.Try))
        self.assertIsInstance(guarded.body[-2],ast.Expr)
        self.assertEqual(guarded.body[-2].value.func.id,'print')
        self.assertIsInstance(guarded.body[-1],ast.Assign)
        self.assertTrue(guarded.body[-1].value.value)

    def test_no_flush_keyword_in_json_encoding(self):
        tree=ast.parse(SCRIPT.read_text())
        for call in (n for n in ast.walk(tree) if isinstance(n,ast.Call)):
            if isinstance(call.func,ast.Attribute) and call.func.attr in ('dump','dumps'):
                self.assertNotIn('flush',[n.arg for n in call.keywords])


if __name__=='__main__':
    unittest.main()
