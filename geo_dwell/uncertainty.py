"""定位误差方框的 possible / certain 停留区间计算（全程 Fraction 精确运算）。

每个采样点附带非负整数定位误差半径。相邻采样时刻之间，中心位置与半径
均随时间线性插值；每个时刻的可能位置是以定位点为中心、半径为半边长的
**闭合轴对齐正方形**。各时刻相互独立，不额外限制真实路径。对每只动物、
每个保护区分别计算：

- possible：正方形至少一点属于区域（区域含外环与洞边界、排除洞内部）；
- certain ：正方形全部点都属于区域（覆盖洞内部即不成立，不能只查角点）。

两个集合在参数域都是闭集：本模块收集所有“方框-环”组合关系可能变化的
临界参数，逐开区间取中点精确判定，再取闭区间；孤立的单点接触（零长度）
由上层区间合并器丢弃，不产生区间。
"""

from fractions import Fraction

from .clipping import _segment_edge_params, _on_ring_boundary
from .geometry import ring_edges, point_in_ring_interior


def _seg_meets_box(c, d, xlo, xhi, ylo, yhi, strict):
    """闭线段 [c,d] 与轴对齐矩形是否有公共点（全程精确）。

    strict=False 判定闭矩形 [xlo,xhi]×[ylo,yhi]；
    strict=True  判定开矩形 (xlo,xhi)×(ylo,yhi)，即正方形的内部。

    线段参数化为 p(t) = c + t·(d−c), t∈[0,1]，逐轴求参数范围后取交：
    闭矩形可行 ⟺ max(下界) ≤ min(上界)；开矩形可行 ⟺ max(下界) < min(上界)
    （0/1 为闭界、其余为严界时，该比较同样严格成立）。
    """
    lo = Fraction(0)
    hi = Fraction(1)
    for p0, p1, blo, bhi in ((c[0], d[0], xlo, xhi),
                             (c[1], d[1], ylo, yhi)):
        delta = p1 - p0
        if delta == 0:
            if strict:
                if not (blo < p0 < bhi):
                    return False
            elif not (blo <= p0 <= bhi):
                return False
            continue
        t1 = Fraction(blo - p0, delta)
        t2 = Fraction(bhi - p0, delta)
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > lo:
            lo = t1
        if t2 < hi:
            hi = t2
    return lo < hi if strict else lo <= hi


def _critical_params(a, b, r0, r1, rings):
    """收集方框与环的组合关系可能发生变化的全部参数 u（含端点 0/1）。

    三类临界事件（相邻事件之间所有相关判定恒定）：

    1. 中心轨迹与环边相交——中心在环内/环外的归属判定改变；
    2. 环顶点落在方框边界上——v_x = cx(u) ± r(u) 或 v_y = cy(u) ± r(u)，
       均为 u 的一次方程；
    3. 方框角点落在环边所在直线上——角点坐标对 u 线性，叉积方程一次。

    半径 r(u) 在 (0,1) 内恒正（端点非负的线性插值），退化 r=0 只可能
    出现在段端点或全程，均已被端点 0/1 覆盖，无需额外事件。
    """
    cuts = {Fraction(0), Fraction(1)}
    ax, ay = a
    dx = b[0] - ax
    dy = b[1] - ay
    dr = r1 - r0
    moving = dx != 0 or dy != 0
    for ring in rings:
        edges = list(ring_edges(ring))
        if moving:
            for c, d in edges:
                cuts.update(_segment_edge_params(a, b, c, d))
        for vx, vy in ring:
            for sign in (1, -1):
                den = dx + sign * dr
                if den:
                    u = Fraction(vx - ax - sign * r0, den)
                    if 0 <= u <= 1:
                        cuts.add(u)
                den = dy + sign * dr
                if den:
                    u = Fraction(vy - ay - sign * r0, den)
                    if 0 <= u <= 1:
                        cuts.add(u)
        for (ex0, ey0), (ex1, ey1) in edges:
            edx = ex1 - ex0
            edy = ey1 - ey0
            for sx in (1, -1):
                for sy in (1, -1):
                    cdx = dx + sx * dr
                    cdy = dy + sy * dr
                    den = cdx * edy - cdy * edx
                    if den == 0:
                        continue
                    num = (ax + sx * r0 - ex0) * edy \
                        - (ay + sy * r0 - ey0) * edx
                    u = Fraction(-num, den)
                    if 0 <= u <= 1:
                        cuts.add(u)
    return cuts


def _square_status(a, b, r0, r1, u, outer, holes):
    """参数 u 处方框的 (possible, certain) 精确判定。

    记 S 为该时刻的闭正方形，对多边形 P 使用如下等价判定：

    - S 与 P 闭区域相交   ⟺ 某边与闭 S 相交，或中心 ∈ P 闭区域；
    - S 含于 P 闭区域     ⟺ 中心 ∈ P 闭区域，且无边与 S 内部相交；
    - S 含于 P 内部       ⟺ 中心 ∈ P 内部，且无边与闭 S 相交；
    - S 与 P 内部相交     ⟺ 中心 ∈ P 内部，或某边与 S 内部相交。

    于是（利用“S 连通、洞互不相交且严格在外环内”）：

    - possible ⟺ S 与外环闭区域相交，且 S 不完全落入某个洞内部；
    - certain  ⟺ S 含于外环闭区域，且 S 与每个洞内部都不相交。
    """
    ax, ay = a
    cx = ax + (b[0] - ax) * u
    cy = ay + (b[1] - ay) * u
    r = Fraction(r0) + (r1 - r0) * u
    xlo, xhi = cx - r, cx + r
    ylo, yhi = cy - r, cy + r
    center = (cx, cy)

    def any_edge_meets(ring, strict):
        for c, d in ring_edges(ring):
            if _seg_meets_box(c, d, xlo, xhi, ylo, yhi, strict):
                return True
        return False

    center_in_outer = point_in_ring_interior(center, outer) or \
        _on_ring_boundary(center, outer)

    # possible：与外环闭区域相交，且不完全落入某个洞内部。
    possible = center_in_outer or any_edge_meets(outer, strict=False)
    if possible:
        for hole in holes:
            if point_in_ring_interior(center, hole) and \
                    not any_edge_meets(hole, strict=False):
                possible = False
                break

    # certain：含于外环闭区域，且与每个洞内部都不相交。
    certain = center_in_outer and not any_edge_meets(outer, strict=True)
    if certain:
        for hole in holes:
            if point_in_ring_interior(center, hole) or \
                    any_edge_meets(hole, strict=True):
                certain = False
                break
    return possible, certain


def uncertainty_pieces(a, b, r0, r1, outer, holes):
    """返回 (possible, certain) 的 u 参数区间列表。

    每条轨迹段 A→B（半径 r0→r1 线性插值）在相邻临界参数间取中点判定，
    判定为真的开区间取闭区间后返回；孤立接触只发生在临界参数上，
    不产生正长度区间。
    """
    cuts = sorted(_critical_params(a, b, r0, r1, (outer, *holes)))
    possible, certain = [], []
    for lo, hi in zip(cuts, cuts[1:]):
        if lo == hi:
            continue
        mid = (lo + hi) / 2
        poss, cert = _square_status(a, b, r0, r1, mid, outer, holes)
        if poss:
            possible.append((lo, hi))
        if cert:
            certain.append((lo, hi))
    return possible, certain
