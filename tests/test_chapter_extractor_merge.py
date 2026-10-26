"""跨页表格合并的防吞表保护测试。

## 背景(实测 bug)

``PDFChapterExtractor.should_merge_tables`` 决定两张表是否该拼接。
拼接前靠 ``_header_indicates_other_statement`` 拦"下一张报表"，
但那个函数只认**带编号前缀**的报表名（``3、合并利润表``）。

真实 A 股年报有三种版式：

  编号式   000423 → header = "3、合并利润表|单位：元"        → 保护生效
  裸标题式 600285 → header = "合并利润表|2024 年1—12 月"      → 保护失效
  无报表名 600285 → header = "2024 年1—12 月|单位：元币种：人民币" → 保护失效

保护失效时，跨页合并会把**下一张报表**（如母公司利润表）拼到当前表尾部。
实测 600285/2024 合并利润表 112 行（应为 66），row 67 起是母公司口径
（一、营业收入 27.75 亿 vs 合并 35.01 亿）。

本测试用真实 PDF 复现 + 用合成表数据锁住规则。

## 依赖

需要 data/600285/ 与 data/000423/ 下的 PDF。若不存在则 skip。
"""
from pathlib import Path

import pytest

from src.tools.chapter_extractor import PDFChapterExtractor

PDF_DIRS = [
    Path("data/600285"),
    Path("data/000423"),
]


def _pdfs():
    out = []
    for d in PDF_DIRS:
        if d.exists():
            out += sorted(d.glob("*.pdf"))
    return out


pytestmark = pytest.mark.skipif(
    not _pdfs(), reason="需要 data/600285 或 data/000423 下的 PDF"
)


# ──────────────────────────────────────────────────────────────────────────────
# 报表名识别:裸标题 vs 编号前缀
# ──────────────────────────────────────────────────────────────────────────────


def test_detect_statement_kind_handles_bare_and_numbered():
    """报表名识别要同时支持裸标题与带编号前缀两种写法。"""
    e = PDFChapterExtractor.__new__(PDFChapterExtractor)  # 不需要 __init__ 的静态用法
    detect = PDFChapterExtractor._detect_statement_kind

    # 编号式
    assert detect("1、合并资产负债表\n编制单位：某公司") == "合并资产负债表"
    assert detect("3、合并利润表\n单位：元") == "合并利润表"
    assert detect("5、合并现金流量表\n单位：元") == "合并现金流量表"

    # 裸标题式(600285 版式)
    assert detect("合并利润表\n2024 年1—12 月") == "合并利润表"
    assert detect("公司负责人：熊伟|合并现金流量表|2024 年1—12 月") == "合并现金流量表"

    # 母公司 vs 合并 必须区分(否则会把母公司表当合并表)
    assert detect("母公司利润表") == "母公司利润表"
    assert detect("4、母公司利润表") == "母公司利润表"

    # 不含报表名
    assert detect("2024 年1—12 月|单位：元币种：人民币") is None
    assert detect("") is None


def test_detect_statement_kind_prefers_longer_keyword():
    """长关键词优先,避免「合并利润表」被「利润表」抢先匹配。"""
    detect = PDFChapterExtractor._detect_statement_kind
    # 若先匹「利润表」会得到母公司利润表 —— 错
    assert detect("合并利润表") == "合并利润表"
    assert detect("合并所有者权益变动表") == "合并所有者权益变动表"


# ──────────────────────────────────────────────────────────────────────────────
# 顶级小节标题 → 新报表起点
# ──────────────────────────────────────────────────────────────────────────────


def test_is_statement_start_row_detects_first_section():
    """识别"报表的第一个小节标题" —— 它只可能出现在报表开头。"""
    is_start = PDFChapterExtractor._is_statement_start_row

    # 利润表首行
    assert is_start(["一、营业总收入", "", "3,500,831,286.92", "3,311,472,606.54"])
    assert is_start(["一、营业收入", "", "2,775,530,463.59", "2,604,419,153.91"])
    # 现金流量表首行
    assert is_start(["一、经营活动产生的现金流量：", "", "", ""])
    # 资产负债表首行
    assert is_start(["流动资产：", "", ""])

    # 续页的普通数据行 —— 不是起始
    assert not is_start(["减：所得税费用", "", "104,988,304.87", "84,928,470.59"])
    assert not is_start(["货币资金", "", "1,452,295,049.08", "1,925,840,182.39"])
    # 资产负债表第二个分类 —— 不是起始
    assert not is_start(["非流动资产：", "", "", ""])
    assert not is_start(["流动负债：", "", "", ""])
    # 利润表第二个顶级小节 —— 不是起始
    assert not is_start(["二、营业总成本", "", "2,768,148,768.85", "2,683,303,531.91"])


