from pathlib import Path

import pytest

from src.tools.a_share_code_lookup import AShareCodeLookup


@pytest.fixture(scope="module")
def lookup() -> AShareCodeLookup:
    return AShareCodeLookup(Path("data/db/a_share_code_name.csv"))


def test_finds_dong_e_company_by_full_or_short_name(lookup):
    assert lookup.lookup("东阿阿胶股份有限公司", "东阿阿胶") == "000423"


def test_returns_short_name_only_when_full_name_missing(lookup):
    assert lookup.lookup("", "平安银行") == "000001"


def test_handles_embedded_spaces_in_csv_names(lookup):
    sample_row = next(
        r for r in open("data/db/a_share_code_name.csv", encoding="utf-8").read().splitlines()[1:]
        if r.startswith("000002,")
    )
    code, _ = sample_row.split(",")
    assert lookup.lookup("万科企业股份有限公司", "万科") == code


def test_returns_empty_for_unknown_name(lookup):
    assert lookup.lookup("完全不存在这家公司XX", "") == ""


def test_returns_empty_when_match_is_ambiguous(lookup):
    assert lookup.lookup("股份", "") == ""
