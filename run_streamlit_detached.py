from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "work"
LOG_DIR.mkdir(exist_ok=True)

cmd = [
    sys.executable,
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
creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
process = subprocess.Popen(
    cmd,
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL,
    stdout=stdout,
    stderr=stderr,
    creationflags=creationflags,
)
print(process.pid)
