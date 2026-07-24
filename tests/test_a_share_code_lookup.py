import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.a_share_code_lookup import AShareCodeLookup

CSV_PATH = PROJECT_ROOT / "data" / "db" / "a_share_code_name.csv"


@pytest.fixture(scope="module")
def lookup() -> AShareCodeLookup:
    return AShareCodeLookup(CSV_PATH)


def test_finds_dong_e_company_by_full_or_short_name(lookup):
    assert lookup.lookup("东阿阿胶股份有限公司", "东阿阿胶") == "000423"


def test_returns_short_name_only_when_full_name_missing(lookup):
    assert lookup.lookup("", "平安银行") == "000001"


def test_handles_embedded_spaces_in_csv_names(lookup):
    with CSV_PATH.open(encoding="utf-8") as csv_file:
        sample_row = next(
            r for r in csv_file.read().splitlines()[1:] if r.startswith("000002,")
        )
    code, _ = sample_row.split(",")
    assert lookup.lookup("万科企业股份有限公司", "万科") == code


def test_returns_empty_for_unknown_name(lookup):
    assert lookup.lookup("完全不存在这家公司XX", "") == ""


def test_returns_empty_when_match_is_ambiguous(lookup):
    with CSV_PATH.open(encoding="utf-8", newline="") as csv_file:
        matching_names = [
            row[1] for row in csv.reader(csv_file) if len(row) > 1 and row[1].startswith("中国")
        ]
    assert len(matching_names) >= 2
    assert lookup.lookup("中国", "") == ""
