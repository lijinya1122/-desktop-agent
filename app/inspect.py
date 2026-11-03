"""验收命令：所有数字都由程序打印，不是报告里手写的表格。

    python -m app.inspect skills --out skill_report.json
    python -m app.inspect custom --out custom_report.json
    python -m app.inspect daemon --out daemon_report.json      # 选做

三条命令都不依赖界面，也不联网（reviewer 走规则引擎，结果可复现）。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import agents_md, hooks  # noqa: E402
from agent import skills as skmod  # noqa: E402
from agent import tools as tmod  # noqa: E402
from agent.reviewer import Reviewer  # noqa: E402

# 触发试验：6 条正例 + 2 条**不该触发**的（expected = None）
TRIALS = [
    ("帮我跑一下测试", "run-tests"),
    ("测试没过，为什么挂了", "run-tests"),
    ("跑测试看看", "run-tests"),
    ("把这段 diff 审一遍", "review-diff"),
    ("review 一下刚才的改动", "review-diff"),
    ("查课表：周五什么时候上课", "course-lookup"),
    ("今天天气怎么样", None),
    ("帮我写一封请假邮件", None),
]


def _dump(data: dict, out: str | None, title: str) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"已写入 {out}")
    print(text)


# ---------------------------------------------------------------- skills
def cmd_skills(args) -> int:
    # 开关关掉时连目录都不读：验收要能看出 before/after 的差别
    reg = skmod.SkillRegistry.load(ROOT) if skmod.enabled() else skmod.SkillRegistry()
    trials = []
    fp = 0
    for query, expected in TRIALS:
        hit, _score = reg.match(query)
        got = hit.name if hit else None
        ok = got == expected
        if expected is None and got is not None:
            fp += 1
        trials.append({"query": query, "expected": expected, "hit": got, "ok": ok})

    data = {
        "generated_by": "python -m app.inspect skills",
        "skills_enabled": skmod.enabled(),
        "skills": [
            {
                "name": s.name,
                "has_scripts": s.has_scripts,
                "uses_mcp": s.uses_mcp,
                "header_tokens": s.header_tokens(),
                "body_tokens": skmod.estimate_tokens(s.body),
                "path": str(s.path.relative_to(ROOT)).replace("\\", "/"),
            }
            for s in reg.skills.values()
        ],
        "catalog_tokens": reg.catalog_tokens(),
        "full_tokens": reg.full_tokens(),
        "disclosure_ratio": reg.disclosure_ratio(),
        "trials": trials,
        "false_positive": fp,
        "thresholds": {"skills_min": 3, "ratio_min": 5, "trials_min": 6, "false_positive_max": 0},
    }
    shapes = {("scripts" if s["has_scripts"] else "mcp" if s["uses_mcp"] else "prompt")
              for s in data["skills"]}
    data["shapes"] = sorted(shapes)
    _dump(data, args.out, "skills")
    print(f"\n核对：技能 {len(data['skills'])} 个、形态 {data['shapes']}、"
          f"ratio {data['disclosure_ratio']}、误触发 {fp}")
    return 0


# ---------------------------------------------------------------- custom
def _autotest_scenario() -> dict:
    """真跑一遍：先红 → 改对 → 绿 → 再改错 → 红 → 再改对 → 绿。"""
    if not hooks.enabled():
        return {"runs": 0, "red": 0, "green": 0, "red_to_green": 0, "injected_lines": 0}
    tmp = Path(tempfile.mkdtemp(prefix="autotest-")) / "ws"
    tmp.mkdir(parents=True)
    for f in ("stats.py", "test_stats.py"):
        shutil.copy2(ROOT / "workspace" / f, tmp / f)
    tmod.set_workspace(tmp)

    runs = red = green = r2g = injected = 0

    def one(name: str, call) -> None:
        nonlocal runs, red, green, r2g, injected
        was_red = red > green          # 上一次是不是红的
        ok = True
        try:
            if call:
                call()
        except Exception:
            ok = False
        res = hooks.run_autotest(tmp)
        if not res:
            return
        runs += 1
        if res["ok"]:
            green += 1
            if was_red:
                r2g += 1
        else:
            red += 1
        summary = hooks.post_tool("edit", {}, ok, tmp)
        if summary:
            injected = max(injected, len(summary.splitlines()))

    def fix(name: str) -> None:
        tmod.edit("stats.py", f"def {name}(nums):\n    if not nums:\n        return 0",
                  f"def {name}(nums):\n    if not nums:\n        raise ValueError('空列表')")

    one("baseline", None)                 # 1) 原本就红：空列表返回 0，测试断言要它抛错
    one("fix both", lambda: (fix("mean"), fix("median")))   # 2) 一次改对 → 绿
    one("break median", lambda: tmod.edit(
        "stats.py",
        "def median(nums):\n    if not nums:\n        raise ValueError('空列表')",
        "def median(nums):\n    if not nums:\n        return 'oops'"))   # 3) 手抖改错 → 红
    one("fix median", lambda: tmod.edit(
        "stats.py",
        "def median(nums):\n    if not nums:\n        return 'oops'",
        "def median(nums):\n    if not nums:\n        raise ValueError('空列表')"))   # 4) 照红字改回 → 绿

    shutil.rmtree(tmp.parent, ignore_errors=True)
    return {"runs": runs, "red": red, "green": green,
            "red_to_green": r2g, "injected_lines": injected}


def cmd_custom(args) -> int:
    ws = ROOT / "workspace"
    amd = agents_md.load(ws)

    denied = []
    for tool, payload, label in (
        ("write", {"path": ".env", "content": "OPENAI_API_KEY=sk-xxx"}, ".env"),
        ("bash", {"command": "rm -rf build/"}, "rm -rf build/"),
        ("bash", {"command": "git push --force origin main"}, "git push --force origin main"),
    ):
        reason = hooks.pre_tool(tool, payload)
        if reason:
            denied.append({"tool": tool,
                           "path": label if tool == "write" else "",
                           "command": "" if tool == "write" else label,
                           "reason": reason})

    auto = _autotest_scenario()
    rev = Reviewer(ROOT).run()

    data = {
        "generated_by": "python -m app.inspect custom",
        "hooks_enabled": hooks.enabled(),
        "agents_md": {"found": amd.found, "bytes": amd.bytes, "layers": amd.layers,
                      "tokens": amd.tokens(),
                      "paths": [str(p).replace("\\", "/") for p in amd.paths]},
        "denied": denied,
        "autotest": auto,
        "reviewer": {"runs": rev.runs, "issues_found": len(rev.issues),
                     "main_context_delta": rev.main_context_delta,
                     "subagent_tokens": rev.subagent_tokens,
                     "changed_files": rev.changed_files[:8],
                     "final_message": rev.final_message.splitlines()[:3]},
        "thresholds": {"agents_md_max_bytes": agents_md.MAX_BYTES, "denied_min": 2,
                       "red_to_green_min": 1, "main_context_delta_max": 500},
    }
    _dump(data, args.out, "custom")
    print(f"\n核对：AGENTS.md {amd.bytes} 字节（{'全局+项目' if amd.layers == ['global', 'project'] else amd.layers}）、"
          f"拦截 {len(denied)} 条、测试 {auto['runs']} 次（红→绿 {auto['red_to_green']}）、"
          f"reviewer 上下文 +{rev.main_context_delta} token")
    return 0


# ---------------------------------------------------------------- daemon
def cmd_daemon(args) -> int:
    from agent import daemon

    data = daemon.inspect_report(ROOT)
    _dump(data, args.out, "daemon")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.inspect",
                                 description="生成验收 JSON（数字全部由程序打印）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("skills", cmd_skills, "技能系统报告"),
                            ("custom", cmd_custom, "定制层报告"),
                            ("daemon", cmd_daemon, "常驻能力报告（选做）")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--out", default=None, help="写到文件（同时打印）")
        p.set_defaults(func=fn)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
