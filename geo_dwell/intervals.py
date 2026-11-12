"""停留区间合并：重叠或端点相接的区间合并，丢弃零长度区间，按起点排序。"""

from fractions import Fraction


def merge_intervals(intervals):
    """合并 (start, end) 绝对时间区间。

    - 仅保留正长度区间（孤立触碰 end == start 不产生时长）；
    - 重叠或端点相接（next.start <= prev.end）的区间合并为一个；
    - 结果按起点排序。
    """
    positive = [(s, e) for s, e in intervals if e > s]
    if not positive:
        return []

    positive.sort(key=lambda se: (se[0], se[1]))
    merged = [list(positive[0])]
    for start, end in positive[1:]:
        if start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def total_duration(intervals):
    """合并后区间的累计时长（精确 Fraction）。"""
    total = Fraction(0)
    for start, end in intervals:
        total += end - start
    return total
