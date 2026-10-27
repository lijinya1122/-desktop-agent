"""MCP 客户端：stdio + JSON-RPC（第 29、31 页）。

一个 server 就是一个子进程，协议只有三句：
  tools/list —— 你能干什么？
  tools/call —— 我要这个。
  result     —— 给你。
注意：stdout 是协议通道，server 里用 print 调试会直接把连接搞死，日志必须写 stderr。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2024-11-05"


class MCPError(Exception):
    pass


def _tool_alias(server: str, tool: str) -> str:
    return f"mcp_{server}_{tool}"


class MCPServer:
    """与一个 MCP server 保持一对一会话的 client。"""

    def __init__(self, name: str, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env_patch = env or {}
        self.cwd = cwd
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.tools: List[Dict[str, Any]] = []
        self.error: str = ""
        self._id = 0

    # ---------------------------------------------------------------- 生命周期
    async def start(self, timeout: float = 15.0) -> List[Dict[str, Any]]:
        env = dict(os.environ)
        env.update({k: str(v) for k, v in self.env_patch.items()})
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        cmd = self.command
        if cmd in ("python", "python3", "py"):
            # 打包后没有配套的 python，靠 PATH 找；找不到就优雅失败（界面显示 error）
            cmd = shutil.which(cmd) or cmd
        try:
            self.proc = await asyncio.create_subprocess_exec(
                cmd, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env, cwd=self.cwd or None,
            )
        except FileNotFoundError:
            raise MCPError(f"启动失败，找不到命令：{self.command}")
        except Exception as e:
            raise MCPError(f"启动失败：{e}")

        await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "desktop-agent", "version": "1.0.0"},
        }, timeout=timeout)
        # 通知，不需要回包
        self._send_notify("notifications/initialized", {})
        result = await self._request("tools/list", {}, timeout=timeout)
        self.tools = (result or {}).get("tools", [])
        return self.tools

    async def stop(self) -> None:
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        # Windows 上不显式关 transport，解释器退出时会刷一堆 ResourceWarning
        tr = getattr(self.proc, "_transport", None)
        if tr is not None:
            try:
                tr.close()
            except Exception:
                pass
        self.proc = None
        self.tools = []

    # ------------------------------------------------------------------ 传输层
    def _send_notify(self, method: str, params: Dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, obj: Dict[str, Any]) -> None:
        assert self.proc and self.proc.stdin
        line = json.dumps(obj, ensure_ascii=False)
        self.proc.stdin.write((line + "\n").encode("utf-8"))

    async def _request(self, method: str, params: Dict[str, Any],
                       timeout: float = 30.0) -> Dict[str, Any]:
        assert self.proc and self.proc.stdin and self.proc.stdout
        self._id += 1
        rid = self._id
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            await self.proc.stdin.drain()
        except Exception:
            pass

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise MCPError(f"{self.name}: {method} 超时（{timeout}s）")
            raw = await asyncio.wait_for(self.proc.stdout.readline(),
                                         timeout=remaining)
            if not raw:
                err = ""
                if self.proc.stderr:
                    try:
                        b = await asyncio.wait_for(self.proc.stderr.read(2000), timeout=1)
                        err = b.decode("utf-8", "replace").strip()
                    except Exception:
                        pass
                raise MCPError(f"{self.name}: 连接已断开。server 日志：{err[:400]}")
            text = raw.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                # 最常见的坑：server 里 print 了调试信息，污染了协议通道
                continue
            if msg.get("id") != rid:
                continue  # 通知或别人的回包，跳过
            if "error" in msg:
                raise MCPError(f"{self.name}: {msg['error']}")
            return msg.get("result", {})

    # -------------------------------------------------------------------- 调用
    async def call_tool(self, tool: str, arguments: Dict[str, Any],
                        timeout: float = 60.0) -> str:
        res = await self._request("tools/call", {"name": tool, "arguments": arguments},
                                  timeout=timeout)
        parts: List[str] = []
        for block in (res or {}).get("content", []):
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
        if res.get("isError"):
            parts.insert(0, "[server 返回错误] ")
        return "\n".join(parts) or "(空结果)"

    def schemas(self) -> List[Dict[str, Any]]:
        out = []
        for t in self.tools:
            out.append({
                "type": "function",
                "function": {
                    "name": _tool_alias(self.name, t.get("name", "")),
                    "description": "[MCP:%s] %s" % (self.name, t.get("description", "")),
                    "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
                },
            })
        return out


class MCPManager:
    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self._alias: Dict[str, tuple] = {}
        self.status: Dict[str, str] = {}   # name -> ok / error 文本

    async def load(self, config: Dict[str, Any], base: Path) -> None:
        await self.close_all()
        servers = (config or {}).get("mcpServers", {})
        for name, cfg in servers.items():
            if not cfg.get("enabled", True):
                self.status[name] = "已禁用"
                continue
            command = cfg.get("command")
            if not command:
                self.status[name] = "缺少 command"
                continue
            args = [str(a) for a in cfg.get("args", [])]
            if args and not Path(args[0]).is_absolute():
                maybe = base / args[0]
                if maybe.exists():
                    args[0] = str(maybe)
            cwd = cfg.get("cwd")
            if cwd and not Path(cwd).is_absolute():
                cwd = str(base / cwd)
            srv = MCPServer(name, command, args, cfg.get("env"), cwd or str(base))
            try:
                tools = await srv.start()
                self.servers[name] = srv
                self.status[name] = "ok · %d 工具" % len(tools)
            except Exception as e:
                self.status[name] = f"失败：{e}"
                await srv.stop()
        self._rebuild_alias()

    def _rebuild_alias(self) -> None:
        self._alias = {}
        for name, srv in self.servers.items():
            for t in srv.tools:
                self._alias[_tool_alias(name, t.get("name", ""))] = (srv, t.get("name", ""))

    async def close_all(self) -> None:
        for srv in list(self.servers.values()):
            await srv.stop()
        self.servers.clear()
        self._alias.clear()
        self.status.clear()

    def schemas(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for srv in self.servers.values():
            out.extend(srv.schemas())
        return out

    def has(self, alias: str) -> bool:
        return alias in self._alias

    async def call(self, alias: str, arguments: Dict[str, Any]) -> str:
        pair = self._alias.get(alias)
        if not pair:
            raise MCPError(f"没有这个 MCP 工具：{alias}")
        srv, tool = pair
        return await srv.call_tool(tool, arguments or {})

    def summary(self) -> List[Dict[str, Any]]:
        out = []
        for name, srv in self.servers.items():
            out.append({
                "name": name,
                "status": self.status.get(name, ""),
                "tools": [t.get("name", "") for t in srv.tools],
            })
        for name, st in self.status.items():
            if name not in self.servers:
                out.append({"name": name, "status": st, "tools": []})
        return out


def is_mcp_tool(name: str) -> bool:
    return name.startswith("mcp_")
