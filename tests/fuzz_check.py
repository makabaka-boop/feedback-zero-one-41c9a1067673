"""随机化强度测试（不计入常规验收，手动运行）：

用高分辨率参数采样作为独立参考，交叉核对精确裁剪得到的停留时长，
并检查“拆分共线/非共线轨迹段”和“反转环方向”的不变性。

运行:: python3 tests/fuzz_check.py
"""

import os
import random
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_dwell.geometry import validate_zone
from geo_dwell.clipping import clip_segment, zone_contains
from geo_dwell.intervals import merge_intervals, total_duration

random.seed(20261112)


def random_simple_polygon(rng, lo=0, hi=40):
    """构造一个简单多边形（允许凹）：对随机角度点按极角排序保证简单，
    再随机向内推几个点制造凹口。"""
    cx = rng.randint(lo + 8, hi - 8)
    cy = rng.randint(lo + 8, hi - 8)
    pts = []
    angles = sorted(rng.uniform(0, 6.283) for _ in range(rng.randint(5, 9)))
    for ang in angles:
        r = rng.randint(6, 14)
        pts.append((int(cx + r * __import__("math").cos(ang)),
                    int(cy + r * __import__("math").sin(ang))))
    # 随机把 1~2 个点向中心拉动，形成凹多边形（仍保持简单的概率很高；
    # 若校验拒绝则丢弃重试）。
    for _ in range(rng.randint(0, 2)):
        k = rng.randrange(len(pts))
        x, y = pts[k]
        pts[k] = (int((x + cx) / 2), int((y + cy) / 2))
    return pts


def random_hole_inside(rng, outer):
    # 取外环内部一个小方框；失败则返回 None。
    xs = [p[0] for p in outer]
    ys = [p[1] for p in outer]
    if max(xs) - min(xs) < 7 or max(ys) - min(ys) < 7:
        return None
    x0 = rng.randint(min(xs) + 2, max(xs) - 5)
    y0 = rng.randint(min(ys) + 2, max(ys) - 5)
    s = rng.randint(1, 2)
    return [(x0, y0), (x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s)]


def reference_length(a, b, outer, holes, steps=4000):
    """高分辨率采样参考：统计落在区域内的参数占比（近似长度）。"""
    inside = 0
    for i in range(steps):
        u = Fraction(2 * i + 1, 2 * steps)
        pt = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        if zone_contains(pt, outer, holes):
            inside += 1
    return Fraction(inside, steps)


def main():
    rng = random.Random(20261112)
    trials = 0
    for _ in range(400):
        outer = random_simple_polygon(rng)
        holes = []
        if rng.random() < 0.4:
            h = random_hole_inside(rng, outer)
            if h:
                holes.append(h)
        try:
            outer, holes = validate_zone(outer, holes, "fz")
        except Exception:
            continue

        a = (rng.randint(-5, 45), rng.randint(-5, 45))
        b = (rng.randint(-5, 45), rng.randint(-5, 45))
        if a == b:
            continue
        trials += 1

        exact = clip_segment(a, b, outer, holes)
        exact_len = sum((hi - lo) for lo, hi in exact)
        ref = reference_length(a, b, outer, holes)
        # 采样误差不超过 2 个采样间隔。
        tol = Fraction(2, 4000) + Fraction(1, 10 ** 6)
        if abs(exact_len - ref) > tol:
            raise AssertionError(
                f"长度不一致 exact={exact_len} ref={ref} "
                f"a={a} b={b} outer={outer} holes={holes}")

        # 反转环方向不变性。
        rev_outer = list(reversed(outer))
        rev_holes = [list(reversed(h)) for h in holes]
        rev = clip_segment(a, b, rev_outer, rev_holes)
        if rev != exact:
            raise AssertionError("反转环方向改变了裁剪结果")

        # 随机参数点拆分线段：子段参数以各自 [0,1] 为基准，
        # 必须按拆分比例 um、(1-um) 缩放回全段参数后再比较。
        um = Fraction(rng.randint(1, 9), 10)
        m = (a[0] + (b[0] - a[0]) * um, a[1] + (b[1] - a[1]) * um)
        iv1 = clip_segment(a, m, outer, holes)
        iv2 = clip_segment(m, b, outer, holes)
        split_len = sum(hi - lo for lo, hi in iv1) * um + \
            sum(hi - lo for lo, hi in iv2) * (1 - um)
        if split_len != exact_len:
            raise AssertionError(
                f"拆分后长度变化 {split_len} != {exact_len}")

        # 合并器的总时长自洽。
        merged = merge_intervals(
            [(lo, hi) for lo, hi in exact] +
            [(lo, hi) for lo, hi in exact])
        if total_duration(merged) != exact_len:
            raise AssertionError("合并自洽检查失败")

    print(f"fuzz OK: {trials} 个有效随机用例全部通过"
          f"（长度交叉核对、反转不变性、拆分不变性、合并自洽）")


if __name__ == "__main__":
    main()
