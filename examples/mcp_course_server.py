"""第二个 MCP server：查课表。只用标准库，和 demo server 一样的三个 method。

这是「自己写的第二个 server」—— 证明 MCP 不只是跑老师给的示例：
数据换成研究生的课表，工具是查课程 / 列全部 / 按星期查。

⚠ stdout 是协议通道，调试日志一律写 stderr。

跑法（不会有任何输出，它在等 stdin）：
    python examples/mcp_course_server.py
"""

import json
import sys
from datetime import datetime


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 课表数据
# （示例数据，换成自己的真实课表即可）
COURSES = [
    {"name": "Python 智能体专题", "day": "周一", "time": "08:00-09:40",
     "place": "教三 401", "teacher": "王老师"},
    {"name": "机器学习", "day": "周一", "time": "14:00-15:40",
     "place": "教二 305", "teacher": "李老师"},
    {"name": "最优化方法", "day": "周二", "time": "10:00-11:40",
     "place": "教三 208", "teacher": "张老师"},
    {"name": "数据分析与建模", "day": "周三", "time": "08:00-09:40",
     "place": "实验楼 B203", "teacher": "陈老师"},
    {"name": "自然语言处理专题", "day": "周四", "time": "14:00-15:40",
     "place": "教二 512", "teacher": "刘老师"},
    {"name": "学术写作与规范", "day": "周五", "time": "10:00-11:40",
     "place": "图书馆报告厅", "teacher": "赵老师"},
]

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def query_course(name: str) -> str:
    """按课程名（支持部分匹配）查上课时间、地点和任课老师。"""
    kw = (name or "").strip()
    if not kw:
        return "请给一个课程名，比如：机器学习"
    hits = [c for c in COURSES if kw in c["name"]]
    if not hits:
        names = "、".join(c["name"] for c in COURSES)
        return f"课表里没有「{kw}」。当前有：{names}"
    return "\n".join(
        f"{c['name']}：{c['day']} {c['time']}　{c['place']}　{c['teacher']}"
        for c in hits)


def list_courses() -> str:
    """列出整张课表。用户问「这学期有哪些课」「课表给我看看」时用。"""
    return "\n".join(
        f"{c['day']} {c['time']}　{c['name']}　{c['place']}　{c['teacher']}"
        for c in COURSES)


def courses_on(day: str = "") -> str:
    """查某一天有哪几节课；不传 day 就按今天查。"""
    d = (day or "").strip()
    if not d:
        d = WEEK[datetime.now().weekday()]
    hits = [c for c in COURSES if c["day"] == d]
    if not hits:
        return f"{d} 没课。"
    return f"{d} 的课：\n" + "\n".join(
        f"  {c['time']}　{c['name']}　{c['place']}　{c['teacher']}" for c in hits)


TOOLS = {
    "query_course": {
        "fn": query_course,
        "schema": {
            "name": "query_course",
            "description": "按课程名查上课时间、地点和任课老师，支持部分匹配（如「机器」）。",
            "inputSchema": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "课程名或关键字"}},
                "required": ["name"],
            },
        },
    },
    "list_courses": {
        "fn": list_courses,
        "schema": {
            "name": "list_courses",
            "description": "列出整张课表。用户问「这学期有什么课」「给我课表」时使用。",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
    },
    "courses_on": {
        "fn": courses_on,
        "schema": {
            "name": "courses_on",
            "description": "查某一天有哪几节课；不给 day 就按今天查。",
            "inputSchema": {
                "type": "object",
                "properties": {"day": {"type": "string", "description": "周一…周日，默认按今天"}},
                "required": [],
            },
        },
    },
}


def main():
    log("[course-server] 已启动，等待 JSON-RPC…")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        log(f"[course-server] <- {method}")

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "course-schedule", "version": "1.0.0"}}}
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
            continue
        else:
            resp = {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"不支持的方法：{method}"}}

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
