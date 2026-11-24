# -*- coding: utf-8 -*-
"""生成《MiniCursor 智能体 10 分钟课堂展示操作手册》（docs/课堂展示操作手册.docx）。

    python scripts/make_demo_docx.py
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

doc = Document()

# ---- 全局样式：正文微软雅黑 10.5pt，代码 Consolas 9pt 灰底 ----
normal = doc.styles["Normal"]
normal.font.name = "微软雅黑"
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

for hn, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5)):
    st = doc.styles[hn]
    st.font.name = "微软雅黑"
    st.font.size = Pt(size)
    st.font.color.rgb = RGBColor(0x1F, 0x3B, 0x5C)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def para(text, bold=False, size=10.5, color=None, style=None, space_after=4):
    p = doc.add_paragraph(style=style)
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(space_after)
    return p


def code(lines):
    """命令/输出：等宽 + 浅灰底。"""
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


def say(text):
    para("口播：" + text, color=RGBColor(0x2E, 0x75, 0xB6), space_after=6)


# ================================================================ 封面
h = doc.add_heading("MiniCursor 智能体 · 10 分钟课堂展示操作手册", level=0)
para("一苇以航小组（MP17 宗雯雯 / MP19 张琳羚 / MP16 李进雅 / MP20 郭婉婷）　"
     "版本 v1.5　配套作业：第一二三次大作业 + 增量 D/E/F",
     color=RGBColor(0x66, 0x66, 0x66))
para("原则：能真跑的绝不放截图；截图只是给听众对画面的参照。全程约 10 分钟，"
     "两人配合最佳——一人操作，一人念口播和数字。", bold=True)

# ================================================================ 检查清单
doc.add_heading("一、演示前 5 分钟检查清单", level=1)
for item in [
    "终端两个标签页都 cd 到项目根：cd …\\2026.9-python\\desktop-agent，并激活 .venv（见下）",
    "确认无 API Key → 自动进入演示模式（界面左下角有 DEMO 标记）：模型离线回放、工具真执行",
    "确认演示靶子还在：workspace\\stats.py 里有两处 return 0（不要提前修！）",
    "确认 git 工作区干净（git status）：parallel 实验要求干净工作树",
    "演示视频（演示视频.mp4）已在桌面文件夹，万一现场环境崩，切视频兜底",
]:
    p = doc.add_paragraph(style="List Bullet")
    p.add_run(item)

para("终端初始化（两个标签页都执行一次）：")
code(["cd C:\\Users\\Lenovo\\Desktop\\研一课程上\\python\\homework7\\2026.9-python\\desktop-agent",
      ".venv\\Scripts\\activate",
      "python main.py        ← 只在标签页1执行：启动界面（约 3 秒后窗口弹出）"])

# ================================================================ 流程总表
doc.add_heading("二、10 分钟流程总表", level=1)
table = doc.add_table(rows=1, cols=4)
table.style = "Light Grid Accent 1"
hdr = table.rows[0].cells
for i, t in enumerate(("时间", "环节", "关键动作", "亮出的数字")):
    hdr[i].text = t
rows = [
    ("0:00–0:40", "开场 + 启动", "python main.py 双开界面", "三句话定位"),
    ("0:40–2:40", "① 真·修 bug", "输入任务→看它失败→恢复→确认→测试", "edit 失败 1 次 / 测试 4/4"),
    ("2:40–3:40", "② 护栏拦截", "发一条带 .env 和 rm -rf 的任务", "拦截 2 次 + 替代方案"),
    ("3:40–5:00", "③ 技能系统", "app.inspect skills + 开关对比", "ratio 6.3 / 误触发 0"),
    ("5:00–6:30", "④ 增量 D 体检", "app.inspect readiness", "9/9 → L4（及格线 L3）"),
    ("6:30–8:00", "⑤ 增量 E 并行", "app.inspect parallel", "1.73× / 冲突实验 1 文件"),
    ("8:00–9:20", "⑥ 增量 F 评审", "app.review", "召回 100% / 误报 0"),
    ("9:20–10:00", "收尾", "三份 JSON 一句话串讲", "见速记卡"),
]
for r in rows:
    cells = table.add_row().cells
    for i, v in enumerate(r):
        cells[i].text = v
para("")

# ================================================================ 环节 0
doc.add_heading("三、环节 0｜开场 + 启动（0:00–0:40）", level=1)
say("我们做的是一个能自己动手干活的桌面智能体：它不是给建议，是真开文件、真改代码、"
    "真跑测试；改之前给你看 diff，点了执行才落盘；危险操作有代码级护栏。"
    "模型可以换，今天为了稳定用演示模式——模型是脚本回放，但你们看到的每一次文件操作都是真的。")
para("操作：")
code(["python main.py"])
para("预期画面（界面三栏：左侧会话、中间沙箱文件、右侧工具与状态；左下角 MCP 状态：demo/course 均 ok）：", space_after=2)
img("screenshot.png", 15.0, "启动后的完整界面（标签页1）")

# ================================================================ 环节 1
doc.add_heading("四、环节 1｜真·修一个 bug（0:40–2:40）", level=1)
say("先看它怎么干活、怎么失败、怎么恢复——这是 ReAct 循环加上确认闸门，"
    "失败不藏起来，恢复有痕迹。")
para("在输入框逐字输入（或提前贴好）并回车：")
code(["修一下 stats.py 的空列表 bug：mean 和 median 都改，然后跑测试验证"])
para("你会依次看到（每一张都停 2–3 秒再点「执行」）：")
for item in [
    "① bash dir 摸工作区（工具卡，真输出）",
    "② read stats.py（带行号全文）",
    "③ 红色失败卡：edit 失败——old 出现 2 次，执行会失败 ← 停在这里讲：工具拒绝猜测，逼模型补全函数签名",
    "④ 模型补签名重试 → 绿色 diff 确认卡（红绿对照）→ 点「执行」落盘",
    "⑤ 写测试的确认卡同样点「执行」→ bash 真跑出 测试 4/4 通过",
]:
    p = doc.add_paragraph(style="List Number")
    p.add_run(item)
img("shot2_edit_fail_recover.png", 8.5, "③ edit 失败卡与恢复")
img("shot3_diff_confirm.png", 8.5, "④ diff 确认卡：点了执行才落盘")
para("预期结论：测试 4/4 通过；stepInfo 显示「完成」。", bold=True)

# ================================================================ 环节 2
doc.add_heading("五、环节 2｜护栏拦截（2:40–3:40）", level=1)
say("护栏是代码不是提示词：agent/hooks.py 里的三条规则，模型绕不过去，"
    "而且拒绝时给替代方案——这是它在工作，不是在说教。")
code(["把 API Key 写进 .env，再清理一下临时目录 rm -rf ../.."])
para("预期画面：")
for item in [
    "① write .env 被拒：密钥不入库——Key 放环境变量或本机设置（红色失败卡，未落盘）",
    "② bash rm -rf 被拒：不可逆删除，并给出替代方案（先 git clean -nd 看会删什么 / git restore）",
    "③ 两次拦截都在 trace 里有记录（docs\\trace.md）",
]:
    p = doc.add_paragraph(style="List Number")
    p.add_run(item)
para("加分动作（10 秒）：把设置里 ENABLE_HOOKS 关掉再发同一条任务 → 拦截消失 → 开回来。"
     "证明开关是同一份代码的两次运行。")

# ================================================================ 环节 3
doc.add_heading("六、环节 3｜技能系统（3:40–5:00）", level=1)
say("技能 = 把「这类事怎么做」写成可复用资产。启动只注入目录（每技能一句话），"
    "模型判断需要时才调 use_skill 加载正文——省 token，还不牺牲能力。")
para("标签页2 依次执行：")
code(["Get-ChildItem skills\\Name          # 四个技能：run-tests / review-diff / course-lookup / package-release",
      "",
      "python -m app.inspect skills         # 数字从程序来",
      "",
      "$env:ENABLE_SKILLS='0'               # 现场关掉",
      "python -m app.inspect skills         # ratio → 0，技能列表为空",
      "$env:ENABLE_SKILLS='1'               # 开回来"])
para("预期输出（开）：", space_after=2)
code(["disclosure_ratio : 6.3     # 目录 183 token / 全文 1162 token",
      "skills           : 4       # 三种形态：纯提示词 / 带脚本 / 走 MCP",
      "false_positive   : 0       # 8 条触发试验（含 2 条反例）无一次误触发"])
para("亮数字：6.3 倍的注入节省、误触发 0、开关现场可关。", bold=True)

# ================================================================ 环节 4
doc.add_heading("七、环节 4｜增量 D：readiness 体检（5:00–6:30）", level=1)
say("第 1 讲说「多数失败不是模型不强，是环境没给可检查的信号」。"
    "所以我们给仓库做了一个体检：九根柱子，判据全是能跑的命令，不收形容词。")
code(["python -m app.inspect readiness --out readiness_report.json"])
para("预期输出：", space_after=2)
code(["核对：9/9 根柱子通过 → L4，一条命令测试=有（19s），最该补：CI / pre-commit / 结构化日志",
      "",
      "python -m app.check                 # 一条命令跑完：样式(5s)+自检13/13(10s)+冒烟8/8(4s)"])
img("shot4_test_pass.png", 8.5, "测试绿：体检的「tests」柱就是它")
para("讲法：L1 能跑 → L2 写下来了 → L3 标准化（及格线）→ L4 反馈够快。"
     "我们现在 L4，差 CI 才到 L5——体检自己告诉我们还差什么，这就是闭环。", bold=True)

# ================================================================ 环节 5
doc.add_heading("八、环节 5｜增量 E：worktree 双工位（6:30–8:00）", level=1)
say("并行不是把速度乘三，是把「看清楚」的成本也乘三。所以这条命令做三件事："
    "开两个工位并行干活；合回来并跑测试；再故意让两个分支踩同一个文件，看冲突怎么暴露。")
code(["python -m app.inspect parallel --out parallel_report.json     # 全程约 15 秒"])
para("预期输出：", space_after=2)
code(["核对：双工位并行 wall 2.6s（串行估 4.5s，1.73×），干净合并 2 支，冲突实验抓到 1 个文件",
      "",
      "conflict_reason: 两个工位在文件层踩脚：两个分支都重写了 workspace/NOTES.md",
      "                 的同一行，git 无法裁决——对策：切任务时写明边界"])
para("讲法：任务切分守「文件层互不相碰」→ 干净合并；踩了同一行 → git 如实报冲突。"
     "收尾 worktree remove 和删分支是命令自动做的——第 2 讲说这三个收尾最容易忘。", bold=True)

# ================================================================ 环节 6
doc.add_heading("九、环节 6｜增量 F：评审考卷（8:00–9:20）", level=1)
say("第 4 讲的核心：评审不是一个更大的提示词。我们按专科拆成四路——安全、正确性、性能、质量——"
    "各看一面，裁判去重、定档、只回一条评论。然后拿 8 份已知 bug 的 PR 当考卷打分。")
code(["python -m app.review --out review_report.json"])
para("预期输出：", space_after=2)
code(["核对：召回 100%（11/11）｜误报 0 条（≤3）｜达标",
      "",
      "[汇总评审] 本批 8 份 PR：5 份必须改、1 份建议改、2 份可以合。",
      "已知 11 处 bug 命中 11（召回 100%），误报 0 条。"])
para("讲法：rubric 三档里「必须改」有牙齿——能真拦一次合并；"
     "四专科检不出意图错/需求不全，那三类留给人——这是分工不是妥协。"
     "第一版召回只有 73%，三个漏报都是拿考卷修出来的：评审器被评审喂大。", bold=True)

# ================================================================ 环节 7
doc.add_heading("十、环节 7｜收尾（9:20–10:00）", level=1)
say("收个尾：所有验收数字都是程序打印的三份 JSON——readiness（9/9→L4）、"
    "parallel（1.73×）、review（召回 100% 误报 0）；仓库六个 tag 对应六个可回退版本；"
    "一条 python -m app.check 十九秒跑完全部检查。谢谢大家。")
para("顺手展示（5 秒）：")
code(["Get-ChildItem *.json | Select-Object Name    # 三份报告文件就在交付包里"])
para("若被打断/时间不够：跳过环节 3，直接从环节 4 讲体检——数字都在 JSON 里，可以口头带过。")

# ================================================================ 速记卡
doc.add_heading("十一、数字速记卡（背这一页就够）", level=1)
card = doc.add_table(rows=1, cols=2)
card.style = "Light Grid Accent 1"
h2 = card.rows[0].cells
h2[0].text = "数字"
h2[1].text = "一句话解释"
facts = [
    ("edit 失败 1 次 → 恢复", "工具拒绝猜：old 出现 2 次不让执行"),
    ("测试 4/4", "改完自动真跑，不是嘴上说改了"),
    ("拦截 3 条 hook", "密钥 / 不可逆命令 / 写完自动测试，全是代码"),
    ("ratio 6.3", "技能目录 183 token / 全文 1162 token"),
    ("误触发 0", "8 条触发试验含 2 条反例"),
    ("9/9 → L4", "九柱体检；及格线 L3；一条命令 19s"),
    ("1.73×", "双工位并行 wall 2.6s vs 串行 4.5s"),
    ("冲突 1 文件", "故意踩脚实验，git 如实报 CONFLICT"),
    ("召回 100% 误报 0", "评审考卷 8 份 PR 11 处标注；及格线 60%/≤3"),
    ("6 个 tag", "v1.0 → v1.5，每一步可回退"),
]
for a, b in facts:
    c = card.add_row().cells
    c[0].text = a
    c[1].text = b

# ================================================================ 预案
doc.add_heading("十二、翻车预案", level=1)
plan = doc.add_table(rows=1, cols=2)
plan.style = "Light Grid Accent 1"
h3 = plan.rows[0].cells
h3[0].text = "症状"
h3[1].text = "处置"
plans = [
    ("界面没弹出", "看终端报错；多为端口占用——关掉旧实例再 python main.py"),
    ("WS 断开 / 界面转圈", "直接刷新窗口；会话历史在内存，重发任务即可"),
    ("任务跑完无确认卡", "确认 settings.json 里 confirm_writes=false 时仍会对写操作弹卡；重发任务"),
    ("parallel 报「工作树不干净」", "git status 看看，把改动提交或 git checkout -- 还原"),
    ("体检等级不是 L4", "现场如实读数字并说明哪根柱子没过——诚实比数字好看值钱"),
    ("环境彻底崩", "切桌面文件夹里的 演示视频.mp4（1 分 18 秒真录屏），口头补讲"),
]
for a, b in plans:
    c = plan.add_row().cells
    c[0].text = a
    c[1].text = b

out = DOCS / "课堂展示操作手册.docx"
doc.save(str(out))
print(f"已生成 {out}")
