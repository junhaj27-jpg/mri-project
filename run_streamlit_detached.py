from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "work"
LOG_DIR.mkdir(exist_ok=True)
VENV = ROOT / ".venv"
SITE_PACKAGES = VENV / "Lib" / "site-packages"
BASE_PYTHON = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe"
PYTHON = BASE_PYTHON if BASE_PYTHON.exists() else Path(sys.executable)

cmd = [
    str(PYTHON),
    "-m",
    "streamlit",
    "run",
    "app.py",
    "--server.port",
    "8501",
    "--server.headless=true",
    "--server.fileWatcherType=none",
    "--browser.gatherUsageStats=false",
]

stdout = (LOG_DIR / "streamlit.out.log").open("a", encoding="utf-8")
stderr = (LOG_DIR / "streamlit.err.log").open("a", encoding="utf-8")
env = os.environ.copy()
env["PYTHONPATH"] = str(SITE_PACKAGES) + os.pathsep + str(VENV) + os.pathsep + env.get("PYTHONPATH", "")
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
