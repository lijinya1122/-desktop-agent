"""离线回放模型：没有 API Key 也能把整条链路跑一遍。

只用于 scripts/selftest.py 和界面里的「演示模式」。
它不接网络，按顺序回放一组写好的决策 —— 工具是真的、失败是真的、diff 是真的。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional


def default_script() -> List[Dict[str, Any]]:
    list_cmd = "dir" if os.name == "nt" else "ls -la"
    return [
        {"content": "先看一下工作区里有什么。",
         "calls": [("bash", {"command": list_cmd, "timeout": 15})]},
        {"content": "读一下 stats.py。",
         "calls": [("read", {"path": "stats.py"})]},
        {"content": "空列表返回 0 不合理，改成抛 ValueError。",
         "calls": [("edit", {"path": "stats.py", "old": "        return 0",
                             "new": "        raise ValueError(\"nums 不能为空\")"})]},
        # 这一步会真的失败：old 出现 2 次，edit 拒绝猜 —— 演示里的「故意失败」
        {"content": "old 不唯一，我把它写长一点，带上函数签名。",
         "calls": [("edit", {"path": "stats.py",
                             "old": "def mean(nums):\n    if not nums:\n        return 0",
                             "new": "def mean(nums):\n    if not nums:\n        raise ValueError(\"nums 不能为空\")"})]},
        {"content": "median 同样处理。",
         "calls": [("edit", {"path": "stats.py",
                             "old": "def median(nums):\n    if not nums:\n        return 0",
                             "new": "def median(nums):\n    if not nums:\n        raise ValueError(\"nums 不能为空\")"})]},
        {"content": "跑一遍测试验证。",
         "calls": [("bash", {"command": "python test_stats.py", "timeout": 60})]},
        {"content": "已修改 stats.py 两处（mean/median），测试 4/4 通过。"},
    ]


class MockLLM:
    def __init__(self, script: Optional[List[Dict[str, Any]]] = None):
        self.script = script or default_script()
        self.i = 0

    def describe(self) -> str:
        return "mock-replay（离线回放，不联网）"

    async def chat(self, messages: List[Dict[str, Any]],
                   tools: Optional[List[Dict[str, Any]]] = None,
                   on_text: Optional[Callable[[str], Any]] = None,
                   cancel: Optional[asyncio.Event] = None) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        item = self.script[self.i] if self.i < len(self.script) else {"content": "回放结束。"}
        self.i += 1
        reply: Dict[str, Any] = {"role": "assistant", "content": item.get("content", ""),
                                 "tool_calls": []}
        if item.get("content") and on_text:
            r = on_text(item["content"])
            if asyncio.iscoroutine(r):
                await r
        for idx, (name, args) in enumerate(item.get("calls", [])):
            reply["tool_calls"].append({
                "id": f"mock_{self.i}_{idx}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            })
        return reply
