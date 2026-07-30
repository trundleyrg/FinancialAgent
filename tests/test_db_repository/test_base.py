import pytest
from src.db.repository.base import _ModelToDict, BaseRepository
from src.db.repository.keys import ReportKey
from tests.test_db_repository.conftest import FakeConnector, FakeModel


class TestModelToDict:
    def test_none_returns_none(self):
        assert _ModelToDict.convert(None) is None

    def test_dict_passes_through(self):
        d = {"a": 1, "b": "x"}
        assert _ModelToDict.convert(d) == {"a": 1, "b": "x"}

    def test_model_with_dunder_dict_uses_dunder_dict(self):
        m = FakeModel(monetary_funds=1000.0, total_assets=5000.0)
        out = _ModelToDict.convert(m)
        assert out == {"monetary_funds": 1000.0, "total_assets": 5000.0}

    def test_model_dunder_dict_excludes_private_and_id(self):
        m = FakeModel(monetary_funds=1000.0)
        m.__dict__["_database"] = "secret"
        m.__dict__["id"] = 99
        out = _ModelToDict.convert(m)
        assert "id" not in out
        assert "_database" not in out
        assert out["monetary_funds"] == 1000.0

    def test_object_with_data_attr_fallback(self):
        class HasData:
            _data = {"x": 1, "y": 2}
        out = _ModelToDict.convert(HasData())
        assert out == {"x": 1, "y": 2}


class TestBaseRepositoryResolveStockCode:
    def test_returns_stock_code_if_already_set(self, fake_connector):
        repo = BaseRepository(fake_connector)
        assert repo.resolve_stock_code(ReportKey(stock_code="000423")) == "000423"

    def test_resolves_from_company_name_via_financial_reports(self, fake_connector):
        fake_connector.seed("financial_reports", [
            {"company_name": "东阿阿胶", "stock_code": "000423", "report_year": 2023, "report_period": "FY"},
        ])
        repo = BaseRepository(fake_connector)
        assert repo.resolve_stock_code(ReportKey(company_name="东阿阿胶")) == "000423"

    def test_returns_none_when_no_data(self, fake_connector):
        repo = BaseRepository(fake_connector)
        assert repo.resolve_stock_code(ReportKey(company_name="UNKNOWN")) is None

    def test_returns_none_when_no_address(self, fake_connector):
        repo = BaseRepository(fake_connector)
        # No address resolution path: company_name + year/period but no matching records.
        # (Strict ReportKey.__post_init__ makes a key with neither stock_code nor company_name
        # impossible to construct, so the original "neither set" scenario is unreachable.)
        assert repo.resolve_stock_code(ReportKey(company_name="UNKNOWN", year=2024, period="FY")) is None


class TestBaseRepositoryQuery:
    def test_query_returns_dicts_only(self, fake_connector):
        fake_connector.seed("financial_reports", [
            {"id": 1, "company_name": "东阿阿胶", "stock_code": "000423",
             "report_year": 2023, "report_period": "FY"},
            {"id": 2, "company_name": "东阿阿胶", "stock_code": "000423",
             "report_year": 2024, "report_period": "FY"},
        ])
        repo = BaseRepository(fake_connector)
        out = repo._query("financial_reports", ReportKey(stock_code="000423", year=2024))
        assert out == [
            {"company_name": "东阿阿胶", "stock_code": "000423",
             "report_year": 2024, "report_period": "FY"},
        ]
        # id 已剥离
        assert "id" not in out[0]

    def test_query_first_returns_none_when_empty(self, fake_connector):
        repo = BaseRepository(fake_connector)
        assert repo._query_first("financial_reports", ReportKey(stock_code="999999")) is None

    def test_query_converts_model_instances(self, fake_connector):
        # 模拟 connector 返回 Peewee-style Model 实例（带 __dict__）
        fake_connector.seed("financial_reports", [
            FakeModel(company_name="X", stock_code="000423", report_year=2024),
        ])
        repo = BaseRepository(fake_connector)
        out = repo._query("financial_reports", ReportKey(stock_code="000423"))
        assert out == [{"company_name": "X", "stock_code": "000423", "report_year": 2024}]
