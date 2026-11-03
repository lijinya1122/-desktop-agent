# MiniCursor v1.2 · 桌面编程智能体（Release 说明）

组队：一苇以航　｜　成员：李进雅（MP2608016）、宗雯雯（MP2608017）、张琳羚（MP2608019）、郭婉婷（MP2608020）

## 下载（二选一）

| 附件 | 用法 |
|---|---|
| `MiniCursor_Setup.zip` | 解压出 Setup.exe，双击安装（推荐，桌面出图标） |
| `MiniCursor_1.0.0_Windows_x64.zip` | 免安装，解压后双击 `MiniCursor.exe` |

两个包都自带 `skills/`（四个技能）与 `AGENTS.md`（项目地图）。
**没有 API Key 也能完整跑通**：右上角设置 → 勾「演示模式」→ 保存，
输入任务即可看到 读文件 → edit 失败 → 恢复 → diff 确认 → 测试全绿的完整链路（工具是真执行，不联网）。
有 Key 则取消演示模式，在设置里填自己的 Key。

## 版本线（tag）

| Tag | 内容 | 链接 |
|---|---|---|
| v1.0 | 基线：ReAct 循环、四个工具、MCP、护栏、打包 | [v1.0](https://github.com/lijinya1122/-desktop-agent/releases/tag/v1.0.0) |
| v1.1 | 增量一：技能系统（渐进披露） | [v1.1](https://github.com/lijinya1122/-desktop-agent/releases/tag/v1.1) |
| v1.2 | 增量二：定制层（AGENTS.md / hooks / reviewer） | [v1.2](https://github.com/lijinya1122/-desktop-agent/releases/tag/v1.2) |

## v1.1 技能系统：数字（`skill_report.json`，程序打印）

- 4 个技能，三种形态齐全：`run-tests`（纯提示词）/ `review-diff`（带 `scripts/collect_diff.py`）/ `course-lookup`（走 MCP）/ `package-release`（打包流程）
- **渐进披露**：常驻上下文只有目录 183 token；正文 1162 token 仅在调用 `use_skill(name)` 时注入 —— 比例 **6.3x**
- 触发靠 `description` 里的触发语：8 条触发试验（含 2 条不该触发的）全部正确，**误触发 0**
- 开关：`ENABLE_SKILLS=0` 整层关闭（验收可现场关掉对比）

## v1.2 定制层：数字（`custom_report.json`，程序打印）

- **AGENTS.md 两层注入**：`~/.desktop-agent/AGENTS.md`（全局偏好）→ 项目根 `AGENTS.md`（项目地图，3.7 KB）
- **三条 hook 是代码，不是提示词**：写 `.env`/`*.pem` 拒绝（密钥不入库）；`rm -rf` / `git push --force` / `git reset --hard` 拦下**并给替代方案**（`git revert` / `git clean -nd`）；`write`/`edit` 之后自动跑测试，只回注 4 行摘要
- **自动测试回注**：4 次运行，红 2 绿 2，**红→绿 2 次**；回注 4 行 vs 整段 traceback 的 60–80 行
- **reviewer 子 agent**：只读（`read` + 只认 `git diff/show/status/log` 的 bash），固定五条清单，只回最后一条消息 —— 一次审查在子 agent 里消化 **13,123 token**，主上下文只 **+58 token**（上限 500）
- 开关：`ENABLE_HOOKS=0` 整层关闭

## 回归（v1.0 没有被破坏）

- 自检 `python scripts/selftest.py` → **13/13**
- WebSocket 冒烟 `python scripts/smoke_ws.py` → **8/8**
- 安装包重打、重装验证：exe 内 `_internal\skills\` 与 `AGENTS.md` 就位

## 复现验收

```powershell
python -m app.inspect skills --out skill_report.json
python -m app.inspect custom --out custom_report.json
```

## 已知限制

- 停止是软中断：正在跑的 bash（最长 120s）仍会跑完，硬中断需要接管子进程句柄
- reviewer 目前是规则引擎（确定性、可复现），不是另一个 LLM 实例
- 上下文压缩是粗粒度占位替换，旧观察被压缩后如需再用只能重读
