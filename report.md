# report.md · 大作业报告

> 姓名：李进雅　｜　学号：MP2608016　｜　组队：无
> 仓库：https://github.com/lijinya1122/desktop-agent　｜　Release：`<填写链接>`

## 1. 做了什么

**Mini Cursor**：一个双击打开的桌面窗口（`pywebview`，有标题栏，不是 localhost 网页），
里面跑着一个 ReAct 循环的编程智能体，四个工具（`read / write / edit / bash`），
并且真接上了一个 MCP server（`examples/mcp_demo_server.py`，纯标准库 stdio JSON-RPC）。

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
python scripts/selftest.py   # 工具单测 + MCP 往返 + 完整 ReAct 轨迹（自动生成 docs/trace.md）
python scripts/smoke_ws.py   # 起后端、打 REST、连 WebSocket 走事件流
python app.py                # 双击体验（没 Key 可在设置里开「演示模式」）
```

自检 13/13、冒烟 8/8、演示模式全链路（含确认闸门）通过 —— 结果都贴在上面对应脚本的输出里。
