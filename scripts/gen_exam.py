"""生成评审考卷：datasets/review/ 下 8 个带已知 bug 的 PR + labels.json。

    python scripts/gen_exam.py
"""
import json
from pathlib import Path

d = Path(__file__).resolve().parents[1] / "datasets" / "review"
d.mkdir(parents=True, exist_ok=True)

prs = {}

prs["pr_01"] = '''"""用户查询接口。"""
import sqlite3

def find_user(conn, uid):
    # 直接把用户输入拼进 SQL
    cur = conn.execute(f"SELECT * FROM users WHERE id = {uid}")
    return cur.fetchone()
'''

prs["pr_02"] = '''"""配置读取。"""
API_KEY = "sk-prod-a7f3b2c9d8e1f4a6b5c3d2e1f0a9b8c7"

def get_header():
    return {"Authorization": f"Bearer {API_KEY}"}
'''

prs["pr_03"] = '''"""批量导入。"""
def import_rows(rows):
    total = 0
    for row in rows:
        conn.execute("INSERT INTO logs VALUES (?)", (row,))
        total += 1
    conn.commit()
    return total
'''

prs["pr_04"] = '''"""购物车。"""
def add_item(cart=[], item=None):
    if item is None:
        return cart
    cart.append(item)
    return cart
'''

prs["pr_05"] = '''"""分页读取。"""
def read_page(items, page):
    start = page * 10
    out = []
    for i in range(start, start + 10):
        if i <= len(items):
            out.append(items[i])
    return out
'''

prs["pr_06"] = '''"""临时调试中。"""
def calc_discount(price, vip):
    print("price=", price, "vip=", vip)
    # TODO 下个月再改成配置驱动
    if vip:
        return price * 0.8
    return price
'''

prs["pr_07"] = '''"""日志备份。"""
def backup(path):
    f = open(path, "r")
    data = f.read()
    f.close()
    try:
        process(data)
    except Exception:
        pass
    return data
'''

prs["pr_08"] = '''"""表达式计算服务。"""
def evaluate(expr):
    return eval(expr)

def safe_div(a, b):
    return a / b
'''

labels = {
    "prs": [
        {"id": "pr_01", "file": "pr_01.py", "bugs": [
            {"kind": "sql_injection", "line": 5, "desc": "f-string 把 uid 直接拼进 SQL"}]},
        {"id": "pr_02", "file": "pr_02.py", "bugs": [
            {"kind": "hardcoded_secret", "line": 2, "desc": "生产密钥硬编码在源码里"}]},
        {"id": "pr_03", "file": "pr_03.py", "bugs": [
            {"kind": "n_plus_one", "line": 5, "desc": "循环里逐条 execute，应批量 executemany"}]},
        {"id": "pr_04", "file": "pr_04.py", "bugs": [
            {"kind": "mutable_default", "line": 3, "desc": "可变默认参数 cart=[]，多次调用共享同一列表"}]},
        {"id": "pr_05", "file": "pr_05.py", "bugs": [
            {"kind": "off_by_one", "line": 7, "desc": "i <= len(items) 会越界，应为 <"}]},
        {"id": "pr_06", "file": "pr_06.py", "bugs": [
            {"kind": "debug_print", "line": 4, "desc": "调试 print 残留"},
            {"kind": "todo_left", "line": 5, "desc": "TODO 残留"}]},
        {"id": "pr_07", "file": "pr_07.py", "bugs": [
            {"kind": "open_without_with", "line": 4, "desc": "open 没用 with，异常时文件不关闭"},
            {"kind": "except_pass", "line": 8, "desc": "except: pass 静默吞异常"}]},
        {"id": "pr_08", "file": "pr_08.py", "bugs": [
            {"kind": "eval_use", "line": 3, "desc": "eval 执行任意输入，注入风险"},
            {"kind": "zero_division", "line": 6, "desc": "b 可能为 0，未防护"}]},
    ]
}

for pid, src in prs.items():
    (d / f"{pid}.py").write_text(src, encoding="utf-8")
(d / "labels.json").write_text(
    json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"生成 {len(prs)} 个 PR，"
      f"{sum(len(p['bugs']) for p in labels['prs'])} 个标注 bug → {d}")
