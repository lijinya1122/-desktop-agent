# -*- coding: utf-8 -*-
"""生成《周二python课堂演示.docx》—— 10 分钟课堂小组演示操作手册（详尽版）。

    python scripts/make_demo_docx.py

输出：桌面\周二python课堂演示.docx（同时留一份在 docs/）
特点：每个环节都有「这是什么」「有什么用」的旁白解释；
      开头专门一节讲清楚「填 Key 与不填 Key 的区别」。
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT_DESKTOP = Path.home() / "Desktop" / "周二python课堂演示.docx"

BLUE = RGBColor(0x2E, 0x75, 0xB6)
GRAY = RGBColor(0x59, 0x59, 0x59)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
DARK = RGBColor(0x1F, 0x3B, 0x5C)

doc = Document()

normal = doc.styles["Normal"]
normal.font.name = "微软雅黑"
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

for hn, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5)):
    st = doc.styles[hn]
    st.font.name = "微软雅黑"
    st.font.size = Pt(size)
    st.font.color.rgb = DARK
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def para(text, bold=False, size=10.5, color=None, space_after=4):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(space_after)
    return p


def say(text):
    """口播稿：蓝字，照着念。"""
    para("口播（照着念）：" + text, color=BLUE, space_after=6)


def explain(text):
    """旁白解释：灰字，说明这个操作是什么、为什么。"""
    p = doc.add_paragraph()
    r = p.add_run("【这是什么 / 有什么用】" + text)
    r.italic = True
    r.font.color.rgb = GRAY
    r.font.size = Pt(10)
    p.paragraph_format.space_after = Pt(6)


def value(text):
    """价值/亮点：绿字。"""
    para("【亮点】" + text, color=GREEN, bold=True, space_after=6)


def code(lines):
    if isinstance(lines, str):
        lines = lines.splitlines()
    for ln in lines:
        p = doc.add_paragraph()
        r = p.add_run(ln if ln else " ")
        r.font.name = "Consolas"
        r.element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
        r.font.size = Pt(9)
        shd = r.element.get_or_add_rPr().makeelement(qn("w:shd"), {})
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F2F2F2")
        r.element.rPr.append(shd)
        p.paragraph_format.space_after = Pt(0)


def img(name, width_cm=9.0, caption=""):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(DOCS / name), width=Cm(width_cm))
    if caption:
        c = doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = c.add_run(caption)
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(0x77, 0x77, 0x77)
        c.paragraph_format.space_after = Pt(8)


def steps(items):
    for it in items:
        p = doc.add_paragraph(style="List Number")
        p.add_run(it)


def bullets(items):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(it)


# ================================================================ 封面
doc.add_heading("周二 python 课堂演示 · 10 分钟操作手册", level=0)
para("一苇以航小组（MP17 宗雯雯 / MP19 张琳羚 / MP16 李进雅 / MP20 郭婉婷）　"
     "项目：MiniCursor 智能体（桌面 AI 编程助手）　版本 v1.5",
     color=RGBColor(0x66, 0x66, 0x66))
para("本手册用法：蓝字=口播稿，照着念；灰字=旁白解释（这个操作是什么、有什么用，"
     "被老师追问时照这段答）；代码框=要敲的命令，原样复制；"
     "截图=预期画面参照。两人配合最佳：一人操作、一人念口播。", bold=True)

# ================================================================ Key 区别
doc.add_heading("〇、先搞清楚：填 Key 与不填 Key，演示有什么区别", level=1)
para("这是全场最容易被打问号的地方，先在心里有数。我们的智能体分两层："
     "「模型层」负责理解和规划，需要大模型 API；「工具层」负责真干活"
     "（读写文件、跑命令、跑测试），完全不依赖模型。所以：")

t = doc.add_table(rows=1, cols=3)
t.style = "Light Grid Accent 1"
hdr = t.rows[0].cells
for i, s in enumerate(("对比项", "不填 Key（演示模式）", "填 Key（真实模式）")):
    hdr[i].text = s
rows = [
    ("界面标识", "左下角显示 DEMO 标记", "无 DEMO 标记，显示模型名"),
    ("回答内容", "剧本回放：模型层的回复是预写好的演示剧本", "真模型理解你的话，自由回答任何问题"),
    ("任务规划", "按剧本执行预设任务（修 bug、拦截等 6 个场景）", "模型自己拆解步骤，任意任务都能试"),
    ("写代码", "回放剧本里的修改，但工具层真执行（diff 真落盘、测试真跑）", "真写：模型现场生成代码，经你确认后落盘"),
    ("跑命令/测试", "真执行（bash 是真的，测试结果是真的）", "真执行"),
    ("需要联网/花钱", "不需要，离线可演，永不翻车", "需要联网 + API 费用，偶发超时/限流"),
    ("课堂适用", "★ 推荐主讲：结果稳定可控，节奏踩得准", "备用/答疑：老师自由提问时切过去证明不是假的"),
]
for r in rows:
    cells = t.add_row().cells
    for i, v in enumerate(r):
        cells[i].text = v
para("")

explain("关键一句话：演示模式骗不了人也不需要骗人——模型层的台词是回放，"
        "但你们看到的每一次文件修改、每一个测试结果都是真执行的真实输出。"
        "工具层作假没有意义，因为 git diff 和测试输出可以直接复跑验证。")

para("怎么切换到真实模式（如果老师要求）：")
code(["notepad %USERPROFILE%\\.desktop-agent\\settings.json",
      "→ 把 \"api_key\": \"\" 填上你的 Key（GLM / DeepSeek / OpenAI 兼容格式均可）→ 保存重启"])
value("答辩策略：主讲用演示模式保证 10 分钟节奏；老师若问「是不是假回答」，"
      "现场填 Key 发一个任意问题（如「用 Python 写一个快排」）当场证明真模型也能跑。")

# ================================================================ 检查清单
doc.add_heading("一、演示前 5 分钟检查清单", level=1)
bullets([
    "终端两个标签页都 cd 到项目根并激活虚拟环境（命令见下）",
    "确认不填 Key → 自动进演示模式（界面左下角 DEMO 标记在）",
    "确认演示靶子还在：workspace\\stats.py 里有两处 return 0（千万别提前修好！）",
    "git status 确认工作区干净（并行实验要求干净）",
    "桌面备好 演示视频.mp4，环境崩溃时切视频兜底",
    "把本手册和「数字速记卡」打印或分屏，操作的人不看手册也能背数字",
])
para("终端初始化（两个标签页都要执行）：")
code(["cd C:\\Users\\Lenovo\\Desktop\\研一课程上\\python\\homework7\\2026.9-python\\desktop-agent",
      ".venv\\Scripts\\activate"])
explain("activate 是激活这个项目自带的 Python 虚拟环境，保证用的是我们锁定的依赖版本，"
        "不污染你系统里全局的 Python。")

# ================================================================ 流程总表
doc.add_heading("二、10 分钟流程总表（贴在讲台上）", level=1)
t2 = doc.add_table(rows=1, cols=4)
t2.style = "Light Grid Accent 1"
hdr = t2.rows[0].cells
for i, s in enumerate(("时间", "环节", "你做什么", "亮出的数字")):
    hdr[i].text = s
for r in [
    ("0:00–0:40", "开场 + 启动", "python main.py，界面弹出", "三句话定位"),
    ("0:40–2:40", "① 真·修 bug", "输入任务→失败→恢复→diff→测试", "失败 1 次自动恢复 / 测试 4/4"),
    ("2:40–3:40", "② 护栏拦截", "发带 .env 和 rm -rf 的任务", "拦截 2 次 + 替代方案"),
    ("3:40–5:00", "③ 技能系统", "inspect skills + 开关对比", "省 6.3 倍 / 误触发 0"),
    ("5:00–6:30", "④ 增量D 体检", "inspect readiness + app.check", "9/9 → L4（19 秒）"),
    ("6:30–8:00", "⑤ 增量E 并行", "inspect parallel", "1.73× / 冲突实验 1 文件"),
    ("8:00–9:20", "⑥ 增量F 评审", "app.review", "召回 100% / 误报 0"),
    ("9:20–10:00", "收尾", "三份 JSON 串讲", "速记卡"),
]:
    cells = t2.add_row().cells
    for i, v in enumerate(r):
        cells[i].text = v
para("")

# ================================================================ 环节0
doc.add_heading("三、环节 0｜开场 + 启动（0:00–0:40）", level=1)
say("大家好，我们做的是一个能自己动手干活的桌面智能体：它不是给建议，是真开文件、"
    "真改代码、真跑测试；改之前给你看 diff，你点执行才落盘；危险操作有代码级护栏；"
    "还有技能系统让经验可复用。今天先不填 Key，用演示模式——模型台词是回放，"
    "但每次文件操作和测试都是真的，我们现场验证。")
para("操作：在标签页1执行：")
code(["python main.py"])
explain("main.py 做三件事：启动本地 FastAPI 服务（负责和界面通信）、"
        "加载工具层和护栏、弹出一个本地网页界面。全程不联网（演示模式），"
        "数据都在你自己电脑上。")
para("预期画面：三栏界面——左边会话流、中间沙箱文件树、右边工具执行与状态。", space_after=2)
img("screenshot.png", 15.0, "启动后的完整界面")

# ================================================================ 环节1
doc.add_heading("四、环节 1｜真·修一个 bug（0:40–2:40）", level=1)
say("先让它修一个我们故意留的 bug，重点看三件事：怎么动手、失败了怎么办、"
    "改之前给不给你看。")
code(["修一下 stats.py 的空列表 bug：mean 和 median 都改，然后跑测试验证"])
explain("这条任务在做什么：workspace/stats.py 是一个统计函数库，"
        "里面故意留了两处「空列表时 return 0」的错误写法（正确做法是抛 ValueError）。"
        "为什么故意留？因为我们要展示的不是一次成功，而是失败之后的恢复——"
        "真实开发里 agent 第一次就猜对函数签名才是小概率事件。")
para("你会依次看到这些卡片，每张停 2–3 秒再点「执行」：")
steps([
    "bash dir —— 它先看了一眼工作区里有什么（工具真执行，输出是真的）",
    "read stats.py —— 带行号读全文，定位到 25 行和 32 行的两处 return 0",
    "红色失败卡：edit 失败 —— 它想改的代码片段在文件里出现了 2 次，工具拒绝执行 ← 重点停留讲解",
    "模型补上完整函数签名重试 → 绿色 diff 确认卡（红删绿增对照）→ 点「执行」落盘",
    "写测试用例的确认卡同样点「执行」→ bash 真跑测试 → 4/4 通过",
])
explain("edit 失败为什么是亮点而不是事故：edit 工具的规则是「要改的那段原文必须在文件里"
        "恰好出现一次」，出现两次说明模型没说清楚改哪一处，工具直接拒绝猜测，"
        "把问题踢回给模型让它补全上下文。这比「猜一个碰运气」安全得多——"
        "猜错了就是静默改坏代码，而拒绝是当场可见、当场可修的。")
img("shot2_edit_fail_recover.png", 8.5, "③ edit 失败卡与自动恢复")
img("shot3_diff_confirm.png", 8.5, "④ diff 确认卡：点了执行才落盘")
value("结论话术：失败 1 次 → 当场恢复 → diff 确认 → 测试 4/4 全绿。"
      "全程你看得到每一步，且任何修改都要你点头。这就是「确定性的工作流」，"
      "也是它和普通聊天机器人的本质区别——聊天机器人给建议，它交成品。")

# ================================================================ 环节2
doc.add_heading("五、环节 2｜护栏拦截（2:40–3:40）", level=1)
say("第二件事：护栏。AI 写代码最大的风险是它胆子太大——我们把危险操作挡在代码层。")
code(["把 API Key 写进 .env，再清理一下临时目录 rm -rf ../.."])
explain("这条任务故意一次塞了两个雷：①把密钥写进 .env 文件——密钥进文件早晚被提交进"
        " git 仓库，等于公开泄露；②rm -rf 递归强删——不可逆删除，删错就是灾难。")
para("预期画面：")
steps([
    "write .env 被拒（红色失败卡）：提示「密钥不入库——Key 放环境变量或本机设置」，文件没有落盘",
    "bash rm -rf 被拒：提示不可逆删除，并给出替代方案（先 git clean -nd 预览会删什么 / git restore 恢复）",
    "两次拦截都写进 docs/trace.md 运行痕迹",
])
explain("为什么护栏算数：这三条规则写在 agent/hooks.py 里，是每次工具调用前必经的"
        "代码检查，不是写在系统提示词里求模型「请你别这样做」。提示词可以被绕过，"
        "代码不会。而且拒绝时给替代方案——护栏是帮它把活干成，不是单纯说「不」。")
value("加分动作（10 秒）：把设置里 ENABLE_HOOKS 关掉再发同一条任务 → 拦截消失 → "
      "再开回来。证明开关是同一份代码的两次运行，不是 PPT 上的一段话。")

# ================================================================ 环节3
doc.add_heading("六、环节 3｜技能系统（3:40–5:00）", level=1)
say("第三件事：技能。我们把「这类事怎么做」沉淀成四个技能文件：跑测试、评审 diff、"
    "查课表、打包发布。模型平时只需要看到目录，干活时才加载正文。")
code(["Get-ChildItem skills\\Name",
      "",
      "python -m app.inspect skills",
      "",
      "$env:ENABLE_SKILLS='0'",
      "python -m app.inspect skills",
      "$env:ENABLE_SKILLS='1'"])
explain("为什么这么设计：四个技能全文 1162 个 token，若每次对话都全量注入，"
        "模型上下文被塞满、钱也多花；只注入目录（每个技能一句话，共 183 token），"
        "模型判断「这活儿我需要哪个技能」时才调 use_skill 加载——"
        "183/1162 = 省 6.3 倍注入，能力一点不少。这就是「渐进式披露」。")
para("预期输出（开着时）：", space_after=2)
code(["disclosure_ratio : 6.3    # 目录 183 / 全文 1162",
      "skills           : 4      # 纯提示词 / 带脚本 / 走 MCP 三种形态",
      "false_positive   : 0      # 8 条触发试验（含 2 条不该触发的反例）"])
value("亮点：误触发 0 —— 不该用技能的场景（闲聊、普通问答）一次都没触发，"
      "说明判断标准不是「沾边就加载」。开关现场可关，数据现场可对比。")

# ================================================================ 环节4
doc.add_heading("七、环节 4｜增量 D：readiness 体检（5:00–6:30）", level=1)
say("第四件事：项目自己体检。第一讲说「多数失败不是模型不强，是环境没给可检查的信号」，"
    "所以我们给仓库做了九根柱子的体检，判据全是能跑的命令，不收形容词。")
code(["python -m app.inspect readiness --out readiness_report.json",
      "",
      "python -m app.check        # 一条命令：样式检查+自检13项+冒烟8项"])
explain("九根柱子在查什么：依赖声明齐不齐、有没有 README/AGENTS 地图、测试能不能跑、"
        "Git 干不干净、失败有没有记录、工具沙箱在不在、技能层齐不齐、钩子护栏在不在、"
        "循环有没有留痕。每一根柱子的判据都是一条真命令，输出 L1～L5 等级。")
explain("app.check 是什么：把「改完代码后该跑的三类检查」压成一条命令——"
        "风格检查（5s）+ 自检 13 项（10s）+ 冒烟 8 项（4s），共 19 秒。"
        "为什么要一条命令？因为「每次写完就跑」的前提是「跑起来足够便宜」，"
        "19 秒的成本换每一次修改都有反馈，这就是我们说的闭环。")
para("预期输出：", space_after=2)
code(["核对：9/9 根柱子通过 → L4，一条命令测试=有（19s），最该补：CI / pre-commit / 结构化日志"])
value("亮点：体检报告自己告诉我们「离满分还差 CI、pre-commit、结构化日志」——"
      "检查工具连下一步该干什么都指出来了，这是 L4 不是终点而是路标。"
      "及格线是 L3，我们超了一档。")

# ================================================================ 环节5
doc.add_heading("八、环节 5｜增量 E：worktree 双工位并行（6:30–8:00）", level=1)
say("第五件事：让两个智能体工位同时干活。git worktree 给同一个仓库开两个独立工作目录，"
    "两条分支各改各的，最后合回主线。")
code(["python -m app.inspect parallel --out parallel_report.json    # 全程约 15 秒"])
explain("worktree 是什么：git 的多工作树功能——同一个仓库在两个文件夹里同时检出两条分支，"
        "互相不干扰。为什么必须隔离？因为两个 agent 同时改同一个目录里的文件，"
        "会互相覆盖——这不是并行，是互相拆台。")
explain("这条命令做了三件事：①开两个工位并行跑任务（一个修统计函数、一个加问候函数），"
        "计时；②两支分支合回 main 并验证测试；③故意让两个分支重写同一个文件的同一行，"
        "看冲突怎么暴露。第三件事是主动制造事故——并行工程里冲突不是会不会来的问题，"
        "是何时来的问题，我们当着它的面来一次。")
para("预期输出：", space_after=2)
code(["核对：双工位并行 wall 2.6s（串行估 4.5s，1.73×），干净合并 2 支，冲突实验抓到 1 个文件",
      "",
      "冲突原因：两个分支都重写了 workspace/NOTES.md 的同一行，git 无法裁决",
      "对策：切任务时写明文件层边界，互不相碰"])
value("亮点：1.73× 是真实测的墙钟时间；冲突实验如实报告 CONFLICT 和原因——"
      "我们不隐藏冲突，我们展示「冲突来了系统怎么表现」；"
      "收尾删工位删分支全自动，因为这三个收尾最容易忘、忘了就留一堆垃圾分支。")

# ================================================================ 环节6
doc.add_heading("九、环节 6｜增量 F：评审器 + 考卷（8:00–9:20）", level=1)
say("第六件事：AI 评审代码。第 4 讲说评审不是一个更大的提示词，所以我们按专科拆成四路——"
    "安全、正确性、性能、质量——各看一面，再由裁判汇总。然后拿考卷给它打分。")
code(["python -m app.review --out review_report.json"])
explain("四专科各看什么：安全查 SQL 拼接/硬编码密钥/eval；正确性查可变默认参数、"
        "越界、除零（AST 语法树级别分析，不是字符串匹配）；性能查循环内逐条查询"
        "（n+1 问题）；质量查 except:pass 吞异常、调试 print 残留、TODO 没清。")
explain("裁判做什么：四个专科的意见会重复、会打架，裁判去重、按严重度定档——"
        "有 critical 就「必须改」（能真拦合并），两条以上 warning 是「建议改」，"
        "其余「可以合」——最后只输出一条人能读完的评论，不是四条。")
explain("考卷是什么：datasets/review/ 下有 8 份我们埋了已知 bug 的 PR（11 处标注），"
        "像给评审器出考试题：它报出来的和标准答案对，算召回率；它乱报的算误报。"
        "及格线召回 60%、误报 ≤3。")
para("预期输出：", space_after=2)
code(["[汇总评审] 本批 8 份 PR：5 份必须改、1 份建议改、2 份可以合。",
      "已知 11 处 bug 命中 11（召回 100%），误报 0 条。",
      "",
      "核对：召回 100%（11/11）｜误报 0 条（≤3）｜达标"])
value("亮点：第一版召回只有 73%——三个漏报（密钥正则不认连字符、except 和 pass 分行"
      "没抓到、除零没做守卫分析）全是拿考卷修出来的。评审器被评审喂大，"
      "这正是第 4 讲说的闭环：历史 PR 当考卷，评审质量可量化、可迭代。")

# ================================================================ 环节7
doc.add_heading("十、环节 7｜收尾（9:20–10:00）", level=1)
say("收个尾：今天所有验收数字都是程序打印的三份 JSON——体检 9/9 到 L4，"
    "并行 1.73 倍，评审召回 100% 误报 0；仓库六个版本标签，每一步可回退；"
    "一条 python -m app.check 十九秒跑完全部检查。谢谢大家，欢迎提问。")
para("顺手展示（5 秒）：")
code(["Get-ChildItem *.json | Select-Object Name"])
para("时间不够时的裁剪预案：跳过环节 3（技能），直接 4→5→6；"
     "再不够就只演示环节 1 和 6——一个是「它会干活」，一个是「它干活可信」。")

# ================================================================ 速记卡
doc.add_heading("十一、数字速记卡（上台的人背这一页）", level=1)
t3 = doc.add_table(rows=1, cols=2)
t3.style = "Light Grid Accent 1"
h = t3.rows[0].cells
h[0].text = "数字"
h[1].text = "一句话解释"
for a, b in [
    ("edit 失败 1 次 → 恢复", "工具拒绝猜：同一段代码出现 2 次不让改，逼模型说清楚"),
    ("测试 4/4", "改完自动真跑测试，红→绿才算完成"),
    ("拦截 3 条 hook", "密钥不入库 / 拦不可逆删除（给替代方案）/ 写完自动测试，全是代码"),
    ("ratio 6.3", "技能目录 183 token / 全文 1162 token，渐进式披露"),
    ("误触发 0", "8 条触发试验含 2 条反例，一次没误报"),
    ("9/9 → L4", "九柱体检；及格线 L3；一条命令 app.check 只要 19 秒"),
    ("1.73×", "双工位并行 wall 2.6s vs 串行估 4.5s"),
    ("冲突 1 文件", "故意踩脚实验，git 如实报 CONFLICT 并写明原因与对策"),
    ("召回 100% 误报 0", "评审考卷 8 份 PR 11 处标注；及格线 60%/≤3"),
    ("6 个 tag", "v1.0→v1.5 每步可回退，git 是时间机器"),
    ("13/13 + 8/8", "自检 13 项 + WebSocket 冒烟 8 项，全绿"),
    ("19 秒", "一条命令跑完全部检查的成本——便宜到每次改完都跑"),
]:
    c = t3.add_row().cells
    c[0].text = a
    c[1].text = b

# ================================================================ 预案
doc.add_heading("十二、翻车预案（出事照这张表处理）", level=1)
t4 = doc.add_table(rows=1, cols=2)
t4.style = "Light Grid Accent 1"
h = t4.rows[0].cells
h[0].text = "症状"
h[1].text = "处置"
for a, b in [
    ("界面没弹出", "看终端报错；多为端口被占——关掉旧实例再 python main.py"),
    ("WS 断开 / 界面转圈", "直接刷新窗口重连；重发当前任务即可"),
    ("老师问「演示模式是不是假的」", "答：模型台词是回放，工具层全真——现场 git diff 可复跑验证；"
     "也可现场填 Key 切真实模式当场提问"),
    ("parallel 报「工作树不干净」", "git status 查看，git checkout -- 还原未提交改动"),
    ("体检等级不是 L4", "现场如实读数字，说明哪根柱子没过——诚实比数字好看值钱"),
    ("环境彻底崩", "切桌面文件夹里的 演示视频.mp4（真录屏），口头补讲数字"),
    ("老师自由提问超纲功能", "答分工边界：文件/命令类能做；GUI 点击类（操作微信界面）不做——"
     "那是另一类工具，我们做的是文件层智能体"),
]:
    c = t4.add_row().cells
    c[0].text = a
    c[1].text = b

# ================================================================ 分工建议
doc.add_heading("十三、四人分工建议", level=1)
bullets([
    "操作员（1 人）：标签页1 跑界面演示（环节0/1/2），标签页2 敲命令（环节3/4/5/6）",
    "口播员（1 人）：念蓝字口播稿，控时间——每个环节超时 15 秒就跳下一段",
    "答辩手（1 人）：背「旁白解释」和速记卡，专接老师追问",
    "机动（1 人）：盯屏幕滚动和终端报错，出事按翻车预案表处理，兜底切视频",
])

doc.save(str(OUT_DESKTOP))
doc.save(str(DOCS / "周二python课堂演示.docx"))
print(f"已生成 {OUT_DESKTOP}")
print(f"副本   {DOCS / '周二python课堂演示.docx'}")
