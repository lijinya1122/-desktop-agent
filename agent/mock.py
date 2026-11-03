"""离线回放模型：没有 API Key 也能把整条链路跑一遍。

只用于 scripts/selftest.py 和界面里的「演示模式」。
它不接网络，按顺序回放一组写好的决策 —— 工具是真的、失败是真的、diff 是真的。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional


# 回放节奏：默认 0.05s（自检用，几乎瞬间跑完）；
# 录演示时设 MOCK_TICK=0.9，让每一步像真模型一样有间隔
TICK = float(os.environ.get("MOCK_TICK", "0.05"))


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


def script_newfile() -> List[Dict[str, Any]]:
    """第二个演示脚本：write 建新文件 + bash 跑它 + 故意越界被拒。"""
    run_cmd = "python hello.py" if os.name == "nt" else "python3 hello.py"
    return [
        {"content": "先看一下工作区里有什么。",
         "calls": [("bash", {"command": "dir" if os.name == "nt" else "ls -la", "timeout": 15})]},
        {"content": "写一个 hello.py，打印九九乘法表。",
         "calls": [("write", {"path": "hello.py", "content": (
             '"""九九乘法表。"""\n\n\n'
             "def table():\n"
             "    for i in range(1, 10):\n"
             "        row = []\n"
             "        for j in range(1, i + 1):\n"
             "            row.append(f\"{j}x{i}={i * j}\")\n"
             '        print("  ".join(row))\n\n\n'
             'if __name__ == "__main__":\n'
             "    table()\n")})]},
        {"content": "跑一下确认输出对不对。",
         "calls": [("bash", {"command": run_cmd, "timeout": 60})]},
        # 越界被拒：让工具层挡住，演示「安全边界是真的」
        {"content": "顺手看看工作区外面有什么。",
         "calls": [("read", {"path": "../README.md"})]},
        {"content": "已新建 hello.py，九九乘法表打印正常；越界的读写被工具层拒绝了。"},
    ]


def script_course() -> List[Dict[str, Any]]:
    """第三个演示脚本：走我自己写的 MCP server 查真课表。"""
    return [
        {"content": "查一下周五的课。",
         "calls": [("mcp_course_courses_on", {"day": "周五"})]},
        {"content": "周五这几门，已经按上课时间排好了。这个 server 是我自己写的，"
                    "纯标准库 stdio JSON-RPC，三个工具：按课程名查、列全表、按星期查。"},
    ]


def script_hooks() -> List[Dict[str, Any]]:
    """第四个演示脚本：两条 hook 都被代码拦下，并给替代方案。"""
    return [
        {"content": "先把 API Key 写进 .env，以后跑起来方便。",
         "calls": [("write", {"path": ".env",
                             "content": "OPENAI_API_KEY=sk-REPLACE-ME\n"})]},
        {"content": "被拦下了：密钥文件不许写，压根没落到磁盘。Key 放环境变量或本机设置里。"
                    "那我清理一下临时目录。",
         "calls": [("bash", {"command": "rm -rf ../..", "timeout": 10})]},
        {"content": "这条也被拦：不可逆删除，hook 顺手给了替代方案 —— 先 git clean -nd "
                    "看一眼会删什么，或者用 git restore 恢复。这两条都是代码里的规则，"
                    "不是提示词求它别做。"},
    ]


def pick_script(task: str) -> List[Dict[str, Any]]:
    """按任务关键词选回放脚本 —— 演示模式因此不止能演一个任务。"""
    t = (task or "").lower()
    if any(k in t for k in (".env", "密钥", "api key", "rm -rf", "强推", "reset --hard")):
        return script_hooks()
    if any(k in t for k in ("课表", "课程", "周五", "星期", "mcp")):
        return script_course()
    if any(k in t for k in ("九九", "乘法表", "hello", "新建", "写一个", "创建")):
        return script_newfile()
    return default_script()


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
        await asyncio.sleep(TICK)
        item = self.script[self.i] if self.i < len(self.script) else {"content": "回放结束。"}
        self.i += 1
        reply: Dict[str, Any] = {"role": "assistant", "content": item.get("content", ""),
                                 "tool_calls": []}
        if item.get("content") and on_text:
            text = item["content"]
            step = max(4, len(text) // 6)          # 分块吐字，像流式
            for i in range(0, len(text), step):
                r = on_text(text[i:i + step])
                if asyncio.iscoroutine(r):
                    await r
                await asyncio.sleep(TICK * 0.5)
        for idx, (name, args) in enumerate(item.get("calls", [])):
            reply["tool_calls"].append({
                "id": f"mock_{self.i}_{idx}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            })
        return reply
