"""四个工具：read / write / edit / bash。

原则（第 20、36 页）：
  · 前半段是普通 Python 函数，先单独跑通再接给模型；
  · 后半段是一张说明书，description 写「什么时候用」，它就是提示词；
  · 权限、沙箱、超时全在这一层 —— 模型永远不碰文件系统，它只申请。
"""

from __future__ import annotations

import base64
import difflib
import mimetypes
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

WORKSPACE: Path = Path.cwd()

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}
DENY_COMMANDS = [
    "rm -rf /", "rm -rf /*", "format ", "del /f /s /q c:",
    "shutdown", ":(){", "mkfs", "dd if=", "git push --force",
]
DIFF_MAX_LINES = 400


class ToolError(Exception):
    """工具失败。故意不抛 Traceback 给模型 —— 错误信息是它的下一步线索。"""


@dataclass
class ToolResult:
    text: str                                   # 回灌给模型的观察
    blocks: List[Dict[str, Any]] = field(default_factory=list)   # 多模态内容块
    diff: str = ""                              # 给界面看的 diff
    extra: Dict[str, Any] = field(default_factory=dict)


def set_workspace(path: Path) -> None:
    global WORKSPACE
    WORKSPACE = Path(path).expanduser().resolve()
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def _top_level() -> str:
    try:
        names = sorted(
            f"{p.name}/" if p.is_dir() else p.name for p in WORKSPACE.iterdir()
        )
    except Exception:
        return ""
    return "、".join(names[:12])


def _resolve(path: str) -> Path:
    """路径白名单。resolve() + 前缀校验 —— 这一行比任何提示词都可靠。"""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = WORKSPACE / p
    try:
        rp = p.resolve()
    except OSError:
        raise ToolError(f"路径无效：{path}")
    root = WORKSPACE.resolve()
    if rp != root and root not in rp.parents:
        raise ToolError(
            f"拒绝：路径越界（{path}）。只能访问工作区内的文件，可用目录：{_top_level()}"
        )
    return rp


def _decode(data: bytes) -> str:
    """cmd.exe 输出 GBK（中文 Windows），Python 脚本被我们要求输出 UTF-8 —— 依次试。"""
    text = ""
    for enc in ("utf-8", "gbk"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = data.decode("utf-8", "replace")
    return text.replace("\r\n", "\n")   # 统一换行，别让 \r 占模型的上下文


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: int(limit * 0.7)]
    tail = text[-int(limit * 0.2):]
    return f"{head}\n…[已截断，省略 {len(text) - len(head) - len(tail)} 字符]…\n{tail}"


def _unified_diff(old: str, new: str, path: str) -> str:
    lines = list(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(),
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=2,
        )
    )
    if len(lines) > DIFF_MAX_LINES:
        lines = lines[:DIFF_MAX_LINES] + [f"… diff 过长，省略 {len(lines) - DIFF_MAX_LINES} 行"]
    return "\n".join(lines)


def _atomic_write(p: Path, content: str) -> None:
    """临时文件 + rename：写一半崩了也不会留下半个文件。"""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp_", suffix=".write")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp, p)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------
