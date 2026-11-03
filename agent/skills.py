"""技能系统：目录常驻，正文按需加载（渐进披露）。

规则只有三条：
  1. 启动时只读每个 SKILL.md 的 YAML 头（name + description），正文不进上下文；
  2. 模型判断需要用时，调 use_skill(name)，正文这时才注入；
  3. 触发靠 description 里的触发语，不靠目录名猜。

为什么：20 个技能全塞进去是 2 万 token，每轮都要重付；只放目录是 800 token。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SKILL_FILE = "SKILL.md"


def enabled() -> bool:
    """开关：ENABLE_SKILLS=0 时整层关掉（验收会现场关掉跑一遍）。"""
    return os.environ.get("ENABLE_SKILLS", "1") not in ("0", "false", "False", "")


def estimate_tokens(text: str) -> int:
    """粗估 token：中日韩字符按 1 字 ≈ 1.5 token 的倒数算，其余按 4 字符 1 token。"""
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = max(0, len(text) - cjk)
    return int(cjk / 1.5 + other / 4) + 1


def _split_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    """拆出 --- 包起来的 YAML 头（只支持 key: value 这种最简形式）。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    head, body = parts[1], parts[2]
    meta: Dict[str, str] = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body.lstrip("\n")


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    has_scripts: bool = False
    uses_mcp: bool = False

    @property
    def dir(self) -> Path:
        return self.path.parent

    def header_tokens(self) -> int:
        return estimate_tokens(f"- {self.name}: {self.description}")

    def full_text(self) -> str:
        return self.body


def _triggers(description: str) -> List[str]:
    """从 description 里挖触发语：引号里的短语 + 「Use this when」后面那串。"""
    out: List[str] = []
    for m in re.finditer(r"[\"“「]([^\"”」]{2,30})[\"”」]", description):
        out.append(m.group(1))
    tail = ""
    for kw in ("Use this when", "use this when", "适用", "当用户"):
        i = description.find(kw)
        if i >= 0:
            tail = description[i + len(kw):]
            break
    if tail:
        for piece in re.split(r"[、,，;；/。\s]+", tail):
            piece = piece.strip(" ：:。\"“”「」")
            if 2 <= len(piece) <= 20:
                out.append(piece)
    # 去重且保序
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


@dataclass
class SkillRegistry:
    skills: Dict[str, Skill] = field(default_factory=dict)
    roots: List[Path] = field(default_factory=list)

    # ---------------------------------------------------------------- 载入
    @classmethod
    def load(cls, workspace: Optional[Path] = None,
             extra_roots: Optional[List[Path]] = None) -> "SkillRegistry":
        roots: List[Path] = []
        if extra_roots:
            roots.extend(extra_roots)
        # 项目级：仓库根的 skills/
        here = Path(__file__).resolve().parent.parent
        roots.append(here / "skills")
        # 用户级：~/.desktop-agent/skills（换项目也带走）
        roots.append(Path.home() / ".desktop-agent" / "skills")
        if workspace:
            roots.append(Path(workspace) / "skills")

        reg = cls(roots=[r for r in roots if r.exists()])
        for root in reg.roots:
            for md in sorted(root.glob(f"*/{SKILL_FILE}")):
                try:
                    meta, body = _split_front_matter(md.read_text(encoding="utf-8"))
                except Exception:
                    continue
                name = meta.get("name") or md.parent.name
                desc = meta.get("description", "").strip()
                if not name or not desc:
                    continue
                has_scripts = (md.parent / "scripts").is_dir() or "scripts/" in body
                uses_mcp = ("mcp_" in body) or ("MCP" in body.upper() and "mcp" in body.lower())
                reg.skills[name] = Skill(
                    name=name, description=desc, body=body.strip(),
                    path=md, has_scripts=has_scripts, uses_mcp=uses_mcp,
                )
        return reg

    # ---------------------------------------------------------------- 目录
    def catalog(self) -> str:
        return "\n".join(f"- {s.name}: {s.description}" for s in self.skills.values())

    def catalog_tokens(self) -> int:
        return estimate_tokens(self.catalog())

    def full_tokens(self) -> int:
        return estimate_tokens("\n\n".join(s.full_text() for s in self.skills.values()))

    def disclosure_ratio(self) -> float:
        c = self.catalog_tokens()
        return round(self.full_tokens() / c, 1) if c else 0.0

    def get(self, name: str) -> Optional[Skill]:
        return self.skills.get(name) or self.skills.get(name.strip().lower())

    def load_body(self, name: str) -> str:
        """渐进披露的第二步：只有这一步才把正文交出去。"""
        s = self.get(name)
        if not s:
            names = "、".join(self.skills) or "（没有技能）"
            return f"没有这个技能：{name}。已有：{names}"
        return (f"技能 {s.name} 正文已加载，按下面的步骤执行，不要跳步：\n\n"
                f"{s.full_text()}")

    def schemas(self) -> List[Dict[str, object]]:
        return [{
            "type": "function",
            "function": {
                "name": "use_skill",
                "description": (
                    "加载某个技能的完整步骤（正文）。目录里只有名字和一句话描述；"
                    "判断需要用它时再调用，一次只加载一个。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string",
                                 "description": "技能名，必须来自技能目录"},
                    },
                    "required": ["name"],
                },
            },
        }]

    # ---------------------------------------------------------------- 匹配
    def match(self, query: str) -> Tuple[Optional[Skill], int]:
        """按 description 里的触发语打分（不看目录名）。返回 (技能, 命中长度)。"""
        best: Optional[Skill] = None
        best_len = 0
        q = query.lower()
        for s in self.skills.values():
            for t in _triggers(s.description):
                if t.lower() in q and len(t) > best_len:
                    best, best_len = s, len(t)
        return best, best_len
