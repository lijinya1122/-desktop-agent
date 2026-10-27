"""演示用的统计小工具（大作业的工作区靶子）。"""


def mean(nums):
    if not nums:
        return 0
    total = 0
    for n in nums:
        total += n
    return total / len(nums)


def median(nums):
    if not nums:
        return 0
    ordered = sorted(nums)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
