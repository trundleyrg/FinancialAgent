"""ShareStructureRepository 单元测试。"""
from src.db.repository.keys import ReportKey
from src.db.repository.share_structure import ShareStructureRepository
from tests.test_db_repository.conftest import FakeConnector


def _seed_structure(conn, rows):
    conn.seed("share_structure", rows)


def test_get_structure(fake_connector):
    _seed_structure(fake_connector, [
        {"company_name": "A", "stock_code": "000001",
         "report_year": 2024, "report_period": "FY",
         "total_shares": 1000000.0, "restricted_shares": 100000.0},
    ])
    repo = ShareStructureRepository(fake_connector)
    out = repo.get_structure(
        ReportKey(stock_code="000001", year=2024, period="FY")
    )
    assert out["total_shares"] == 1000000.0


def test_get_structure_no_match(fake_connector):
    repo = ShareStructureRepository(fake_connector)
    assert repo.get_structure(ReportKey(stock_code="999999")) is None


def test_list_structures(fake_connector):
    fake_connector.seed("share_structure", [
        {"company_name": "A", "stock_code": "000001",
         "report_year": 2024, "report_period": "FY", "total_shares": 200.0},
    ])
    repo = ShareStructureRepository(fake_connector)
    out = repo.list_structures(ReportKey(stock_code="000001", year=2024))
    assert len(out) == 1
    assert out[0]["total_shares"] == 200.0


def test_multi_year_structures_missing_years_absent(fake_connector):
    fake_connector.seed("share_structure", [
        {"company_name": "A", "stock_code": "000001",
         "report_year": 2022, "report_period": "FY", "total_shares": 100.0},
        {"company_name": "A", "stock_code": "000001",
         "report_year": 2024, "report_period": "FY", "total_shares": 300.0},
    ])
    repo = ShareStructureRepository(fake_connector)
    out = repo.get_multi_year_structures(
        ReportKey(stock_code="000001", period="FY"),
        start_year=2021, end_year=2024,
    )
    assert set(out.keys()) == {2022, 2024}
