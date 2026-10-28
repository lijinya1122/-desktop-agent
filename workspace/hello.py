def multiplication_table(n=9):
    """打印 n 行九九乘法表（下三角）。"""
    for i in range(1, n + 1):
        row = []
        for j in range(1, i + 1):
            row.append(f"{j}x{i}={i * j}")
        print("\t".join(row))


if __name__ == "__main__":
    multiplication_table()
