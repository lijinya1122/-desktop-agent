"""ReAct 循环：决策 → 动作 → 观察 → 再决策（第 19、21 页）。

所谓 Agent 框架，就是这段代码加了很多工程细节。
三道护栏：步数上限、上下文预算、整体超时 —— 任一触发即退出，宁可失败不要失控。
"""

from __future__ import annotations

import asyncio
import difflib
import json
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent import prompts
from agent.config import Settings
from agent.llm import LLMClient, LLMError, messages_tokens
from agent.mcp import MCPManager, is_mcp_tool
from agent import tools as tmod
from agent.tools import ToolError, ToolResult, WORKSPACE, _unified_diff

EventFn = Callable[[Dict[str, Any]], Any]


@dataclass
class Step:
    index: int
    thought: str = ""
    calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RunResult:
    answer: str
    steps: int
    reason: str = "done"        # done / max_steps / timeout / cancelled / error
    trace: List[Dict[str, Any]] = field(default_factory=list)


def workspace_tree(root, limit: int = 120) -> List[str]:
    from pathlib import Path
    root = Path(root)
    out: List[str] = []
    skip = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", ".idea"}
    try:
        for p in sorted(root.rglob("*")):
            if any(part in skip for part in p.parts):
                continue
            rel = p.relative_to(root)
            depth = len(rel.parts)
            if depth > 3:
                continue
            out.append(("  " * (depth - 1)) + (p.name + "/" if p.is_dir() else p.name))
            if len(out) >= limit:
                out.append("… 还有更多文件")
                break
    except Exception:
        pass
    return out


