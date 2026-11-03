"""main.py 的季报子命令与本地文件扫描。"""
from pathlib import Path

import main


def test_list_local_annual_pdfs_excludes_quarterly(tmp_path, monkeypatch):
    """季报文件不能被当成年报本地已有文件。"""
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "data" / "600285"
    d.mkdir(parents=True)
    (d / "羚锐制药_600285_2024.pdf").write_bytes(b"%PDF-1.4")
    (d / "羚锐制药_600285_2025Q1.pdf").write_bytes(b"%PDF-1.4")
    (d / "羚锐制药_600285_2025H1.pdf").write_bytes(b"%PDF-1.4")

    annual = main.list_local_report_pdfs("600285", ("FY",))
    assert [p.name for p in annual] == ["羚锐制药_600285_2024.pdf"]

    periodic = main.list_local_report_pdfs("600285", ("Q1", "H1", "Q3"))
    assert sorted(p.name for p in periodic) == [
        "羚锐制药_600285_2025H1.pdf",
        "羚锐制药_600285_2025Q1.pdf",
    ]


def test_period_suffix_for_non_fy():
    assert main.period_suffix("FY") == ""
    assert main.period_suffix("Q1") == "Q1"
    assert main.period_suffix("H1") == "H1"
    assert main.period_suffix("Q3") == "Q3"


def test_quarterly_pipeline_parses_downloaded_pdfs(tmp_path, monkeypatch):
    """qrun 对每个下载到的 PDF 都调用一次解析。"""
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "data" / "600285"
    d.mkdir(parents=True)
    (d / "羚锐制药_600285_2025Q1.pdf").write_bytes(b"%PDF-1.4")

    called = []
    monkeypatch.setattr(main, "download_periodic_reports",
                        lambda code, years, periods: [d / "羚锐制药_600285_2025Q1.pdf"])
    monkeypatch.setattr(main, "parse_pdf_to_db",
                        lambda p: called.append(p) or {"consolidated_balance_sheet": 1})

    main.quarterly_pipeline("600285", [2025], periods=("Q1",))
    assert len(called) == 1
    assert called[0].name == "羚锐制药_600285_2025Q1.pdf"


def test_quarterly_pipeline_survives_single_parse_failure(tmp_path, monkeypatch):
    """单个 PDF 解析失败不能中断整批。"""
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "data" / "600285"
    d.mkdir(parents=True)
    (d / "a_600285_2025Q1.pdf").write_bytes(b"%PDF-1.4")
    (d / "b_600285_2025Q1.pdf").write_bytes(b"%PDF-1.4")

    ok = []

    def fake_parse(p):
        if p.name.startswith("a_"):
            raise ValueError("boom")
        ok.append(p)
        return {}

    monkeypatch.setattr(main, "download_periodic_reports",
                        lambda code, years, periods: sorted(d.glob("*.pdf")))
    monkeypatch.setattr(main, "parse_pdf_to_db", fake_parse)

    main.quarterly_pipeline("600285", [2025], periods=("Q1",))
    assert len(ok) == 1
