# 项目地图

MiniCursor：本地桌面编程智能体。PyWebView 窗口 + 本地后端（127.0.0.1:8765）+ WebSocket 事件流。

```
app.py            ← 入口：起后端、开窗口、首次运行铺演示工作区
agent/loop.py     ← ReAct 循环（决策→工具→观察），三道护栏都在这里
agent/tools.py    ← read/write/edit/bash 四个工具 + 路径沙箱，改描述要同步改 SCHEMAS
agent/llm.py      ← 模型客户端（OpenAI 兼容），流式输出与取消
agent/mcp.py      ← MCP 客户端（stdio JSON-RPC），工具名前缀 mcp_<server>_
agent/skills.py   ← 技能系统：只加载目录，正文靠 use_skill(name) 按需注入
agent/hooks.py    ← 三条硬约束（PreToolUse 拦截 / PostToolUse 自动测试）
agent/agents_md.py← AGENTS.md 两层注入（全局 → 项目）
agent/reviewer.py ← 只读 reviewer 子 agent，只回最后一条消息
server/app.py     ← FastAPI + WebSocket，前端只发消息、收事件
ui/               ← 单页界面，无构建步骤，改完刷新即可
skills/*/SKILL.md ← 技能（一个目录一件事，≤80 行）
app/inspect.py    ← 验收命令：skills / custom / daemon 三份 JSON
scripts/          ← selftest.py（冒烟）、failure_demo.py、make_submission.py
examples/         ← 两个 MCP server（demo / course）
workspace/        ← 沙箱目录；stats.py 里**故意留着空列表 bug**，别顺手修
```

# 构建与测试

```powershell
.venv\Scripts\python.exe scripts/selftest.py                      # 冒烟，必须 13/13
.venv\Scripts\python.exe scripts/smoke_ws.py                       # WebSocket 8/8
.venv\Scripts\python.exe -m app.inspect skills --out skill_report.json
.venv\Scripts\python.exe -m app.inspect custom --out custom_report.json
```

打包：`pyinstaller desktop-agent.spec` → `Compress-Archive` → `ISCC.exe installer\install.iss`。

# 代码风格

- 只用标准库 + fastapi + uvicorn + pywebview + openai，**不引新依赖**（打包体积会翻倍）。
- 面向用户的报错要说「下一步怎么办」，不要只抛 traceback。
- 工具返回值一律经 `tools._truncate()` 截断，不要直接塞进上下文。
- 路径必须过 `tools._resolve()`，不要自己拼 `Path.cwd() / ...`。
- 前端不加构建工具：直接写原生 JS，事件名与 `server/app.py` 里的 `emit` 保持一致。

# 坑

- **不要用 `python app.py` 当交付演示**：必须是双击 exe，否则按「不是桌面应用」扣分。
- 打包版 `workspace` 在 `~/.desktop-agent/workspace`，不在 `_MEIPASS` 里（那里只读，write 全废）。
- `agents_md.find_project()` 会一路往上找到 `C:\`，测试时把工作区设成临时目录，别在仓库根跑。
- Windows 上 `bash` 工具实际调 PowerShell/cmd：`python` 是解释器别名，`rm -rf` 之类会被 hook 拦下。
- 关闭窗口要正常点 ✕；强杀会留下 `msedgewebview2.exe` 僵尸进程，下次启动黑屏。
- `docs/trace.md`、`docs/failures.md` 是脚本自动生成的，**不要手改**。
