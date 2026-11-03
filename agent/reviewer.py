"""reviewer 子 agent：只读、固定清单、只回最后一条消息。

为什么要隔离：主 agent 的上下文是预算。让子 agent 去啃完整 diff，
主上下文只收一行结论 —— 这是「子 agent 的价值就在这一行」。

工具只给两个：
  read(path)            —— 只能读工作区内的文件
  bash("git diff ...")  —— 只放行 git diff / git show / git status

检查清单固定五条，不让模型自由发挥：
  1. 有没有改到不该改的文件  2. 有没有新增依赖  3. 有没有 except: pass
  4. 新逻辑有没有测试覆盖    5. 有没有调试残留（print( / TODO / breakpoint()）
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent.gitutil import git_exe
from agent.skills import estimate_tokens

CHECKLIST = [
    "有没有改到不该改的文件（配置 / 锁文件 / 别人的模块）",
    "有没有新增依赖（requirements.txt / pyproject.toml 被动过）",
    "有没有 except: pass 或吞掉异常",
    "新逻辑有没有被测试覆盖（改了源码但没动测试）",
    "有没有调试残留（print( / TODO / breakpoint()）",
]

BAD_FILES = ("requirements.txt", "pyproject.toml", "package-lock.json",
             "poetry.lock", "Pipfile.lock", ".env")
CODE_EXT = (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java")


@dataclass
class ReviewResult:
    issues: List[str] = field(default_factory=list)
    final_message: str = ""
    subagent_tokens: int = 0
    main_context_delta: int = 0
    changed_files: List[str] = field(default_factory=list)
    runs: int = 1


class Reviewer:
    """一个独立的、只读的审查者。主 agent 只拿它最后那条消息。"""

    def __init__(self, root: Path, target: str = "HEAD"):
        self.root = Path(root)
        self.target = target
        self.evidence: List[str] = []
        self.tool_calls: List[Dict[str, str]] = []

    # ------------------------------------------------------------ 只读工具
    def tool_bash(self, command: str) -> str:
        if not re.match(r"^\s*git\s+(diff|show|status|log)\b", command):
            return "拒绝：reviewer 的 bash 只允许 git diff / git show / git status / git log"
        self.tool_calls.append({"tool": "bash", "arg": command})
        argv = shlex.split(command)
        argv[0] = git_exe()          # Windows 上 git 常常不在 PATH
        try:
            p = subprocess.run(argv, cwd=str(self.root),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60)
            out = (p.stdout or "") + (p.stderr or "")
        except Exception as e:
            out = f"命令失败：{e}"
        self.evidence.append(out)
        return out

    def tool_read(self, path: str) -> str:
        self.tool_calls.append({"tool": "read", "arg": path})
        p = (self.root / path).resolve()
        try:
            p.relative_to(self.root.resolve())
        except ValueError:
            return "拒绝：路径越界"
        if not p.is_file():
            return f"没有这个文件：{path}"
        text = p.read_text(encoding="utf-8", errors="replace")
        self.evidence.append(text)
        return text

    # ------------------------------------------------------------ 审查
    def _collect(self) -> Tuple[str, List[str]]:
        diff = self.tool_bash(f"git -C . show --unified=1 --no-color {self.target}")
        stat = self.tool_bash(f"git -C . show --stat --oneline {self.target}")
        files = []
        for ln in stat.splitlines():
            if "|" in ln:
                files.append(ln.split("|")[0].strip())
        return diff, files

    def _analyze(self, diff: str, files: List[str]) -> List[str]:
        issues: List[str] = []
        added = [ln[1:] for ln in diff.splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")]

        # 1. 不该改的文件
        for f in files:
            name = f.rsplit("/", 1)[-1]
            if name in BAD_FILES or name.endswith((".lock", ".pem", ".key")) or name.startswith(".env"):
                issues.append(f"{f} → 这类文件通常不该手改（依赖/密钥/锁文件）→ 还原它，用命令重新生成")

        # 2. 新增依赖
        for ln in added:
            if re.match(r"^\s*[A-Za-z0-9_.\-]+\s*[=><~!]=?\s*\d", ln) and any(
                    f.endswith(("requirements.txt", "pyproject.toml")) for f in files):
                issues.append(f"{ln.strip()[:40]} → 新增依赖 → 确认真的需要，能标准库解决就别加")
                break

        # 3. 吞异常
        for i, ln in enumerate(added):
            if re.search(r"except[^:]*:\s*pass", ln) or re.search(r"except\s+Exception\s*:\s*pass", ln):
                issues.append(f"新增代码里有 `except: pass` → 吞掉异常 → 至少 log 或抛 AppError")
                break

        # 4. 改了源码没改测试
        src = [f for f in files if f.endswith(CODE_EXT) and "test" not in f.lower()]
        tst = [f for f in files if "test" in f.lower()]
        if src and not tst:
            issues.append(f"{src[0]} → 改了源码但没动测试 → 至少补一条覆盖新分支的用例")

        # 5. 调试残留
        for ln in added:
            if re.search(r"\bprint\(|\bTODO\b|breakpoint\(\)|\bpdb\.set_trace", ln):
                issues.append(f"{ln.strip()[:60]} → 调试残留 → 提交前删掉或换成日志")
                break

        # 去重，最多 5 条
        seen, out = set(), []
        for x in issues:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out[:5]

    def run(self) -> ReviewResult:
        diff, files = self._collect()
        if not diff.strip():
            return ReviewResult(issues=[], final_message="没发现改动（diff 为空）。",
                                changed_files=[], runs=1,
                                subagent_tokens=estimate_tokens("".join(self.evidence)))
        issues = self._analyze(diff, files)

        if issues:
            msg = f"审查完成：{len(issues)} 个问题\n" + "\n".join(
                f"{i}. {x}" for i, x in enumerate(issues, 1))
        else:
            msg = "审查完成：没发现问题（五条清单逐条看过）。"

        sub_tokens = estimate_tokens("".join(CHECKLIST) + "".join(self.evidence))
        return ReviewResult(
            issues=issues, final_message=msg, changed_files=files,
            subagent_tokens=sub_tokens,
            main_context_delta=estimate_tokens(msg),
            runs=1,
        )
