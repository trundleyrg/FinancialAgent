"""ReportRepository 单元测试。"""
import datetime

from src.db.repository.keys import ReportKey
from src.db.repository.reports import ReportRepository
from tests.test_db_repository.conftest import FakeConnector


def _seed_reports(conn):
    conn.seed("financial_reports", [
        {"id": 1, "company_name": "东阿阿胶", "company_short_name": "东阿",
         "stock_code": "000423", "report_year": 2023, "report_period": "FY",
         "source_file": "f1"},
        {"id": 2, "company_name": "东阿阿胶", "company_short_name": "东阿",
         "stock_code": "000423", "report_year": 2024, "report_period": "FY",
         "source_file": "f2"},
        {"id": 3, "company_name": "贵州茅台", "company_short_name": "茅台",
         "stock_code": "600519", "report_year": 2024, "report_period": "FY",
         "source_file": "f3"},
    ])


class TestGetReport:
    def test_returns_dict_when_match(self, fake_connector):
        _seed_reports(fake_connector)
        repo = ReportRepository(fake_connector)
        out = repo.get_report(ReportKey(stock_code="000423", year=2024, period="FY"))
        assert out["company_name"] == "东阿阿胶"
        assert out["report_year"] == 2024

    def test_returns_none_when_no_match(self, fake_connector):
        repo = ReportRepository(fake_connector)
        assert repo.get_report(ReportKey(stock_code="999999")) is None

    def test_resolves_company_name_to_stock_code(self, fake_connector):
        _seed_reports(fake_connector)
        repo = ReportRepository(fake_connector)
        out = repo.get_report(ReportKey(company_name="东阿阿胶", year=2024, period="FY"))
        assert out["stock_code"] == "000423"


class TestListReports:
    def test_returns_all_periods_of_year(self, fake_connector):
        fake_connector.seed("financial_reports", [
            {"id": 1, "company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "Q1", "source_file": "f"},
            {"id": 2, "company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "source_file": "f"},
        ])
        repo = ReportRepository(fake_connector)
        out = repo.list_reports(ReportKey(stock_code="000001", year=2024))
        periods = {r["report_period"] for r in out}
        assert periods == {"Q1", "FY"}


class TestAggregates:
    def test_list_companies(self, fake_connector):
        _seed_reports(fake_connector)
        repo = ReportRepository(fake_connector)
        out = repo.list_companies()
        # 按 stock_code 排序便于断言
        assert sorted(out, key=lambda x: x["stock_code"]) == [
            {"company_name": "东阿阿胶", "stock_code": "000423"},
            {"company_name": "贵州茅台", "stock_code": "600519"},
        ]

    def test_list_company_years(self, fake_connector):
        _seed_reports(fake_connector)
        repo = ReportRepository(fake_connector)
        assert repo.list_company_years("000423") == [2024, 2023]

    def test_list_all_years(self, fake_connector):
        _seed_reports(fake_connector)
        repo = ReportRepository(fake_connector)
        assert repo.list_all_years() == [2024, 2023]


class TestListAvailablePeriods:
    def test_returns_periods(self, fake_connector):
        fake_connector.seed("financial_reports", [
            {"id": 1, "company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "Q1", "source_file": "f"},
            {"id": 2, "company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "source_file": "f"},
        ])
        repo = ReportRepository(fake_connector)
        out = repo.list_available_periods(ReportKey(stock_code="000001", year=2024))
        assert sorted(out) == ["FY", "Q1"]


class TestCheckDataAvailability:
    def test_returns_dict_shape(self, fake_connector):
        for y in [2020, 2021, 2022, 2023]:
            fake_connector.seed("financial_reports", [
                {"id": y, "company_name": "A", "stock_code": "000001",
                 "report_year": y, "report_period": "FY", "source_file": "f"},
            ])
        repo = ReportRepository(fake_connector)
        out = repo.check_data_availability(
            ReportKey(stock_code="000001"), years=4
        )
        # Window is [current_year - 3, ..., current_year]
        current_year = datetime.datetime.now().year
        assert out["required_years"] == list(range(current_year - 3, current_year + 1))
        # At minimum, has_data/data_coverage fields exist
        assert "has_data" in out
        assert "data_coverage" in out
        assert "missing_years" in out
        assert "available_years" in out
        assert "has_latest_year" in out
        assert "total_available" in out

    def test_partial_coverage(self, fake_connector):
        fake_connector.seed("financial_reports", [
            {"id": 1, "company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "source_file": "f"},
        ])
        repo = ReportRepository(fake_connector)
        out = repo.check_data_availability(
            ReportKey(stock_code="000001"), years=5
        )
        assert out["total_available"] == 1  # only 2024 in DB


class TestListMultiYearReports:
    def test_missing_years_absent(self, fake_connector):
        fake_connector.seed("financial_reports", [
            {"id": 1, "company_name": "A", "stock_code": "000001",
             "report_year": 2022, "report_period": "FY", "source_file": "f"},
            {"id": 2, "company_name": "A", "stock_code": "000001",
             "report_year": 2024, "report_period": "FY", "source_file": "f"},
        ])
        repo = ReportRepository(fake_connector)
        out = repo.list_multi_year_reports(
            ReportKey(stock_code="000001", period="FY"),
            start_year=2021, end_year=2024,
        )
        assert set(out.keys()) == {2022, 2024}  # 2021/2023 缺失
        assert out[2024]["report_year"] == 2024
