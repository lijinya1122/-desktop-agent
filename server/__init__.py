"""HTTP + WebSocket 层。只负责搬运事件，不含任何智能体逻辑。"""

from server.app import create_app  # noqa: F401

__all__ = ["create_app"]
