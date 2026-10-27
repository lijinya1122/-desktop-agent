# 怎么打的包

打包路线选的是 **PyInstaller**（后端 + 前端一起打成一个 exe，最简单，一条命令）。

## 1. 打 exe

```bash
.venv\Scripts\activate
pip install pyinstaller==6.11.1
pyinstaller desktop-agent.spec --noconfirm --clean
```

产物：`dist/MiniCursor/MiniCursor.exe`（onedir 模式，启动比 onefile 快得多）。

## 2. spec 里必须写死的三件事

```python
datas = [("ui", "ui"), ("mcp.json", "."), ("workspace", "workspace")]
hiddenimports = ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto_impl",
                 "uvicorn.protocols.websockets.auto_impl", "uvicorn.lifespan.on",
                 "engineio.async_drivers.threading", "webview", "clr"]
```

- `ui` 必须带 —— 少了它界面是白屏
- `hiddenimports` 里那几行 `uvicorn.*` 不带的话，exe 起来报 `Failed to load module`
- `console=False`：不要黑框

## 3. 打包后最容易踩的两个坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 找不到 `ui/`、`mcp.json` | 资源在 `sys._MEIPASS` 里，不在 cwd | `agent/config.py:resource()` 统一走 `_MEIPASS` |
| 写不了配置 | 资源目录只读 | 配置/日志一律写 `Path.home()/.desktop-agent`，见 `app_home()` |

## 4. 验证（别跳过）

```bash
# 双击 dist/MiniCursor/MiniCursor.exe
# 检查项：出窗口 → 有标题栏 → 左下角 MCP 已连接 → 设置里能填 Key → 跑一次任务
```

`mcp.json` 里的 `python` 命令在没装 Python 的机器上会连不上；
Release 里附一个 `说明.txt`：要么装 Python，要么把 `command` 改成打包后的 server 路径。

## 5. 做成「双击能装」的安装包

免安装版（解压即用，立刻能用）：

```bash
Compress-Archive -Path "dist\MiniCursor\*" -DestinationPath "dist\MiniCursor_1.0.0_Windows_x64.zip" -Force
```

真正的安装程序（有开始菜单 + 桌面快捷方式 + 卸载项）：

1. 装 Inno Setup 6（免费）：<https://jrsoftware.org/isdl.php>
2. 打开 `installer/install.iss` → Build → Compile（或 `iscc installer\install.iss`）
3. 产物：`installer\MiniCursor_1.0.0_Windows_x64_Setup.exe`

## 6. 发 Release

```bash
git tag v1.0.0 && git push origin v1.0.0
# GitHub → Releases → 上传 dist/MiniCursor_1.0.0_Windows_x64.zip（或 Setup.exe）+ report.md
```

## 7. 打包后踩到的两个坑（已修）

| 现象 | 原因 | 处理 |
|---|---|---|
| 智能体写文件失败 | exe 解压目录 `_MEIPASS` 只读 | 打包后工作区改到 `~/.desktop-agent/workspace`，首次启动自动铺一份演示文件（`agent/config.py:default_workspace`） |
| MCP server 连不上 | 目标机器 PATH 里没有 `python` | `agent/mcp.py` 用 `shutil.which` 找，找不到就优雅失败（左下角显示 error），不影响主流程 |
| 窗口 10 秒后自己关 | 强杀进程留下的僵尸 `msedgewebview2.exe` 干扰 | 不是代码问题；别用 `Stop-Process -Force`，正常关闭窗口即可 |
