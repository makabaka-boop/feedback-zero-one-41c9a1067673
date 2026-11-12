"""作业引擎：严格解析 UTF-8 JSON、编排裁剪与合并、构建结果结构。"""

import json
from fractions import Fraction

from .errors import GeoDwellError
from .geometry import validate_zone
from .clipping import clip_segment, stationary_intervals
from .intervals import merge_intervals, total_duration

I32_MIN, I32_MAX = -(1 << 31), (1 << 31) - 1
U64_MAX = (1 << 63) - 1  # 非负有符号 64 位整数秒


class _RejectDupKeys(dict):
    """JSON object_pairs_hook：拒绝重复键。"""

    def __init__(self, pairs):
        super().__init__()
        for key, value in pairs:
            if key in self:
                raise GeoDwellError(f"JSON 中存在重复键: {key!r}")
            self[key] = value


def _is_int(v):
    """严格整数：布尔不是整数。"""
    return isinstance(v, int) and not isinstance(v, bool)


def _check_identifier(v, label):
    if not isinstance(v, str) or not v:
        raise GeoDwellError(f"{label} 必须是非空字符串")
    if not all("0" <= ch <= "9" or "a" <= ch <= "z" or "A" <= ch <= "Z"
               for ch in v):
        raise GeoDwellError(f"{label} 必须是 ASCII 字母数字串: {v!r}")
    return v


def _require_keys(obj, required, label):
    if not isinstance(obj, dict):
        raise GeoDwellError(f"{label} 必须是 JSON 对象")
    missing = [k for k in required if k not in obj]
    if missing:
        raise GeoDwellError(f"{label} 缺少必填字段: {', '.join(missing)}")


def parse_input(payload):
    """解析并校验输入，返回 (samples 分组 dict, zones dict)。"""
    if not isinstance(payload, dict):
        raise GeoDwellError("顶层必须是 JSON 对象")
    _require_keys(payload, ["samples", "zones"], "顶层")

    raw_samples = payload["samples"]
    raw_zones = payload["zones"]
    if not isinstance(raw_samples, list) or not isinstance(raw_zones, list):
        raise GeoDwellError("samples 与 zones 必须是数组")

    animals = {}
    for i, s in enumerate(raw_samples):
        label = f"samples[{i}]"
        _require_keys(s, ["animal_id", "t", "x", "y"], label)
        aid = _check_identifier(s["animal_id"], f"{label}.animal_id")
        t, x, y = s["t"], s["x"], s["y"]
        if not _is_int(t) or not (0 <= t <= U64_MAX):
            raise GeoDwellError(
                f"{label}.t 必须是 0..2^63-1 的非负有符号 64 位整数")
        if not _is_int(x) or not (I32_MIN <= x <= I32_MAX):
            raise GeoDwellError(f"{label}.x 必须是有符号 32 位整数")
        if not _is_int(y) or not (I32_MIN <= y <= I32_MAX):
            raise GeoDwellError(f"{label}.y 必须是有符号 32 位整数")
        animals.setdefault(aid, []).append((t, x, y))

    for aid, pts in animals.items():
        pts.sort(key=lambda p: p[0])
        times = [p[0] for p in pts]
        if len(set(times)) != len(times):
            raise GeoDwellError(
                f"动物 {aid!r} 存在重复时刻 t（同动物时刻必须唯一）")

    zones = {}
    for i, z in enumerate(raw_zones):
        label = f"zones[{i}]"
        _require_keys(z, ["zone_id", "outer_ring", "holes"], label)
        zid = _check_identifier(z["zone_id"], f"{label}.zone_id")
        if zid in zones:
            raise GeoDwellError(f"zone_id 重复: {zid!r}")
        outer, holes = validate_zone(z["outer_ring"], z["holes"], zid)
        zones[zid] = (outer, holes)

    return animals, zones


def _fraction_obj(value):
    """把 Fraction 转为约分后的 {numerator, denominator}，分母恒正。"""
    return {"numerator": value.numerator, "denominator": value.denominator}


def _dwell_for_animal(points, zones):
    """计算一只动物在所有保护区的停留区间。"""
    result = {}
    for zid, (outer, holes) in zones.items():
        raw_intervals = []
        for (t0, x0, y0), (t1, x1, y1) in zip(points, points[1:]):
            a, b = (x0, y0), (x1, y1)
            dt = Fraction(t1 - t0)
            if a == b:
                pieces = stationary_intervals(a, dt, outer, holes)
            else:
                pieces = clip_segment(a, b, outer, holes)
            for u_lo, u_hi in pieces:
                start = Fraction(t0) + dt * u_lo
                end = Fraction(t0) + dt * u_hi
                raw_intervals.append((start, end))

        merged = merge_intervals(raw_intervals)
        result[zid] = {
            "intervals": [
                {
                    "start": _fraction_obj(s),
                    "end": _fraction_obj(e),
                    "duration": _fraction_obj(e - s),
                }
                for s, e in merged
            ],
            "total_duration": _fraction_obj(total_duration(merged)),
        }
    return result


def process(payload):
    """主入口：输入已解析的 JSON 数据，返回可 json.dump 的结果结构。"""
    animals, zones = parse_input(payload)

    out_animals = []
    for aid in sorted(animals):
        points = animals[aid]  # 已按 t 排序；单点动物自然得到空区间与 0 时长
        dwell = _dwell_for_animal(points, zones)
        out_animals.append({
            "animal_id": aid,
            "zones": [
                dict(zone_id=zid, **dwell[zid])
                for zid in sorted(zones)
            ],
        })
    return {"animals": out_animals}


def loads(text):
    """解析 UTF-8 JSON 文本（拒绝重复键）并执行作业。"""
    payload = json.loads(text, object_pairs_hook=_RejectDupKeys)
    return process(payload)
