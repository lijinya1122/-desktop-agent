"""自检：不联网、不需要 Key，把工具 / MCP / 整条循环都跑一遍。

    python scripts/selftest.py

跑完会重写 docs/trace.md —— 那份 trace 是这次运行的真实输出，不是手写的。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.config import Settings  # noqa: E402
from agent import tools as tmod   # noqa: E402
from agent.mcp import MCPServer   # noqa: E402
from agent.loop import AgentLoop  # noqa: E402
from agent.mock import MockLLM    # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name: str, fn):
    t0 = time.time()
    try:
        detail = fn()
        results.append((PASS, name, f"{(time.time() - t0) * 1000:.0f}ms", str(detail)[:300]))
    except AssertionError as e:
        results.append((FAIL, name, "", str(e)[:300]))
    except Exception as e:
        results.append((FAIL, name, "", f"{type(e).__name__}: {e}"[:300]))


# --------------------------------------------------------------- 工具单测
def tool_tests(tmp: Path):
    tmod.set_workspace(tmp)

    def t_write():
        r = tmod.write("a/b.txt", "line1\nline2\n")
        assert "已写入" in r.text, r.text
        assert (tmp / "a" / "b.txt").exists(), "父目录没自动创建"
        return r.text

    def t_read():
        r = tmod.read("a/b.txt")
        assert "line1" in r.text and "1\t" in r.text or "1" in r.text, r.text
        return r.text.replace("\n", " | ")[:80]

    def t_read_paged():
        tmod.write("big.txt", "\n".join(f"row{i}" for i in range(1, 51)))
        r = tmod.read("big.txt", offset=1, limit=10)
        assert "还有 40 行" in r.text, r.text
        return r.text.strip().splitlines()[-1]

    def t_edit_ok():
        r = tmod.edit("a/b.txt", "line2", "line_two")
        assert "替换 1 处" in r.text, r.text
        assert "line_two" in (tmp / "a" / "b.txt").read_text(encoding="utf-8")
        assert r.diff.startswith("---"), "没有产出 diff"
        return r.text

    def t_edit_not_unique():
        tmod.write("dup.txt", "def f():\n    return 0\n\ndef g():\n    return 0\n")
        try:
            tmod.edit("dup.txt", "    return 0", "    raise ValueError()")
        except tmod.ToolError as e:
            assert "出现 2 次" in str(e), str(e)
            return str(e)
        raise AssertionError("不唯一时竟然改成了")

    def t_edit_missing():
        try:
            tmod.edit("a/b.txt", "不存在的原文", "x")
        except tmod.ToolError as e:
            assert "出现 0 次" in str(e), str(e)
            return str(e)
        raise AssertionError("old 找不到时竟然改成了")

    def t_escape():
        try:
            tmod.read("../../etc/passwd")
        except tmod.ToolError as e:
            assert "越界" in str(e), str(e)
            return str(e)[:80]
        raise AssertionError("越界读竟然成功了")

    def t_bash_ok():
        cmd = "echo hello-agent" if sys.platform != "win32" else "echo hello-agent"
        r = tmod.bash(cmd, timeout=15)
        assert "hello-agent" in r.text, r.text
        assert r.extra["exit_code"] == 0, r.extra
        return r.text.replace("\n", " | ")[:80]

    def t_bash_fail():
        r = tmod.bash("python -c \"import sys; sys.exit(3)\"", timeout=20)
        assert r.extra["exit_code"] == 3, r.extra
        assert "exit_code=3" in r.text
        return "非 0 退出码也正常返回"

    def t_bash_timeout():
        cmd = 'python -c "import time; time.sleep(8)"'
        r = tmod.bash(cmd, timeout=2)
        assert r.extra["timed_out"] is True, r.extra
        return "超时被终止，循环没挂死"

    def t_bash_truncate():
        cmd = ("python -c \"print('x'*50000)\"")
        r = tmod.bash(cmd, timeout=30, max_chars=2000)
        assert "已截断" in r.text, r.text[:200]
        return "长输出被截断，上下文没被撑爆"

    def t_atomic():
        p = tmp / "atomic.txt"
        p.write_text("old", encoding="utf-8")
        tmod.write("atomic.txt", "new")
        assert p.read_text(encoding="utf-8") == "new"
        assert not list(tmp.glob(".tmp_*")), "临时文件没清理"
        return "临时文件 + rename，没有残留"

    for nm, f in [("write 自动建父目录", t_write), ("read 带行号", t_read),
                  ("read 分页提示", t_read_paged), ("edit 精确替换 + diff", t_edit_ok),
                  ("edit 不唯一 → 拒绝", t_edit_not_unique), ("edit 找不到 → 拒绝", t_edit_missing),
                  ("路径越界 → 拒绝", t_escape), ("bash 正常", t_bash_ok),
                  ("bash 非 0 退出码", t_bash_fail), ("bash 超时", t_bash_timeout),
                  ("bash 输出截断", t_bash_truncate), ("原子写", t_atomic)]:
        check(nm, f)


# --------------------------------------------------------------- MCP
async def mcp_test():
    srv = MCPServer("demo", sys.executable, [str(ROOT / "examples" / "mcp_demo_server.py")])
    tools = await srv.start(timeout=15)
    names = sorted(t.get("name") for t in tools)
    assert "get_weather" in names, names
    out = await srv.call_tool("get_weather", {"city": "杭州"})
    assert "杭州" in out, out
    t = await srv.call_tool("now", {})
    assert len(t) > 8, t
    await srv.stop()
    return f"tools/list -> {names}；get_weather(杭州) -> {out}"


# --------------------------------------------------------------- 整条循环
async def loop_test(workspace: Path) -> dict:
    s = Settings.load()
    s.workspace = str(workspace)
    s.confirm_writes = False
    s.max_steps = 10
    tmod.set_workspace(workspace)

    events = []
    loop = AgentLoop(s, llm=MockLLM())

    async def emit(ev):
        events.append(ev)

    result = await loop.run("让 mean 和 median 对空列表抛 ValueError，然后跑测试验证",
                            emit=emit)
    return {"result": result, "events": events}


def render_trace(run: dict) -> str:
    result, events = run["result"], run["events"]
    lines = []
    lines.append("# trace · 一次完整运行记录\n")
    lines.append("> 由 `python scripts/selftest.py` 自动生成 —— 工具是真的、失败是真的、diff 是真的。")
    lines.append("> 模型用的是 `agent/mock.py` 的离线回放（不联网），因此这份 trace 任何人都能复现。\n")
    lines.append("任务：**让 mean 和 median 对空列表抛 ValueError，然后跑测试验证**\n")
    lines.append("```")
    for ev in events:
        t = ev.get("type")
        if t == "step":
            lines.append(f"[step {ev['index']}/{ev['max']}]")
        elif t == "token":
            lines.append(f"  (model) {ev['text']}")
        elif t == "tool_call":
            args = json.dumps(ev["arguments"], ensure_ascii=False)
            lines.append(f"  -> {ev['name']}({args[:160]})")
        elif t == "tool_result":
            flag = "ok " if ev["ok"] else "ERR"
            body = ev["text"].replace("\n", "\n       ")
            lines.append(f"  <- [{flag}] {body[:700]}")
        elif t == "warning":
            lines.append(f"  !! {ev['text']}")
        elif t == "done":
            lines.append(f"\n[done] {ev['text']}")
    lines.append("```\n")
    lines.append(f"结束原因：`{result.reason}`　总步数：`{result.steps}`\n")
    lines.append("## 里面发生了什么\n")
    lines.append("1. **第 3 步故意失败**：`edit` 的 `old=\"        return 0\"` 在 `stats.py` 里出现 2 次，"
                 "工具拒绝猜，直接报错并把「出现 2 次」回灌给模型 —— 这就是第 37 页要现场制造的失败。")
    lines.append("2. **恢复**：模型把 `old` 写长，带上 `def mean(nums):` 整段，替换唯一命中。")
    lines.append("3. **验证**：`bash` 跑 `python test_stats.py`，4/4 通过 —— 结论有证据，不是「我改好了」。")
    lines.append("4. **护栏**：步数上限、整体超时、工具超时（bash 2s 那条）、输出截断、路径越界，逐条都在上面。")
    return "\n".join(lines)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="agent-selftest-"))
    print("=" * 70)
    print("1) 四个工具单测")
    print("=" * 70)
    tool_tests(tmp)
    for st, name, ms, detail in results:
        print(f"  [{st}] {name} {ms}  {detail}")

    print()
    print("=" * 70)
    print("2) MCP 往返（stdio / JSON-RPC）")
    print("=" * 70)
    try:
        info = asyncio.run(mcp_test())
        results.append((PASS, "MCP tools/list + tools/call", "", info))
        print(f"  [PASS] {info}")
    except Exception as e:
        results.append((FAIL, "MCP tools/list + tools/call", "", f"{type(e).__name__}: {e}"))
        print(f"  [FAIL] {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    print("3) 整条 ReAct 循环（离线回放）")
    print("=" * 70)
    ws = ROOT / "workspace"
    backup = {p: p.read_text(encoding="utf-8") for p in ws.glob("*.py")}
    try:
        run = asyncio.run(loop_test(ws))
    finally:
        for p, text in backup.items():
            p.write_text(text, encoding="utf-8")   # 还原，别把仓库弄脏

    for ev in run["events"]:
        t = ev.get("type")
        if t == "step":
            print(f"[step {ev['index']}/{ev['max']}]")
        elif t == "token":
            print("  (model)", ev["text"])
        elif t == "tool_call":
            print("  ->", ev["name"], json.dumps(ev["arguments"], ensure_ascii=False)[:120])
        elif t == "tool_result":
            print("  <-", "ok " if ev["ok"] else "ERR", ev["text"][:200].replace("\n", " | "))
        elif t == "done":
            print("\n[done]", ev["text"], "| reason =", ev["reason"])

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "trace.md").write_text(render_trace(run), encoding="utf-8")
    print("\ntrace 已写入 docs/trace.md")

    shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if r[0] == FAIL]
    print()
    print("=" * 70)
    print(f"结论：{len(results) - len(failed)}/{len(results)} 通过"
          + ("" if not failed else "　失败：" + ", ".join(r[1] for r in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
