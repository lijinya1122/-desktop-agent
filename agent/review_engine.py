"""增量 F｜评审引擎：四专科 + 一个汇总裁判（课件 P30 的形状）。

为什么不是一个更大的 prompt（课件 P31）：
  · 注意力稀释 —— 四套标准挤一个上下文，后面那套被前面挤掉；
  · 不能分级 —— 改错字也要跑完四套标准；
  · 不能并行 —— 一个 prompt 就是一条串行推理链。
所以这里按专科拆开，每个专科一个独立的检查函数（AST + 规则，结果可复现），
裁判只做四个动作：去重、重分类、合理性过滤、按 rubric 定档（P32，先落三档）。

检得出的五类：逻辑与正确性 / 可读与可维护 / 性能 / 安全 / 部落知识（本仓库约定）。
检不出的三类（意图错、需求不全、组织上下文）留给人 —— 那是分工，不是妥协。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

SECRET_RE = re.compile(r"(sk-[A-Za-z0-9-]{16,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")
SQL_FSTRING_RE = re.compile(r"f[\"'][^\"']*\b(SELECT|INSERT|UPDATE|DELETE)\b[^\"']*\{", re.I)
TODO_RE = re.compile(r"#\s*(TODO|FIXME|XXX)\b")


@dataclass
class Finding:
    kind: str            # bug 类型（与考卷 labels 的 kind 对应）
    line: int
    specialist: str      # 哪个专科报的
    severity: str        # critical / warning / suggestion
    evidence: str        # 那一行代码
    desc: str


# ---------------------------------------------------------------- 安全专科
def specialist_security(src: str, path: str) -> List[Finding]:
    out: List[Finding] = []
    for i, line in enumerate(src.splitlines(), 1):
        if SECRET_RE.search(line):
            out.append(Finding("hardcoded_secret", i, "安全", "critical",
                               line.strip()[:60], "疑似硬编码密钥（sk-/AKIA/私钥块），进仓库=已泄露"))
        if SQL_FSTRING_RE.search(line):
            out.append(Finding("sql_injection", i, "安全", "critical",
                               line.strip()[:60], "f-string 拼 SQL，等价于把输入当成代码执行；用参数绑定"))
        if re.search(r"\beval\s*\(", line):
            out.append(Finding("eval_use", i, "安全", "critical",
                               line.strip()[:60], "eval 执行任意字符串；对外部输入使用=注入风险"))
    return out


# ---------------------------------------------------------------- 正确性专科
def specialist_correctness(src: str, path: str) -> List[Finding]:
    out: List[Finding] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [Finding("syntax_error", e.lineno or 1, "正确性", "critical",
                        "", f"语法错误：{e.msg}")]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for d in node.args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    out.append(Finding("mutable_default", node.lineno, "正确性", "critical",
                                       f"def {node.name}(...)",
                                       "可变默认参数：默认值在定义时创建一次，多次调用共享同一个对象"))
        if isinstance(node, ast.Compare):
            if any(isinstance(op, ast.Eq) and isinstance(c, ast.Constant) and c.value is None
                   for op, c in zip(node.ops, node.comparators)):
                out.append(Finding("none_compare", node.lineno, "正确性", "suggestion",
                                   "", "与 None 比较应使用 is None"))
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"<=\s*len\(", line):
            out.append(Finding("off_by_one", i, "正确性", "critical",
                               line.strip()[:60], "<= len(...) 会越界一位，应为 <"))
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        params = {a.arg for a in fn.args.args}
        guarded = set()
        for node in ast.walk(fn):   # 函数体内有对该参数的判断 → 认为有守卫
            if isinstance(node, ast.If) and any(
                    p in ast.dump(node.test) for p in params):
                guarded |= {p for p in params if p in ast.dump(node.test)}
        for node in ast.walk(fn):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                rhs = node.right
                if isinstance(rhs, ast.Name) and rhs.id in params and rhs.id not in guarded:
                    out.append(Finding("zero_division", node.lineno, "正确性", "warning",
                                       lines[node.lineno - 1].strip()[:60],
                                       f"除数 {rhs.id} 是函数参数且未判空，传 0 直接崩"))
    return out


# ---------------------------------------------------------------- 性能专科
def specialist_performance(src: str, path: str) -> List[Finding]:
    out: List[Finding] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    fn = sub.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                    if name in ("execute", "query", "requests_get", "get"):
                        out.append(Finding("n_plus_one", sub.lineno, "性能", "warning",
                                           name, "循环内逐条查询（n+1）：应批量执行或一次取回"))
                        break
    return out


# ---------------------------------------------------------------- 质量专科
def specialist_quality(src: str, path: str) -> List[Finding]:
    out: List[Finding] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if TODO_RE.search(line):
            out.append(Finding("todo_left", i, "质量", "suggestion",
                               s[:60], "TODO/FIXME 残留，要么当场做掉要么进任务系统"))
        if re.match(r"print\(", s) and not s.startswith("#"):
            out.append(Finding("debug_print", i, "质量", "suggestion",
                               s[:60], "调试 print 残留，提交前应换成日志或删掉"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and len(node.body) == 1 \
                and isinstance(node.body[0], ast.Pass):
            out.append(Finding("except_pass", node.lineno, "质量", "warning",
                               lines[node.lineno - 1].strip()[:60],
                               "except: pass 静默吞掉异常，出问题时无从排查"))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
            parent_with = False
            out.append(Finding("open_without_with", node.lineno, "质量", "warning",
                               lines[node.lineno - 1].strip()[:60],
                               "open 没有用 with 管理，异常路径不会关闭文件"))
    # open_without_with 误报过滤：如果同一行（附近 2 行）出现在 with 语句里，砍掉
    in_with: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "open":
                    in_with.add(sub.lineno)
    return [f for f in out if not (f.kind == "open_without_with" and f.line in in_with)]


SPECIALISTS = [
    ("安全", specialist_security),
    ("正确性", specialist_correctness),
    ("性能", specialist_performance),
    ("质量", specialist_quality),
]

# rubric（课件 P32，课上先落三档）：
#   任一 critical            → 必须改（request_changes，有牙齿，能拦合并）
#   无 critical 且 ≥2 warning → 建议改（minor_issues）
#   其余                      → 可以合（approved / with_comments）
RUBRIC = {"critical": "必须改", "warning_majority": "建议改", "clean": "可以合"}


def judge(findings: List[Finding]) -> Dict[str, Any]:
    """裁判：去重 → 重分类 → 合理性过滤 → 定档。只回一条能执行的判定。"""
    seen: Dict[tuple, Finding] = {}
    for f in findings:  # 去重：两个专科报同一个位置 → 合并，保留更严重的那个
        key = (f.kind, f.line)
        if key not in seen or _rank(f.severity) > _rank(seen[key].severity):
            seen[key] = f
    deduped = list(seen.values())
    criticals = [f for f in deduped if f.severity == "critical"]
    warnings = [f for f in deduped if f.severity == "warning"]
    if criticals:
        verdict = RUBRIC["critical"]
    elif len(warnings) >= 2:
        verdict = RUBRIC["warning_majority"]
    else:
        verdict = RUBRIC["clean"]
    return {"verdict": verdict, "findings": deduped,
            "n_critical": len(criticals), "n_warning": len(warnings)}


def _rank(sev: str) -> int:
    return {"critical": 2, "warning": 1, "suggestion": 0}.get(sev, 0)


def review_file(path: Path) -> Dict[str, Any]:
    src = path.read_text(encoding="utf-8", errors="replace")
    findings: List[Finding] = []
    for name, fn in SPECIALISTS:
        findings.extend(fn(src, str(path)))
    j = judge(findings)
    comment = _one_comment(path.name, j)
    return {"file": path.name, **j, "comment": comment}


def _one_comment(fname: str, j: Dict[str, Any]) -> str:
    """裁判输出：一条评论（课件 P37 第 01 条 —— 人要读的是一份，不是四份）。"""
    lines = [f"[评审] {fname} → 判定：{j['verdict']}"]
    for f in j["findings"]:
        lines.append(f"  L{f.line} [{f.severity}] ({f.specialist}) {f.desc} — {f.evidence}")
    if not j["findings"]:
        lines.append("  四个专科均未发现问题。")
    return "\n".join(lines)


def review_pr(path: Path) -> List[Dict[str, Any]]:
    """给考卷用的简版：只回 findings（kind+line），供召回率计算。"""
    src = path.read_text(encoding="utf-8", errors="replace")
    findings: List[Finding] = []
    for _, fn in SPECIALISTS:
        findings.extend(fn(src, str(path)))
    j = judge(findings)
    return [{"kind": f.kind, "line": f.line, "severity": f.severity,
             "specialist": f.specialist, "desc": f.desc} for f in j["findings"]]
