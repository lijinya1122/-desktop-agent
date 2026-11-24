"""批量导入。"""
def import_rows(rows):
    total = 0
    for row in rows:
        conn.execute("INSERT INTO logs VALUES (?)", (row,))
        total += 1
    conn.commit()
    return total
