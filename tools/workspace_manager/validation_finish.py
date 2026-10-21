"""Finish acceptance against the actual library and allocated device."""
import json
import subprocess
from tools.workspace_manager import manager as mgr


def finish(record, built, gpu, env, library, identity_binary):
    mgr.require(mgr.common.sha(library) == built['arm']['library_sha256'],
                'validation library differs from build')
    actual = json.loads(subprocess.check_output([str(identity_binary)], env=env, text=True))
    mgr.require(actual == gpu, 'allocated validation device changed')
    record['complete'] = True
