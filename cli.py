#!/usr/bin/env python3
"""仓库根入口，便于在隔离模式下直接运行::

    python3 -I cli.py input.json output.json
    python3 cli.py --input input.json --output output.json

输入文件来自不可信目录时，用 ``-I`` 可阻止其目录中的同名模块（如 json.py）
被解释器加载；本脚本只依赖标准库与同仓库的 geo_dwell 包。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geo_dwell.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
