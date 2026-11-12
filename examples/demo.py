"""端到端综合演示：一个输入同时覆盖题面要求的各类几何情形。

运行:: python3 -I examples/demo.py
也可生成输入文件后走 CLI::

    python3 -I cli.py examples/demo_input.json /tmp/demo_out.json
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_dwell import process  # noqa: E402
from fractions import Fraction  # noqa: E402

# 凹多边形（U 形）：(2,4)-(4,4) 是凹口外的缺口
U_SHAPE = [(0, 0), (6, 0), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6)]
# 带洞正方形
OUTER = [(0, 0), (10, 0), (10, 10), (0, 10)]
HOLE = [(3, 3), (7, 3), (7, 7), (3, 7)]
# 菱形（用于顶点穿越）
DIAMOND = [(2, 0), (4, 2), (2, 4), (0, 2)]

payload = {
    "samples": [
        # 题面基准：3 秒穿过 [0,2]^2，停留 3/4 秒
        {"animal_id": "elk", "t": 0, "x": -1, "y": 1},
        {"animal_id": "elk", "t": 3, "x": 7, "y": 1},

        # 凹多边形：穿过 U 形，凹口处离开，形成两段停留
        {"animal_id": "fox", "t": 0, "x": -1, "y": 4},
        {"animal_id": "fox", "t": 8, "x": 7, "y": 4},

        # 带洞保护区：穿过洞内部，洞内部被扣除
        {"animal_id": "bear", "t": 0, "x": -1, "y": 5},
        {"animal_id": "bear", "t": 11, "x": 10, "y": 5},

        # 顶点穿越：菱形 y=2 从左顶点进、右顶点出
        {"animal_id": "owl", "t": 0, "x": -1, "y": 2},
        {"animal_id": "owl", "t": 5, "x": 4, "y": 2},
        # 孤立顶点触碰：沿 y=0 只碰到菱形下顶点 (2,0)
        {"animal_id": "bat", "t": 0, "x": 0, "y": 0},
        {"animal_id": "bat", "t": 4, "x": 4, "y": 0},

        # 共线重叠 + 重复位置：先沿正方形底边移动，再在区内静止 2 秒
        {"animal_id": "seal", "t": 0, "x": -1, "y": 0},
        {"animal_id": "seal", "t": 3, "x": 2, "y": 0},
        {"animal_id": "seal", "t": 5, "x": 2, "y": 0},

        # 单点动物：无时长，但组合保留
        {"animal_id": "lonely", "t": 42, "x": 1, "y": 1},
    ],
    "zones": [
        {"zone_id": "square", "outer_ring": [[0, 0], [2, 0], [2, 2], [0, 2]],
         "holes": []},
        {"zone_id": "ushape", "outer_ring": U_SHAPE, "holes": []},
        {"zone_id": "holed", "outer_ring": OUTER, "holes": [HOLE]},
        {"zone_id": "diamond", "outer_ring": DIAMOND, "holes": []},
    ],
}


def show(result):
    for animal in result["animals"]:
        print(f"动物 {animal['animal_id']}:")
        for z in animal["zones"]:
            td = Fraction(z["total_duration"]["numerator"],
                          z["total_duration"]["denominator"])
            ivs = []
            for iv in z["intervals"]:
                s = Fraction(iv["start"]["numerator"], iv["start"]["denominator"])
                e = Fraction(iv["end"]["numerator"], iv["end"]["denominator"])
                ivs.append(f"[{s}, {e}]")
            print(f"  {z['zone_id']:8s} 总时长={td!s:>6}  区间={', '.join(ivs) or '无'}")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "demo_input.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    result = process(payload)
    show(result)
    print("\n输入已写入 examples/demo_input.json，可再用 CLI 核对原子输出。")
