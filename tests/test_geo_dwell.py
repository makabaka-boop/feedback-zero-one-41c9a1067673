"""自动验收：覆盖题目要求的全部关键场景。

运行方式（在仓库根目录）::

    python3 -I -m unittest discover -s tests -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_dwell import process, GeoDwellError  # noqa: E402

SQUARE = [[0, 0], [2, 0], [2, 2], [0, 2]]


def run(samples, zones):
    return process({"samples": samples, "zones": zones})


def total(result, animal, zone):
    a = next(x for x in result["animals"] if x["animal_id"] == animal)
    z = next(x for x in a["zones"] if x["zone_id"] == zone)
    return frac(z["total_duration"]), z["intervals"]


def frac(obj):
    return Fraction(obj["numerator"], obj["denominator"])


def sample(aid, t, x, y):
    return {"animal_id": aid, "t": t, "x": x, "y": y}


def zone(zid, outer, holes=None):
    return {"zone_id": zid, "outer_ring": outer, "holes": holes or []}


def run_unc(samples, zones, radii):
    """带定位误差半径的作业入口。"""
    return process({"samples": samples, "zones": zones,
                    "uncertainty_radii": radii})


def unc_total(result, animal, zone_id, key):
    """取某动物某保护区的 possible/certain 总时长与区间。"""
    a = next(x for x in result["animals"] if x["animal_id"] == animal)
    z = next(x for x in a["zones"] if x["zone_id"] == zone_id)
    return frac(z[key]["total_duration"]), z[key]["intervals"]


class CanonicalAndVariants(unittest.TestCase):
    """题面基准：(-1,1)->(7,1)，3 秒，穿过 [0,2]^2 停留 3/4 秒。"""

    def test_canonical_three_quarter_second(self):
        result = run(
            [sample("a1", 0, -1, 1), sample("a1", 3, 7, 1)],
            [zone("z1", SQUARE)],
        )
        td, intervals = total(result, "a1", "z1")
        self.assertEqual(td, Fraction(3, 4))
        self.assertEqual(len(intervals), 1)
        self.assertEqual(frac(intervals[0]["start"]), Fraction(3, 8))
        self.assertEqual(frac(intervals[0]["end"]), Fraction(9, 8))
        self.assertEqual(frac(intervals[0]["duration"]), Fraction(3, 4))

    def test_split_collinear_trajectory_unchanged(self):
        """拆分共线轨迹段：在同一直线上加采样点，结果必须完全一致。

        基准线 (-1,1)->(7,1) 上只有整数点可作拆分点，取 x=3（对应 t=1.5
        不是整数），因此改用等价的 8 秒整数网格场景验证拆分不变性：
        单段与两段拆分的停留区间、总时长必须相同。
        """
        single = run(
            [sample("a", 0, -1, 1), sample("a", 8, 7, 1)],
            [zone("z", SQUARE)],
        )
        split = run(
            [sample("a", 0, -1, 1),
             sample("a", 4, 3, 1),
             sample("a", 8, 7, 1)],
            [zone("z", SQUARE)],
        )
        td1, iv1 = total(single, "a", "z")
        td2, iv2 = total(split, "a", "z")
        self.assertEqual(td1, Fraction(2))
        self.assertEqual(td1, td2)
        self.assertEqual(iv1, iv2)  # 拆成 (0,1] 与 [1,2] 后在端点相接并合并

    def test_reversed_ring_orientation_unchanged(self):
        """反转外环方向不改变任何结果。"""
        forward = run(
            [sample("a", 0, -1, 1), sample("a", 3, 7, 1)],
            [zone("z", SQUARE)],
        )
        reversed_ring = list(reversed(SQUARE))
        backward = run(
            [sample("a", 0, -1, 1), sample("a", 3, 7, 1)],
            [zone("z", reversed_ring)],
        )
        self.assertEqual(forward, backward)


class ConcavePolygon(unittest.TestCase):
    """凹多边形：U 形区域，直线路径进入->离开凹口->再进入，得到两段并各自计时。"""

    U_SHAPE = [
        (0, 0), (6, 0), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6),
    ]

    def test_path_crosses_concavity_two_intervals(self):
        result = run(
            [sample("a", 0, -1, 4), sample("a", 8, 7, 4)],
            [zone("u", self.U_SHAPE)],
        )
        td, intervals = total(result, "a", "u")
        # 速度 1 单位/秒；区内 x 范围 [0,2] 与 [4,6]，共 4 个单位 => 4 秒
        self.assertEqual(td, Fraction(4))
        self.assertEqual(len(intervals), 2)
        self.assertEqual(frac(intervals[0]["start"]), Fraction(1))
        self.assertEqual(frac(intervals[0]["end"]), Fraction(3))
        self.assertEqual(frac(intervals[1]["start"]), Fraction(5))
        self.assertEqual(frac(intervals[1]["end"]), Fraction(7))


class Holes(unittest.TestCase):
    """带洞保护区：洞内部排除、洞边界保留。"""

    OUTER = [(0, 0), (10, 0), (10, 10), (0, 10)]
    HOLE = [(3, 3), (7, 3), (7, 7), (3, 7)]

    def test_path_through_hole_interior(self):
        result = run(
            [sample("a", 0, -1, 5), sample("a", 11, 10, 5)],
            [zone("z", self.OUTER, [self.HOLE])],
        )
        td, intervals = total(result, "a", "z")
        # 区内: [0,3] 与 [7,10] 共 6 单位；速度 1 单位/秒 => 6 秒
        self.assertEqual(td, Fraction(6))
        self.assertEqual(len(intervals), 2)

    def test_path_along_hole_boundary_kept_and_merged(self):
        """沿洞边界移动计时，且与两侧区内区间在端点相接后合并为一段。"""
        result = run(
            [sample("a", 0, -1, 3), sample("a", 11, 10, 3)],
            [zone("z", self.OUTER, [self.HOLE])],
        )
        td, intervals = total(result, "a", "z")
        # y=3 全程在区域内（洞边界 y=3 保留）：x=0..10 => 10 秒
        self.assertEqual(td, Fraction(10))
        self.assertEqual(len(intervals), 1)

    def test_hole_reversed_orientation_unchanged(self):
        h_rev = list(reversed(self.HOLE))
        r1 = run(
            [sample("a", 0, -1, 5), sample("a", 11, 10, 5)],
            [zone("z", self.OUTER, [self.HOLE])],
        )
        r2 = run(
            [sample("a", 0, -1, 5), sample("a", 11, 10, 5)],
            [zone("z", self.OUTER, [h_rev])],
        )
        self.assertEqual(r1, r2)


class VertexCrossing(unittest.TestCase):
    """顶点穿越：从顶点进入 vs 仅在顶点孤立触碰。"""

    DIAMOND = [(2, 0), (4, 2), (2, 4), (0, 2)]

    def test_enter_through_vertex_counts_boundary(self):
        # y=2 水平穿过菱形：x=0（顶点）进入，x=4（顶点）离开，全程 4 秒
        result = run(
            [sample("a", 0, -1, 2), sample("a", 5, 4, 2)],
            [zone("d", self.DIAMOND)],
        )
        td, intervals = total(result, "a", "d")
        self.assertEqual(td, Fraction(4))
        self.assertEqual(len(intervals), 1)

    def test_tangent_touch_at_vertex_no_duration(self):
        # 路径沿 y=0，仅在顶点 (2,0) 孤立触碰：无正长度区间
        result = run(
            [sample("a", 0, 0, 0), sample("a", 4, 4, 0)],
            [zone("d", self.DIAMOND)],
        )
        td, intervals = total(result, "a", "d")
        self.assertEqual(td, Fraction(0))
        self.assertEqual(intervals, [])


class CollinearOverlap(unittest.TestCase):
    """轨迹与环边共线重叠：沿外边界移动计时；区间在端点相接时合并。"""

    def test_collinear_overlap_on_outer_boundary(self):
        result = run(
            [sample("a", 0, -1, 0), sample("a", 4, 3, 0)],
            [zone("s", SQUARE)],
        )
        td, intervals = total(result, "a", "s")
        # 与底边 y=0 共线重叠 x∈[0,2]，2 个单位 / 速度 1 => 2 秒
        self.assertEqual(td, Fraction(2))
        self.assertEqual(len(intervals), 1)
        self.assertEqual(frac(intervals[0]["start"]), Fraction(1))
        self.assertEqual(frac(intervals[0]["end"]), Fraction(3))

    def test_adjacent_segments_merge_at_touch_endpoint(self):
        """两段在边界上首尾相接，合并为一个区间。"""
        result = run(
            [sample("a", 0, 0, 0),
             sample("a", 1, 1, 0),
             sample("a", 2, 2, 0)],
            [zone("s", SQUARE)],
        )
        td, intervals = total(result, "a", "s")
        self.assertEqual(td, Fraction(2))
        self.assertEqual(len(intervals), 1)


class RepeatedPosition(unittest.TestCase):
    """重复位置（静止段）按点归属计时；区外静止不计时。"""

    def test_stationary_inside_counts(self):
        result = run(
            [sample("a", 0, 1, 1),
             sample("a", 5, 1, 1),
             sample("a", 6, 1, 1)],
            [zone("s", SQUARE)],
        )
        td, intervals = total(result, "a", "s")
        self.assertEqual(td, Fraction(6))
        self.assertEqual(len(intervals), 1)

    def test_stationary_outside_zero(self):
        result = run(
            [sample("a", 0, 9, 9), sample("a", 5, 9, 9)],
            [zone("s", SQUARE)],
        )
        td, intervals = total(result, "a", "s")
        self.assertEqual(td, Fraction(0))
        self.assertEqual(intervals, [])

    def test_stationary_on_hole_boundary_counts(self):
        outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
        hole = [(3, 3), (7, 3), (7, 7), (3, 7)]
        result = run(
            [sample("a", 0, 5, 3), sample("a", 4, 5, 3)],
            [zone("z", outer, [hole])],
        )
        td, intervals = total(result, "a", "z")
        self.assertEqual(td, Fraction(4))
        self.assertEqual(len(intervals), 1)

    def test_stationary_in_hole_interior_zero(self):
        outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
        hole = [(3, 3), (7, 3), (7, 7), (3, 7)]
        result = run(
            [sample("a", 0, 5, 5), sample("a", 4, 5, 5)],
            [zone("z", outer, [hole])],
        )
        td, intervals = total(result, "a", "z")
        self.assertEqual(td, Fraction(0))
        self.assertEqual(intervals, [])


class StructuralGuarantees(unittest.TestCase):
    """全组合输出、单点动物、多保护区独立、分数约分与排序。"""

    def test_all_animal_zone_combinations_present(self):
        result = run(
            [sample("a1", 0, 0, 0),
             sample("a2", 0, 9, 9), sample("a2", 1, 9, 9)],
            [zone("z1", SQUARE), zone("z2", [[5, 5], [8, 5], [8, 8], [5, 8]])],
        )
        ids = [(a["animal_id"], z["zone_id"])
               for a in result["animals"] for z in a["zones"]]
        self.assertEqual(sorted(ids),
                         [("a1", "z1"), ("a1", "z2"),
                          ("a2", "z1"), ("a2", "z2")])
        # 单点动物：无时长，但组合保留
        a1 = next(a for a in result["animals"] if a["animal_id"] == "a1")
        for z in a1["zones"]:
            self.assertEqual(frac(z["total_duration"]), Fraction(0))
            self.assertEqual(z["intervals"], [])

    def test_overlapping_zones_computed_independently(self):
        z2 = [[1, 1], [3, 1], [3, 3], [1, 3]]
        result = run(
            [sample("a", 0, -1, 1), sample("a", 4, 3, 1)],
            [zone("z1", SQUARE), zone("z2", z2)],
        )
        t1, _ = total(result, "a", "z1")
        t2, _ = total(result, "a", "z2")
        self.assertEqual(t1, Fraction(2))   # x∈[0,2]，速度 1 单位/秒
        self.assertEqual(t2, Fraction(2))   # x∈[1,3]

    def test_fractions_reduced_and_positive_denominator(self):
        # 构造必然产生分数的交点（斜向穿边）
        diamond = [(2, 0), (4, 2), (2, 4), (0, 2)]
        result = run(
            [sample("a", 0, 0, 0), sample("a", 4, 4, 4)],
            [zone("d", diamond)],
        )
        _, intervals = total(result, "a", "d")
        for iv in intervals:
            for key in ("start", "end", "duration"):
                self.assertGreater(iv[key]["denominator"], 0)
                from math import gcd
                self.assertEqual(
                    gcd(abs(iv[key]["numerator"]), iv[key]["denominator"]), 1)

    def test_intervals_sorted_by_start(self):
        result = run(
            [sample("a", 0, -1, 4), sample("a", 8, 7, 4)],
            [zone("u", [(0, 0), (6, 0), (6, 6), (4, 6), (4, 2),
                        (2, 2), (2, 6), (0, 6)])],
        )
        _, intervals = total(result, "a", "u")
        starts = [frac(i["start"]) for i in intervals]
        self.assertEqual(starts, sorted(starts))


class InputAndGeometryValidation(unittest.TestCase):
    """严格类型/范围校验与非法几何定位。"""

    def _expect(self, payload, needle):
        with self.assertRaises(GeoDwellError) as ctx:
            process(payload)
        self.assertIn(needle, str(ctx.exception))

    def test_boolean_rejected_as_integer(self):
        self._expect(
            {"samples": [sample("a", 0, True, 1)],
             "zones": [zone("z", SQUARE)]},
            "整数")

    def test_t_out_of_range(self):
        self._expect(
            {"samples": [sample("a", -1, 0, 0)],
             "zones": [zone("z", SQUARE)]},
            "t")

    def test_coord_out_of_i32(self):
        self._expect(
            {"samples": [sample("a", 0, 2 ** 31, 0)],
             "zones": [zone("z", SQUARE)]},
            "x")

    def test_bad_identifier(self):
        self._expect(
            {"samples": [sample("a-b", 0, 0, 0)],
             "zones": [zone("z", SQUARE)]},
            "ASCII")

    def test_duplicate_time_same_animal(self):
        self._expect(
            {"samples": [sample("a", 1, 0, 0), sample("a", 1, 1, 1)],
             "zones": [zone("z", SQUARE)]},
            "重复时刻")

    def test_ring_too_short(self):
        self._expect(
            {"samples": [], "zones": [zone("z", [(0, 0), (1, 1)])]},
            "外环")

    def test_ring_repeated_points(self):
        # 重复点不满足“至少三个不同点”，或在简单性检查处被拦截；
        # 两种情况都必须整次拒绝并定位到外环。
        with self.assertRaises(GeoDwellError) as ctx:
            process({"samples": [],
                     "zones": [zone("z", [(0, 0), (0, 0), (1, 1), (2, 0)])]})
        self.assertIn("外环", str(ctx.exception))

    def test_zero_area_ring(self):
        self._expect(
            {"samples": [],
             "zones": [zone("z", [(0, 0), (1, 1), (2, 2)])]},
            "面积为零")

    def test_self_intersecting_ring_locates_ring(self):
        bowtie = [(0, 0), (2, 2), (2, 0), (0, 2)]
        self._expect(
            {"samples": [], "zones": [zone("z", bowtie)]},
            "外环")

    def test_hole_outside_outer_rejected(self):
        outer = [(0, 0), (4, 0), (4, 4), (0, 4)]
        hole = [(5, 5), (7, 5), (7, 7), (5, 7)]
        self._expect(
            {"samples": [], "zones": [zone("z", outer, [hole])]},
            "洞环 #0")

    def test_hole_touching_outer_boundary_rejected(self):
        outer = [(0, 0), (4, 0), (4, 4), (0, 4)]
        hole = [(2, 0), (3, 0), (3, 2), (2, 2)]  # 一条边压在外环边上
        self._expect(
            {"samples": [], "zones": [zone("z", outer, [hole])]},
            "洞环 #0")

    def test_nested_holes_rejected(self):
        outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
        h1 = [(1, 1), (9, 1), (9, 9), (1, 9)]
        h2 = [(3, 3), (7, 3), (7, 7), (3, 7)]
        self._expect(
            {"samples": [], "zones": [zone("z", outer, [h1, h2])]},
            "洞环")

    def test_duplicate_zone_id_rejected(self):
        self._expect(
            {"samples": [],
             "zones": [zone("z", SQUARE), zone("z", SQUARE)]},
            "zone_id 重复")

    def test_missing_field_rejected(self):
        self._expect(
            {"samples": [{"animal_id": "a", "t": 0, "x": 0}],
             "zones": []},
            "缺少必填字段")

    def test_duplicate_json_keys_rejected(self):
        from geo_dwell.engine import loads
        text = json.dumps({"samples": [], "zones": []}).replace(
            '"samples"', '"samples": [], "samples"', 1)
        with self.assertRaises(GeoDwellError):
            loads(text)


class UncertaintyRadii(unittest.TestCase):
    """定位误差半径：possible（方框至少一点在区内）与 certain（全部点在区内）。

    每个时刻的可能位置是以定位点为中心、半径为半边长的闭合轴对齐正方形；
    半径与中心均按相邻采样时刻线性插值；区域含外环及洞边界、排除洞内部。
    """

    HOLE_OUTER = [[0, 0], [10, 0], [10, 10], [0, 10]]

    def test_box_encloses_zone_possible_only(self):
        """方框包住整个保护区：possible 全程成立，certain 不成立。"""
        result = run_unc(
            [sample("elk", 0, 1, 1), sample("elk", 4, 1, 1)],
            [zone("z", SQUARE)],
            [5, 5],
        )
        td, _ = total(result, "elk", "z")
        self.assertEqual(td, Fraction(4))          # 中心轨迹始终在区内
        pt, piv = unc_total(result, "elk", "z", "possible")
        self.assertEqual(pt, Fraction(4))          # 方框始终盖住整个区域
        self.assertEqual(len(piv), 1)
        self.assertEqual(frac(piv[0]["start"]), Fraction(0))
        self.assertEqual(frac(piv[0]["end"]), Fraction(4))
        ct, civ = unc_total(result, "elk", "z", "certain")
        self.assertEqual(ct, Fraction(0))          # 方框远大于区域，不可能全在区内
        self.assertEqual(civ, [])

    def test_corners_inside_but_box_covers_hole_not_certain(self):
        """角点均在区内却包住洞：certain 必须不成立（不能只查方框角点）。"""
        hole = [[4, 4], [6, 4], [6, 6], [4, 6]]
        result = run_unc(
            [sample("a", 0, 5, 5), sample("a", 6, 5, 5)],
            [zone("z", self.HOLE_OUTER, [hole])],
            [3, 3],  # 方框 [2,8]^2：四角 (2,2)(8,2)(2,8)(8,8) 都在区域内
        )
        ct, civ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(0))          # 方框覆盖洞内部 => certain 失败
        self.assertEqual(civ, [])
        pt, _ = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(6))          # 方框与区域有大片相交
        td, _ = total(result, "a", "z")
        self.assertEqual(td, Fraction(0))          # 中心点在洞内部，中心轨迹无停留

    def test_brief_intersection_during_motion(self):
        """运动中短暂相交：中心始终区外，方框扫过时 possible 短暂成立。"""
        result = run_unc(
            [sample("a", 0, -3, 3), sample("a", 10, 7, 3)],
            [zone("z", SQUARE)],
            [2, 2],
        )
        td, _ = total(result, "a", "z")
        self.assertEqual(td, Fraction(0))          # 中心轨迹 y=3 在区外
        pt, piv = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(6))          # 方框 x 范围扫过 [0,2]：t∈[1,7]
        self.assertEqual(len(piv), 1)
        self.assertEqual(frac(piv[0]["start"]), Fraction(1))
        self.assertEqual(frac(piv[0]["end"]), Fraction(7))
        ct, _ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(0))          # 方框高 4 > 区域高 2，永不 certain

    def test_nested_crossing_full_intervals(self):
        """匀速穿越：certain ⊂ 中心轨迹 ⊂ possible 三层区间与时长全部核对。"""
        big = [[0, 0], [10, 0], [10, 10], [0, 10]]
        result = run_unc(
            [sample("a", 0, -4, 5), sample("a", 18, 14, 5)],
            [zone("z", big)],
            [2, 2],
        )
        td, iv = total(result, "a", "z")
        self.assertEqual(td, Fraction(10))         # 中心 x∈[0,10]：t∈[4,14]
        self.assertEqual(frac(iv[0]["start"]), Fraction(4))
        self.assertEqual(frac(iv[0]["end"]), Fraction(14))
        pt, piv = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(14))         # 方框触区：t∈[2,16]
        self.assertEqual(len(piv), 1)
        self.assertEqual(frac(piv[0]["start"]), Fraction(2))
        self.assertEqual(frac(piv[0]["end"]), Fraction(16))
        ct, civ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(6))          # 方框完全入内：t∈[6,12]
        self.assertEqual(len(civ), 1)
        self.assertEqual(frac(civ[0]["start"]), Fraction(6))
        self.assertEqual(frac(civ[0]["end"]), Fraction(12))

    def test_radius_grows_certain_shrinks(self):
        """半径变化：0→3 线性增长，certain 区间随方框越界而截止。"""
        z4 = [[0, 0], [4, 0], [4, 4], [0, 4]]
        result = run_unc(
            [sample("a", 0, 2, 2), sample("a", 3, 2, 2)],
            [zone("z", z4)],
            [0, 3],  # r(t)=t，方框 [2-t, 2+t]^2
        )
        ct, civ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(2))          # t≤2 时方框含于区域
        self.assertEqual(frac(civ[0]["start"]), Fraction(0))
        self.assertEqual(frac(civ[0]["end"]), Fraction(2))
        pt, _ = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(3))          # 中心始终在区内 => possible 全程
        td, _ = total(result, "a", "z")
        self.assertEqual(td, Fraction(3))

    def test_radius_shrinks_to_zero_possible_vanishes(self):
        """半径退化为零：6→0 线性收缩，方框与区域的相交随之消失。"""
        z4 = [[0, 0], [4, 0], [4, 4], [0, 4]]
        result = run_unc(
            [sample("a", 0, 9, 9), sample("a", 6, 9, 9)],
            [zone("z", z4)],
            [6, 0],  # r(t)=6-t，方框 [3+t, 15-t]^2
        )
        pt, piv = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(1))          # 仅 t∈[0,1] 方框触区
        self.assertEqual(len(piv), 1)
        self.assertEqual(frac(piv[0]["end"]), Fraction(1))
        ct, _ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(0))
        td, _ = total(result, "a", "z")
        self.assertEqual(td, Fraction(0))          # 中心点 (9,9) 始终在区外

    def test_merge_across_segments_and_isolated_certain_dropped(self):
        """端点相接合并：两段 possible 在共享端点相接并合并；
        仅单点成立的 certain（t=5 方框恰与区域重合）不产生区间。"""
        result = run_unc(
            [sample("a", 0, -4, 1), sample("a", 4, 0, 1), sample("a", 8, 4, 1)],
            [zone("z", SQUARE)],
            [1, 1, 1],
        )
        pt, piv = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(4))          # [3,4] 与 [4,7] 端点相接合并
        self.assertEqual(len(piv), 1)
        self.assertEqual(frac(piv[0]["start"]), Fraction(3))
        self.assertEqual(frac(piv[0]["end"]), Fraction(7))
        ct, civ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(0))          # 孤立接触不产生区间
        self.assertEqual(civ, [])
        td, iv = total(result, "a", "z")
        self.assertEqual(td, Fraction(2))          # 中心轨迹 [4,6]
        self.assertEqual(len(iv), 1)

    def test_zero_radii_match_center(self):
        """半径全程退化为零：possible / certain 与中心轨迹完全一致。"""
        result = run_unc(
            [sample("a", 0, 0, 0), sample("a", 1, 1, 0), sample("a", 2, 2, 0)],
            [zone("z", SQUARE)],
            [0, 0, 0],
        )
        td, iv = total(result, "a", "z")
        self.assertEqual(td, Fraction(2))          # 沿底边移动计时
        for key in ("possible", "certain"):
            kt, kiv = unc_total(result, "a", "z", key)
            self.assertEqual(kt, Fraction(2))
            self.assertEqual(len(kiv), 1)
            self.assertEqual(frac(kiv[0]["start"]), Fraction(0))
            self.assertEqual(frac(kiv[0]["end"]), Fraction(2))

    def test_hole_boundary_touch_allowed_for_certain(self):
        """方框贴外环边界与洞边界（边界属于区域）：certain 仍然成立。"""
        hole = [[4, 4], [6, 4], [6, 6], [4, 6]]
        result = run_unc(
            [sample("a", 0, 2, 5), sample("a", 4, 2, 5)],
            [zone("z", self.HOLE_OUTER, [hole])],
            [2, 2],  # 方框 [0,4]×[3,7]：左贴外环、右贴洞边界
        )
        ct, _ = unc_total(result, "a", "z", "certain")
        self.assertEqual(ct, Fraction(4))
        pt, _ = unc_total(result, "a", "z", "possible")
        self.assertEqual(pt, Fraction(4))
        td, _ = total(result, "a", "z")
        self.assertEqual(td, Fraction(4))

    def test_box_inside_hole_interior_no_dwell(self):
        """方框完全落入洞内部：possible 与 certain 均不成立。"""
        hole = [[3, 3], [7, 3], [7, 7], [3, 7]]
        result = run_unc(
            [sample("a", 0, 5, 5), sample("a", 4, 5, 5)],
            [zone("z", self.HOLE_OUTER, [hole])],
            [1, 1],  # 方框 [4,6]^2 ⊂ 洞内部 (3,7)^2
        )
        for key in ("possible", "certain"):
            kt, kiv = unc_total(result, "a", "z", key)
            self.assertEqual(kt, Fraction(0))
            self.assertEqual(kiv, [])
        td, _ = total(result, "a", "z")
        self.assertEqual(td, Fraction(0))

    def test_single_point_animal_with_radii(self):
        """单点动物无时长，但 possible / certain 组合保留。"""
        result = run_unc(
            [sample("lonely", 42, 1, 1)],
            [zone("z", SQUARE)],
            [3],
        )
        z = result["animals"][0]["zones"][0]
        for key in ("possible", "certain"):
            self.assertEqual(z[key]["intervals"], [])
            self.assertEqual(frac(z[key]["total_duration"]), Fraction(0))

    def test_output_compatible_without_radii(self):
        """未提供数组时输出逐项兼容：不出现 possible / certain 字段。"""
        result = run(
            [sample("a", 0, -1, 1), sample("a", 3, 7, 1)],
            [zone("z", SQUARE)],
        )
        for a in result["animals"]:
            for z in a["zones"]:
                self.assertEqual(
                    sorted(z.keys()), ["intervals", "total_duration", "zone_id"])

    def test_center_results_preserved_with_radii(self):
        """提供半径时原中心轨迹结果逐项保留，仅追加 possible / certain。"""
        samples = [sample("a", 0, -1, 1), sample("a", 3, 7, 1)]
        zones = [zone("z", SQUARE)]
        plain = run(samples, zones)
        with_unc = run_unc(samples, zones, [1, 1])
        z_plain = plain["animals"][0]["zones"][0]
        z_unc = with_unc["animals"][0]["zones"][0]
        self.assertEqual(z_unc["intervals"], z_plain["intervals"])
        self.assertEqual(z_unc["total_duration"], z_plain["total_duration"])
        # 半径 1 的方框：possible [0, 3/2]，certain 仅孤立点（无区间）
        pt, piv = unc_total(with_unc, "a", "z", "possible")
        self.assertEqual(pt, Fraction(3, 2))
        self.assertEqual(frac(piv[0]["start"]), Fraction(0))
        self.assertEqual(frac(piv[0]["end"]), Fraction(3, 2))
        ct, _ = unc_total(with_unc, "a", "z", "certain")
        self.assertEqual(ct, Fraction(0))

    # ---------------- 输入校验：整次拒绝并定位下标 ----------------

    def _expect_unc(self, payload, needle):
        with self.assertRaises(GeoDwellError) as ctx:
            process(payload)
        self.assertIn(needle, str(ctx.exception))

    def test_radii_length_mismatch_rejected(self):
        self._expect_unc(
            {"samples": [sample("a", 0, 0, 0), sample("a", 1, 1, 1)],
             "zones": [zone("z", SQUARE)],
             "uncertainty_radii": [1]},
            "长度")

    def test_radii_not_array_rejected(self):
        for bad in (5, "x", None):
            self._expect_unc(
                {"samples": [sample("a", 0, 0, 0)],
                 "zones": [zone("z", SQUARE)],
                 "uncertainty_radii": bad},
                "数组")

    def test_radii_negative_rejected_locates_index(self):
        self._expect_unc(
            {"samples": [sample("a", 0, 0, 0), sample("a", 1, 1, 1),
                         sample("a", 2, 2, 2)],
             "zones": [zone("z", SQUARE)],
             "uncertainty_radii": [0, 1, -2]},
            "uncertainty_radii[2]")

    def test_radii_boolean_rejected_locates_index(self):
        self._expect_unc(
            {"samples": [sample("a", 0, 0, 0), sample("a", 1, 1, 1)],
             "zones": [zone("z", SQUARE)],
             "uncertainty_radii": [1, True]},
            "uncertainty_radii[1]")

    def test_radii_out_of_i32_rejected(self):
        self._expect_unc(
            {"samples": [sample("a", 0, 0, 0)],
             "zones": [zone("z", SQUARE)],
             "uncertainty_radii": [2 ** 31]},
            "uncertainty_radii[0]")

    def test_radii_non_integer_rejected(self):
        for bad in (1.5, "1", None):
            self._expect_unc(
                {"samples": [sample("a", 0, 0, 0)],
                 "zones": [zone("z", SQUARE)],
                 "uncertainty_radii": [bad]},
                "uncertainty_radii[0]")


class CliAtomicity(unittest.TestCase):
    """CLI 端到端：成功才整体替换，失败保持旧文件。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gd-test-")
        self.good = os.path.join(self.tmp, "good.json")
        self.bad = os.path.join(self.tmp, "bad.json")
        self.out = os.path.join(self.tmp, "out.json")
        self.cli = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cli.py")
        with open(self.good, "w", encoding="utf-8") as fh:
            json.dump({"samples": [sample("a", 0, -1, 1),
                                   sample("a", 3, 7, 1)],
                       "zones": [zone("z", SQUARE)]}, fh)
        with open(self.bad, "w", encoding="utf-8") as fh:
            json.dump({"samples": [],
                       "zones": [zone("z", [(0, 0), (1, 1), (2, 2)])]}, fh)

    def _run(self, in_path, out_path):
        return subprocess.run(
            [sys.executable, "-I", self.cli, in_path, out_path],
            capture_output=True, text=True)

    def test_success_replaces_old_output(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("OLD CONTENT")
        proc = self._run(self.good, self.out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(self.out, encoding="utf-8") as fh:
            data = json.load(fh)
        td, _ = total(data, "a", "z")
        self.assertEqual(td, Fraction(3, 4))

    def test_failure_keeps_old_output(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("OLD CONTENT")
        proc = self._run(self.bad, self.out)
        self.assertNotEqual(proc.returncode, 0)
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "OLD CONTENT")
        self.assertIn("面积为零", proc.stderr)

    def test_bad_radii_keeps_old_output(self):
        """非法 uncertainty_radii 整次拒绝，已有输出文件保持不变。"""
        bad_radii = os.path.join(self.tmp, "bad_radii.json")
        with open(bad_radii, "w", encoding="utf-8") as fh:
            json.dump({"samples": [sample("a", 0, 0, 0), sample("a", 1, 1, 1)],
                       "zones": [zone("z", SQUARE)],
                       "uncertainty_radii": [1]}, fh)  # 长度不符
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("OLD CONTENT")
        proc = self._run(bad_radii, self.out)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("uncertainty_radii", proc.stderr)
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "OLD CONTENT")

    def test_success_with_uncertainty_radii(self):
        """带半径的端到端：原中心结果保留，possible / certain 追加。"""
        inp = os.path.join(self.tmp, "unc.json")
        with open(inp, "w", encoding="utf-8") as fh:
            json.dump({"samples": [sample("a", 0, -1, 1), sample("a", 3, 7, 1)],
                       "zones": [zone("z", SQUARE)],
                       "uncertainty_radii": [1, 1]}, fh)
        proc = self._run(inp, self.out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(self.out, encoding="utf-8") as fh:
            data = json.load(fh)
        td, _ = total(data, "a", "z")
        self.assertEqual(td, Fraction(3, 4))       # 中心轨迹结果不变
        pt, _ = unc_total(data, "a", "z", "possible")
        self.assertEqual(pt, Fraction(3, 2))
        ct, _ = unc_total(data, "a", "z", "certain")
        self.assertEqual(ct, Fraction(0))

    def test_no_temp_files_left(self):
        self._run(self.good, self.out)
        leftovers = [f for f in os.listdir(self.tmp)
                     if f.startswith(".geo_dwell-")]
        self.assertEqual(leftovers, [])

    def test_untrusted_input_dir_cannot_hijack_imports(self):
        """不可信输入目录放置 json.py，隔离模式下不得被加载。"""
        evil_dir = tempfile.mkdtemp(prefix="gd-untrusted-")
        evil_input = os.path.join(evil_dir, "in.json")
        with open(evil_input, "w", encoding="utf-8") as fh:
            json.dump({"samples": [], "zones": []}, fh)
        with open(os.path.join(evil_dir, "json.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("raise RuntimeError('untrusted json.py executed')\n")
        out_path = os.path.join(self.tmp, "out2.json")
        proc = subprocess.run(
            [sys.executable, "-I", self.cli, evil_input, out_path],
            capture_output=True, text=True, cwd=evil_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
