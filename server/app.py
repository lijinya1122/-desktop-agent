"""后端：FastAPI + WebSocket 事件流。

顺序是「后端先跑通，再做界面」——关掉前端，用 curl -N 也能看到完整事件流：
    python -c "import server.app as a; a.run(port=8765, window=False)"
    wscat -c ws://127.0.0.1:8765/ws      # 发 {"type":"chat","text":"..."}
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent.config import Settings, load_mcp_config, resource
from agent.loop import AgentLoop
from agent.mcp import MCPManager

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", ".idea", ".mypy_cache"}


def create_app() -> FastAPI:
    app = FastAPI(title="desktop-agent", version="1.0.0")
    ui_dir = resource("ui")
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    @app.get("/")
    async def index():
        idx = ui_dir / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return JSONResponse({"ok": True, "hint": "ui/ 目录不存在"})

    @app.get("/api/health")
    async def health():
        s = Settings.load()
        return {"ok": True, "workspace": str(s.workspace_path()),
                "key_set": bool(s.api_key), "model": s.model}

    # ------------------------------------------------------------ 文件
    @app.get("/api/tree")
    async def tree(depth: int = 4):
        s = Settings.load()
        root = s.workspace_path()
        return {"root": str(root), "nodes": _tree(root, root, depth)}

    @app.get("/api/file")
    async def get_file(path: str):
        s = Settings.load()
        root = s.workspace_path().resolve()
        p = (root / path).resolve()
        if root not in p.parents and p != root:
            return JSONResponse({"error": "路径越界"}, status_code=403)
        if not p.exists() or p.is_dir():
            return JSONResponse({"error": "文件不存在"}, status_code=404)
        try:
            return {"path": path, "content": p.read_text(encoding="utf-8")}
        except UnicodeDecodeError:
            return JSONResponse({"error": "不是文本文件"}, status_code=415)

    # ------------------------------------------------------------ 设置
    @app.get("/api/settings")
    async def get_settings():
        s = Settings.load()
        return {"settings": s.public(), "mcp": MCP_HOLDER.status_summary()}

    @app.post("/api/settings")
    async def post_settings(payload: Dict[str, Any]):
        s = Settings.load()
        for k in ("api_key", "base_url", "model", "workspace", "temperature",
                  "max_steps", "timeout", "token_budget", "confirm_writes",
                  "auto_compress", "demo_mode"):
            if k in payload and payload[k] is not None:
                setattr(s, k, payload[k])
        if s.workspace:
            Path(s.workspace).expanduser().mkdir(parents=True, exist_ok=True)
        s.save()
        return {"settings": s.public()}

    # ------------------------------------------------------------ MCP
    @app.post("/api/mcp/reload")
    async def mcp_reload():
        cfg = load_mcp_config()
        await MCP_HOLDER.reload(cfg, resource("."))
        return {"mcp": MCP_HOLDER.status_summary()}

    # ------------------------------------------------------------ WebSocket
    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        sess = Session(websocket)
        await sess.emit({"type": "hello",
                         "model": Settings.load().model,
                         "mcp": MCP_HOLDER.status_summary()})
        pump = asyncio.create_task(_pump(websocket, sess))
        work = asyncio.create_task(_worker(sess))
        try:
            await asyncio.gather(pump, work)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            pump.cancel()
            work.cancel()

    return app


def _tree(root: Path, cur: Path, depth: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if depth <= 0:
        return out
    try:
        items = sorted(cur.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except Exception:
        return out
    for p in items:
        if p.name.startswith(".") or (p.is_dir() and p.name in SKIP_DIRS):
            continue
        node: Dict[str, Any] = {
            "name": p.name,
            "path": str(p.relative_to(root)).replace("\\", "/"),
            "type": "dir" if p.is_dir() else "file",
        }
        if p.is_dir():
            node["children"] = _tree(root, p, depth - 1)
        out.append(node)
    return out


class MCPHolder:
    """全局持有一份 MCP 连接池，界面可以热重载。"""

    def __init__(self):
        self.manager = MCPManager()

    def status_summary(self) -> List[Dict[str, Any]]:
        return self.manager.summary()

    async def reload(self, cfg: Dict[str, Any], base: Path) -> None:
        await self.manager.load(cfg, base)

    async def close(self) -> None:
        await self.manager.close_all()


MCP_HOLDER = MCPHolder()


class Session:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.queue: "asyncio.Queue[str]" = asyncio.Queue()
        self.cancel = asyncio.Event()
        self.pending: Optional[asyncio.Future] = None
        self.history: List[Dict[str, Any]] = []

    async def emit(self, ev: Dict[str, Any]) -> None:
        try:
            await self.ws.send_text(json.dumps(ev, ensure_ascii=False))
        except Exception:
            pass

    def stop(self) -> None:
        self.cancel.set()
        if self.pending and not self.pending.done():
            self.pending.set_result(False)


async def _pump(ws: WebSocket, sess: Session) -> None:
    while True:
        raw = await ws.receive_text()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        t = msg.get("type")
        if t == "chat":
            await sess.queue.put(str(msg.get("text", "")))
        elif t == "stop":
            await sess.emit({"type": "status", "text": "收到停止指令"})
            sess.stop()
        elif t == "confirm":
            if sess.pending and not sess.pending.done():
                sess.pending.set_result(bool(msg.get("accept")))
        elif t == "reset":
            sess.history.clear()
            await sess.emit({"type": "reset"})


async def _worker(sess: Session) -> None:
    while True:
        text = await sess.queue.get()
        if not text.strip():
            continue
        sess.cancel = asyncio.Event()

        async def confirm_cb(name: str, args: Dict[str, Any], diff: str) -> bool:
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            sess.pending = fut
            await sess.emit({"type": "confirm_request", "name": name,
                             "arguments": args, "diff": diff})
            try:
                return bool(await asyncio.wait_for(fut, timeout=180))
            except asyncio.TimeoutError:
                return False
            finally:
                sess.pending = None

        s = Settings.load()
        llm = None
        if s.demo_mode:
            from agent.mock import MockLLM, pick_script
            llm = MockLLM(pick_script(text))   # 按提问挑回放脚本，演示模式不止一个任务
        loop = AgentLoop(s, mcp=MCP_HOLDER.manager, confirm_cb=confirm_cb, llm=llm)
        try:
            result = await loop.run(text, emit=sess.emit, cancel=sess.cancel,
                                    history=sess.history)
        except Exception as e:  # 任何异常都不能把连接打死
            await sess.emit({"type": "error", "text": f"{type(e).__name__}: {e}"})
            await sess.emit({"type": "done", "text": f"出错了：{e}", "reason": "error"})
            continue
        sess.history.append({"role": "user", "content": text})
        sess.history.append({"role": "assistant", "content": result.answer})


def run(port: int = 8765, window: bool = True) -> None:
    import uvicorn
    app = create_app()

    async def _startup():
        cfg = load_mcp_config()
        if cfg.get("mcpServers"):
            await MCP_HOLDER.reload(cfg, resource("."))

    app.add_event_handler("startup", _startup)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run(port=int(os.environ.get("DESKTOP_AGENT_PORT", "8765")), window=False)
