"""Quick smoke test of dividend skill with real MiniMax LLM."""
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
    "report_year": 2024,
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
print(f"result keys: {list(result.keys())}", flush=True)
print(f"dividend_analysis type: {type(result.get('dividend_analysis'))}", flush=True)

a = result.get("dividend_analysis")
if a:
    print(f"dividend_analysis is dict with keys: {list(a.keys()) if isinstance(a, dict) else 'NOT A DICT'}", flush=True)
else:
    print(f"dividend_analysis falsy: {a!r}", flush=True)
    a = {}

print()
print("=== 产出 ===", flush=True)
print(f"  investment_rating: {a.get('investment_rating')!r}", flush=True)
print(f"  financial_health_score: {a.get('financial_health_score')!r}", flush=True)
print(f"  payout_ratio: {a.get('payout_ratio')!r}", flush=True)
print(f"  dividend_stability_years: {a.get('dividend_stability_years')!r}", flush=True)
print(f"  cash_flow_coverage: {a.get('cash_flow_coverage')!r}", flush=True)
print(f"  reasoning 末 80: ...{(a.get('reasoning') or '')[-80:]!r}", flush=True)

print()
print("=== DB ===")
row = get_db()._duckdb_conn.execute(
    """
    SELECT id, investment_rating,
           json_extract_string(input_context, '$.analysis_metrics.dividend_info.payout_ratio') AS payout
    FROM skill_analysis_results
    WHERE stock_code='000423' AND skill_name='dividend'
    ORDER BY id DESC LIMIT 1
    """
).fetchone()
print(f"  id={row[0]} rating={row[1]} payout={row[2]}")