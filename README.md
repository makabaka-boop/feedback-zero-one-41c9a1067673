# 动物轨迹 → 保护区停留时长（纯后端空间数据作业）

把动物定位轨迹转换为每只动物在每个保护区的**停留区间**与**累计停留时长**。
只用 Python 标准库；线段裁剪、几何校验、区间合并全部自行实现，
**不调用任何几何库或空间数据库**；全程整数 / 有理数精确运算，
**不经过任何浮点数近似**。

## 运行环境与入口

需要 Python 3.9+（开发环境为 3.11），无第三方依赖。

```bash
# 推荐：隔离模式（-I）运行，避免不可信输入目录中的同名模块（如 json.py）被加载
python3 -I cli.py <input.json> <output.json>
python3 -I cli.py --input <input.json> --output <output.json>

# 安装为包后也可用模块方式
python -m geo_dwell <input.json> <output.json>
```

- 输入：UTF-8 JSON，含 `samples` 与 `zones`。
- 输出：UTF-8 JSON。**全部成功才整体替换旧输出**——先写同目录临时文件再
  `os.replace` 原子替换；任何解析 / 几何 / 计算错误都不会触碰已有输出文件，
  进程以非零码退出并在 stderr 打印带环定位的错误信息。

## 输入格式

```json
{
  "samples": [
    {"animal_id": "elk", "t": 0, "x": -1, "y": 1},
    {"animal_id": "elk", "t": 3, "x": 7, "y": 1}
  ],
  "zones": [
    {"zone_id": "square",
     "outer_ring": [[0, 0], [2, 0], [2, 2], [0, 2]],
     "holes": []}
  ]
}
```

可选的定位误差数组（与 `samples` 逐项对应）：

```json
{
  "samples": [...],
  "uncertainty_radii": [2, 0],
  "zones": [...]
}
```

约束（违反任意一条整次拒绝）：

- 标识 `animal_id` / `zone_id`：非空 ASCII 字母数字串；`zone_id` 唯一。
- `t`：非负有符号 64 位整数秒（0 … 2^63−1）；同一动物时刻唯一。
- `x` / `y`：有符号 32 位整数；**整数禁止布尔**（`true`/`false` 不是整数）。
- `uncertainty_radii`（可选）：与 `samples` 等长，元素为 0 … 2^31−1 的
  非负有符号 32 位整数，禁止布尔；长度不符或元素非法都整次拒绝，
  错误信息定位到具体下标（如 `uncertainty_radii[2]`）。
- 环：至少 3 个**不同整数坐标点**的数组，首点不重复，闭合边隐含。
- 环必须**简单**（边不自交、不接触，相邻边不共线回折）且**面积非零**。
- 洞严格位于外环内部；各环边界不能接触或相交；洞之间不得包含。
- 环方向任意（顺/逆时针结果一致，已由测试覆盖）。

## 输出格式

保留**所有动物 × 所有保护区**组合；区间按起点排序，重叠或端点相接的区间合并，
只输出正长度区间（孤立触碰不产生时长）；端点与时长均为**约分后的分子、正分母**：

```json
{
  "animals": [
    {
      "animal_id": "elk",
      "zones": [
        {
          "zone_id": "square",
          "intervals": [
            {
              "start":    {"numerator": 3, "denominator": 8},
              "end":      {"numerator": 9, "denominator": 8},
              "duration": {"numerator": 3, "denominator": 4}
            }
          ],
          "total_duration": {"numerator": 3, "denominator": 4}
        }
      ]
    }
  ]
}
```

无任何停留时 `intervals` 为 `[]`、`total_duration` 为 `0/1`；
单点动物无时长但组合保留；不同保护区可重叠，各自独立计算。

提供 `uncertainty_radii` 时，每个保护区组合**追加** `possible` 与
`certain` 两个子对象（原中心轨迹的 `intervals` / `total_duration`
原样保留），区间与分数编码沿用同一格式：

```json
{
  "zone_id": "square",
  "intervals": [...],
  "total_duration": {"numerator": 3, "denominator": 4},
  "possible": {"intervals": [...], "total_duration": {"numerator": 3, "denominator": 2}},
  "certain":  {"intervals": [],    "total_duration": {"numerator": 0, "denominator": 1}}
}
```

