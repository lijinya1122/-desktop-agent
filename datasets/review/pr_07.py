"""日志备份。"""
def backup(path):
    f = open(path, "r")
    data = f.read()
    f.close()
    try:
        process(data)
    except Exception:
        pass
    return data
