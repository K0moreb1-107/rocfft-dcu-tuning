"""Workspace paths for tools; historical evidence is never edited in place."""
from datetime import datetime
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent

def result_directory(task):
    run_id = os.environ.get("SLURM_JOB_ID") or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = ROOT / "results" / task / (run_id + "_" + str(os.getpid()))
    path.mkdir(parents=True, exist_ok=False)
    return path

def prepare_legacy_csv(task, filename):
    path = ROOT / "results" / task / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    old = ROOT / "archives/unclassified/evidence" / filename
    if not path.exists() and old.is_file():
        shutil.copy2(old, path)
    return path
