"""智能体包：循环 + 四个工具。可以脱离界面单独跑（python -m agent.cli）。"""

from agent.config import Settings, load_mcp_config  # noqa: F401

__all__ = ["Settings", "load_mcp_config"]
