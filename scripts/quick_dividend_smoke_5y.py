"""近五年红利股分析 smoke test（用最新 2025 年报 + 近 5 年财务时间序列）。"""
import sys
import time
sys.path.insert(0, ".")

from src.utils.llm_client import AIClient
from src.skills.dividend.skill import run as dividend_run
from src.db.db_connector import get_db

client = AIClient({})
state = {
    "company_name": "东阿阿胶股份有限公司",
    "stock_code": "000423",
    "report_year": 2025,
    "report_period": "FY",
}
get_db()._duckdb_conn.execute(
    "DELETE FROM skill_analysis_results WHERE stock_code='000423' AND skill_name='dividend'"
)

t0 = time.time()
result = dividend_run(state, client.llm)
elapsed = time.time() - t0
print(f"耗时 {elapsed:.1f}s", flush=True)
print(f"error_msg: {result.get('error_msg')}", flush=True)

a = result.get("dividend_analysis") or {}
print()
print("=== 产出 ===", flush=True)
for k in (
    "investment_rating", "financial_health_score", "payout_ratio",
    "dividend_stability_years", "cash_flow_coverage",
):
    print(f"  {k}: {a.get(k)!r}", flush=True)
reasoning = a.get("reasoning") or ""
print(f"  reasoning (last 300): ...{reasoning[-300:]!r}", flush=True)

print()
print("=== DB ===", flush=True)
row = get_db()._duckdb_conn.execute(
    """
    SELECT id, investment_rating,
           json_extract_string(input_context, '$.multi_year_raw') IS NOT NULL AS has_multiyear,
           json_extract_string(input_context, '$.analysis_metrics.dividend_info.payout_ratio') AS payout,
           created_at
    FROM skill_analysis_results
    WHERE stock_code='000423' AND skill_name='dividend'
    ORDER BY id DESC LIMIT 1
    """
).fetchone()
if row:
    print(f"  id={row[0]} rating={row[1]!r} has_multiyear={bool(row[2])} payout={row[3]!r}", flush=True)
    print(f"  created_at={row[4]}", flush=True)
else:
    print("  no row", flush=True)
