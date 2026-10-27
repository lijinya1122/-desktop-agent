"""命令行入口：agent/ 能脱离界面单独跑 —— 这是评审第一眼看的。

    python -m agent.cli "让 mean 对空列表抛 ValueError，然后跑测试"
    python -m agent.cli --mock            # 离线回放，不需要 Key
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict

from agent.config import Settings, load_mcp_config, resource
from agent.loop import AgentLoop
from agent.mcp import MCPManager


async def main_async(task: str, use_mock: bool, with_mcp: bool, out: str = "") -> int:
    s = Settings.load()
    mcp = MCPManager()
    if with_mcp:
        await mcp.load(load_mcp_config(), resource("."))
        print("MCP:", json.dumps(mcp.summary(), ensure_ascii=False))

    llm = None
    if use_mock:
        from agent.mock import MockLLM
        llm = MockLLM()
    loop = AgentLoop(s, mcp=mcp, llm=llm)
    print("模型：", loop.client.describe())
    print("工作区：", s.workspace_path())
    print("-" * 60)

    lines: list = []

    async def emit(ev: Dict[str, Any]) -> None:
        t = ev.get("type")
        if t == "step":
            print(f"\n[step {ev['index']}/{ev['max']}]")
        elif t == "token":
            print(ev["text"], end="", flush=True)
        elif t == "tool_call":
            print(f"  → {ev['name']}({json.dumps(ev['arguments'], ensure_ascii=False)[:200]})")
        elif t == "tool_result":
            flag = "ok " if ev.get("ok") else "ERR"
            print(f"  ← [{flag}] {ev['text'][:500]}")
        elif t == "warning":
            print(f"  ! {ev['text']}")
        elif t == "done":
            print(f"\n回答：{ev['text']}")
        lines.append(ev)

    result = await loop.run(task, emit=emit)
    print("-" * 60)
    print(f"结束原因：{result.reason}　步数：{result.steps}")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result.trace, f, ensure_ascii=False, indent=2)
        print("trace 已写入：", out)
    return 0 if result.reason == "done" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="桌面智能体的命令行入口")
    ap.add_argument("task", nargs="?", default="读一下工作区里有什么文件")
    ap.add_argument("--mock", action="store_true", help="离线回放模式，不需要 API Key")
    ap.add_argument("--mcp", action="store_true", help="加载 mcp.json 里的 server")
    ap.add_argument("--trace", default="", help="把 trace 写成 json")
    args = ap.parse_args()
    return asyncio.run(main_async(args.task, args.mock, args.mcp, args.trace))


if __name__ == "__main__":
    sys.exit(main())
