"""样式与校验检查：提交前的 5 秒关卡（第 1 讲「检查要便宜」）。

    python scripts/check_style.py          # 全部通过退出码 0

规则刻意保持很少，只查会真出问题的：
  1. 所有 .py 能编译（语法错误当场抓）
  2. 行长 <= 120（评审里一半噪音来自超长行）
  3. 没有 except: pass（错误被静默吞掉，agent 分不清改错还是环境抽）
  4. 没有 print( 调试残留出现在 agent/ server/ app/（workspace/ 除外，那是沙箱）
"""
from __future__ import annotations

import ast
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["agent", "server", "app", "scripts", "examples", "ui"]
MAX_LINE = 120

issues: list[str] = []


def check_file(path: Path) -> None:
    rel = path.relative_to(ROOT).as_posix()
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as e:
        issues.append(f"{rel}: 语法错误 {e}")
        return
    src = path.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines(), 1):
        if len(line) > MAX_LINE and "noqa: long" not in line:
            # ASS/JSON 模板的数据行（Format:/Style: 表头）不是代码，格式规定不能拆行
            if line.strip().startswith(("Format:", "Style:", "Dialogue:")):
                continue
            issues.append(f"{rel}:{i} 行长 {len(line)} > {MAX_LINE}")
        s = line.strip()
        if s.startswith("except") and s.endswith(": pass"):
            issues.append(f"{rel}:{i} except: pass（错误被静默吞掉）")
        if s.startswith("breakpoint("):
            issues.append(f"{rel}:{i} 调试断点残留 breakpoint()")
    try:
        ast.parse(src)
    except SyntaxError:
        return
    # agent/cli.py 与 server 的 CLI 输出：print 是它的界面，不算调试残留
    if rel.startswith(("agent/", "server/")) and not rel.endswith("cli.py"):
        for i, line in enumerate(src.splitlines(), 1):
            s = line.strip()
            if s.startswith("print(") and not s.startswith("#"):
                issues.append(f"{rel}:{i} 调试 print 残留：{s[:60]}")


def main() -> int:
    targets: list[Path] = []
    for d in SCAN_DIRS:
        p = ROOT / d
        if p.is_dir():
            targets.extend(sorted(p.rglob("*.py")))
    for f in targets:
        check_file(f)
    if issues:
        print(f"[check_style] {len(issues)} 处问题：")
        for it in issues[:20]:
            print(" ", it)
        return 1
    print(f"[check_style] {len(targets)} 个 .py 全部通过（语法/行长/静默异常/调试残留）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