def test_is_statement_start_row_skips_repeated_header():
    """续页先重复表头、再出现顶级标题 —— 应跳过表头继续判定。"""
    is_start = PDFChapterExtractor._is_statement_start_row
    # 重复表头 + 母公司利润表首行 → 是新报表
    assert is_start([
        ["项目", "附注", "2024 年度", "2023 年度"],
        ["一、营业收入", "", "2,775,530,463.59", "2,604,419,153.91"],
    ])


# ──────────────────────────────────────────────────────────────────────────────
# 端到端:真实 PDF 的表不能被污染
# ──────────────────────────────────────────────────────────────────────────────


def _sections():
    return [
        "合并资产负债表", "母公司资产负债表",
        "合并利润表", "母公司利润表",
        "合并现金流量表", "母公司现金流量表",
    ]


@pytest.mark.parametrize("pdf", _pdfs(), ids=lambda p: f"{p.parent.name}/{p.stem[-8:]}")
def test_no_table_contains_next_statement(pdf):
    """每张表内部不得出现"报表首个顶级小节"(除第 1 行外)。

    若出现,说明跨页合并把下一张报表吞进来了。
    """
    e = PDFChapterExtractor(str(pdf))
    try:
        mt = e.extract_main_tables()
        for sec in _sections():
            obj = mt.get(sec)
            if not (obj and hasattr(obj, "table_data")):
                continue
            rows = obj.table_data
            for i, r in enumerate(rows[2:], start=2):
                label = str(r[0] or "").replace("\n", "").strip()
                if not label:
                    continue
                assert not PDFChapterExtractor._is_statement_start_row([label]), (
                    f"{pdf.parent.name}/{pdf.stem}: {sec} 第 {i} 行出现报表起始标题"
                    f"「{label}」→ 跨页合并吞了下一张报表"
                )
    finally:
        e.close()


@pytest.mark.parametrize("pdf", _pdfs(), ids=lambda p: f"{p.parent.name}/{p.stem[-8:]}")
def test_no_duplicate_header_inside_table(pdf):
    """表内不得有第二处「项目 / 科目」表头(续页重复表头应被跳过)。"""
    e = PDFChapterExtractor(str(pdf))
    try:
        mt = e.extract_main_tables()
        for sec in _sections():
            obj = mt.get(sec)
            if not (obj and hasattr(obj, "table_data")):
                continue
            rows = obj.table_data
            dup_at = [
                i for i, r in enumerate(rows[1:], start=1)
                if r and str(r[0] or "").replace("\n", "").strip() in ("项目", "科目")
            ]
            assert not dup_at, (
                f"{pdf.parent.name}/{pdf.stem}: {sec} 在第 {dup_at} 行有重复表头"
                f" → 跨页合并未跳过续页表头"
            )
    finally:
        e.close()


@pytest.mark.parametrize("pdf", _pdfs(), ids=lambda p: f"{p.parent.name}/{p.stem[-8:]}")
def test_merged_table_rows_have_uniform_width(pdf):
    """合并后的表行宽必须一致(否则列错位,数据不可用)。"""
    e = PDFChapterExtractor(str(pdf))
    try:
        mt = e.extract_main_tables()
        for sec in _sections():
            obj = mt.get(sec)
            if not (obj and hasattr(obj, "table_data")) or len(obj.table_data) < 3:
                continue
            widths = {len(r) for r in obj.table_data}
            assert len(widths) == 1, (
                f"{pdf.parent.name}/{pdf.stem}: {sec} 行宽不一致 {sorted(widths)}"
                f" → 合并了两张列数不同的表"
            )
    finally:
        e.close()


def test_600285_2024_income_statement_not_polluted():
    """回归锁定:600285/2024 合并利润表曾 112 行(吞了母公司利润表)。

    正确行数应与母公司利润表同量级(~66),且 row 66 附近不应是
    母公司口径的「一、营业收入 2,775,530,463.59」。
    """
    pdf = Path("data/600285/羚锐制药_600285_2024.pdf")
    if not pdf.exists():
        pytest.skip("需要 600285/2024 PDF")
    e = PDFChapterExtractor(str(pdf))
    try:
        mt = e.extract_main_tables()
        obj = mt.get("合并利润表")
        if not (obj and hasattr(obj, "table_data")):
            pytest.skip("未提取到合并利润表")
        rows = obj.table_data
        assert len(rows) < 100, (
            f"合并利润表 {len(rows)} 行,疑似吞了母公司利润表(应 ~66 行)"
        )
        # 合并口径的营业总收入应在表内
        labels = [str(r[0] or "").replace("\n", "").strip() for r in rows]
        assert "一、营业总收入" in labels, "合并利润表应含「一、营业总收入」"
        # 母公司口径的「一、营业收入」不应出现在合并利润表
        assert "一、营业收入" not in labels, (
            "合并利润表里出现了「一、营业收入」(母公司口径)→ 吞表了"
        )
    finally:
        e.close()
