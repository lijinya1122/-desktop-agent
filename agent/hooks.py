"""Hooks：软的写成硬的。

三条规则（都是代码，不是提示词里的一句话）：
  PreToolUse  写 .env / *.pem / *.key        → 拒绝，理由：密钥不入库
  PreToolUse  rm -rf / git push -f / reset --hard → 拒绝，并给替代方案
  PostToolUse write / edit 之后               → 自动跑测试，只回「失败摘要」三行

第三条的要点是「摘要」：回注 80 行 traceback 会把上下文挤爆，只回三行。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SECRET_SUFFIX = (".env", ".pem", ".key", ".p12", ".pfx", ".keystore")
SECRET_NAMES = ("id_rsa", "id_ed25519", ".env.local", ".env.production", "credentials")

DANGEROUS = [
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r|\brm\s+-rf\b",
     "rm -rf 会不可逆地删文件。先 `git clean -nd` 看一眼会删什么，"
     "或者用 `git restore <path>` / `git stash` 恢复，别直接删目录。"),
    (r"\bgit\s+push\s+.*(--force|-f)\b",
     "强推会覆盖远端别人的提交。用 `git revert <sha>` 造一个新提交，"
     "或 `git push --force-with-lease` 至少要确认远端没人动过。"),
    (r"\bgit\s+reset\s+--hard\b",
     "hard reset 会丢掉未提交的改动。用 `git stash` 先存起来，"
     "或 `git restore --staged` 只取消暂存。"),
    (r"\bgit\s+clean\s+-[a-z]*x[a-z]*f",
     "clean -xf 会删掉未跟踪文件。先 `git clean -nd` 预览。"),
    (r"\bdel\s+/s\s+/q|\bformat\s+[a-z]:|\bdiskpart\b",
     "这是系统级删除/格式化，工具层不允许执行。请说明目的，改用文件级操作。"),
]


def enabled() -> bool:
    """开关：ENABLE_HOOKS=0 时整层关掉（验收会现场关掉跑一遍）。"""
    return os.environ.get("ENABLE_HOOKS", "1") not in ("0", "false", "False", "")


def _is_secret_path(path: str) -> bool:
    p = path.replace("\\", "/").lower().strip()
    name = p.rsplit("/", 1)[-1]
    if name in SECRET_NAMES:
        return True
    return any(name.endswith(suf) for suf in SECRET_SUFFIX)


def pre_tool(name: str, args: Dict[str, object]) -> Optional[str]:
    """返回拒绝理由（非空即拒绝）。返回 None 表示放行。"""
    if not enabled():
        return None

    if name in ("write", "edit"):
        path = str(args.get("path", ""))
        if _is_secret_path(path):
            return ("密钥不入库：不写 .env / *.pem / *.key。"
                    "Key 放环境变量或本机 ~/.desktop-agent/settings.json（已在 .gitignore 里）。")

    if name == "bash":
        cmd = str(args.get("command", ""))
        for pattern, advice in DANGEROUS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return f"这条命令被 hook 拦下（不可逆操作）：{advice}"

    return None


# ---------------------------------------------------------------- 自动测试
def _guess_cmd(cwd: Path) -> Optional[str]:
    env = os.environ.get("AGENT_AUTOTEST_CMD")
    if env:
        return env
    if (cwd / "test_stats.py").is_file():
        return "python test_stats.py"
    if any(cwd.glob("test_*.py")) or (cwd / "tests").is_dir():
        return "python -m pytest -q --tb=no"
    return None


def _summarize(stdout: str, stderr: str, code: int) -> Tuple[int, int, List[str]]:
    """从输出里数出红/绿，并挑最多 2 行失败信息。"""
    text = (stdout or "") + "\n" + (stderr or "")
    reds = re.findall(r"^\s*(?:FAIL|FAILED|ERROR|FAIL:)\s*[:]?\s*(\S+)", text, re.M)
    greens = re.findall(r"^\s*(?:PASS|PASSED|ok)\s*[:]?\s*(\S+)", text, re.M)
    red = len(reds) if reds else (1 if code != 0 else 0)
    green = len(greens)
    fails: List[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^(FAIL|ERROR|AssertionError|E\s+assert)", s) or "AssertionError" in s:
            fails.append(s[:120])
        if len(fails) >= 2:
            break
    return red, green, fails


def run_autotest(cwd: Path, cmd: Optional[str] = None,
                 timeout: int = 90) -> Optional[Dict[str, object]]:
    """跑一次测试，返回真实结果；没有可跑的测试就返回 None。"""
    command = cmd or _guess_cmd(Path(cwd))
    if not command:
        return None
    try:
        p = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        code = p.returncode
        out, err = p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return {"cmd": command, "ok": False, "red": 1, "green": 0,
                "fails": [f"测试命令超过 {timeout}s 被终止"], "code": None}
    except Exception as e:
        return {"cmd": command, "ok": False, "red": 1, "green": 0,
                "fails": [f"测试命令无法执行：{e}"], "code": None}
    red, green, fails = _summarize(out, err, code)
    return {"cmd": command, "ok": code == 0, "red": red, "green": green,
            "fails": fails, "code": code}


def post_tool(name: str, args: Dict[str, object], ok: bool,
              cwd: Path) -> Optional[str]:
    """写操作之后自动跑测试，返回要回注给模型的「三行摘要」。"""
    if not enabled() or not ok or name not in ("write", "edit"):
        return None
    res = run_autotest(Path(cwd))
    if res is None:
        return None
    if res["ok"]:
        return f"[自动测试] {res['cmd']} → 通过（{res['green']} 绿）"
    head = f"[自动测试] {res['cmd']} → 失败：{res['red']} 红 / {res['green']} 绿"
    lines = [head] + [f"  {f}" for f in (res["fails"] or [])][:2]
    lines.append("  先照着失败信息改，不要删测试或改断言。")
    return "\n".join(lines)
