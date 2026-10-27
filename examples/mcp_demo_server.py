"""MCP server 示例：只用标准库，约 90 行，看清它只是 JSON。

协议就三个 method：initialize / tools/list / tools/call。
⚠ stdout 是协议通道 —— 调试用 print 会直接把连接搞死，日志一律写 stderr。

跑法（不会有任何输出，因为它在等 stdin）：
    python examples/mcp_demo_server.py
自检：
    python scripts/selftest.py
"""

import json
import sys
from datetime import datetime


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 工具函数
def get_weather(city: str) -> str:
    """查询某个城市的实时天气。当用户问冷热、下雨、穿衣时使用。"""
    table = {
        "杭州": "多云，22℃，湿度 61%，东南风 2 级",
        "北京": "晴，18℃，湿度 30%，西北风 4 级",
        "上海": "阴有小雨，20℃，湿度 78%",
    }
    return f"{city}：{table.get(city, '暂无该城市数据（示例 server 只内置了杭州/北京/上海）')}"


def now(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """返回本机当前时间。当用户问「现在几点」「今天几号」这类实时问题使用。"""
    return datetime.now().strftime(fmt)


def add(a: float, b: float) -> str:
    """把两个数相加。需要精确计算时使用 —— 模型自己算不准小数。"""
    return f"{a} + {b} = {a + b}"


# ---------------------------------------------------------------- 说明书
TOOLS = {
    "get_weather": {
        "fn": get_weather,
        "schema": {
            "name": "get_weather",
            "description": "查询某个城市的实时天气。当用户问冷热、下雨、穿衣时使用。",
            "inputSchema": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名，如：杭州"}},
                "required": ["city"],
            },
        },
    },
    "now": {
        "fn": now,
        "schema": {
            "name": "now",
            "description": "返回本机当前时间。当用户问「现在几点」「今天几号」时使用。",
            "inputSchema": {
                "type": "object",
                "properties": {"fmt": {"type": "string", "description": "strftime 格式，默认 %Y-%m-%d %H:%M:%S"}},
                "required": [],
            },
        },
    },
    "add": {
        "fn": add,
        "schema": {
            "name": "add",
            "description": "把两个数相加。需要精确计算时使用。",
            "inputSchema": {
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        },
    },
}


def main():
    log("[demo-server] 已启动，等待 JSON-RPC…")
    for line in sys.stdin:                       # 一行一个消息
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        log(f"[demo-server] <- {method}")

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "class-demo", "version": "1.0.0"}}}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": rid,
                    "result": {"tools": [t["schema"] for t in TOOLS.values()]}}
        elif method == "tools/call":
            params = req.get("params") or {}
            name, args = params.get("name"), params.get("arguments") or {}
            tool = TOOLS.get(name)
            if not tool:
                resp = {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32601, "message": f"没有这个工具：{name}"}}
            else:
                try:
                    text = tool["fn"](**args)
                    resp = {"jsonrpc": "2.0", "id": rid,
                            "result": {"content": [{"type": "text", "text": text}]}}
                except Exception as e:
                    resp = {"jsonrpc": "2.0", "id": rid,
                            "result": {"content": [{"type": "text",
                                                    "text": f"调用失败：{type(e).__name__}: {e}"}],
                                       "isError": True}}
        elif method in ("notifications/initialized", "initialized"):
            continue                              # 通知不回包
        else:
            resp = {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"不支持的方法：{method}"}}

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()                         # 必须 flush


if __name__ == "__main__":
    main()
