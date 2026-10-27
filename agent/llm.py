"""LLM 客户端：OpenAI 兼容 /chat/completions，SSE 流式。

只做一件事：把 messages + tools 发出去，把「文本增量」和「工具调用意图」收回来。
模型永远不碰文件系统 —— 它只输出结构化的申请。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

import httpx


class LLMError(Exception):
    pass


def estimate_tokens(text: str) -> int:
    """粗估：中英混合按 1 token ≈ 1.6 字符。够用来做预算护栏。"""
    return int(len(text or "") / 1.6) + 1


def messages_tokens(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        c = m.get("content") or ""
        if isinstance(c, list):
            c = " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
        total += estimate_tokens(str(c))
        for tc in m.get("tool_calls") or []:
            total += estimate_tokens(json.dumps(tc, ensure_ascii=False))
    return total


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str,
                 temperature: float = 0.2, timeout: float = 180.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def describe(self) -> str:
        masked = (self.api_key[:3] + "***" + self.api_key[-4:]) if len(self.api_key) > 8 else "(未设置)"
        return f"{self.model} @ {self.base_url} · key={masked}"

    async def chat(self, messages: List[Dict[str, Any]],
                   tools: Optional[List[Dict[str, Any]]] = None,
                   on_text: Optional[Callable[[str], Any]] = None,
                   cancel: Optional[asyncio.Event] = None) -> Dict[str, Any]:
        """返回 {"role":"assistant","content":str,"tool_calls":[...]}。"""
        if not self.api_key:
            raise LLMError("还没配置 API Key：请在界面「设置」里填写，或设置环境变量 OPENAI_API_KEY")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        content_parts: List[str] = []
        calls: Dict[int, Dict[str, Any]] = {}
        usage: Dict[str, Any] = {}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=20.0, read=self.timeout)
        ) as client:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")[:600]
                        raise LLMError(f"HTTP {resp.status_code}：{body}")
                    async for line in resp.aiter_lines():
                        if cancel is not None and cancel.is_set():
                            break
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if "error" in obj:
                            raise LLMError(str(obj["error"])[:400])
                        if obj.get("usage"):
                            usage = obj["usage"]
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        if delta.get("content"):
                            content_parts.append(delta["content"])
                            if on_text:
                                r = on_text(delta["content"])
                                if asyncio.iscoroutine(r):
                                    await r
                        for d in delta.get("tool_calls") or []:
                            idx = d.get("index", 0)
                            slot = calls.setdefault(
                                idx, {"id": "", "name": "", "arguments": ""}
                            )
                            if d.get("id"):
                                slot["id"] = d["id"]
                            fn = d.get("function") or {}
                            if fn.get("name"):
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["arguments"] += fn["arguments"]
            except httpx.HTTPError as e:
                raise LLMError(f"网络错误：{type(e).__name__}: {e}")

        tool_calls: List[Dict[str, Any]] = []
        for idx in sorted(calls):
            slot = calls[idx]
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"].strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": slot["arguments"]}
            tool_calls.append({
                "id": slot["id"] or f"call_{idx}",
                "type": "function",
                "function": {"name": slot["name"], "arguments": json.dumps(args, ensure_ascii=False)},
            })

        reply: Dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
        }
        if usage:
            reply["usage"] = usage
        return reply