def read(path: str, offset: int = 1, limit: int = 800) -> ToolResult:
    """读取工作区内的文件内容。需要看某个文件里写了什么时使用。

    文本按行返回并带行号；超大文件会分页并告诉你还剩多少行；
    图片返回图片内容，不要试图用文本方式读取图片。
    """
    p = _resolve(path)
    if not p.exists():
        raise ToolError(f"文件不存在：{path}。可用目录：{_top_level()}")

    if p.suffix.lower() in IMAGE_EXT:
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return ToolResult(
            text=f"[图片] {path}（{p.stat().st_size} 字节，{mime}）",
            blocks=[{"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64[:200000]}"}}],
            extra={"kind": "image", "path": str(p)},
        )

    try:
        raw = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"不是 UTF-8 文本：{path}（二进制文件请用 bash 处理）")

    lines = raw.splitlines()
    total = len(lines)
    start = max(1, int(offset))
    end = min(total, start + max(1, int(limit)) - 1)
    body = "\n".join(f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1))
    head = f"文件：{path}（共 {total} 行）\n"
    tail = ""
    if end < total:
        tail = (f"\n… 还有 {total - end} 行未显示，"
                f"继续读请传 offset={end + 1}")
    return ToolResult(head + body + tail,
                      extra={"kind": "read", "path": str(p), "total_lines": total})


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def write(path: str, content: str) -> ToolResult:
    """把完整内容写入文件（新建或整体覆盖）。

    只在确实要整体生成/重写一个文件时使用；
    改动已有文件的一小部分请优先用 edit，避免整文件重排。
    父目录会自动创建，写入是原子的。
    """
    p = _resolve(path)
    old = ""
    old_lines = 0
    if p.exists():
        try:
            old = p.read_text(encoding="utf-8")
            old_lines = len(old.splitlines())
        except UnicodeDecodeError:
            raise ToolError(f"目标已存在且不是 UTF-8 文本，拒绝覆盖：{path}")
    _atomic_write(p, content)
    new_lines = len(content.splitlines())
    rel = str(p.relative_to(WORKSPACE.resolve())) if str(p).startswith(
        str(WORKSPACE.resolve())) else path
    diff = _unified_diff(old, content, rel)
    msg = f"已写入 {rel}：原 {old_lines} 行 → 现 {new_lines} 行"
    if old_lines:
        msg += "（这是覆盖写入，原来的内容已被替换）"
    return ToolResult(msg, diff=diff,
                      extra={"kind": "write", "path": rel,
                             "old_lines": old_lines, "new_lines": new_lines})


# --------------------------------------------------------------------------
# edit
# --------------------------------------------------------------------------
def edit(path: str, old: str, new: str) -> ToolResult:
    """精确字符串替换，用于修改文件的一小段。

    old 必须是文件中唯一出现的原文（连同缩进一起照抄）。
    出现 0 次或多次都会报错而不会猜 —— 这时请把 old 写长一点，
    带上函数名、变量名等更多上下文，让它唯一。
    不要用它做整文件重写。
    """
    if not old:
        raise ToolError("old 不能为空")
    p = _resolve(path)
    if not p.exists():
        raise ToolError(f"文件不存在：{path}。可用目录：{_top_level()}")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"不是 UTF-8 文本，无法 edit：{path}")

    count = text.count(old)
    if count == 0:
        hint = ""
        first = old.strip().splitlines()[0] if old.strip() else ""
        if first:
            near = [i + 1 for i, ln in enumerate(text.splitlines()) if first in ln]
            if near:
                hint = f"；相近的行号：{near[:5]}（注意缩进与空格必须完全一致）"
        raise ToolError(f"edit 失败：old 在 {path} 中出现 0 次{hint}。"
                        f"请先 read 该文件，照抄原文（含缩进）。")
    if count > 1:
        raise ToolError(
            f"edit 失败：old 在 {path} 中出现 {count} 次，无法确定改哪一处。"
            f"请把 old 写长一点（多带几行上下文）让它唯一，不要用模糊匹配。"
        )

    updated = text.replace(old, new, 1)
    _atomic_write(p, updated)
    rel = str(p.relative_to(WORKSPACE.resolve())) if str(p).startswith(
        str(WORKSPACE.resolve())) else path
    diff = _unified_diff(text, updated, rel)
    added = len(new.splitlines()) - len(old.splitlines())
    return ToolResult(
        f"已修改 {rel}：替换 1 处，行数变化 {added:+d}",
        diff=diff,
        extra={"kind": "edit", "path": rel, "replacements": 1, "delta_lines": added},
    )


