"""把真实界面操作录成视频（CDP 收帧，不是截图轮播）。

    python scripts/record_demo.py --out "C:\\Users\\Lenovo\\Desktop\\一苇以航\\演示视频2.mp4"

做法：
  1) 起后端（`app.py --no-window`，MOCK_TICK 放慢，让每步有真实间隔）
  2) 起系统 Edge（headless），CDP `Page.startScreencast` 持续收真实渲染帧
  3) 脚本自动输入任务、点发送、看到 diff 卡片、点「执行」、等测试结果
  4) 按每帧时间戳用 ffmpeg 合成 mp4（帧率自适应，画面和事件同步）

不联网、不需要 Key（演示模式），也不动你的鼠标键盘。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

import websockets

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

TASK_FIX = "修一下 stats.py 的空列表 bug：mean 和 median 都改，然后跑测试验证"
TASK_NEW = "写一个 hello.py 打印九九乘法表，写完跑一下看看"
TASK_COURSE = "用 MCP 查一下周五有什么课"
TASK_HOOK = "把 API Key 写进 .env，再清理一下旧文件"

# 事件时间线（相对录制开始，秒）—— 给字幕对齐用
EVENTS: List[Tuple[str, float]] = []


def mark(name: str, t0: float) -> None:
    EVENTS.append((name, round(time.time() - t0, 2)))


# ---------------------------------------------------------------- 基础
def pick_port(start: int = 8800) -> int:
    for p in range(start, start + 100):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("没有空闲端口")


def http_json(url: str, method: str = "GET", body: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def find_edge() -> str:
    for p in EDGE_CANDIDATES:
        if Path(p).is_file():
            return p
    raise RuntimeError("没找到 Edge / Chrome")


class CDP:
    """极简 CDP 客户端：发命令、收事件。"""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.n = 0
        self.pending: Dict[int, asyncio.Future] = {}
        self.listeners: Dict[str, List[Any]] = {}

    async def call(self, method: str, **params: Any) -> Dict[str, Any]:
        self.n += 1
        mid = self.n
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        return await asyncio.wait_for(fut, 60)

    async def notify(self, method: str, **params: Any) -> None:
        """只发不等：ack 这类消息如果等响应，会和收帧循环互相卡死。"""
        await self.ws.send(json.dumps({"method": method, "params": params}))

    async def pump(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            mid = msg.get("id")
            if mid is not None:
                fut = self.pending.pop(mid, None)
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(str(msg["error"])))
                    else:
                        fut.set_result(msg.get("result") or {})
                continue
            for h in self.listeners.get(msg.get("method", ""), []):
                await h(msg.get("params") or {})


class Frames:
    def __init__(self, d: Path) -> None:
        self.d = d
        self.items: List[Tuple[float, Path]] = []

    async def on_frame(self, p: Dict[str, Any], cdp: CDP) -> None:
        path = self.d / f"f{len(self.items):05d}.jpg"
        try:
            path.write_bytes(base64.b64decode(p["data"]))
        except Exception:
            return
        self.items.append((float(p["metadata"].get("timestamp") or time.time()), path))
        await cdp.notify("Page.screencastFrameAck", sessionId=p["sessionId"])


# ---------------------------------------------------------------- 页面操作
async def js(cdp: CDP, expr: str) -> Any:
    r = await cdp.call("Runtime.evaluate", expression=expr,
                       returnByValue=True, awaitPromise=True)
    return (r.get("result") or {}).get("value")


async def poll_frames(cdp: CDP, sink: "Frames", interval: float = 0.07) -> None:
    """降级方案：定时截图（headless 下 screencast 几乎不推帧）。"""
    while True:
        try:
            r = await cdp.call("Page.captureScreenshot", format="jpeg", quality=88)
            data = r.get("data")
            if data:
                path = sink.d / f"p{len(sink.items):05d}.jpg"
                path.write_bytes(base64.b64decode(data))
                sink.items.append((time.time(), path))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


async def wait_js(cdp: CDP, expr: str, timeout: float = 90.0, step: float = 0.25) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if await js(cdp, expr):
                return True
        except Exception:
            pass
        await asyncio.sleep(step)
    return False


async def type_task(cdp: CDP, text: str, per: float = 0.055) -> None:
    await js(cdp, "document.querySelector('#input').value=''")
    await js(cdp, "document.querySelector('#input').focus()")
    for ch in text:
        await js(cdp, f"(()=>{{const e=document.querySelector('#input');"
                      f"e.value += {json.dumps(ch)};}})()")
        await asyncio.sleep(per)


async def run_task(cdp: CDP, text: str, has_confirm: bool, t0: float) -> None:
    await type_task(cdp, text)
    mark(f"typed:{text[:6]}", t0)
    await asyncio.sleep(0.6)                       # 看一眼输入框再发
    await js(cdp, "document.querySelector('#btnSend').click()")
    mark("sent", t0)
    # 先等这一轮真的跑起来，否则上一个任务的「完成」会被误判成本轮结束
    await wait_js(cdp, "document.querySelector('#btnStop').disabled === false", timeout=20)

    if not has_confirm:
        # 没有确认卡的任务：老老实实等 busy 结束且面板写「完成」
        ok = await wait_js(
            cdp,
            "document.querySelector('#btnStop').disabled"
            " && document.querySelector('#stepInfo').textContent.includes('完成')",
            timeout=150)
        mark("done" if ok else "done_timeout", t0)
        print(f"  任务完成：{ok}")
        return

    if has_confirm:
        # mock 一次任务可能有 2-3 张确认卡（失败的 edit 不弹卡）——逐张点
        deadline = time.time() + 150
        clicked = 0
        while time.time() < deadline:
            hit = await js(cdp, "(()=>{const b=document.querySelector('.card.confirm button.primary');"
                                "if(b){b.click();return true}return false})()")
            if hit:
                clicked += 1
                mark(f"confirm_clicked_{clicked}", t0)
                print(f"  点了第 {clicked} 张确认卡")
                await asyncio.sleep(2.0)      # 让 diff 卡在画面上停留
            idle = await js(cdp, "document.querySelector('#btnStop').disabled")
            if idle and await js(cdp, "document.querySelector('#stepInfo').textContent.includes('完成')"):
                break
            await asyncio.sleep(0.5)
        mark(f"confirms={clicked}", t0)

    done = await js(cdp, "document.querySelector('#btnStop').disabled"
                         " && document.querySelector('#stepInfo').textContent.includes('完成')")
    mark("done" if done else "done_timeout", t0)
    print(f"  任务完成：{done}")


# ---------------------------------------------------------------- 合成
def compose(frames: List[Tuple[float, Path]], out: Path, fps: int = 30) -> Dict[str, Any]:
    import imageio_ffmpeg

    if len(frames) < 10:
        raise SystemExit(f"帧太少（{len(frames)}），录屏可能失败")

    lst = out.parent / "screencast_concat.txt"
    lines: List[str] = []
    for i, (ts, p) in enumerate(frames):
        nxt = frames[i + 1][0] if i + 1 < len(frames) else ts + 1.5
        dur = max(0.03, min(nxt - ts, 2.0))
        lines.append(f"file '{p.as_posix()}'")
        lines.append(f"duration {dur:.3f}")
    lines.append(f"file '{frames[-1][1].as_posix()}'")
    lst.write_text("\n".join(lines), encoding="utf-8")

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(lst),
           "-vf", f"fps={fps},scale=1440:-2:flags=lanczos",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        raise SystemExit("ffmpeg 失败：\n" + (p.stderr or "")[-1500:])

    total = frames[-1][0] - frames[0][0]
    return {"out": str(out), "frames": len(frames), "seconds": round(total, 1),
            "size_mb": round(out.stat().st_size / 1e6, 1)}


# ---------------------------------------------------------------- 主流程
async def record(out: Path, tick: float, keep: bool) -> Dict[str, Any]:
    t0 = time.time()
    port = pick_port()
    base = f"http://127.0.0.1:{port}"
    work = Path(tempfile.mkdtemp(prefix="screencast-"))
    frames = Frames(work)

    env = dict(os.environ)
    env.update({"MOCK_TICK": str(tick), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    server = subprocess.Popen([PY, "app.py", "--no-window", "--port", str(port)],
                              cwd=str(ROOT), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    edge = None
    try:
        for _ in range(120):
            try:
                if http_json(f"{base}/api/health").get("ok"):
                    break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            raise SystemExit("后端没起来")

        # 演示模式 + 写操作要确认（这样才有 diff 卡片可点）
        http_json(f"{base}/api/settings", "POST",
                  {"demo_mode": True, "confirm_writes": True,
                   "workspace": str(ROOT / "workspace")})
        print("后端就绪，演示模式已开")

        # 有窗口但移到屏幕外：headless 下 screencast 基本不推帧，有窗口才能拿到真实渲染
        edge = subprocess.Popen([
            find_edge(),
            "--remote-debugging-port=9333", "--remote-allow-origins=*",
            f"--user-data-dir={work / 'profile'}",
            "--window-size=1500,940", "--window-position=-2600,0",
            "--hide-scrollbars", "--force-device-scale-factor=1",
            "--no-first-run", "--no-default-browser-check", "--no-proxy-server",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--disable-features=Translate,MediaRouter",
            base + "/",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ws_url = ""
        for _ in range(80):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9333/json/list", timeout=2) as r:
                    for t in json.loads(r.read().decode()):
                        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.4)
        if not ws_url:
            raise SystemExit("连不上 Edge 调试口")

        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            cdp = CDP(ws)
            pump = asyncio.create_task(cdp.pump())
            cdp.listeners["Page.screencastFrame"] = [lambda p: frames.on_frame(p, cdp)]
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            await cdp.call("Page.startScreencast", format="jpeg", quality=88,
                           maxWidth=1500, maxHeight=940, everyNthFrame=1)

            ready = await wait_js(cdp, "!!document.querySelector('#btnSend')", timeout=40)
            info = await js(cdp, "JSON.stringify({w:innerWidth,h:innerHeight,"
                                 "len:document.body.innerText.length})")
            mark("ui_ready", t0)
            print(f"页面就绪：{ready}　尺寸/文本：{info}")
            await asyncio.sleep(2.0)

            poll_task = None
            if len(frames.items) < 8:           # headless / 显卡异常时降级
                await cdp.call("Page.stopScreencast")
                poll_task = asyncio.create_task(poll_frames(cdp, frames, 0.065))
                mark("capture=poll", t0)
                print("  screencast 帧率不足，改用定时截图")
            await wait_js(cdp, "document.querySelector('#mcpBadge').textContent.length > 6",
                          timeout=20)
            mark("mcp_ready", t0)
            await asyncio.sleep(2.0)            # 停留：看清整个界面

            print("任务一：修 bug（会看到 edit 失败 → 恢复 → diff 确认 → 测试）")
            await run_task(cdp, TASK_FIX, has_confirm=True, t0=t0)
            await asyncio.sleep(2.5)

            print("任务二：新建文件 + 跑一遍 + 越界被拒")
            await run_task(cdp, TASK_NEW, has_confirm=True, t0=t0)
            await asyncio.sleep(2.0)

            print("任务三：MCP 查课表（紫色 MCP 卡片）")
            await run_task(cdp, TASK_COURSE, has_confirm=False, t0=t0)
            await asyncio.sleep(2.0)

            print("任务四：hook 拦截（.env 密钥 / rm -rf 不可逆）")
            await run_task(cdp, TASK_HOOK, has_confirm=False, t0=t0)
            await asyncio.sleep(2.5)
            mark("end", t0)
            (out.parent / "events.json").write_text(
                json.dumps(EVENTS, ensure_ascii=False), encoding="utf-8")

            if poll_task:
                poll_task.cancel()
                try:
                    await poll_task
                except BaseException:           # CancelledError 不继承 Exception
                    pass
            else:
                await cdp.call("Page.stopScreencast")
            pump.cancel()
    finally:
        try:                                   # 还原设置：不要把演示模式留给用户
            http_json(f"{base}/api/settings", "POST", {"demo_mode": False})
        except Exception:
            pass
        if edge:
            edge.kill()
        server.kill()

    res = compose(frames.items, out)
    if not keep:
        for _, p in frames.items:
            p.unlink(missing_ok=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="录真实界面操作过程")
    ap.add_argument("--out", default=str(Path.home() / "Desktop" / "演示视频2.mp4"))
    ap.add_argument("--tick", type=float, default=0.9, help="每步间隔秒数（越大越慢）")
    ap.add_argument("--keep", action="store_true", help="保留中间帧")
    args = ap.parse_args()
    res = asyncio.run(record(Path(args.out), args.tick, args.keep))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
