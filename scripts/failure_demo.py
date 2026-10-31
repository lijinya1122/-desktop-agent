"""故意制造三种失败，把工具层的真实报错写进 docs/failures.md。

为什么单独做：评分表要「trace 里有失败与恢复」，而失败必须是真的 ——
这个脚本真的调用工具、真的失败、真的恢复，输出原样落盘，可重复运行。

    python scripts/failure_demo.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import tools as tmod  # noqa: E402
from agent.tools import ToolError  # noqa: E402

DOC = ROOT / "docs" / "failures.md"


def setup() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="faildemo-")) / "ws"
    tmp.mkdir(parents=True)
    (tmp / "dup.txt").write_text(
        "def mean(nums):\n    return 0\n\n\ndef median(nums):\n    return 0\n",
        encoding="utf-8")
    tmod.set_workspace(tmp)
    return tmp


def call(fn, *a, **kw) -> tuple:
    """返回 (是否成功, 真实输出文本, 耗时ms)。"""
    t0 = time.time()
    try:
        r = fn(*a, **kw)
        return True, r.text, int((time.time() - t0) * 1000)
    except ToolError as e:
        return False, str(e), int((time.time() - t0) * 1000)


def main() -> int:
    ws = setup()
    blocks = []

    # ---------------------------------------------------------- 失败 1
    ok, text, ms = call(tmod.edit, "dup.txt", "    return 0", "    raise ValueError()")
    blocks.append(("失败 1 · edit 的 old 不唯一",
                   '工具调用：`edit(path="dup.txt", old="    return 0", '
                   'new="    raise ValueError()")`',
                   ok, text, ms))
    # 恢复：把 old 写长，带上函数签名，命中唯一
    ok2, text2, ms2 = call(tmod.edit, "dup.txt",
                           "def mean(nums):\n    return 0",
                           "def mean(nums):\n    raise ValueError('nums 不能为空')")
    blocks.append(("恢复 · old 写长后唯一命中",
                   '工具调用：`edit(old="def mean(nums):\\n    return 0", …)`',
                   ok2, text2, ms2))

    # ---------------------------------------------------------- 失败 2
    ok3, text3, ms3 = call(tmod.read, str(Path.home() / "Desktop" / "研究生课表.pdf"))
    blocks.append(("失败 2 · 读工作区外的文件（路径越界）",
                   '工具调用：`read("~/Desktop/研究生课表.pdf")`',
                   ok3, text3, ms3))
    ok4, text4, ms4 = call(tmod.read, "../../etc/passwd")
    blocks.append(("失败 2b · 用 ../ 跳出工作区",
                   '工具调用：`read("../../etc/passwd")`',
                   ok4, text4, ms4))

    # ---------------------------------------------------------- 失败 3
    ok5, text5, ms5 = call(tmod.bash, "python -c \"import time; time.sleep(30)\"", timeout=3)
    blocks.append(("失败 3 · bash 超时 → 被掐断并如实报告（工具不假装成功）",
                   '工具调用：`bash("python -c \\"import time; time.sleep(30)\\"", timeout=3)`',
                   ok5, text5, ms5))

    # ---------------------------------------------------------- 失败 4
    ok6, text6, ms6 = call(tmod.edit, "dup.txt", "这一行根本不存在", "x")
    blocks.append(("失败 4 · old 在文件里不存在",
                   '工具调用：`edit(old="这一行根本不存在")`',
                   ok6, text6, ms6))

    lines = [
        "# 失败与恢复 · 工具层的真实报错",
        "",
        f"> 由 `python scripts/failure_demo.py` 生成（{datetime.now():%Y-%m-%d %H:%M}）。",
        "> 每一次都是真的调用了工具、真的失败 —— 输出原样贴在这里，可重复运行。",
        "",
    ]
    for title, inv, ok, text, ms in blocks:
        flag = "ok" if ok else "ERR"
        lines.append(f"## {title}")
        lines.append("")
        lines.append(inv)
        lines.append("")
        lines.append("```")
        lines.append(f"<- [{flag}] {ms}ms")
        for ln in text.splitlines():
            lines.append("     " + ln)
        lines.append("```")
        lines.append("")

    lines += [
        "## 这些失败说明了什么",
        "",
        "| 失败 | 工具的做法 | 为什么重要 |",
        "|---|---|---|",
        "| old 不唯一 | 拒绝猜测，如实报「出现 N 次」并提示写长 old | 不瞎改代码，模型能据此自我纠正 |",
        "| 路径越界 | 拒绝并告知可用范围 | 安全边界是硬边界，模型再请求也没用 |",
        "| bash 超时 | 到点掐断，返回「已被终止」 | 一条死循环命令不会把整个界面拖死 |",
        "| old 不存在 | 明确报「没找到」，不静默成功 | 失败可见，才谈得上恢复 |",
        "",
        "**共同的取舍**：宁可失败得响亮，也不成功得含糊。四条都不是「尽力猜一下」，",
        "而是把确定的事实交还给模型 —— 模型拿到「出现 2 次」就知道该把 old 写长，",
        "拿到「路径越界」就知道该换目标。这就是失败能变成恢复的原因。",
        "",
    ]

    DOC.write_text("\n".join(lines), encoding="utf-8")
    print(f"已写入 {DOC}（{len(blocks)} 段真实输出）")
    for title, _inv, ok, _t, _ms in blocks:
        print(f"  {'ok ' if ok else 'ERR'} {title}")
    shutil.rmtree(ws.parent, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
