"""配置与路径。

Key 只存在两处（优先级从高到低）：
  1. 环境变量 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
  2. 用户目录 ~/.desktop-agent/settings.json（界面里填的 Key 写到这里）
永远不会写回仓库，也不会发给前端明文。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict

APP_NAME = "desktop-agent"
APP_TITLE = "Mini Cursor"


def project_root() -> Path:
    """开发时是仓库根；PyInstaller 打包后是 sys._MEIPASS。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def resource(rel: str) -> Path:
    return project_root() / rel


def app_home() -> Path:
    """可写目录。打包后资源目录不可写，所以配置和日志一律落到这里。"""
    env = os.environ.get("DESKTOP_AGENT_HOME")
    p = Path(env).expanduser() if env else Path.home() / ".desktop-agent"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return app_home() / "settings.json"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def default_workspace() -> Path:
    """打包后 _MEIPASS 是只读的，工作区必须落到用户目录，否则 write/edit 全废。"""
    if _frozen():
        ws = app_home() / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        if not any(ws.iterdir()):
            src = resource("workspace")
            if src.exists():
                for p in src.glob("*"):          # 把自带的演示文件铺一份进去
                    if p.is_file():
                        shutil.copy2(p, ws / p.name)
        return ws
    ws = project_root() / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@dataclass
class Settings:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    temperature: float = 0.2
    max_steps: int = 12          # 护栏 1：步数上限
    token_budget: int = 48000    # 护栏 2：上下文预算（估算 token）
    timeout: int = 600           # 护栏 3：整体超时（秒）
    max_tool_chars: int = 20000  # 工具返回值上限，防上下文爆炸
    workspace: str = ""
    confirm_writes: bool = True  # 写操作先给 diff 再执行
    auto_compress: bool = True   # 超预算时自动压缩上下文
    demo_mode: bool = False      # 离线回放：不联网也能走完整链路（演示/教学用）

    @classmethod
    def load(cls) -> "Settings":
        data: Dict[str, Any] = {}
        p = settings_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        known = {k: v for k, v in data.items() if k in cls.__annotations__}
        s = cls(**known)
        # 环境变量兜底（.env 由启动脚本 load_dotenv 注入）
        s.api_key = os.environ.get("OPENAI_API_KEY", s.api_key)
        s.base_url = os.environ.get("OPENAI_BASE_URL", s.base_url)
        s.model = os.environ.get("OPENAI_MODEL", s.model)
        if not s.workspace:
            s.workspace = str(default_workspace())
        return s

    def save(self) -> None:
        data = asdict(self)
        settings_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            os.chmod(settings_path(), 0o600)
        except Exception:
            pass

    def workspace_path(self) -> Path:
        p = Path(self.workspace).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def public(self) -> Dict[str, Any]:
        """发给前端的副本：Key 只回显掩码。"""
        d = asdict(self)
        key = self.api_key
        d["api_key"] = ""
        d["api_key_set"] = bool(key)
        d["api_key_hint"] = (key[:3] + "***" + key[-4:]) if len(key) > 8 else ""
        d["workspace_exists"] = Path(self.workspace).exists()
        return d


def mcp_config_path() -> Path:
    env = os.environ.get("DESKTOP_AGENT_MCP")
    if env:
        return Path(env).expanduser()
    local = app_home() / "mcp.json"
    return local if local.exists() else resource("mcp.json")


def load_mcp_config() -> Dict[str, Any]:
    p = mcp_config_path()
    if not p.exists():
        return {"mcpServers": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"mcpServers": {}}
