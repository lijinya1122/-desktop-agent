"""全自动生成演示视频：真实截图 + 实测数字卡片 + 中文旁白 + 烧录字幕。

不需要录屏、不需要麦克风：
  画面 = docs/shot*.png（真跑出来的截图）+ 程序打印的数字（skill_report/custom_report）
  旁白 = Windows 自带 SAPI（Microsoft Huihui）
  合成 = imageio-ffmpeg 自带的 ffmpeg（PIL 画帧 → ffmpeg 编码）

用法：
    python scripts/make_video.py --out "C:\\Users\\Lenovo\\Desktop\\一苇以航\\演示视频.mp4"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 720
FPS = 30
BUILD = ROOT / "build" / "video"

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BD = r"C:\Windows\Fonts\msyhbd.ttc"

BG_TOP = (11, 17, 30)
BG_BOT = (24, 35, 61)
ACCENT = (86, 145, 255)
GREEN = (52, 211, 153)
TEXT = (233, 239, 249)
MUTED = (151, 166, 192)
CARD = (21, 30, 49)
BORDER = (43, 57, 86)


# ---------------------------------------------------------------- 文案
def scenes() -> List[Dict[str, object]]:
    return [
        {
            "tag": "演示",
            "title": "MiniCursor 桌面编程智能体",
            "bullets": [
                "小组：一苇以航　·　MP2608016 李进雅",
                "纯 Python 本地智能体：pywebview 窗口 + 127.0.0.1:8765",
                "画面来自真实运行截图，数字来自程序打印的报告",
            ],
            "image": None,
            "narration": "这是小组一苇以航的作业演示。画面全部来自真实运行的截图，"
                         "所有数字都是程序自己打印出来的，不是手写的。",
        },
        {
            "tag": "01",
            "title": "双击打开的是桌面窗口",
            "bullets": [
                "pywebview + WebView2，不是 localhost 网页",
                "左边对话与工具卡片，右边工作区文件",
                "顶部显示已挂载工具数：内置 4 + MCP 6",
            ],
            "image": "shot1_bash_read.png",
            "narration": "双击图标打开的是真正的桌面窗口，不是浏览器里的网页。"
                         "左边是对话和工具卡片，右边是工作区。",
        },
        {
            "tag": "02",
            "title": "第一步就失败：edit 拒绝猜",
            "bullets": [
                "任务：修 stats.py 的空列表 bug",
                "工具返回：old 在文件里出现 2 次，无法定位",
                "它没有硬改，而是把上下文写长再来一次",
            ],
            "image": "shot2_edit_fail_recover.png",
            "narration": "我让它修空列表的 bug。第一次编辑直接失败，"
                         "因为要替换的那段代码在文件里出现了两次。工具没有猜，直接报错。",
        },
        {
            "tag": "03",
            "title": "写操作先给 diff，确认才落盘",
            "bullets": [
                "第二次 edit 成功，改动以红绿对比呈现",
                "用户点确认之前，文件不会被写入",
                "工作区之外的路径在工具层直接拒绝",
            ],
            "image": "shot3_diff_confirm.png",
            "narration": "把上下文写长之后它就成功了。每次写文件之前，"
                         "都会先把改动做成对比给我看，确认之后才落盘。",
        },
        {
            "tag": "04",
            "title": "说改了就真改了",
            "bullets": [
                "4 个用例全部通过，0 失败",
                "测试是 bash 工具真跑出来的，不是模型说的",
                "改了源码却没动测试，会被 reviewer 挑出来",
            ],
            "image": "shot4_test_pass.png",
            "narration": "说改好了就真改好了。这四条用例是工具真跑出来的，全部通过。",
        },
        {
            "tag": "05",
            "title": "第二个 MCP server：真实课表",
            "bullets": [
                "自己写的 stdio JSON-RPC 服务，纯标准库",
                "三个工具：查询某门课 / 整张课表 / 某天有课",
                "12 条真实课程，按星期与时间排序",
            ],
            "image": None,
            "kpi": [("12", "门真实课程"), ("3", "个 MCP 工具"), ("0", "行第三方依赖")],
            "narration": "除了内置的四个工具，还接了两个 MCP 服务。"
                         "第二个是我自己写的查课表，十二条真实课程，纯标准库。",
        },
        {
            "tag": "06",
            "title": "三道护栏都写在代码里",
            "bullets": [
                "路径越界：workspace 之外一律拒绝",
                "命令超时：bash 3 秒被掐断，返回退出码为空",
                "确认闸门：写操作必须点确认才执行",
            ],
            "image": None,
            "kpi": [("3", "道硬护栏"), ("3s", "命令超时上限"), ("0", "次越界成功")],
            "narration": "三道护栏写在代码里，不是提示词：路径越界直接拒绝，"
                         "命令超时被掐断，写操作必须我点确认。",
        },
        {
            "tag": "07",
            "title": "增量一：技能系统（渐进披露）",
            "bullets": [
                "4 个技能，三种形态：纯提示词 / 带脚本 / 走 MCP",
                "上下文只放目录，调用 use_skill 才加载正文",
                "触发靠 description 里的触发语，误触发 0 次",
            ],
            "image": None,
            "kpi": [("183", "目录 token"), ("1162", "正文 token"), ("6.3x", "省下的比例")],
            "narration": "增量一加的是技能系统。平时上下文里只放技能目录，一百八十三个词元；"
                         "正文一千一百六十二个词元，需要的时候才加载，相差六点三倍。",
        },
        {
            "tag": "08",
            "title": "增量二：定制层（hook + 子 agent）",
            "bullets": [
                "AGENTS.md 两层注入：全局偏好 + 项目地图",
                "写密钥文件 / rm -rf / 强推：拦下并给替代方案",
                "改完自动跑测试，只回注 4 行摘要，不回整段堆栈",
                "reviewer 子 agent 只读，只回最后一条消息",
            ],
            "image": None,
            "kpi": [("3", "条硬拦截"), ("2", "次红转绿"), ("+30", "主上下文 token")],
            "narration": "增量二加的是定制层。三条硬约束真的拦下了三次危险操作；"
                         "改完自动跑测试，红转绿两次；审查子 agent 消化一万三千个词元，"
                         "主对话只增加五十八个。",
        },
        {
            "tag": "09",
            "title": "可验收，也可回退",
            "bullets": [
                "python -m app.inspect skills / custom 一键复现两份 JSON",
                "ENABLE_SKILLS=0 关技能，ENABLE_HOOKS=0 关 hook",
                "自检 13/13，冒烟 8/8，v1.0 的功能没有被破坏",
            ],
            "image": None,
            "kpi": [("13/13", "自检"), ("8/8", "冒烟"), ("2", "个总开关")],
            "narration": "能力可以一键复现，也可以用环境变量整体关掉。"
                         "自检十三项、冒烟八项全部通过，原来的功能没有被破坏。",
        },
        {
            "tag": "10",
            "title": "谢谢",
            "bullets": [
                "一苇以航：李进雅 · 宗雯雯 · 张琳羚 · 郭婉婷",
                "仓库、安装包、报告见提交文件夹",
                "本片由脚本自动合成：scripts/make_video.py",
            ],
            "image": None,
            "narration": "以上是一苇以航小组的演示，谢谢观看。",
        },
    ]


# 旁注：无声版靠这两行字把话说清楚（比旁白更省时间，也更适合静音播放）
NOTES = [
    "画面全部来自真实运行截图；数字来自 python -m app.inspect 打印的 JSON，不是手写表格。脚本 scripts/make_video.py 可一键重出。",
    "pywebview + WebView2 打成 exe，双击即开，不是浏览器访问 localhost；左下角 MCP 状态由 stdio 探活得到。",
    "edit 要求 old 在文件里唯一；文件中有两处 return 0，工具直接报『old 出现 2 次』，拒绝猜位置 —— 这是防止改错文件的关键一票。",
    "写操作前先渲染红绿 diff，用户点确认才落盘；工作区之外的路径在 _resolve() 里被拒，这一层提示词管不到。",
    "测试是 bash 工具真跑出来的：4 个用例 0 失败。模型只能读到这行输出，没法自己编『已通过』。",
    "mcp_course_server.py 纯标准库实现 stdio JSON-RPC，暴露 3 个工具，读入 12 条真实课程，按星期 + 时间排序。",
    "三道护栏都在代码里：路径白名单、命令超时 3 秒、写确认闸门；另有连续 3 次相同调用检测。",
    "只把 name + description 放进 system prompt（183 token）；正文 1162 token 仅在 use_skill 时注入，比例 6.3 倍；8 条触发试验误触发 0。",
    "AGENTS.md 两层注入（全局 + 项目 3.7KB）；hook 拦下 3 次危险操作并给替代方案；改后自动测试红转绿 2 次、只回注 4 行；reviewer 消化 13k token，主上下文只加 30（上限 500）。",
    "两份 JSON 均由程序打印：skill_report.json / custom_report.json；ENABLE_SKILLS=0、ENABLE_HOOKS=0 可整体关闭。自检 13/13、冒烟 8/8。",
    "仓库 github.com/lijinya1122/-desktop-agent，tag：v1.0 基线 / v1.1 技能 / v1.2 定制层；安装包与报告见提交文件夹。",
]


# ---------------------------------------------------------------- 语音
def tts(scenes_: List[Dict[str, object]], out_dir: Path) -> List[Path]:
    """用 Windows 自带 SAPI 逐段合成中文旁白（不联网）。"""
    ps = out_dir / "tts.ps1"
    lines = ["Add-Type -AssemblyName System.Speech",
             "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
             "try { $s.SelectVoice('Microsoft Huihui Desktop') } catch {}",
             "$s.Rate = 0"]
    wavs: List[Path] = []
    for i, sc in enumerate(scenes_):
        wav = out_dir / f"seg{i:02d}.wav"
        txt = str(sc["narration"]).replace("'", "’")
        lines += [f"$s.SetOutputToWaveFile('{wav}')", f"$s.Speak('{txt}')"]
        wavs.append(wav)
    lines.append("$s.Dispose()")
    ps.write_text("\n".join(lines), encoding="utf-8-sig")

    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(ps)], capture_output=True, timeout=600)
    return wavs


def wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / float(f.getframerate())
    except Exception:
        return 0.0


# ---------------------------------------------------------------- 绘图
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size, index=0)
    except Exception:
        return ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", size)


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    out, cur = [], ""
    for ch in text:
        if f.getlength(cur + ch) > max_w and cur:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def bg() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(
            int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    return img


def draw_scene(idx: int, total: int, sc: Dict[str, object]) -> Image.Image:
    img = bg()
    d = ImageDraw.Draw(img)

    # 顶部标签 + 标题
    tag = str(sc["tag"])
    d.rounded_rectangle([64, 52, 64 + 28 + font(15).getlength(tag) + 22, 88],
                        radius=8, fill=(30, 44, 74))
    d.text((64 + 14, 59), tag, font=font(15, True), fill=ACCENT)
    d.text((64, 104), str(sc["title"]), font=font(38, True), fill=TEXT)
    d.line([(64, 166), (64 + 72, 166)], fill=ACCENT, width=4)

    # 内容区（190 - 545）
    y0 = 200
    image_name: Optional[str] = sc.get("image")  # type: ignore[assignment]
    if image_name:
        p = ROOT / "docs" / str(image_name)
        if p.is_file():
            shot = Image.open(p).convert("RGB")
            box_w, box_h = 600, 330
            shot.thumbnail((box_w, box_h), Image.LANCZOS)
            card = Image.new("RGB", (box_w, box_h), (16, 23, 38))
            card.paste(shot, ((box_w - shot.width) // 2, (box_h - shot.height) // 2))
            img.paste(card, (64, y0))
            d.rectangle([64, y0, 64 + box_w, y0 + box_h], outline=BORDER, width=2)
            tx = 64 + box_w + 44
            tw = W - tx - 64
        else:
            tx, tw = 64, W - 128
    else:
        tx, tw = 64, W - 128

    bullets: List[str] = list(sc.get("bullets") or [])  # type: ignore[arg-type]
    kpi = sc.get("kpi")
    by = y0
    if kpi:
        card_w = (tw - 2 * 18) // 3
        for i, (num, label) in enumerate(kpi):  # type: ignore[misc]
            cx = tx + i * (card_w + 18)
            d.rounded_rectangle([cx, by, cx + card_w, by + 108], radius=14,
                                fill=CARD, outline=BORDER, width=1)
            d.text((cx + 20, by + 16), num, font=font(38, True),
                   fill=GREEN if i == 0 else TEXT)
            d.text((cx + 20, by + 70), label, font=font(15), fill=MUTED)
        by += 108 + 32

    fy = font(20)
    for b in bullets:
        d.rounded_rectangle([tx + 2, by + 10, tx + 10, by + 18], radius=3, fill=ACCENT)
        for j, line in enumerate(wrap(b, fy, tw - 32)):
            if by > 540:
                break
            d.text((tx + 26, by), line, font=fy, fill=TEXT if j == 0 else MUTED)
            by += 31
        by += 10

    # 旁注条（没有配音，靠这段文字讲清楚）
    note = str(sc.get("note") or "").strip()
    if note:
        d.rounded_rectangle([64, 556, W - 64, 646], radius=12, fill=(18, 26, 43),
                            outline=BORDER, width=1)
        d.rectangle([64, 556, 70, 646], fill=ACCENT)
        d.text((88, 568), "旁注", font=font(13, True), fill=ACCENT)
        ny = 590
        for line in wrap(note, font(18), W - 64 - 110)[:2]:
            d.text((88, ny), line, font=font(18), fill=(205, 216, 235))
            ny += 27

    # 底部进度条 + 页脚
    d.rectangle([0, H - 6, W, H], fill=(18, 26, 42))
    d.rectangle([0, H - 6, int(W * (idx + 1) / total), H], fill=ACCENT)
    d.text((64, 664), "MiniCursor　·　一苇以航　·　MP2608016",
           font=font(14), fill=(110, 124, 148))
    right = f"{idx + 1} / {total}"
    d.text((W - 64 - font(14).getlength(right), 664), right,
           font=font(14), fill=(110, 124, 148))
    return img


# ---------------------------------------------------------------- 合成
def read_seconds(sc: Dict[str, object], note: str) -> float:
    """无声版：按「要读多少字」定时长，保证每屏都读得完。"""
    chars = len(note) + len(str(sc["title"]))
    chars += sum(len(str(b)) for b in (sc.get("bullets") or []))  # type: ignore[union-attr]
    return max(5.2, 3.0 + chars * 0.062)


def build(out: Path, voice: bool = False) -> Dict[str, object]:
    BUILD.mkdir(parents=True, exist_ok=True)
    scs = scenes()
    for i, sc in enumerate(scs):
        sc["note"] = NOTES[i] if i < len(NOTES) else ""

    wavs: List[Path] = tts(scs, BUILD) if voice else []
    durs: List[float] = []
    pngs: List[Path] = []
    for i, sc in enumerate(scs):
        d = (max(3.4, wav_seconds(wavs[i]) + 1.0) if voice
             else read_seconds(sc, str(sc["note"])))
        durs.append(d)
        png = BUILD / f"slide{i:02d}.png"
        draw_scene(i, len(scs), sc).save(png)
        pngs.append(png)

    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for i in range(len(scs)):
        cmd += ["-loop", "1", "-t", f"{durs[i]:.2f}", "-i", str(pngs[i])]
        if voice:
            cmd += ["-i", str(wavs[i])]

    parts, concat = [], ""
    step = 2 if voice else 1
    for i, dur in enumerate(durs):
        vi = step * i
        fade_out = max(0.1, dur - 0.45)
        parts.append(
            f"[{vi}:v]scale={W}:{H},setsar=1,fps={FPS},"
            f"fade=t=in:st=0:d=0.45,fade=t=out:st={fade_out:.2f}:d=0.45,"
            f"format=yuv420p[v{i}]")
        if voice:
            parts.append(
                f"[{vi + 1}:a]aresample=44100,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"apad=pad_dur={dur:.2f},atrim=0:{dur:.2f},asetpts=PTS-STARTPTS[a{i}]")
            concat += f"[v{i}][a{i}]"
        else:
            concat += f"[v{i}]"
    parts.append(concat + (f"concat=n={len(durs)}:v=1:a=1[v][a]" if voice
                           else f"concat=n={len(durs)}:v=1:a=0[v]"))

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]"]
    if voice:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", f"{sum(durs):.2f}", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        raise SystemExit("ffmpeg 失败：\n" + (p.stderr or "")[-2000:])

    return {"out": str(out), "voice": voice, "seconds": round(sum(durs), 1),
            "size_mb": round(out.stat().st_size / 1e6, 1),
            "scenes": len(scs), "per_scene": [round(x, 1) for x in durs]}


def main() -> int:
    ap = argparse.ArgumentParser(description="合成演示视频（无需录屏）")
    ap.add_argument("--out", default=str(Path.home() / "Desktop" / "演示视频.mp4"))
    ap.add_argument("--voice", action="store_true",
                    help="加中文旁白（默认不加：画面旁注 + 静音，适合静音播放）")
    args = ap.parse_args()
    res = build(Path(args.out), voice=args.voice)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
