#!/usr/bin/env bash
# 一键自动验收：运行单元/端到端测试与随机化强度测试。
# 全程使用 -I 隔离模式，仅依赖 Python 标准库。
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/2 单元与端到端验收（38 项） =="
python3 -I -m unittest discover -s tests -v

echo
echo "== 2/2 随机化强度测试（凹多边形/洞/拆分/反转交叉核对） =="
python3 -I tests/fuzz_check.py

echo
echo "全部验收通过。"
