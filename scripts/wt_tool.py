"""worktree 工位内的任务执行器：模型层=脚本化 plan，工具层=agent 的真工具。

    python scripts/wt_tool.py <action> <path> [name]

动作：
  read <path>                    用 tools.read 看文件（带行号）
  fix-and-add <stats.py路径>     修空列表 bug（2 处 return 0 → raise）+ 用 edit 加 stdev
  add-greet <hello.py路径>       用 write 给 hello.py 加 greet
  add-test <test路径>            用 write 追加 stdev 的两个用例

每个动作都走 agent.tools —— 沙箱、行号、diff 语义和真会话完全一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import tools as t  # noqa: E402


def fix_and_add(path: str) -> None:
    src = Path(path).read_text(encoding="utf-8")
    # 第一步（edit 工具语义）：两处 return 0 → raise ValueError
    src2 = src.replace("    if not nums:\n        return 0",
                       '    if not nums:\n        raise ValueError("空列表")')
    if src2 == src:
        raise SystemExit("edit 失败：没找到靶子（old 出现 0 次）")
    # 第二步：文件尾追加 stdev，用 write 工具整体写回
    addition = '''

def stdev(nums):
    """样本标准差（n-1）；至少要两个数。"""
    if len(nums) < 2:
        raise ValueError("stdev 需要至少两个数")
    m = mean(nums)
    var = sum((x - m) ** 2 for x in nums) / (len(nums) - 1)
    return var ** 0.5
'''
    t.write(path, src2.rstrip("\n") + addition)   # 失败会抛 ToolError（非零退出）
    print("[wt_tool] stats.py：修 bug + 加 stdev 完成")


def add_greet(path: str) -> None:
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    src = src.rstrip("\n") + '''


def greet(n):
    """返回 n 行问候（worktree 工位 B 的任务）。"""
    return [f"hello #{i}" for i in range(1, n + 1)]
'''
    t.write(path, src)
    print("[wt_tool] hello.py：加 greet 完成")


def add_test(path: str) -> None:
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    addition = '''

def test_stdev_basic():
    assert abs(stats.stdev([2, 4, 4, 4, 5, 5, 7, 9]) - 2.138) < 0.01


def test_stdev_need_two():
    try:
        stats.stdev([1])
    except ValueError:
        return
    raise AssertionError("stdev([1]) 应该抛 ValueError")
'''
    t.write(path, src.rstrip("\n") + addition)
    print("[wt_tool] test_stats.py：+2 个 stdev 用例")


def main() -> None:
    action = sys.argv[1]
    path = sys.argv[2]
    if action == "read":
        r = t.read(path)
        print(r.text[:400])
    elif action == "fix-and-add":
        fix_and_add(path)
    elif action == "add-greet":
        add_greet(path)
    elif action == "add-test":
        add_test(path)
    else:
        raise SystemExit(f"未知动作 {action}")


if __name__ == "__main__":
    main()
