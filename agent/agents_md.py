"""AGENTS.md：进门就懂这个仓库。

两段拼起来，顺序固定为「全局 → 项目」：
  全局：~/.desktop-agent/AGENTS.md   （我的口味，换项目也带着）
  项目：从工作区往上找到的第一份 AGENTS.md （这个仓库怎么跑、哪里有坑）

纪律：这是「地图」，不是文档。≤300 行，不贴代码片段。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from agent.skills import estimate_tokens

MAX_BYTES = 12000           # 约 300 行；超了说明在写文档，不是在写地图


def enabled() -> bool:
    return os.environ.get("ENABLE_AGENTS_MD", "1") not in ("0", "false", "False", "")


def global_path() -> Path:
    return Path.home() / ".desktop-agent" / "AGENTS.md"


def find_project(start: Path) -> Optional[Path]:
    """从 start 往上找 AGENTS.md，找最近的一份。"""
    try:
        p = Path(start).resolve()
    except Exception:
        return None
    for cur in [p, *p.parents]:
        f = cur / "AGENTS.md"
        if f.is_file():
            return f
    return None


@dataclass
class AgentsMd:
    found: bool = False
    bytes: int = 0
    layers: List[str] = field(default_factory=list)
    text: str = ""
    paths: List[str] = field(default_factory=list)

    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def prompt_block(self) -> str:
        if not self.text.strip():
            return ""
        warn = ""
        if self.bytes > MAX_BYTES:
            warn = (f"\n（注意：AGENTS.md 共 {self.bytes} 字节，超过 {MAX_BYTES} 的建议上限，"
                    f"说明它正在变成文档，应该只留「怎么跑」和「哪里有坑」。）")
        return (f"<agents_md>\n以下是这个仓库的约定（全局 → 项目），先遵守它再动手：\n"
                f"{self.text.strip()}\n</agents_md>{warn}")


def load(workspace: Path, with_global: bool = True) -> AgentsMd:
    """读两层：全局 + 项目。任何一层都没有就是 found=False。"""
    out = AgentsMd()
    chunks: List[str] = []

    if with_global:
        g = global_path()
        if g.is_file():
            try:
                t = g.read_text(encoding="utf-8")
                chunks.append(f"<!-- 全局：{g} -->\n{t.strip()}")
                out.layers.append("global")
                out.paths.append(str(g))
            except Exception:
                pass

    proj = find_project(Path(workspace))
    if proj is not None:
        try:
            t = proj.read_text(encoding="utf-8")
            chunks.append(f"<!-- 项目：{proj} -->\n{t.strip()}")
            out.layers.append("project")
            out.paths.append(str(proj))
        except Exception:
            pass

    out.text = "\n\n".join(chunks)
    out.found = bool(chunks)
    out.bytes = len(out.text.encode("utf-8"))
    return out
