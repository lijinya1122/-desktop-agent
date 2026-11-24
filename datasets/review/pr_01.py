"""用户查询接口。"""
import sqlite3

def find_user(conn, uid):
    # 直接把用户输入拼进 SQL
    cur = conn.execute(f"SELECT * FROM users WHERE id = {uid}")
    return cur.fetchone()
