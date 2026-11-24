"""增量 E｜开两个工位跑一次：git worktree 隔离 + 并行任务 + 合并冲突实验。

    python -m app.inspect parallel --out parallel_report.json
    （等价：python scripts/parallel_demo.py --out parallel_report.json）

第 2 讲的主张：并行不是把速度乘三，是把「看清楚」的成本也乘三。
所以本实验做三件事，一个都不能省：
  1. worktree 起两个工位，任务切分遵守「文件层互不相碰」；
  2. 并行跑完各自跑测试，再合回 main，记录耗时与冲突；
  3. 追加一个「故意踩脚」实验：两个分支改同一行，看冲突怎么暴露、原因是什么。

报告里每个数字都来自这条命令本身（git 的输出 + 计时器），不是手写。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
_venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
PY = str(_venv_py.resolve()) if _venv_py.exists() else (shutil.which("python") or "python")


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {r.stderr.strip()}")
    return r


# ---------------------------------------------------------------- 工位任务
def wt_task(name: str, wt: Path) -> Dict[str, Any]:
    """在一个 worktree 里用 agent 的真工具完成任务，并跑测试。

    模型层 = 演示模式回放（脚本化的 plan），工具层 = 真执行（read/write/bash）。
    两个任务在文件层互不相碰：A 只碰 stats.py + test_stats.py，B 只碰 hello.py。
    """
    t0 = time.time()
    steps: List[str] = []
    ws = wt / "workspace"

    def run_tool(desc: str, cmd: List[str], cwd: Path = wt) -> str:
        steps.append(desc)
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"{desc} 失败: {(r.stderr or r.stdout)[:300]}")
        return r.stdout

    if name == "A":  # 修空列表 bug + 加 stdev + 补 2 个用例
        run_tool("read stats.py", [PY, "-X", "utf8", str(ROOT / "scripts" / "wt_tool.py"),
                                   "read", str(ws / "stats.py")])
        run_tool("edit stats.py（修 bug + 加 stdev）",
                 [PY, "-X", "utf8", str(ROOT / "scripts" / "wt_tool.py"),
                  "fix-and-add", str(ws / "stats.py")])
        run_tool("edit test_stats.py（+2 用例）",
                 [PY, "-X", "utf8", str(ROOT / "scripts" / "wt_tool.py"),
                  "add-test", str(ws / "test_stats.py")])
        out = run_tool("bash 跑测试（workspace 下）", [PY, "-X", "utf8", "test_stats.py"], cwd=ws)
        ok = "6/6 通过" in out
    else:  # 给 hello.py 加 greet(n)
        run_tool("read hello.py", [PY, "-X", "utf8", str(ROOT / "scripts" / "wt_tool.py"),
                                   "read", str(ws / "hello.py")])
        run_tool("edit hello.py（+greet）", [PY, "-X", "utf8", str(ROOT / "scripts" / "wt_tool.py"),
                                            "add-greet", str(ws / "hello.py")])
        out = run_tool("bash 跑 hello.py", [PY, "-X", "utf8", str(ws / "hello.py")])
        ok = "1x1" in out

    return {"task": name, "seconds": round(time.time() - t0, 1), "steps": steps,
            "tests_pass": bool(ok)}


def main() -> int:
    ap = argparse.ArgumentParser(description="增量 E：worktree 双工位并行实验")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    report: Dict[str, Any] = {"worktrees": [], "merge": {}, "conflict_experiment": {}}

    try:
        # 0. 前置：main 干净才敢开工
        if git("status", "--porcelain").stdout.strip():
            raise RuntimeError("工作树不干净：先提交再并行（派活纪律 01）")

        # 1. 两个工位（路径全部用绝对路径 —— git 对相对路径的解析基准和 shell 不同）
        wt_dirs = {"wt-a": (ROOT.parent / "wt-a").resolve(), "wt-b": (ROOT.parent / "wt-b").resolve()}
        for tag, branch in (("wt-a", "feat/stdev"), ("wt-b", "feat/greet")):
            git("worktree", "add", str(wt_dirs[tag]), "-b", branch)
        report["worktrees"] = [
            {"name": "wt-a", "branch": "feat/stdev", "dir": str(wt_dirs["wt-a"])},
            {"name": "wt-b", "branch": "feat/greet", "dir": str(wt_dirs["wt-b"])}]
        listing = git("worktree", "list").stdout.strip()

        # 2. 并行跑（同时开两个工位）
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(wt_task, "A", wt_dirs["wt-a"]),
                    pool.submit(wt_task, "B", wt_dirs["wt-b"])]
            results = [f.result() for f in futs]
        wall = round(time.time() - t0, 1)
        serial = round(sum(r["seconds"] for r in results), 1)
        report["tasks"] = results
        report["parallel"] = {"wall_seconds": wall, "serial_estimate": serial,
                              "speedup": round(serial / wall, 2)}

        # 3. 合回 main（干净合并）
        for r in results:
            r["tests_pass"] = bool(r["tests_pass"])
        merges = []
        for branch in ("feat/stdev", "feat/greet"):
            m = git("merge", "--no-edit", branch)
            merges.append({"branch": branch, "clean": "CONFLICT" not in m.stdout,
                           "summary": m.stdout.strip().splitlines()[0] if m.stdout else ""})
        report["merge"] = {"clean_merges": merges, "conflict_files": []}

        # 4. 冲突实验：两个分支改 workspace/NOTES.md 的同一行
        wt_c = (ROOT.parent / "wt-c").resolve()
        wt_d = (ROOT.parent / "wt-d").resolve()
        git("worktree", "add", str(wt_c), "-b", "feat/notes-c")
        git("worktree", "add", str(wt_d), "-b", "feat/notes-d")
        notes = "并行实验日志：本行由 {who} 写入\n"
        for tag, who, wdir in (("wt-c", "工位C", wt_c), ("wt-d", "工位D", wt_d)):
            (wdir / "workspace" / "NOTES.md").write_text(notes.format(who=who), encoding="utf-8")
            git("add", "workspace/NOTES.md", cwd=ROOT.parent / tag)
            git("commit", "-m", f"notes: {who} 写入同一行", cwd=ROOT.parent / tag)
        git("merge", "--no-edit", "feat/notes-c")
        m2 = git("merge", "--no-edit", "feat/notes-d", check=False)
        conflict_files = [l.split(":", 1)[-1].strip()
                          for l in (m2.stdout + m2.stderr).splitlines() if "CONFLICT" in l]
        reason = ("两个工位在文件层踩脚：feat/notes-c 和 feat/notes-d 都重写了 "
                  "workspace/NOTES.md 的同一行，git 无法裁决谁对 —— "
                  "对应课件 P22 冲突来源 1（同一个文件）。对策：任务切分时写明边界。")
        report["conflict_experiment"] = {"conflict_files": conflict_files, "reason": reason,
                                         "resolved_by": "abort（实验目的就是看冲突暴露，不解决）"}
        git("merge", "--abort") if conflict_files else None
        if conflict_files:
            git("reset", "--hard", "HEAD")  # 回到只合了 notes-c 的状态

        report["worktree_list"] = listing
        ok = (all(r["tests_pass"] for r in results)
              and all(m["clean"] for m in merges)
              and bool(conflict_files))
        report["ok"] = ok

        # 5. 收尾：删工位、删分支（课件 P19「三个你一定会忘的收尾」）
        cleanup = []
        for tag, wdir in (("wt-a", wt_dirs["wt-a"]), ("wt-b", wt_dirs["wt-b"]),
                          ("wt-c", wt_c), ("wt-d", wt_d)):
            git("worktree", "remove", str(wdir), "--force")
            cleanup.append(tag)
        for branch in ("feat/stdev", "feat/greet", "feat/notes-c", "feat/notes-d"):
            git("branch", "-D", branch)
        report["cleanup"] = cleanup

        data = json.dumps(report, ensure_ascii=False, indent=2)
        print(data[:1600])
        if args.out:
            Path(args.out).write_text(data, encoding="utf-8")
            print(f"\n已写入 {args.out}")
        print(f"核对：双工位并行 wall {wall}s（串行估 {serial}s，{round(serial/wall,2)}x），"
              f"干净合并 2 支，冲突实验抓到 {len(conflict_files)} 个文件")
        return 0 if ok else 1
    finally:
        # 兜底清理：任何异常路径都不给仓库留工位
        r = git("worktree", "list", check=False)
        for line in r.stdout.splitlines():
            if "/wt-" in line.replace("\\", "/"):
                shutil.rmtree(line.split()[0], ignore_errors=True)
        git("worktree", "prune", check=False)
        for b in git("branch", "--list", "feat/*").stdout.split():
            git("branch", "-D", b.strip(), check=False)


if __name__ == "__main__":
    main()
