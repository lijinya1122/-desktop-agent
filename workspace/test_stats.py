"""stats.py 的测试。跑法：python test_stats.py"""

import stats


def test_mean_basic():
    assert stats.mean([1, 2, 3]) == 2


def test_mean_empty():
    try:
        stats.mean([])
    except ValueError:
        return
    raise AssertionError("mean([]) 应该抛 ValueError，而不是返回 0")


def test_median_basic():
    assert stats.median([3, 1, 2]) == 2
    assert stats.median([1, 2, 3, 4]) == 2.5


def test_median_empty():
    try:
        stats.median([])
    except ValueError:
        return
    raise AssertionError("median([]) 应该抛 ValueError，而不是返回 0")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, "-", e)
    print("\n%d/%d 通过" % (len(tests) - failed, len(tests)))
    raise SystemExit(1 if failed else 0)
