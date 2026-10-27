"""后端冒烟：起服务 → 打 REST → 连 WebSocket 走一遍事件流 → 关掉。

    python scripts/smoke_ws.py          # 不需要 Key，也不需要界面

这是「后端先跑通，再做界面」那条要求的证据：关掉前端，事件流照样能看。
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
results = []


def pick_port() -> int:
    for p in range(8800, 8900):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return 8899


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def http_json(url: str, method: str = "GET", body: dict = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "status": e.code}


async def ws_flow(port: int) -> None:
    import websockets
    seen = []
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws", open_timeout=10) as ws:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
            except asyncio.TimeoutError:
                break
            ev = json.loads(raw)
            seen.append(ev.get("type"))
            if ev.get("type") == "hello":
                check("WS hello + MCP 状态", "mcp" in ev, json.dumps(ev.get("mcp"), ensure_ascii=False)[:120])
                await ws.send(json.dumps({"type": "chat", "text": "读一下工作区的 README.md"}))
            if ev.get("type") == "done":
                break
    check("WS 收到完整事件流（无 Key 时走 error→done 出口）",
          "hello" in seen and "done" in seen, " -> ".join(seen))
    check("WS 有 status 事件（工具挂载数）", "status" in seen, "")


def main() -> int:
    port = pick_port()
    print("=" * 70)
    print(f"启动后端 127.0.0.1:{port}")
    print("=" * 70)
    env_port = {"DESKTOP_AGENT_PORT": str(port), "PYTHONIOENCODING": "utf-8"}
    import os
    env = dict(os.environ)
    env.update(env_port)
    proc = subprocess.Popen([PY, "app.py", "--no-window", "--port", str(port)],
                            cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    try:
        # 等健康检查
        ok = False
        for _ in range(60):
            try:
                h = http_json(f"http://127.0.0.1:{port}/api/health")
                ok = True
                break
            except Exception:
                time.sleep(0.5)
        check("GET /api/health", ok, json.dumps(h, ensure_ascii=False) if ok else "超时")

        tree = http_json(f"http://127.0.0.1:{port}/api/tree?depth=3")
        names = [n["name"] for n in tree.get("nodes", [])]
        check("GET /api/tree", "stats.py" in names, "、".join(names))

        f = http_json(f"http://127.0.0.1:{port}/api/file?path=stats.py")
        check("GET /api/file", "def mean" in f.get("content", ""), f.get("path", ""))

        bad = http_json(f"http://127.0.0.1:{port}/api/file?path=../../etc/passwd")
        check("路径越界被拒", "error" in bad, str(bad)[:60])

        s0 = http_json(f"http://127.0.0.1:{port}/api/settings")
        s0["settings"]["api_key"] = "sk-smoke-test-key"
        s1 = http_json(f"http://127.0.0.1:{port}/api/settings", "POST", s0["settings"])
        check("POST /api/settings 保存并掩码回显",
              s1["settings"]["api_key_set"] and s1["settings"]["api_key"] == "",
              f"hint={s1['settings'].get('api_key_hint')!r}")

        # 测试要可复现：关掉演示模式（离线回放）和确认闸门，否则会卡在 confirm_request
        s0["settings"]["api_key"] = ""
        s0["settings"]["demo_mode"] = False
        s0["settings"]["confirm_writes"] = False
        http_json(f"http://127.0.0.1:{port}/api/settings", "POST", s0["settings"])

        asyncio.run(ws_flow(port))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    failed = [r for r in results if not r[0]]
    print()
    print("=" * 70)
    print(f"结论：{len(results) - len(failed)}/{len(results)} 通过"
          + ("" if not failed else "　失败：" + ", ".join(r[1] for r in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
