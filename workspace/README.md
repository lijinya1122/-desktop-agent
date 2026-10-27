# 工作区（智能体的沙箱）

智能体只能在这个目录里读写文件、执行命令。路径越界会被 `resolve()` + 前缀校验直接拒绝。

- `stats.py` —— `mean()` / `median()` 对空列表返回 0（这是留给智能体修的 bug）
- `test_stats.py` —— 4 个测试，跑法：`python test_stats.py`

试着对它说：**「让 mean 和 median 对空列表抛 ValueError，然后跑测试验证」**
你会看到它先读文件、第一次 edit 因为 old 不唯一而失败、补上下文后再改、最后跑测试。
