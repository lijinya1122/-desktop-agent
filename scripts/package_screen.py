"""给真实录屏加包装（对齐参考片风格）：

  1920x1080 深色底 → 左右竖排水印 → 中央放 UI 录屏 → 底部章节字幕
  左下 LIVE DEMO 蓝条 → 右上 SCREEN CAPTURE 页码

    python scripts/package_screen.py --raw build/video/demo_raw.mp4 \
        --out "C:\\Users\\Lenovo\\Desktop\\一苇以航\\演示视频.mp4"
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080
BUILD = ROOT / "build" / "video"

BG = (5, 7, 12)
EDGE = (28, 36, 52)
BLUE = (64, 128, 255)
FG = (235, 240, 248)
DIM = (96, 108, 130)

FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_BD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_EN = r"C:\Windows\Fonts\consola.ttf"


def f(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_BD if bold else FONT, size)
    except Exception:
        return ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", size)


def vertical_text(d: ImageDraw.ImageDraw, x: int, text: str,
                  size: int = 20, fill=None) -> None:
    fo = ImageFont.truetype(FONT_EN, size)
    y = 90
    for ch in text:
        d.text((x, y), ch, font=fo, fill=fill or DIM)
        y += size + 12


def backdrop(path: Path) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # 边角装饰
    d.line([(70, 70), (190, 70)], fill=EDGE, width=2)
    d.line([(70, 70), (70, 190)], fill=EDGE, width=2)
    d.line([(W - 70, H - 70), (W - 190, H - 70)], fill=EDGE, width=2)
    d.line([(W - 70, H - 70), (W - 70, H - 190)], fill=EDGE, width=2)
    # 左右竖排水印
    vertical_text(d, 96, "MINI CURSOR - DESKTOP AGENT - 2026")
    vertical_text(d, W - 116, "ACTUAL UI RECORDING / MOCK MODEL / REAL TOOLS")
    # 右上页码位
    fo = ImageFont.truetype(FONT_EN, 17)
    d.text((W - 430, 64), "SCREEN CAPTURE", font=fo, fill=DIM)
    # 左下 LIVE DEMO 标签（蓝条）
    d.rectangle([64, H - 74, 68, H - 34], fill=BLUE)
    d.text((82, H - 70), "LIVE DEMO", font=ImageFont.truetype(FONT_EN, 18, ), fill=BLUE)
    d.text((82, H - 46), "真实工具执行 · 离线回放模型", font=f(15), fill=DIM)
    img.save(path)


def ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def make_ass(events, total: float, path: Path) -> None:
    def t(name: str, default: float) -> float:
        for k, v in events:
            if k == name:
                return v
        return default

    sents = [v for k, v in events if k == "sent"]
    dones = [v for k, v in events if k == "done"]
    confirms = [v for k, v in events if k.startswith("confirm_clicked_")]

    def at(seq, i, default):
        return seq[i] if len(seq) > i else default

    s1 = at(sents, 0, 13.0)
    s2 = at(sents, 1, 40.0)
    s3 = at(sents, 2, 70.0)
    s4 = at(sents, 3, 82.0)
    c1 = at(confirms, 0, s1 + 12)
    d1 = at(dones, 0, s2 - 6)
    d4 = at(dones, 3, at(dones, -1, total - 8) if dones else total - 8)
    end = total

    lines = [
        (0.4, s1 - 0.2, "真实运行录屏 · 演示模式：模型离线回放，工具是真执行"),
        (s1 + 0.1, c1 - 0.3, "任务一：修空列表 bug —— 第一次 edit 直接失败：old 出现两次，工具拒绝猜"),
        (c1 + 0.4, s2 - 0.2, "补全签名后恢复；写操作先给红绿 diff、点「执行」才落盘 —— 测试 4/4 通过"),
        (s2 + 0.1, s3 - 0.2, "任务二：写 hello.py 跑九九乘法表；越界读 ../README.md 被工具层拒绝"),
        (s3 + 0.1, s4 - 0.2, "任务三：MCP 查课表 —— 自己写的 stdio server，紫色标签就是 MCP 工具调用"),
        (s4 + 0.1, d4 + 0.3, "任务四：hook 拦截 —— 写 .env 被拒、rm -rf 被拦并给替代方案，两条都是代码规则"),
        (d4 + 0.6, end, "四个任务全部真实工具执行 · 自检 13/13 · 冒烟 8/8 · scripts/record_demo.py 一键复现"),
    ]

    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Microsoft YaHei,44,&H00F4F8FF,&H00FFFFFF,&H00101420,&H96000000,-1,0,0,0,100,100,0,0,1,3,2,2,80,80,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(
        f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{txt}\n"
        for a, b, txt in lines)
    path.write_text(head + body, encoding="utf-8-sig")


def package(raw: Path, out: Path) -> dict:
    import imageio_ffmpeg

    BUILD.mkdir(parents=True, exist_ok=True)
    bg_path = BUILD / "backdrop.png"
    backdrop(bg_path)

    events = []
    ev_file = BUILD / "events.json"
    if ev_file.exists():
        events = json.loads(ev_file.read_text(encoding="utf-8"))

    # 先探测 raw 时长（用 ffmpeg 解析一次）
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run([ff, "-hide_banner", "-i", str(raw)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    total = 60.0
    for ln in (probe.stderr or "").splitlines():
        if "Duration" in ln:
            hh, mm, ss = ln.split("Duration:")[1].split(",")[0].strip().split(":")
            total = int(hh) * 3600 + int(mm) * 60 + float(ss)
            break

    ass = BUILD / "demo.ass"
    make_ass(events, total, ass)

    # 中央 UI 区域：宽 1460，垂直居中略偏上（底部留字幕）
    ui_w, ui_h = 1460, 838
    ox, oy = (W - ui_w) // 2, 62

    out.parent.mkdir(parents=True, exist_ok=True)
    raw_abs = raw.resolve()                    # cwd 会切到 BUILD，路径必须绝对
    out_abs = out.resolve()
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-loop", "1", "-t", f"{total:.2f}", "-i", str(bg_path),
           "-i", str(raw_abs),
           "-filter_complex",
           f"[1:v]scale={ui_w}:{ui_h}[ui];"
           f"[0:v][ui]overlay=x={ox}:y={oy}[v];"
           f"[v]subtitles={ass.name}[out]",
           "-map", "[out]", "-an",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_abs)]
    p = subprocess.run(cmd, cwd=str(BUILD), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        raise SystemExit("ffmpeg 失败：\n" + (p.stderr or "")[-1500:])
    return {"out": str(out), "seconds": round(total, 1),
            "size_mb": round(out.stat().st_size / 1e6, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="给真实录屏加包装")
    ap.add_argument("--raw", default=str(BUILD / "demo_raw.mp4"))
    ap.add_argument("--out", default=str(Path.home() / "Desktop" / "一苇以航" / "演示视频.mp4"))
    args = ap.parse_args()
    print(json.dumps(package(Path(args.raw), Path(args.out)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
