# report.md · 大作业报告

> 姓名：李进雅　｜　学号：MP2608016　｜　组队：无
> 仓库：https://github.com/lijinya1122/-desktop-agent　｜　Release：https://github.com/lijinya1122/-desktop-agent/releases/tag/v1.0.0

## 1. 做了什么

**Mini Cursor**：一个双击打开的桌面窗口（`pywebview`，有标题栏，不是 localhost 网页），
里面跑着一个 ReAct 循环的编程智能体，四个工具（`read / write / edit / bash`），
并且**自己写了两个 MCP server**（纯标准库 stdio JSON-RPC）：
`examples/mcp_demo_server.py`（天气/时间/加法，跟着课程示例走通协议）
和 `examples/mcp_course_server.py`（查课表：按课程名查 / 列全表 / 按星期查，
数据是我自己的研究生课表）。第二个是为了证明 MCP 不是只跑老师给的示例。

架构分三层，`agent/` 能脱离界面单独跑（`python -m agent.cli`）：

```
ui/ (三栏)  ←WebSocket 事件流→  server/ (FastAPI)  →  agent/ (循环+工具+MCP)
```

## 2. 关键取舍

### 2.1 工具为什么是四个，不是更多

第 36 页说得直接：`bash` 把"列目录 / 跑测试 / git / 装依赖"全压成一个工具。
我一开始还想加 `list_files`、`search`，后来全删了 —— 工具越少，模型选错的概率越低，
而且 `bash dir` 和 `bash findstr` 本来就能干这些事。

### 2.2 `edit` 的唯一性检查是最值得花时间的一个工具

实现是 `text.count(old)`：0 次报错（并提示相近行号），≥2 次报错要求补上下文，只有 1 次才替换。
不做模糊匹配、不做整文件重写 —— 模糊匹配改一个字符会导致整个文件重排，diff 就没法看了。
失败时把「出现 2 次」原样回灌给模型，它下一步自己会把 old 写长 —— 这比我在提示词里
写十遍「必须唯一」都管用（见 `docs/trace.md` 第 3 步的真实失败与恢复）。

### 2.3 安全边界都在工具层，不在提示词层

- 路径：`resolve()` + 前缀白名单，`../../etc/passwd` 直接拒（自检里验证过）
- `bash`：强制超时（默认 30s，上限 120s）、输出截断、危险命令黑名单
- 写操作：先算 diff 给人确认（界面有「执行 / 拒绝」），确认后才落盘
- Key：只存在 `~/.desktop-agent/settings.json` 或 `.env`，后端持有，前端永远拿不到明文

### 2.4 护栏：宁可失败，不要失控

`max_steps`（默认 12）+ 整体超时（600s）+ 上下文预算（48k token 估算，超了自动压缩旧观察）。
另外做了循环检测：连续 3 次相同调用会提醒模型换路，不再继续烧钱。

## 3. 打包

PyInstaller + `desktop-agent.spec`（onedir）。spec 里带 `ui/`、`mcp.json`、`workspace/`，
`hiddenimports` 补齐 uvicorn 的动态导入模块。细节和踩坑写在 `docs/build.md`。

## 4. 如果只能再加一个工具，我加什么？

**`grep`（工作区内正则搜索，返回 文件:行号:内容）**。
现在它找东西只能靠 `bash findstr` / `bash python -c`，跨 Windows/macOS 的命令不一样，
模型经常在这上面浪费步数。一个跨平台的搜索工具能省掉最多的试错；
而且它只读不写，风险为零。第二个候选是 `apply_patch`（多段一次改），但那等于鼓励批量写，先不做。

## 5. 最不满意的地方（上台要说这句）

**中断是「软」的**：点「停止」是在下一步边界退出，一次正在跑的 `bash`（最长 120s）还是会跑完。
要做成硬中断得把子进程句柄也接管掉，属于下个版本的事。
另一个是上下文压缩太粗：直接把旧观察替换成占位符，如果模型后面还需要那段内容只能重读。

## 6. 怎么验证

```bash
python scripts/selftest.py      # 工具单测 + MCP 往返 + 完整 ReAct 轨迹（自动生成 docs/trace.md）
python scripts/failure_demo.py  # 故意制造 4 种失败 + 1 次恢复（生成 docs/failures.md）
python scripts/smoke_ws.py      # 起后端、打 REST、连 WebSocket 走事件流
python app.py                   # 双击体验（没 Key 可在设置里开「演示模式」）
```

自检 13/13、冒烟 8/8、演示模式全链路（含确认闸门）通过 —— 结果都贴在上面对应脚本的输出里。

真实压测记录见 `docs/stress_test.md`（用真 Key 跑的 5 类任务 + 3 个真发现），
失败与恢复的真实输出见 `docs/failures.md`。

---

# 增量作业（v1.1 / v1.2）

三个增量：技能系统、定制层、（选做）常驻。下面所有数字都是
`python -m app.inspect skills|custom` 打出来的 JSON，不是手写的表格：

```
skill_report.json    catalog_tokens 183 / full_tokens 1162 / ratio 6.3 / trials 8 条 / false_positive 0
custom_report.json   agents_md 3763B（global+project）/ denied 3 / autotest 4 次 r2g 2 / reviewer +58 token
```

## 1. 每个增量做完之后，哪件事变快了

