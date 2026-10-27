"""桌面入口：双击它，出来一个有标题栏的窗口，不是 localhost 网页。

    python app.py                 # 起后端 + pywebview 窗口
    python app.py --no-window     # 只起后端（curl -N / wscat 也能看事件流）
    python app.py --cli "任务"     # 纯终端跑智能体
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# pythonw / 打包后的无控制台模式下 sys.stdout 是 None，print 和 uvicorn 日志会静默失效
if sys.stdout is None:
    _logdir = Path.home() / ".desktop-agent"
    _logdir.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_logdir / "run.log", "a", encoding="utf-8")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

from agent.config import APP_TITLE, Settings, resource  # noqa: E402


def pick_port(preferred: int) -> int:
    for p in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return preferred


def wait_health(port: int, timeout: float = 20.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
                return r.status == 200
        except Exception:
            time.sleep(0.2)
    return False


def start_backend(port: int) -> threading.Thread:
    import uvicorn
    from contextlib import asynccontextmanager
    from server.app import create_app, MCP_HOLDER
    from agent.config import load_mcp_config

    @asynccontextmanager
    async def lifespan(app):
        cfg = load_mcp_config()
        if cfg.get("mcpServers"):
            await MCP_HOLDER.reload(cfg, resource("."))
        yield
        await MCP_HOLDER.close()

    app = create_app()
    app.router.lifespan_context = lifespan   # FastAPI 原生 lifespan 也可以，这里直接替换
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return t


def open_window(port: int) -> None:
    url = f"http://127.0.0.1:{port}/ui/index.html"
    try:
        import webview
    except Exception:
        print("pywebview 未安装，改用系统浏览器打开：", url)
        webbrowser.open(url)
        input("按回车结束服务…")
        return
    window = webview.create_window(
        APP_TITLE, url, width=1440, height=900, min_size=(1000, 640),
        confirm_close=False, text_select=True,
    )
    webview.start(debug=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Mini Cursor · 桌面智能体")
    ap.add_argument("--port", type=int, default=int(__import__("os").environ.get("DESKTOP_AGENT_PORT", 8765)))
    ap.add_argument("--no-window", action="store_true", help="只起后端服务")
    ap.add_argument("--cli", default="", help="终端模式直接跑一个任务")
    ap.add_argument("--mock", action="store_true", help="离线回放模式（不需要 Key）")
    args = ap.parse_args()

    if args.cli:
        from agent.cli import main_async
        import asyncio
        return asyncio.run(main_async(args.cli, args.mock, True))

    port = pick_port(args.port)
    start_backend(port)
    ok = wait_health(port)
    print(f"后端已启动：http://127.0.0.1:{port}  （健康检查 {'通过' if ok else '失败'}）")
    s = Settings.load()
    print("工作区：", s.workspace_path())
    print("模型：", s.model, "| Key：", "已配置" if s.api_key else "未配置（界面里填）")

    if args.no_window:
        print("无窗口模式，Ctrl+C 结束。")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
        return 0

    open_window(port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
