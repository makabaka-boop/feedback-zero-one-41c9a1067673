"""核心线段裁剪与停留区间计算（全程 Fraction 精确运算，无浮点）。

轨迹在相邻采样点之间随时间线性变化。对每条线段 A→B（参数 u∈[0,1]），
收集与保护区所有环边的交点参数及端点 0/1，逐开区间用中点判定归属，
得到落在“外环内（含外环边界）且不在任何洞内部”的 u 区间，
再按该段耗时换算为绝对时间区间。
"""

from fractions import Fraction

from .geometry import ring_edges, point_in_ring_interior, _on_segment_exact


def _segment_edge_params(a, b, c, d):
    """线段 A→B 与环边 C→D 的交点参数 u（A + u(B-A)），返回 Fraction 列表。

    覆盖非平行相交（含端点）与平行共线重叠两种情形；不相交返回空。
    """
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    ex, ey = bx - ax, by - ay          # 轨迹方向
    fx, fy = dx - cx, dy - cy          # 环边方向
    denom = ex * fy - ey * fx          # 两方向叉积
    cxax, cyay = cx - ax, cy - ay

    if denom != 0:
        t = Fraction(cxax * fy - cyay * fx, denom)
        u = Fraction(cxax * ey - cyay * ex, denom)
        if 0 <= t <= 1 and 0 <= u <= 1:
            return [t]
        return []

    # 平行：不共线则无交点。
    if cxax * ey - cyay * ex != 0:
        return []

    # 共线：求环边端点投影到轨迹上的参数，落在 [0,1] 内的构成重叠区间。
    params = []

    def project(px, py):
        if ex != 0:
            return Fraction(px - ax, ex)
        return Fraction(py - ay, ey)

    tc = project(cx, cy)
    td = project(dx, dy)
    for tg in (tc, td):
        if 0 <= tg <= 1:
            params.append(tg)
    # 轨迹端点若落在环边内部，也属于重叠区间的分界参数。
    for tg, (px, py) in ((Fraction(0), a), (Fraction(1), b)):
        if _on_segment_exact(px, py, cx, cy, dx, dy):
            params.append(tg)
    return params


def zone_contains(pt, outer, holes):
    """点是否属于保护区：外环内部或外环边界；排除洞内部（洞边界保留）。"""
    for hole in holes:
        if _on_ring_boundary(pt, hole):
            return True  # 洞边界属于区域
    for hole in holes:
        if point_in_ring_interior(pt, hole):
            return False  # 洞内部不属于区域
    if _on_ring_boundary(pt, outer):
        return True
    return point_in_ring_interior(pt, outer)


def _on_ring_boundary(pt, ring):
    px, py = pt
    for (x1, y1), (x2, y2) in ring_edges(ring):
        if _on_segment_exact(px, py, x1, y1, x2, y2):
            return True
    return False


def clip_segment(a, b, outer, holes):
    """裁剪线段 A→B，返回属于保护区的参数区间列表 [(u_lo, u_hi), ...]。"""
    cuts = {Fraction(0), Fraction(1)}
    for ring in (outer, *holes):
        for c, d in ring_edges(ring):
            cuts.update(_segment_edge_params(a, b, c, d))

    params = sorted(cuts)
    result = []
    for lo, hi in zip(params, params[1:]):
        if lo == hi:
            continue
        mid = (lo + hi) / 2
        mx = a[0] + (b[0] - a[0]) * mid
        my = a[1] + (b[1] - a[1]) * mid
        if zone_contains((mx, my), outer, holes):
            result.append((lo, hi))
    return result


def stationary_intervals(p, duration, outer, holes):
    """静止段（相邻采样点重合）：点属于保护区则整段计时，否则无时长。"""
    if duration > 0 and zone_contains(p, outer, holes):
        return [(Fraction(0), Fraction(1))]
    return []