**技能系统 —— 省的是「每轮都要重付」的钱。**
4 个技能，目录（名字 + 一句话）只占 **183 token**，正文合计 **1162 token**，**ratio 6.3**。
也就是说：以前把流程全塞进 system prompt，每一轮对话都要先付 1162 token 才轮到我的任务；
现在只有真正调用 `use_skill` 的那一轮付正文，其余轮次付 183。二十轮的会话差约 2 万 token。
更直接的收益是**重复纠正消失**：`run-tests` 里写了「先 `-q` 不要 `-v`，最多看 3 个失败」，
它不再把 80 行 traceback 贴给我；`review-diff` 自带 `collect_diff.py`，输出固定 40 行以内。

**定制层 —— 省的是「我盯着它」的时间。**
`custom_report.json` 里 `denied: 3`，三条都是真的被拦下并给出替代方案：
写 `.env` → 「密钥不入库，放环境变量」；`rm -rf build/` → 「先 `git clean -nd` 看会删什么」；
`git push --force` → 「用 `git revert` 造新提交」。
以前这三件事我要在对话里盯着，现在它连试都试不了。

**自动测试回注 —— 从「它说改好了」变成「测试说改好了」。**
`autotest: runs 4 / red 2 / green 2 / red_to_green 2 / injected_lines 4`。
四次里有两次是它先改错（红）→ 照着红字改对（绿）。回注只有 **4 行**（哪个用例 / 期望 / 实际），
而完整 traceback 是 60–80 行 —— 这个差别决定了 `red_to_green` 能不能在同一次对话里发生。

**reviewer 子 agent —— 省的是主上下文。**
一次审查，diff 和文件内容在子 agent 里消化了 **13,123 token**，
主对话只增加了 **58 token**（`main_context_delta: 58`，上限 500），结论是 2 条问题。
如果让主 agent 自己读那 8 个文件的 diff，这 13k token 会一直躺在上下文里，后面每一步都在为它付钱。

## 2. 一次判断错误

**我以为「reviewer 拿不到 diff」是环境问题，其实是我自己写的白名单把它拒了。**

第一次跑 `python -m app.inspect custom`，`reviewer.changed_files` 是空数组、`issues_found: 0`、
`subagent_tokens: 67`。我的判断是：这台机器的 git 不在 PATH 里（打包时确实踩过），
所以 reviewer 的 `subprocess` 调不到 git。于是我加了 `agent/gitutil.py` 去常见路径里找 `git.exe`。

改完重跑，**还是 0**。这次才把 `tool_bash` 的返回值打出来看，第一行赫然是：

```
拒绝：reviewer 的 bash 只允许 git diff / git show / git status / git log
```

原因很蠢：白名单正则写的是 `^\s*git\s+(diff|show|status|log)`，
而我自己在 `_collect()` 里调用的是 `git -C . show ...` —— `-C .` 卡在中间，正则不匹配。
**也就是说，我先写了一个只读白名单，然后被自己的白名单挡住了。**

改法不是放宽到「含 git 就行」（那就等于没有白名单），而是明确允许全局参数：

```python
r"^\s*git\s+(?:-[Cc]\s+\S+\s+|--no-pager\s+)*(diff|show|status|log)\b"
```

教训：**工具被拒绝时，第一件事是看拒绝理由，不是猜环境。**
`gitutil.py` 那一步并不白做（打包版确实需要它），但如果我先读返回值，
就不会先花 20 分钟去修一个不存在的问题。

顺带记一个同类错误：`autotest` 场景我原本设计成「先修 `mean` → 应该变绿」，
跑出来却是 `red 3 / green 1`。因为 `test_stats.py` 有 4 个用例，两个空列表用例都要过，
只修 `mean` 仍然是红 —— 我把「一个 bug」想成了「一个测试」。改成一次修两处后，
才拿到设计的 `4 次 / 红 2 / 绿 2 / 红→绿 2`。

## 3. 如果只保留一个增量，留哪个

**留 `PostToolUse` 那条自动测试 hook。**

理由不是它最聪明，而是它**每一天都会触发**，而且它改的是「事实」而不是「说法」：
`AGENTS.md` 和技能都只是让模型「应该」这么做（软约束，它一忙就忘）；
hook 是代码，写在 `before_tool()` / `after_tool()` 里，模型绕不过去。
`red_to_green: 2` 这两次，如果没有自动测试回注，模型会宣布「已修复」，我要自己跑一遍才发现没修好 ——
这正是这个作业想解决的「它说做完了」问题。

技能系统排第二：它的价值随项目重复度增长，但这个仓库只有 4 个技能，
省下的 token 是 979/轮，很实在，但不如「它骗我一次」的代价大。
reviewer 排第三：它救我一次，但只在交付前那一次。

## 附：怎么复现

```powershell
.venv\Scripts\python.exe -m app.inspect skills --out skill_report.json
.venv\Scripts\python.exe -m app.inspect custom --out custom_report.json
$env:ENABLE_SKILLS=0; .venv\Scripts\python.exe -m app.inspect skills   # 关掉技能：ratio 变 0、技能列表为空
$env:ENABLE_HOOKS=0;  .venv\Scripts\python.exe -m app.inspect custom   # 关掉 hook：denied 变空数组
```
