import pytest
from pathlib import Path

from src.tools.chapter_extractor import PDFChapterExtractor


def _stub_extractor(text):
    extractor = object.__new__(PDFChapterExtractor)
    extractor.doc = [type("Page", (), {"get_text": lambda self: text})()]
    return extractor


def test_lookup_resolves_label_less_first_page():
    # ensure CSV exists in the workspace
    csv = Path("data/db/a_share_code_name.csv")
    if not csv.exists():
        pytest.skip("A-share CSV not built; run script/build_a_share_code_name.py")

    extractor = _stub_extractor("东阿阿胶股份有限公司\n2020年年度报告\n")
    info = extractor.get_company_info()
    assert info[2] == "000423"


def test_returns_5_tuple_when_csv_missing(monkeypatch):
    # force the local CSV fallback to raise FileNotFoundError; chapter_extractor
    # must swallow it and still hand back a 5-tuple without raising.
    from src.tools.a_share_code_lookup import AShareCodeLookup

    def _raise(self, csv_path=None):
        raise FileNotFoundError(csv_path)

    monkeypatch.setattr(AShareCodeLookup, "__init__", _raise)

    extractor = _stub_extractor("某某从未存在公司\n2020年年度报告\n")
    info = extractor.get_company_info()
    assert isinstance(info, tuple)
    assert len(info) == 5
    assert isinstance(info[2], str)