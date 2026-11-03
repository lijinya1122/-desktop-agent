"""按大作业要求，在桌面生成提交文件夹 MP2608016（可重复运行，每次都是最新内容）。

用法：
    python scripts/make_submission.py
生成的目录：
    C:\\Users\\Lenovo\\Desktop\\MP2608016\\
    ├── 提交说明.txt          姓名/学号/两个链接/目录说明
    ├── README.md  report.md
    ├── 源码/                 项目源码（已排除 .venv/.git/dist 等）
    ├── 安装包/               Setup.exe + 免安装 zip
    └── docs/                 trace.md · build.md · 运行截图
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {".venv", ".git", "dist", "build", "__pycache__", ".idea", ".vscode"}
EXCLUDE_FILES = {"*.log", "*.pyc", "thumbs.db"}

REPO_URL = "https://github.com/lijinya1122/-desktop-agent"
RELEASE_URL = "https://github.com/lijinya1122/-desktop-agent/releases/tag/v1.0.0"

# 个人模式默认署名；小组模式见 --team
OWNER_NAME = "李进雅"
OWNER_ID = "MP2608016"
TEAM_NAME = "一苇以航"
MEMBERS = [
    "MP2608016 李进雅",
    "MP2608017 宗雯雯",
    "MP2608019 张琳羚",
    "MP2608020 郭婉婷",
]


def header_block(team: str) -> str:
    """根据个人/小组模式生成 提交说明.txt 的署名段。"""
    if team:
        who = "\n".join(f"  {m}" for m in MEMBERS)
        return (f"组队：{team}\n"
                f"成员（学号 姓名）：\n{who}\n")
    return f"姓名：{OWNER_NAME}\n学号：{OWNER_ID}\n组队：无\n"


README_TXT = """========== 大作业提交说明 ==========

{header}

【两个链接】（评分看的就是这两个）
  仓库（public）：{repo}
  Release：{release}

【目录内容】
  README.md     三步启动、工具规格、护栏说明
  report.md     报告：架构取舍 / 再加一个工具 / 最不满意的地方
  源码/         完整项目源码（agent/ server/ ui/ examples/ scripts/ workspace/）
  安装包/       MiniCursor_1.0.0_Windows_x64_Setup.exe   ← 双击安装（推荐）
                MiniCursor_1.0.0_Windows_x64.zip        ← 解压即用备用
  docs/         trace.md（真实运行记录，含失败与恢复）
                build.md（打包步骤）
                shot1~4*.png（运行截图）

【怎么运行】
  方式一（推荐）：双击 安装包 里的 Setup.exe → 下一步 → 装完自动启动
  方式二：解压 zip → 双击 MiniCursor.exe（不需要装 Python）
  两种都不需要 Python 环境。首次启动在「设置」里填 API Key；
  没 Key 勾选「演示模式」也能完整走一遍（读文件 → edit 失败 → 恢复 → 跑测试）。

【验证】
  python scripts/selftest.py   → 13/13
  python scripts/smoke_ws.py   → 8/8
"""


def copy_source(dst: Path) -> int:
    """复制源码，跳过环境与产物目录。"""
    n = 0
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
            continue
        if p.suffix == ".log":
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst / rel)
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="生成大作业提交文件夹")
    ap.add_argument("--dir", default=OWNER_ID,
                    help=f"文件夹名（默认 {OWNER_ID}，个人模式）")
    ap.add_argument("--team", default="",
                    help="小组名；给了就按小组模式生成（署名换成队名+成员）")
    args = ap.parse_args()

    team = args.team or (TEAM_NAME if args.dir == TEAM_NAME else "")
    dest = Path.home() / "Desktop" / args.dir

    # 覆盖式生成：不删除已存在的目录（删目录容易失败/误删），直接覆盖同名文件
    (dest / "源码").mkdir(parents=True, exist_ok=True)
    (dest / "安装包").mkdir(parents=True, exist_ok=True)
    (dest / "docs").mkdir(parents=True, exist_ok=True)

    n = copy_source(dest / "源码")

    for name in ("README.md", "report.md", "AGENTS.md", "mcp.json", "requirements.txt",
                 "pyproject.toml", "desktop-agent.spec", "第一次运行请看这里.txt",
                 "skill_report.json", "custom_report.json", "daemon_report.json"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, dest / name)

    for p in (ROOT / "docs").glob("*"):
        if p.is_file() and p.suffix.lower() in (".md", ".png"):
            shutil.copy2(p, dest / "docs" / p.name)

    setup = ROOT / "installer" / "MiniCursor_1.0.0_Windows_x64_Setup.exe"
    zips = [ROOT / "dist" / "MiniCursor_1.0.0_Windows_x64.zip",
            ROOT / "installer" / "MiniCursor_Setup.zip"]
    for f in (setup, *zips):
        if f.exists():
            shutil.copy2(f, dest / "安装包" / f.name)
        else:
            print(f"[警告] 缺少 {f.name}，请先打包（见 docs/build.md）")

    # 小组模式：把 report.md / README.md 顶部的署名换成队名 + 成员
    if team:
        members = "、".join(m.split(" ", 1)[1] for m in MEMBERS)
        ids = "、".join(m.split(" ", 1)[0] for m in MEMBERS)
        new_head = f"> 组队：{team}　｜　成员：{members}　｜　学号：{ids}"
        for f in ("report.md", "README.md"):
            fp = dest / f
            if not fp.exists():
                continue
            lines = fp.read_text(encoding="utf-8").splitlines()
            for i, ln in enumerate(lines[:6]):
                if ln.startswith("> 姓名：") or ln.startswith("> 组队："):
                    lines[i] = new_head
                    break
            else:
                lines.insert(0, new_head)
            fp.write_text("\n".join(lines), encoding="utf-8")

    txt = README_TXT.format(header=header_block(team),
                            repo=REPO_URL, release=RELEASE_URL)
    (dest / "提交说明.txt").write_text(txt, encoding="utf-8")

    total = sum(1 for _ in dest.rglob("*") if _.is_file())
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / 1e6
    print(f"已生成：{dest}（{'小组模式 · ' + team if team else '个人模式'}）")
    print(f"源码 {n} 个文件，共 {total} 个文件，{size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
