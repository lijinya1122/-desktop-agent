"""分页读取。"""
def read_page(items, page):
    start = page * 10
    out = []
    for i in range(start, start + 10):
        if i <= len(items):
            out.append(items[i])
    return out
