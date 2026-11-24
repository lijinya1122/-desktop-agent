"""一条命令跑完所有检查（第 1 讲 P13 第 03 件：就一条，写进 AGENTS.md 第一行）。

    python -m app.check        # 样式(5s) -> 自检(10s) -> 冒烟(15s)，全绿退出码 0

这命令同时是 readiness 体检里「一条命令跑测试」那根柱子的证据。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

STEPS = [
    ("样式与校验", [PY, "-X", "utf8", str(ROOT / "scripts" / "check_style.py")]),
    ("自检 13 项", [PY, "-X", "utf8", str(ROOT / "scripts" / "selftest.py")]),
    ("工作区冒烟 8 项", [PY, "-X", "utf8", str(ROOT / "scripts" / "smoke_ws.py")]),
]


def main() -> int:
    total0 = time.time()
    failed = 0
    for name, cmd in STEPS:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        dt = time.time() - t0
        ok = r.returncode == 0
        failed += 0 if ok else 1
        tail = (r.stdout or r.stderr).strip().splitlines()
        tail = tail[-1] if tail else ""
        print(f"[{'OK ' if ok else 'FAIL'}] {name}（{dt:.1f}s）{tail}")
    print(f"---- 一条命令总耗时 {time.time() - total0:.1f}s，"
          f"{'全部通过' if failed == 0 else f'{failed} 项失败'} ----")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
