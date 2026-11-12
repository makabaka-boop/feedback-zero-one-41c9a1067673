"""整数坐标几何原语与保护区合法性校验。

所有坐标均为有符号 32 位整数，本模块只用 int 运算（不引入浮点）。
环（ring）表示为 ``list[tuple[int, int]]``，首点不重复，闭合边由首末点隐含。
"""

from .errors import GeoDwellError


# --------------------------------------------------------------------------
# 基本原语
# --------------------------------------------------------------------------

def cross(ax, ay, bx, by):
    """二维向量叉积 a × b。"""
    return ax * by - ay * bx


def ring_edges(ring):
    """按隐含闭合方式生成环的有向边 (p, q)，首点不重复。"""
    n = len(ring)
    for i in range(n):
        yield ring[i], ring[(i + 1) % n]


def signed_area2(ring):
    """鞋带公式：返回有符号面积的两倍（整数），0 表示退化。"""
    s = 0
    for (x1, y1), (x2, y2) in ring_edges(ring):
        s += x1 * y2 - x2 * y1
    return s


def closed_segments_intersect(p1, q1, p2, q2):
    """判断两条闭合线段是否有任何公共点（含端点接触、共线重叠）。"""
    d1 = (q1[0] - p1[0], q1[1] - p1[1])
    d2 = (q2[0] - p2[0], q2[1] - p2[1])
    c = cross(d1[0], d1[1], d2[0], d2[1])
    r = cross(p2[0] - p1[0], p2[1] - p1[1], d1[0], d1[1])

    if c != 0:
        # 非平行：交点参数 t、u 必须同时落在 [0,1] 闭区间。
        t_num = cross(p2[0] - p1[0], p2[1] - p1[1], d2[0], d2[1])
        u_num = r
        if (0 <= t_num <= c or c <= t_num <= 0) and \
           (0 <= u_num <= c or c <= u_num <= 0):
            return True
        return False

    # 平行。r != 0 时两线不共线，必不相交。
    if r != 0:
        return False

    # 共线：退化为一条直线上的区间重叠判断。
    if d1[0] != 0:
        lo1, hi1 = sorted((p1[0], q1[0]))
        lo2, hi2 = sorted((p2[0], q2[0]))
    else:
        lo1, hi1 = sorted((p1[1], q1[1]))
        lo2, hi2 = sorted((p2[1], q2[1]))
    return max(lo1, lo2) <= min(hi1, hi2)


# --------------------------------------------------------------------------
# 环与保护区合法性校验
# --------------------------------------------------------------------------

def _check_ring(points, where):
    """校验单个环：点不同、至少三点、简单、面积非零。返回整数点元组列表。"""
    if not isinstance(points, list) or len(points) < 3:
        raise GeoDwellError(f"{where}: 环必须是至少 3 个点的数组")

    ring = []
    for i, pt in enumerate(points):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise GeoDwellError(f"{where}: 第 {i} 个点必须是 [x, y] 坐标对")
        x, y = pt
        if not isinstance(x, int) or not isinstance(y, int) \
                or isinstance(x, bool) or isinstance(y, bool):
            raise GeoDwellError(f"{where}: 第 {i} 个点坐标必须是整数（禁止布尔）")
        ring.append((x, y))

    # 至少三个不同的点（首点不重复由输入解析保证，这里再兜底）。
    if len(set(ring)) < 3:
        raise GeoDwellError(f"{where}: 环至少需要 3 个不同的坐标点")

    edges = list(ring_edges(ring))
    n = len(edges)

    if signed_area2(ring) == 0:
        raise GeoDwellError(f"{where}: 环面积为零，非法几何")

    # 简单性：任意两条非相邻边不得接触或相交。
    # 相邻边允许在公共顶点相接；若相邻边在公共顶点之外仍有公共点
    # （即共线回折产生的“尖刺”重叠），同样非法。
    for i in range(n):
        e_p, e_q = edges[i]
        for j in range(i + 1, n):
            f_p, f_q = edges[j]
            adjacent = (j == i + 1) or (i == 0 and j == n - 1)
            if not closed_segments_intersect(e_p, e_q, f_p, f_q):
                continue
            if adjacent:
                # 相邻边在公共顶点相接是允许的；仅当二者共线且反向回折
                # （公共顶点之外仍重叠，即“尖刺”）时才非法。
                di = (e_q[0] - e_p[0], e_q[1] - e_p[1])
                dj = (f_q[0] - f_p[0], f_q[1] - f_p[1])
                if cross(di[0], di[1], dj[0], dj[1]) == 0 and \
                        di[0] * dj[0] + di[1] * dj[1] < 0:
                    raise GeoDwellError(
                        f"{where}: 相邻边 {i} 与 {j} 共线回折，环不简单")
                continue
            raise GeoDwellError(
                f"{where}: 边 {i} 与边 {j} 接触或相交，环不简单")

    return ring


