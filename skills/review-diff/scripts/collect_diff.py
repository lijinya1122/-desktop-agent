"""收集当前改动的 diff 摘要，供 review-diff 技能使用。

用法：
    python skills/review-diff/scripts/collect_diff.py            # 未提交的改动
    python skills/review-diff/scripts/collect_diff.py --staged    # 暂存区
    python skills/review-diff/scripts/collect_diff.py --last      # 最近一次提交

输出刻意压到 40 行以内：技能要的是「改了什么」，不是整份 diff。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

MAX_LINES = 40
SKIP_SUFFIX = (".lock", ".png", ".jpg", ".zip", ".exe", ".pyc")


def _git() -> str:
    """技能要能带走，所以不 import 仓库里的模块，自己找一遍 git。"""
    p = shutil.which("git")
    if p:
        return p
    for c in (r"C:\Program Files\Git\bin\git.exe",
              r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\bin\git.exe"):
        if Path(c).is_file():
            return c
    return "git"


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        return p.stdout or p.stderr
    except Exception as e:
        return f"[collect_diff] 命令失败：{e}"


def main() -> int:
    args = set(sys.argv[1:])
    root = Path(__file__).resolve().parents[3]
    git = [_git(), "-C", str(root), "--no-pager"]

    if "--last" in args:
        stat = run(git + ["show", "--stat", "--oneline", "HEAD"])
        diff = run(git + ["show", "--unified=1", "--no-color", "HEAD"])
        scope = "最近一次提交"
    elif "--staged" in args:
        stat = run(git + ["diff", "--stat", "--cached"])
        diff = run(git + ["diff", "--unified=1", "--no-color", "--cached"])
        scope = "暂存区"
    else:
        stat = run(git + ["diff", "--stat"])
        diff = run(git + ["diff", "--unified=1", "--no-color"])
        scope = "未提交改动"
        if not diff.strip():
            stat = run(git + ["show", "--stat", "--oneline", "HEAD"])
            diff = run(git + ["show", "--unified=1", "--no-color", "HEAD"])
            scope = "未提交改动（工作区干净，改看最近一次提交）"

    files = [ln for ln in stat.splitlines()
             if "|" in ln and not ln.strip().endswith((".lock",))]
    skipped = [f for f in files if f.split("|")[0].strip().endswith(SKIP_SUFFIX)]
    files = [f for f in files if f not in skipped]

    lines = [f"[collect_diff] 范围：{scope}",
             f"[collect_diff] 改动文件 {len(files)} 个："]
    lines += [f"  {f.strip()}" for f in files[:20]]

    body = [ln for ln in diff.splitlines() if ln.startswith(("+", "-", "@@", "diff "))
            and not ln.startswith(("+++", "---"))]
    lines.append(f"[collect_diff] 关键改动（{len(body)} 行，已截断到 {MAX_LINES} 行）：")
    lines += body[:MAX_LINES]
    if len(body) > MAX_LINES:
        lines.append(f"… 还有 {len(body) - MAX_LINES} 行未显示（需要就看具体文件）")
    if skipped:
        lines.append(f"[collect_diff] 已跳过二进制/锁文件 {len(skipped)} 个")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
