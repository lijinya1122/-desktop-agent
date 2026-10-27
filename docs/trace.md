# trace · 一次完整运行记录

> 由 `python scripts/selftest.py` 自动生成 —— 工具是真的、失败是真的、diff 是真的。
> 模型用的是 `agent/mock.py` 的离线回放（不联网），因此这份 trace 任何人都能复现。

任务：**让 mean 和 median 对空列表抛 ValueError，然后跑测试验证**

```
[step 1/10]
  (model) 先看一下工作区里有什么。
  -> bash({"command": "dir", "timeout": 15})
  <- [ok ] $ dir
        Volume in drive C has no label.
        Volume Serial Number is EAA2-C76D
       
        Directory of C:\Users\Lenovo\Desktop\2026.9-python\desktop-agent\workspace
       
       2026/10/27  15:55    <DIR>          .
       2026/10/27  21:12    <DIR>          ..
       2026/10/27  15:06               562 README.md
       2026/10/27  15:55               434 stats.py
       2026/10/27  15:55             1,091 test_stats.py
                      3 File(s)          2,087 bytes
                      2 Dir(s)  67,583,168,512 bytes free
       [exit_code=0]
[step 2/10]
  (model) 读一下 stats.py。
  -> read({"path": "stats.py"})
  <- [ok ] 文件：stats.py（共 20 行）
            1	"""演示用的统计小工具（大作业的工作区靶子）。"""
            2	
            3	
            4	def mean(nums):
            5	    if not nums:
            6	        return 0
            7	    total = 0
            8	    for n in nums:
            9	        total += n
           10	    return total / len(nums)
           11	
           12	
           13	def median(nums):
           14	    if not nums:
           15	        return 0
           16	    ordered = sorted(nums)
           17	    mid = len(ordered) // 2
           18	    if len(ordered) % 2:
           19	        return ordered[mid]
           20	    return (ordered[mid - 1] + ordered[mid]) / 2
[step 3/10]
  (model) 空列表返回 0 不合理，改成抛 ValueError。
  -> edit({"path": "stats.py", "old": "        return 0", "new": "        raise ValueError(\"nums 不能为空\")"})
  <- [ERR] 工具报错：edit 失败：old 在 stats.py 中出现 2 次，无法确定改哪一处。请把 old 写长一点（多带几行上下文）让它唯一，不要用模糊匹配。
[step 4/10]
  (model) old 不唯一，我把它写长一点，带上函数签名。
  -> edit({"path": "stats.py", "old": "def mean(nums):\n    if not nums:\n        return 0", "new": "def mean(nums):\n    if not nums:\n        raise ValueError(\"nums 不能)
  <- [ok ] 已修改 stats.py：替换 1 处，行数变化 +0
[step 5/10]
  (model) median 同样处理。
  -> edit({"path": "stats.py", "old": "def median(nums):\n    if not nums:\n        return 0", "new": "def median(nums):\n    if not nums:\n        raise ValueError(\"num)
  <- [ok ] 已修改 stats.py：替换 1 处，行数变化 +0
[step 6/10]
  (model) 跑一遍测试验证。
  -> bash({"command": "python test_stats.py", "timeout": 60})
  <- [ok ] $ python test_stats.py
       PASS test_mean_basic
       PASS test_mean_empty
       PASS test_median_basic
       PASS test_median_empty
       
       4/4 通过
       [exit_code=0]
[step 7/10]
  (model) 已修改 stats.py 两处（mean/median），测试 4/4 通过。

[done] 已修改 stats.py 两处（mean/median），测试 4/4 通过。
```

结束原因：`done`　总步数：`8`

## 里面发生了什么

1. **第 3 步故意失败**：`edit` 的 `old="        return 0"` 在 `stats.py` 里出现 2 次，工具拒绝猜，直接报错并把「出现 2 次」回灌给模型 —— 这就是第 37 页要现场制造的失败。
2. **恢复**：模型把 `old` 写长，带上 `def mean(nums):` 整段，替换唯一命中。
3. **验证**：`bash` 跑 `python test_stats.py`，4/4 通过 —— 结论有证据，不是「我改好了」。
4. **护栏**：步数上限、整体超时、工具超时（bash 2s 那条）、输出截断、路径越界，逐条都在上面。