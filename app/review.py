"""review 子命令：对一批已知有 bug 的 PR 出意见，算召回与误报（增量 F）。

    python -m app.review --out review_report.json

考卷 = datasets/review/ 下 8 个带已知 bug 的 PR + labels.json（13 处标注）。
逐条判定：引擎报出的 finding 与标注 kind 相同、行号差 ≤ 3 → 记为命中。
误报 = 引擎报出、但考卷没有标注的 finding。
最后按课件 P37 的要求输出**一条**汇总评论（不是四条）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.review_engine import review_file, review_pr  # noqa: E402

EXAM = ROOT / "datasets" / "review"
KIND_MATCH = {  # 考卷 kind 与引擎 kind 的对应（重分类由裁判完成）
    "sql_injection": {"sql_injection"},
    "hardcoded_secret": {"hardcoded_secret"},
    "n_plus_one": {"n_plus_one"},
    "mutable_default": {"mutable_default"},
    "off_by_one": {"off_by_one"},
    "debug_print": {"debug_print"},
    "todo_left": {"todo_left"},
    "open_without_with": {"open_without_with"},
    "except_pass": {"except_pass"},
    "eval_use": {"eval_use"},
    "zero_division": {"zero_division"},
}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.review",
                                 description="对已知 bug 考卷跑评审，算召回与误报")
    ap.add_argument("--out", default=None, help="写到文件（同时打印）")
    ap.add_argument("--exam", default=str(EXAM), help="考卷目录（labels.json 所在）")
    args = ap.parse_args(argv)

    labels = json.loads((Path(args.exam) / "labels.json").read_text(encoding="utf-8"))
    per_pr, hits, misses, false_pos = [], 0, [], []

    for pr in labels["prs"]:
        f = Path(args.exam) / pr["file"]
        got = review_pr(f)
        full = review_file(f)
        used = set()
        bug_rows = []
        for b in pr["bugs"]:
            hit = next((g for g in got
                        if g["kind"] in KIND_MATCH.get(b["kind"], {b["kind"]})
                        and abs(g["line"] - b["line"]) <= 3 and id(g) not in used), None)
            if hit:
                hits += 1
                used.add(id(hit))
            else:
                misses.append({"pr": pr["id"], **b})
            bug_rows.append({"kind": b["kind"], "label_line": b["line"],
                             "hit": bool(hit), "detected_line": hit["line"] if hit else None,
                             "desc": b["desc"]})
        for g in got:  # 没有对应标注的报出 = 误报
            if id(g) not in used:
                false_pos.append({"pr": pr["id"], "kind": g["kind"], "line": g["line"],
                                  "desc": g["desc"], "evidence": "引擎报出但考卷未标注该位置"})
        per_pr.append({"id": pr["id"], "file": pr["file"], "verdict": full["verdict"],
                       "comment": full["comment"], "bugs": bug_rows})

    total = hits + len(misses)
    recall = round(hits / total, 3) if total else 0.0
    n_fp = len(false_pos)
    pass_line = recall >= 0.6 and n_fp <= 3

    comments = "\n\n".join(p["comment"] for p in per_pr)
    summary = (
        f"[汇总评审] 本批 {len(per_pr)} 份 PR：{sum(1 for p in per_pr if p['verdict'] == '必须改')} 份必须改、"
        f"{sum(1 for p in per_pr if p['verdict'] == '建议改')} 份建议改、"
        f"{sum(1 for p in per_pr if p['verdict'] == '可以合')} 份可以合。\n"
        f"已知 {total} 处 bug 命中 {hits}（召回 {recall:.0%}），误报 {n_fp} 条。"
        + ("" if not misses else "\n漏报：" + "、".join(f"{m['pr']}/L{m['line']}({m['kind']})" for m in misses))
        + ("" if not false_pos else "\n误报：" + "、".join(f"{m['pr']}/L{m['line']}({m['kind']})" for m in false_pos))
    )

    report = {
        "recall": recall,
        "false_positives": n_fp,
        "bugs_total": total,
        "bugs_hit": hits,
        "pass_line": {"recall_min": 0.6, "fp_max": 3, "ok": pass_line},
        "per_pr": per_pr,
        "missed": misses,
        "false_pos_detail": false_pos,
        "summary_comment": summary,
        "exam": str(Path(args.exam)),
        "note": "引擎=四专科规则检查（agent/review_engine.py），结果可复现；判定档位=rubric 三档",
    }
    data = json.dumps(report, ensure_ascii=False, indent=2)
    print(data[:1800])
    print("……")
    print(summary)
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
        print(f"\n已写入 {args.out}")
    print(f"核对：召回 {recall:.0%}（≥60%）｜误报 {n_fp} 条（≤3）｜"
          f"{'达标' if pass_line else '未达标'}")
    return 0 if pass_line else 1


if __name__ == "__main__":
    sys.exit(main())
