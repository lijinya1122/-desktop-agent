"""git 可执行文件定位。

Windows 上装了 Git 也常常不在 PATH 里（安装器默认只加 Git Bash 的路径），
所以所有调 git 的地方都走这里，不要直接写 "git"。
"""

from __future__ import annotations

import shutil
from pathlib import Path

_CANDIDATES = (
    r"C:\Program Files\Git\bin\git.exe",
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\bin\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
    "/usr/bin/git",
    "/usr/local/bin/git",
)


def git_exe() -> str:
    p = shutil.which("git")
    if p and Path(p).is_file():
        return p
    for c in _CANDIDATES:
        if Path(c).is_file():
            return c
    return "git"


def available() -> bool:
    from subprocess import run
    try:
        return run([git_exe(), "--version"], capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False
