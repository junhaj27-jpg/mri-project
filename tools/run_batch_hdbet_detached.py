from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
SITE_PACKAGES = VENV / "Lib" / "site-packages"
BASE_PYTHON = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe"
PYTHON = BASE_PYTHON if BASE_PYTHON.exists() else Path(sys.executable)
LOG_DIR = ROOT / "work"
LOG_DIR.mkdir(exist_ok=True)

cmd = [
    str(PYTHON),
    str(ROOT / "tools" / "batch_hdbet_14.py"),
]

env = os.environ.copy()
env["PYTHONPATH"] = str(SITE_PACKAGES) + os.pathsep + str(VENV) + os.pathsep + env.get("PYTHONPATH", "")
stdout = (LOG_DIR / "batch_hdbet_14.out.log").open("a", encoding="utf-8")
stderr = (LOG_DIR / "batch_hdbet_14.err.log").open("a", encoding="utf-8")
creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
process = subprocess.Popen(
    cmd,
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL,
    stdout=stdout,
    stderr=stderr,
    env=env,
    creationflags=creationflags,
)
print(process.pid)