class AgentLoop:
    def __init__(self, settings: Settings, mcp: Optional[MCPManager] = None,
                 confirm_cb: Optional[Callable[..., Any]] = None,
                 llm: Optional[Any] = None):
        self.settings = settings
        self.mcp = mcp or MCPManager()
        self.confirm_cb = confirm_cb
        self._llm_override = llm
        self.client = llm or LLMClient(
            api_key=settings.api_key, base_url=settings.base_url,
            model=settings.model, temperature=settings.temperature,
        )
        self.history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ 预览
    def _preview(self, name: str, args: Dict[str, Any]) -> str:
        """写操作先算一次 diff，执行前给人看一眼。"""
        try:
            if name == "edit":
                p = tmod._resolve(str(args.get("path", "")))
                text = p.read_text(encoding="utf-8")
                old = str(args.get("old", ""))
                n = text.count(old)
                if n == 0:
                    return "（old 未命中，执行会失败）"
                if n > 1:
                    return f"（old 出现 {n} 次，执行会失败）"
                rel = str(p.relative_to(WORKSPACE.resolve()))
                return _unified_diff(text, text.replace(old, str(args.get("new", "")), 1), rel)
            if name == "write":
                p = tmod._resolve(str(args.get("path", "")))
                old = p.read_text(encoding="utf-8") if p.exists() else ""
                rel = str(p.relative_to(WORKSPACE.resolve()))
                return _unified_diff(old, str(args.get("content", "")), rel)
        except Exception as e:
            return f"（预览失败：{e}）"
        return ""

    # ------------------------------------------------------------------ 执行
    async def _execute(self, name: str, args: Dict[str, Any]) -> ToolResult:
        if is_mcp_tool(name):
            if not self.mcp.has(name):
                raise ToolError(f"MCP 工具不可用：{name}（server 未连接）")
            text = await self.mcp.call(name, args)
            return ToolResult(text, extra={"kind": "mcp", "tool": name})
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, tmod.call_tool, name, args)

    # ------------------------------------------------------------------ 主循环
    async def run(self, task: str, emit: EventFn,
                  cancel: Optional[asyncio.Event] = None,
                  history: Optional[List[Dict[str, Any]]] = None) -> RunResult:
        s = self.settings
        tmod.set_workspace(s.workspace_path())
        root = s.workspace_path()
        tree = workspace_tree(root)
        system = prompts.system_prompt(str(root), tree, f"{platform.system()} {platform.release()}")

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(history or self.history)
        messages.append({"role": "user", "content": prompts.user_task(task)})

        schemas = list(tmod.SCHEMAS) + self.mcp.schemas()
        await emit({"type": "status", "text": f"已挂载 {len(schemas)} 个工具（内置 4 + MCP {len(schemas) - 4}）"})

        deadline = time.time() + max(30, int(s.timeout))
        answer = ""
        reason = "done"
        trace: List[Dict[str, Any]] = []
        last_call_sig = ""
        repeat = 0

        async def _emit(ev: Dict[str, Any]) -> None:
            r = emit(ev)
            if asyncio.iscoroutine(r):
                await r

        for step in range(1, int(s.max_steps) + 1):
            if cancel is not None and cancel.is_set():
                reason = "cancelled"
                answer = "已中断：你点了停止，循环在第 %d 步之前停下了。" % step
                break
            if time.time() > deadline:
                reason = "timeout"
                answer = f"达到整体超时（{s.timeout}s），已停止。已完成的部分见上面的工具记录。"
                break

            # 系统提醒：长任务每隔几轮重申一次关键约束，防跑偏
            if step > 1 and step % 3 == 0:
                messages.append({"role": "user", "content": prompts.REMINDER.format(workspace=root)})

            if self.settings.auto_compress:
                messages = self._compress(messages, _emit)

            await _emit({"type": "step", "index": step, "max": s.max_steps})
            try:
                reply = await self.client.chat(
                    messages, tools=schemas,
                    on_text=lambda t: _emit({"type": "token", "text": t}),
                    cancel=cancel,
                )
            except LLMError as e:
                reason = "error"
                answer = f"模型调用失败：{e}"
                await _emit({"type": "error", "text": answer})
                break

            calls = reply.get("tool_calls") or []
            if not calls:
                answer = reply.get("content") or ""
                if not answer:
                    answer = "（模型没有给出结论，也没有调用工具）"
                await _emit({"type": "answer", "text": answer})
                trace.append({"step": step, "thought": answer, "calls": []})
                break

            messages.append({
                "role": "assistant",
                "content": reply.get("content") or "",
                "tool_calls": calls,
            })
            rec = Step(index=step, thought=reply.get("content") or "")

            for call in calls:
                if cancel is not None and cancel.is_set():
                    reason = "cancelled"
                    break
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": fn.get("arguments", "")}
                call_id = call.get("id", f"c{step}")
                await _emit({"type": "tool_call", "id": call_id, "name": name,
                             "arguments": args, "step": step,
                             "mcp": is_mcp_tool(name)})

                # 循环检测：连续同样调用 -> 提醒模型换路
                sig = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
                repeat = repeat + 1 if sig == last_call_sig else 1
                last_call_sig = sig

                # 确认闸门：写操作先给 diff
                if (self.settings.confirm_writes and name in tmod.WRITE_TOOLS
                        and self.confirm_cb is not None):
                    diff = self._preview(name, args)
                    ok = await self.confirm_cb(name, args, diff)
                    if not ok:
                        obs = f"用户拒绝了这次 {name}。请换个思路，或先说明你打算怎么改。"
                        await _emit({"type": "tool_result", "id": call_id, "name": name,
                                     "ok": False, "text": obs, "diff": "", "rejected": True})
                        messages.append({"role": "tool", "tool_call_id": call_id,
                                         "name": name, "content": obs})
                        rec.calls.append({"name": name, "args": args, "ok": False,
                                          "observation": obs})
                        continue

                t0 = time.time()
                try:
                    res = await self._execute(name, args)
                    obs = res.text
                    ok = True
                    diff = res.diff
                except ToolError as e:
                    obs, ok, diff = f"工具报错：{e}", False, ""
                except Exception as e:  # 兜底：任何异常都要变成模型看得懂的话
                    obs, ok, diff = f"工具异常：{type(e).__name__}: {e}", False, ""

                obs = tmod._truncate(obs, int(s.max_tool_chars))
                await _emit({
                    "type": "tool_result", "id": call_id, "name": name,
                    "ok": ok, "text": obs[:4000], "diff": diff,
                    "ms": int((time.time() - t0) * 1000),
                    "truncated": len(obs) > 4000,
                })
                messages.append({"role": "tool", "tool_call_id": call_id,
                                 "name": name, "content": obs})
                rec.calls.append({"name": name, "args": args, "ok": ok,
                                  "observation": obs[:2000]})
                if repeat >= 3:
                    messages.append({
                        "role": "user",
                        "content": f"[提醒] 你已经连续 {repeat} 次用相同参数调用 {name}，"
                                   f"结果没有变化。换一种方式，或者停下来说明卡在哪。",
                    })
                    await _emit({"type": "warning",
                                 "text": f"检测到连续 {repeat} 次相同调用：{name}"})
            else:
                trace.append({"step": rec.index, "thought": rec.thought, "calls": rec.calls})
                continue
            break

        else:
            reason = "max_steps"
            answer = (f"达到步数上限（{s.max_steps} 步）仍未完成，已停止并转人工。"
                      f"上面每一步的工具调用都可以回放。")
            await _emit({"type": "warning", "text": answer})

        if reason == "cancelled" and not answer:
            answer = "已中断。"
        trace.append({"step": "final", "answer": answer, "reason": reason})
        await _emit({"type": "done", "text": answer, "reason": reason, "steps": len(trace)})
        return RunResult(answer=answer, steps=len(trace), reason=reason, trace=trace)

    # ---------------------------------------------------------------- 上下文
    def _compress(self, messages: List[Dict[str, Any]], emit: EventFn) -> List[Dict[str, Any]]:
        """上下文是预算，不是垃圾桶：超预算就把中间的旧观察换成占位符。"""
        budget = int(self.settings.token_budget)
        if messages_tokens(messages) <= budget or len(messages) < 6:
            return messages
        keep_head = 2                    # system + 第一个 user
        keep_tail = 6                    # 最近几轮必须留着
        out = list(messages)
        dropped = 0
        for i in range(keep_head, len(out) - keep_tail):
            m = out[i]
            c = m.get("content")
            if isinstance(c, str) and len(c) > 400:
                dropped += len(c)
                out[i] = {**m, "content": "[…该工具返回已被压缩，需要时请重新调用工具获取…]"}
        if dropped:
            try:
                asyncio.get_event_loop().create_task(
                    emit({"type": "warning",
                          "text": f"上下文接近预算，已压缩约 {dropped // 1000}k 字符的旧观察"})
                )
            except RuntimeError:
                pass
        return out
