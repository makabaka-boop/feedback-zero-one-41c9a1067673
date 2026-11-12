"""命令行入口。

用法::

    python -m geo_dwell <input.json> <output.json>
    python -m geo_dwell --input <input.json> --output <output.json>

成功时把结果原子写入输出路径：先写同目录临时文件再 os.replace 整体替换；
任何解析、几何或计算错误都不会触碰已有输出文件，并以非零码退出。
"""

import argparse
import os
import sys
import tempfile

from .errors import GeoDwellError
from .engine import loads


def _atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".geo_dwell-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # 同目录原子替换
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="geo_dwell",
        description="动物轨迹到保护区停留时长的纯后端空间数据作业")
    parser.add_argument("input_pos", nargs="?", help="输入 UTF-8 JSON 路径")
    parser.add_argument("output_pos", nargs="?", help="输出 JSON 路径")
    parser.add_argument("-i", "--input", dest="input_opt", help="输入 JSON 路径")
    parser.add_argument("-o", "--output", dest="output_opt", help="输出 JSON 路径")
    args = parser.parse_args(argv)

    in_path = args.input_opt or args.input_pos
    out_path = args.output_opt or args.output_pos
    if not in_path or not out_path:
        parser.error("必须提供输入与输出路径")

    try:
        with open(in_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        result = loads(text)
    except GeoDwellError as exc:
        print(f"输入被拒绝: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        print(f"无法读取输入: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:  # json.JSONDecodeError 是 ValueError 子类
        print(f"JSON 解析失败: {exc}", file=sys.stderr)
        return 2

    import json
    try:
        _atomic_write(out_path, json.dumps(result, ensure_ascii=False, indent=2))
    except OSError as exc:
        print(f"无法写入输出: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
