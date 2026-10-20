"""Replay the actual generic callback check from a validator's syntax tree."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace


def require(value, message):
    if not value:
        raise ValueError(message)


def replay(validator, folder, geometry, func, inspector=None):
    tree=ast.parse(Path(validator).read_text())
    guard=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='guard_case')
    checked=next(n for n in ast.walk(guard) if isinstance(n,ast.If)
                 and isinstance(n.test,ast.Subscript) and ast.unparse(n.test)=="chosen['generic']")
    sources=lambda text:dict(re.findall(r'^// ROCFFT_RTC_BEGIN ([^\n]+)\n(.*?)^// ROCFFT_RTC_END \1$',text,re.M|re.S))
    namespace=dict(geometry=geometry,func=func,chosen=geometry['leaves'][0 if func=='z2d_1d' else 1],
        plan=(Path(folder)/'plan.txt').read_text(),gfolder=Path(folder),old=SimpleNamespace(rtc_sources=sources),
        mgr=SimpleNamespace(require=require),re=re,inspect_callback_sources=inspector)
    exec(compile(ast.Module(body=[checked],type_ignores=[]),str(validator),'exec'),namespace)
    return dict(complete=True,N=geometry['N'],func=func)
