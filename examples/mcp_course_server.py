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
# 来源：研究生课表.pdf（南京审计大学 · 统计与数据科学学院 · 2026-2027 学年第一学期）
# 一节 40 分钟，时间按节次起止合并写成区间。
COURSES = [
    {"name": "神经网络与深度学习", "day": "周一", "time": "09:20~11:50", "jieci": "第2-4节",
     "place": "致明楼418", "teacher": "周兴才", "weeks": "7-12周"},
    {"name": "神经网络与深度学习", "day": "周五", "time": "19:20~20:50", "jieci": "第12-13节",
     "place": "致明楼418", "teacher": "周兴才", "weeks": "7-12周"},
    {"name": "英语（专硕）", "day": "周二", "time": "10:20~12:40", "jieci": "第3-5节",
     "place": "致明楼418", "teacher": "胡静", "weeks": "3-18周"},
    {"name": "Python编程与案例实务", "day": "周二", "time": "13:30~16:00", "jieci": "第6-8节",
     "place": "敏达楼202", "teacher": "卢燚", "weeks": "3-18周"},
    {"name": "经济统计与运行监测", "day": "周三", "time": "08:30~11:00", "jieci": "第1-3节",
     "place": "致明楼419", "teacher": "郑彦、王荐", "weeks": "7-17周"},
    {"name": "中国审计学专题", "day": "周三", "time": "15:20~16:50", "jieci": "第8-9节",
     "place": "审计署审计干部教育学院学术报告厅", "teacher": "董必荣等", "weeks": "7-16周"},
    {"name": "统计数据分析方法", "day": "周四", "time": "08:30~11:00", "jieci": "第1-3节",
     "place": "致明楼315", "teacher": "朱春华", "weeks": "3-18周"},
    {"name": "统计计算与数据分析", "day": "周四", "time": "15:20~16:50", "jieci": "第8-9节",
     "place": "致明楼417", "teacher": "张燕", "weeks": "9-17周"},
    {"name": "职业道德与论文写作（应用统计）", "day": "周四", "time": "19:20~20:50",
     "jieci": "第12-13节", "place": "敏行楼205", "teacher": "赵彦勇等", "weeks": "4-15周"},
    {"name": "统计学基础", "day": "周五", "time": "10:20~12:40", "jieci": "第3-5节",
     "place": "致明楼315", "teacher": "李慧琴", "weeks": "3-18周"},
    {"name": "统计计算与数据分析", "day": "周五", "time": "13:30~15:00", "jieci": "第6-7节",
     "place": "致明楼417", "teacher": "张燕", "weeks": "9-17周"},
    {"name": "新时代中国特色社会主义理论与实践", "day": "周五", "time": "15:20~16:50",
     "jieci": "第8-9节", "place": "致明楼报告厅", "teacher": "齐效玫", "weeks": "3-18周"},
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
        f"{c['name']}：{c['day']} {c['time']}（{c['jieci']}, {c['weeks']}）　"
        f"{c['place']}　{c['teacher']}"
        for c in hits)


def _order(items):
    return sorted(items, key=lambda c: (WEEK.index(c["day"]), c["time"]))


def list_courses() -> str:
    """列出整张课表。用户问「这学期有哪些课」「课表给我看看」时用。"""
    head = "南京审计大学 · 2026-2027学年第一学期 · 统计学硕 MP2608016\n"
    return head + "\n".join(
        f"{c['day']} {c['time']}　{c['name']}　{c['place']}　{c['teacher']}　{c['weeks']}"
        for c in _order(COURSES))


def courses_on(day: str = "") -> str:
    """查某一天有哪几节课；不传 day 就按今天查。"""
    d = (day or "").strip()
    if not d:
        d = WEEK[datetime.now().weekday()]
    hits = [c for c in COURSES if c["day"] == d]
    if not hits:
        return f"{d} 没课。"
    return f"{d} 的课：\n" + "\n".join(
        f"  {c['time']}（{c['jieci']}）　{c['name']}　{c['place']}　{c['teacher']}　{c['weeks']}"
        for c in _order(hits))


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