未提供 `uncertainty_radii` 时输出与旧格式逐项一致（不出现这两个字段）。

## 语义要点

- 同动物相邻采样点按时间连接，位置随时间**线性插值**；轨迹仅在首末采样间定义。
- 区域包含外边界与洞边界，但排除洞内部；**沿边移动计时，孤立触碰不产生时长**。
- 静止段（相邻点重合）按该点归属计时：在区内/洞边界上计时，在区外或洞内部不计时。
- 裁剪方法：收集线段与所有环边的交点参数（精确 `Fraction`）及端点 0/1，
  逐开区间取中点做包含判定，从而正确处理共线重叠、顶点穿越等退化情形。
- 定位误差：半径与中心位置均按相邻采样时刻**线性插值**；每个时刻的可能
  位置是以定位点为中心、半径为半边长的**闭合轴对齐正方形**，各时刻独立，
  不额外限制真实路径。
  - `possible`：正方形至少一点属于区域（含外环与洞边界）；
  - `certain`：正方形**全部点**都属于区域——覆盖洞内部即不成立，
    因此不能只查方框角点（角点均在区内仍可能包住洞）；
  - 仅在首末采样间计时，单点无时长；孤立接触不产生区间，端点相接合并；
  - 判定同样全程精确：收集中心轨迹越环、环顶点落上方框边界、方框角点
    落上环边所在直线三类临界参数，逐开区间取中点做精确包含判定。

## 目录结构

```
geo_dwell/
  errors.py      统一错误类型（非法几何带 zone/环定位）
  geometry.py    整数几何原语、环与保护区合法性校验、精确点包含
  clipping.py    精确有理数线段裁剪、静止段处理
  uncertainty.py 误差方框 possible/certain 临界参数与精确判定
  intervals.py   区间合并与累计时长
  engine.py      严格 JSON 解析、编排、输出结构
  __main__.py    模块 CLI 入口（原子写入）
cli.py           仓库根入口，支持 python3 -I cli.py ...
tests/
  test_geo_dwell.py  59 项单元/端到端验收
  fuzz_check.py      随机化强度交叉核对
examples/
  demo.py / demo_input.json  综合演示
run_acceptance.sh    一键验收
```

## 自动验收

```bash
./run_acceptance.sh
# 或分别运行
python3 -I -m unittest discover -s tests -v
python3 -I tests/fuzz_check.py
python3 -I examples/demo.py
```

验收覆盖：凹多边形（U 形两段停留）、带洞保护区（穿洞扣减 / 沿洞边界计时）、
共线重叠（沿外边界移动并合并）、顶点穿越（顶点进入计时 vs 孤立顶点触碰无时长）、
重复位置（区内/区外/洞边界/洞内部静止）、非法几何定位（自交、零面积、
洞在外环外、洞压边界、洞互相包含）、拆分共线轨迹段不变性、反转环方向不变性、
分数约分与正分母、全组合输出、CLI 原子替换与隔离模式防模块劫持。
定位误差半径的独立样例验收：方框包住整个保护区（possible 成立 / certain 不成立）、
角点均在区内却包住洞（certain 不成立，证明不能只查角点）、运动中短暂相交、
匀速穿越三层嵌套区间（certain ⊂ 中心 ⊂ possible，完整区间与时长核对）、
半径线性增长与收缩退化为零、跨段端点相接合并与孤立 certain 剔除、
零半径与中心轨迹一致、贴洞边界 certain 成立、方框落入洞内部无停留、
半径长度/类型/范围非法整次拒绝并定位下标、未提供数组时输出逐项兼容、
非法半径下 CLI 保留旧输出文件。

### 题面基准用例

轨迹 `(-1,1) → (7,1)`、用时 3 秒，穿过 `[0,2]²` 正方形：
区内参数 `u∈[1/8, 3/8]`，对应时刻 `[3/8, 9/8]` 秒，停留 **3/4 秒**
（见 `tests/test_geo_dwell.py::CanonicalAndVariants`）。
