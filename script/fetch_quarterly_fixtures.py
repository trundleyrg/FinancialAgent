#!/usr/bin/env python
"""拉取季报测试夹具到 data/{code}/。

季报 PDF 是几 MB 的二进制,不入库;测试在文件缺失时自动 skip。
用法:
    python script/fetch_quarterly_fixtures.py 600285 2025
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.download_cninfo_reports import CNInfoReportDownloader  # noqa: E402


def main():
    code = sys.argv[1] if len(sys.argv) > 1 else "600285"
    years = [int(y) for y in sys.argv[2:]] if len(sys.argv) > 2 else [2025]
    d = CNInfoReportDownloader()
    ok = d.download_reports(code, years, periods=["Q1", "H1", "Q3"])
    print("完成" if ok else "未找到报告")


if __name__ == "__main__":
    main()
