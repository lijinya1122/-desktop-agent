"""增量 D｜readiness 体检：按「九根柱子」给自己的仓库打分、定级。

    python -m app.inspect readiness --out readiness_report.json

第 1 讲的主张：多数失败不是模型不够强，是环境没有给可以检查的信号。
九根柱子 = agent 需要"自己检查自己"的九件事（课件 P10）：
  样式与校验 / 构建 / 测试 / 文档 / 开发环境 / 可观测性 / 安全 / 任务发现 / 产品与实验

定级（课件 P11，一级要过 80% 判据）：
  L1 能跑 → L2 写下来了 → L3 标准化（检查自动且强制，多数团队的目标）
  → L4 优化过（反馈够快，撑得住独跑）→ L5 不用管

判据全部是能跑的命令和存在的文件，不是形容词。
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

FIXES = {
    "style": "把 scripts/check_style.py 挂到 python -m app.check 的第一步，5 秒反馈买回 120 倍尝试",
    "build": "补 desktop-agent.spec 并用 PyInstaller 打出安装包（见 docs/build.md）",
    "tests": "把 selftest 收进 python -m app.check —— 一条命令跑完所有测试",
    "docs": "补 README / AGENTS.md / docs/ 三份里的缺项，README 要能带新人跑通",
    "env": "补 requirements.txt 和 .env.example，别让 agent 猜变量名",
    "observability": "让 loop 把每一步 trace 落盘（docs/trace.md），卡住时有处可查",
    "security": "补三条 hook（密钥/不可逆命令/自动测试）并把 .env 写进 .gitignore",
    "task_discovery": "写 AGENTS.md 项目地图 + skills/ 目录，让它知道下一步该干什么",
    "product": "补安装包与演示材料（截图 / 演示脚本），做完没人用等于没做",
}

SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{16,}")


def _run(cmd: List[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _pillar_style() -> Dict[str, Any]:
    r = _run([PY, "-X", "utf8", str(ROOT / "scripts" / "check_style.py")], 60)
    return {"ok": r.returncode == 0, "score": 100 if r.returncode == 0 else 0,
            "evidence": "python scripts/check_style.py → " + (r.stdout or r.stderr).strip().splitlines()[-1][:80]}


def _pillar_build() -> Dict[str, Any]:
    spec = (ROOT / "desktop-agent.spec").is_file()
    dist = [p for p in (ROOT / "dist").glob("*") if p.suffix in (".exe", ".zip")] if (ROOT / "dist").is_dir() else []
    ok = spec and bool(dist)
    return {"ok": ok, "score": 100 if ok else 40,
            "evidence": f"spec={'yes' if spec else 'no'}，dist 产物 {len(dist)} 个"}


def _pillar_tests() -> Dict[str, Any]:
    """跑自检；先备份演示靶子，跑完还原 —— 体检不许弄脏仓库。"""
    target = ROOT / "workspace" / "stats.py"
    backup = target.read_text(encoding="utf-8") if target.is_file() else None
    t0 = time.time()
    try:
        r = _run([PY, "-X", "utf8", str(ROOT / "scripts" / "selftest.py")], 180)
        dt = round(time.time() - t0, 1)
        out = (r.stdout or "")
        ms = re.findall(r"(\d+)/(\d+)\s*通过", out)
        # 结论取最后一个（中途子套件也会打「x/y 通过」）
        passed, total = (int(ms[-1][0]), int(ms[-1][1])) if ms else (0, 0)
        ok = r.returncode == 0 and total > 0 and passed == total
        return {"ok": ok, "score": 100 if ok else int(passed / max(total, 1) * 100),
                "evidence": f"python scripts/selftest.py → {passed}/{total}，{dt}s",
                "seconds": dt}
    finally:
        if backup is not None:
            target.write_text(backup, encoding="utf-8")


def _pillar_docs() -> Dict[str, Any]:
    readme = ROOT / "README.md"
    agents = ROOT / "AGENTS.md"
    docs = list((ROOT / "docs").glob("*.md")) if (ROOT / "docs").is_dir() else []
    c1 = readme.is_file() and len(readme_lines(readme)) >= 40
    c2 = agents.is_file()
    c3 = len(docs) >= 3
    ok = c1 and c2 and c3
    return {"ok": ok, "score": 100 if ok else sum((c1, c2, c3)) * 33,
            "evidence": f"README {len(readme_lines(readme))} 行 /"
                        f" AGENTS.md={'yes' if c2 else 'no'} / docs {len(docs)} 份"}


def readme_lines(p: Path) -> List[str]:
    return p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else []


def _pillar_env() -> Dict[str, Any]:
    req = ROOT / "requirements.txt"
    env_ex = ROOT / ".env.example"
    n_deps = len([l for l in req.read_text(encoding="utf-8", errors="replace").splitlines()
                  if l.strip() and not l.startswith("#")]) if req.is_file() else 0
    ok = req.is_file() and env_ex.is_file() and n_deps <= 15
    return {"ok": ok, "score": 100 if ok else 50,
            "evidence": f"requirements.txt {n_deps} 条依赖 / .env.example={'yes' if env_ex.is_file() else 'no'}"}


def _pillar_observability() -> Dict[str, Any]:
    loop = ROOT / "agent" / "loop.py"
    has_trace = loop.is_file() and "trace" in loop.read_text(encoding="utf-8", errors="replace")
    trace_md = (ROOT / "docs" / "trace.md").is_file()
    failures = (ROOT / "docs" / "failures.md").is_file()
    ok = has_trace and trace_md and failures
    return {"ok": ok, "score": 100 if ok else 60,
            "evidence": f"loop 写 trace={'yes' if has_trace else 'no'} /"
                        f" docs/trace.md={'yes' if trace_md else 'no'} /"
                        f" failures.md={'yes' if failures else 'no'}"}


def _pillar_security() -> Dict[str, Any]:
    hooks = ROOT / "agent" / "hooks.py"
    has_hooks = hooks.is_file() and "pre_tool" in hooks.read_text(encoding="utf-8", errors="replace")
    gi = ROOT / ".gitignore"
    ignores_env = gi.is_file() and ".env" in gi.read_text(encoding="utf-8", errors="replace")
    leaks = 0
    for pat in ("*.py", "*.md", "*.json", "*.txt", "*.iss"):
        for f in ROOT.rglob(pat):
            s = str(f)
            if ".venv" in s or "build" in s or "dist" in s or "installer" in s:
                continue
            try:
                leaks += len(SECRET_RE.findall(f.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                pass
    ok = has_hooks and ignores_env and leaks == 0
    return {"ok": ok, "score": 100 if ok else (0 if leaks else 60),
            "evidence": f"hooks 代码={'yes' if has_hooks else 'no'} /"
                        f" .gitignore 防密钥={'yes' if ignores_env else 'no'} / 泄露扫描 {leaks} 处"}


def _pillar_discovery() -> Dict[str, Any]:
    agents = ROOT / "AGENTS.md"
    has_map = agents.is_file() and "项目地图" in agents.read_text(encoding="utf-8", errors="replace")
    skills = list((ROOT / "skills").glob("*/SKILL.md")) if (ROOT / "skills").is_dir() else []
    mcp = ROOT / "mcp.json"
    n_mcp = mcp.read_text(encoding="utf-8", errors="replace").count('"command"') if mcp.is_file() else 0
    ok = has_map and len(skills) >= 3 and n_mcp >= 1
    return {"ok": ok, "score": 100 if ok else sum((has_map, len(skills) >= 3, n_mcp >= 1)) * 33,
            "evidence": f"AGENTS.md 项目地图={'yes' if has_map else 'no'} / 技能 {len(skills)} 个 / MCP server {n_mcp} 个"}


def _pillar_product() -> Dict[str, Any]:
    inst = ROOT / "installer"
    pkg = any(p.suffix == ".exe" for p in inst.glob("*.exe")) if inst.is_dir() else False
    shot = (ROOT / "docs" / "screenshot.png").is_file()
    demo = (ROOT / "docs" / "demo_script.md").is_file()
    ok = pkg and shot and demo
    return {"ok": ok, "score": 100 if ok else sum((pkg, shot, demo)) * 33,
            "evidence": f"安装包={'yes' if pkg else 'no'} / 界面截图={'yes' if shot else 'no'}"
                        f" / 演示脚本={'yes' if demo else 'no'}"}


PILLARS = [
    ("style", "样式与校验", _pillar_style),
    ("build", "构建系统", _pillar_build),
    ("tests", "测试", _pillar_tests),
    ("docs", "文档", _pillar_docs),
    ("env", "开发环境", _pillar_env),
    ("observability", "可观测性", _pillar_observability),
    ("security", "安全", _pillar_security),
    ("task_discovery", "任务发现", _pillar_discovery),
    ("product", "产品与实验", _pillar_product),
]


def readiness_report(root: Path = ROOT) -> Dict[str, Any]:
    pillars: List[Dict[str, Any]] = []
    test_seconds = None
    for key, name, fn in PILLARS:
        try:
            r = fn()
        except Exception as e:  # 体检自身不许崩：柱子出错记为不通过
            r = {"ok": False, "score": 0, "evidence": f"体检异常 {type(e).__name__}: {e}"}
        r = {"key": key, "name": name, **r}
        if key == "tests":
            test_seconds = r.get("seconds")
        pillars.append(r)

    passed = sum(1 for p in pillars if p["ok"])
    ratio = passed / len(pillars)

    # 定级（一级要过 80% 判据；判据写成能跑的命令，不是形容词）
    one_cmd_tests = (ROOT / "app" / "check.py").is_file()
    if ratio >= 1.0 and test_seconds is not None and test_seconds < 60 and one_cmd_tests:
        level = "L4"
    elif ratio >= 0.8 and one_cmd_tests:
        level = "L3"
    elif ratio >= 0.67:
        level = "L2"
    elif ratio >= 0.34:
        level = "L1"
    else:
        level = "L0"

    todo = [FIXES[p["key"]] for p in pillars if not p["ok"]][:3]
    if not todo:
        todo = ["L4 → L5 还差 CI（.github/workflows）：push 后自动跑 python -m app.check",
                "把 pre-commit 钩子接上 git，让检查在 commit 那一刻就发生",
                "给 bash 工具输出加结构化日志，可观测性从「有 trace」升级到「能检索」"]

    return {
        "level": level,
        "passed": passed,
        "total": len(pillars),
        "ratio": round(ratio, 2),
        "one_command_tests": one_cmd_tests,
        "command": "python -m app.check",
        "test_seconds": test_seconds,
        "pillars": pillars,
        "todo_top3": todo,
        "note": "判据全部是能跑的命令与存在的文件（课件 P11：别用「我觉得差不多了」）",
    }
