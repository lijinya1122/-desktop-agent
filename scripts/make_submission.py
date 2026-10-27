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

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = Path.home() / "Desktop" / "MP2608016"

EXCLUDE_DIRS = {".venv", ".git", "dist", "build", "__pycache__", ".idea", ".vscode"}
EXCLUDE_FILES = {"*.log", "*.pyc", "thumbs.db"}

REPO_URL = "https://github.com/lijinya1122/-desktop-agent"
RELEASE_URL = "（发 Release 后填：https://github.com/lijinya1122/-desktop-agent/releases/tag/v1.0.0）"

README_TXT = f"""========== 大作业提交说明 ==========

姓名：李进雅
学号：MP2608016
组队：无

【两个链接】（评分看的就是这两个）
  仓库（public）：{REPO_URL}
  Release：{RELEASE_URL}

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
    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / "源码").mkdir(parents=True)
    (DEST / "安装包").mkdir(parents=True)
    (DEST / "docs").mkdir(parents=True)

    n = copy_source(DEST / "源码")

    for name in ("README.md", "report.md", "mcp.json", "requirements.txt",
                 "pyproject.toml", "desktop-agent.spec"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, DEST / name)

    for p in (ROOT / "docs").glob("*"):
        if p.is_file() and p.suffix.lower() in (".md", ".png"):
            shutil.copy2(p, DEST / "docs" / p.name)

    setup = ROOT / "installer" / "MiniCursor_1.0.0_Windows_x64_Setup.exe"
    zipf = ROOT / "dist" / "MiniCursor_1.0.0_Windows_x64.zip"
    for f in (setup, zipf):
        if f.exists():
            shutil.copy2(f, DEST / "安装包" / f.name)
        else:
            print(f"[警告] 缺少 {f.name}，请先打包（见 docs/build.md）")

    (DEST / "提交说明.txt").write_text(README_TXT, encoding="utf-8")

    total = sum(1 for _ in DEST.rglob("*") if _.is_file())
    size = sum(f.stat().st_size for f in DEST.rglob("*") if f.is_file()) / 1e6
    print(f"已生成：{DEST}")
    print(f"源码 {n} 个文件，共 {total} 个文件，{size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