# --------------------------------------------------------------------------
# bash
# --------------------------------------------------------------------------
def bash(command: str, timeout: int = 30, max_chars: int = 20000) -> ToolResult:
    """在工作区内执行一条 shell 命令。

    列目录、跑测试、git、装依赖、搜索全部走它 —— 不要为这些事另造专用工具。
    非 0 退出码也是正常结果，会把 stdout/stderr/exit_code 一起返回。
    一定有超时，输出会被截断。
    """
    command = (command or "").strip()
    if not command:
        raise ToolError("命令为空")
    low = command.lower()
    for bad in DENY_COMMANDS:
        if bad in low:
            raise ToolError(f"拒绝执行危险命令：{command}")

    timeout = max(1, min(int(timeout), 120))
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})

    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=str(WORKSPACE),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,   # 字节流：cmd.exe 的输出是 GBK，Python 脚本是 UTF-8，收完再解
        )
    except Exception as e:  # pragma: no cover
        raise ToolError(f"命令无法启动：{e}")

    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = b"", b""

    out, err = _decode(out), _decode(err)

    out = _truncate(out or "", max_chars)
    err = _truncate(err or "", max_chars)
    buf = []
    buf.append(f"$ {command}")
    if timed_out:
        buf.append(f"[超过 {timeout}s 已被终止]")
    if out.strip():
        buf.append(out.rstrip())
    if err.strip():
        buf.append(f"[stderr]\n{err.rstrip()}")
    buf.append(f"[exit_code={proc.returncode}]")
    return ToolResult(
        "\n".join(buf),
        extra={"kind": "bash", "command": command,
               "exit_code": proc.returncode, "timed_out": timed_out},
    )


# --------------------------------------------------------------------------
# 说明书：模型只看得到这些
# --------------------------------------------------------------------------
TOOLS: Dict[str, Callable[..., ToolResult]] = {
    "read": read,
    "write": write,
    "edit": edit,
    "bash": bash,
}

SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": (
                "读取工作区内的文件内容。需要看某个文件里写了什么时使用。"
                "文本按行返回并带行号；超大文件会分页并告诉你还剩多少行；"
                "图片返回图片内容，不要试图用文本方式读取图片。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的路径，如 stats.py"},
                    "offset": {"type": "integer", "description": "起始行号，从 1 开始"},
                    "limit": {"type": "integer", "description": "最多读多少行，默认 800"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": (
                "把完整内容写入文件（新建或整体覆盖）。"
                "只在确实要整体生成/重写一个文件时使用；"
                "改动已有文件的一小段请优先用 edit，避免整文件重排。"
                "父目录会自动创建，写入是原子的。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的路径"},
                    "content": {"type": "string", "description": "文件的完整内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": (
                "精确字符串替换，用于修改文件的一小段。"
                "old 必须是文件中唯一出现的原文（连同缩进一起照抄）。"
                "出现 0 次或多次都会报错而不会猜 —— 这时请把 old 写长一点，"
                "带上函数名、变量名等更多上下文让它唯一。不要用它做整文件重写。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区的路径"},
                    "old": {"type": "string", "description": "要被替换的原文，必须唯一"},
                    "new": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "在工作区内执行一条 shell 命令。"
                "列目录、跑测试、git、装依赖、搜索全部走它。"
                "非 0 退出码也是正常结果，会把 stdout/stderr/exit_code 一起返回。"
                "一定有超时，输出会被截断。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 120"},
                },
                "required": ["command"],
            },
        },
    },
]

WRITE_TOOLS = {"write", "edit"}


def call_tool(name: str, arguments: Dict[str, Any]) -> ToolResult:
    """白名单分发：名字不在字典里直接报错。执行权永远在这张表里。"""
    fn = TOOLS.get(name)
    if fn is None:
        raise ToolError(
            f"没有这个工具：{name}。可用工具：{', '.join(sorted(TOOLS))}"
        )
    try:
        return fn(**(arguments or {}))
    except TypeError as e:
        raise ToolError(f"参数不对：{name}({arguments}) -> {e}")
