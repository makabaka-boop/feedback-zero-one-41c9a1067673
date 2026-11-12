"""动物定位轨迹 -> 保护区停留时长 纯后端空间作业。

只依赖 Python 标准库；几何校验、线段裁剪、区间合并全部自行实现，
不调用任何几何库或空间数据库，全程整数/有理数精确运算。
"""

from .errors import GeoDwellError
from .engine import process

__all__ = ["process", "GeoDwellError"]
