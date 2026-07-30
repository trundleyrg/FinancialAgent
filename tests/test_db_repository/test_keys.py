import pytest
from src.db.repository.keys import ReportKey


class TestReportKeyValidation:
    def test_requires_stock_code_or_company_name(self):
        with pytest.raises(ValueError, match="requires stock_code or company_name"):
            ReportKey(year=2024, period="FY")

    def test_accepts_only_stock_code(self):
        k = ReportKey(stock_code="000423", year=2024, period="FY")
        assert k.stock_code == "000423"
        assert k.company_name is None

    def test_accepts_only_company_name(self):
        k = ReportKey(company_name="东阿阿胶", year=2024)
        assert k.company_name == "东阿阿胶"
        assert k.stock_code is None

    def test_is_frozen(self):
        k = ReportKey(stock_code="000423")
        with pytest.raises(Exception):  # FrozenInstanceError
            k.stock_code = "000001"  # type: ignore[misc]


class TestToFilter:
    def test_stock_code_takes_precedence_over_company_name(self):
        k = ReportKey(stock_code="000423", company_name="ignored", year=2024, period="FY")
        assert k.to_filter() == {
            "stock_code": "000423",
            "report_year": 2024,
            "report_period": "FY",
        }

    def test_company_name_only(self):
        k = ReportKey(company_name="东阿阿胶")
        assert k.to_filter() == {"company_name": "东阿阿胶"}

    def test_no_year_no_period(self):
        k = ReportKey(stock_code="000423")
        assert k.to_filter() == {"stock_code": "000423"}

    def test_year_without_period(self):
        k = ReportKey(stock_code="000423", year=2024)
        assert k.to_filter() == {"stock_code": "000423", "report_year": 2024}


class TestWithYear:
    def test_returns_new_instance_with_year_replaced(self):
        original = ReportKey(stock_code="000423", period="FY")
        new = original.with_year(2023)
        assert original.year is None
        assert new.year == 2023
        assert new.stock_code == "000423"
        assert new.period == "FY"