def _ring_boundaries_touch(ring_a, ring_b):
    """两个环的边界是否存在任何公共点（接触或相交）。"""
    for a1, a2 in ring_edges(ring_a):
        for b1, b2 in ring_edges(ring_b):
            if closed_segments_intersect(a1, a2, b1, b2):
                return True
    return False


def validate_zone(outer_raw, holes_raw, zone_id):
    """校验一个保护区，返回 (外环, 洞环列表)。

    - 每个环简单且面积非零；
    - 洞严格位于外环内部（边界不得接触）；
    - 洞之间互不包含，且边界不得接触。
    """
    outer = _check_ring(outer_raw, f"zone {zone_id!r} 外环")

    if not isinstance(holes_raw, list):
        raise GeoDwellError(f"zone {zone_id!r}: holes 必须是数组")

    holes = []
    for k, raw in enumerate(holes_raw):
        where = f"zone {zone_id!r} 洞环 #{k}"
        hole = _check_ring(raw, where)
        holes.append(hole)

    # 洞严格在外环内部：取洞的任一顶点判定；边界接触由边界相交检查覆盖。
    for k, hole in enumerate(holes):
        where = f"zone {zone_id!r} 洞环 #{k}"
        if not point_in_ring_interior(hole[0], outer):
            raise GeoDwellError(f"{where}: 洞未严格位于外环内部")
        if _ring_boundaries_touch(outer, hole):
            raise GeoDwellError(f"{where}: 洞边界与外环边界接触或相交")

    # 洞之间：互不包含、边界不接触。
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            hi, hj = holes[i], holes[j]
            wi = f"zone {zone_id!r} 洞环 #{i}"
            wj = f"zone {zone_id!r} 洞环 #{j}"
            if _ring_boundaries_touch(hi, hj):
                raise GeoDwellError(
                    f"{wi} 与 {wj}: 洞环边界接触或相交")
            inside_ij = point_in_ring_interior(hi[0], hj)
            inside_ji = point_in_ring_interior(hj[0], hi)
            if inside_ij or inside_ji:
                raise GeoDwellError(
                    f"{wi} 与 {wj}: 洞之间存在包含关系，非法几何")

    return outer, holes


# --------------------------------------------------------------------------
# 有理数点的精确包含判定（供裁剪与校验共用）
# --------------------------------------------------------------------------

def point_in_ring_interior(pt, ring):
    """射线法判断点是否严格在环内部（边界上返回 False）。

    pt 坐标可以是 int 或 Fraction；环顶点为整数。全程精确比较。
    """
    px, py = pt
    inside = False
    for (x1, y1), (x2, y2) in ring_edges(ring):
        # 先排除边界点。
        if _on_segment_exact(px, py, x1, y1, x2, y2):
            return False
        if (y1 > py) != (y2 > py):
            x_inter = x1 + (x2 - x1) * (py - y1) / (y2 - y1)
            if x_inter > px:
                inside = not inside
    return inside


def _on_segment_exact(px, py, x1, y1, x2, y2):
    """精确判断点 P 是否在线段 [A,B] 上（坐标可为 Fraction）。"""
    if (px - x1) * (y2 - y1) != (py - y1) * (x2 - x1):
        return False
    return min(x1, x2) <= px <= max(x1, x2) and \
        min(y1, y2) <= py <= max(y1, y2)
