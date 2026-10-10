"""回填 000423 share_structure 数据(2020-2023 新增,2024 修正)。

数据来源:各年年报「第七节 股份变动及股东情况」表 — 股份总数(本次变动后)。
- 2020/2021/2022: 654,021,537 股
- 2023: 643,976,824 股(注销 10,044,713 股回购股份)
- 2024: 643,976,824 股(无变动)

DB 现存 2024 total_shares=1,479,184,875 是脏数据(疑似 PDF 解析时把万股/股混淆),
本次一并修正。
"""
import sys
from pathlib import Path

sys.path.insert(0, '.')
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.db_connector import get_db

CORRECT_TOTAL_SHARES = {
    2020: 654_021_537,
    2021: 654_021_537,
    2022: 654_021_537,
    2023: 643_976_824,  # 注销 10,044,713 股回购股份
    2024: 643_976_824,  # 2024 年报 P60 表格 「股份总数(本次变动后)」
}

SOURCE = "年报P股份变动表-本次变动后股份总数"


def main():
    conn = get_db()._duckdb_conn
    company_name = "东阿阿胶股份有限公司"
    stock_code = "000423"

    # 1. 打印修复前状态
    print("=== 修复前 ===")
    for r in conn.execute(
        f"SELECT report_year, total_shares FROM share_structure "
        f"WHERE stock_code='{stock_code}' ORDER BY report_year"
    ).fetchall():
        print(f"  {r[0]}: {r[1]:,.0f}")

    # 2. 直接 SQL UPSERT
    print("\n=== 回填 / 修正 ===")
    for year, total_shares in CORRECT_TOTAL_SHARES.items():
        # DuckDB 没有原生 ON CONFLICT,先删后插
        conn.execute(
            "DELETE FROM share_structure "
            "WHERE stock_code=? AND report_year=? AND report_period='FY'",
            [stock_code, year],
        )
        conn.execute(
            """
            INSERT INTO share_structure
              (company_name, stock_code, report_year, report_period,
               total_shares, total_shares_ratio)
            VALUES (?, ?, ?, 'FY', ?, 100.0)
            """,
            [company_name, stock_code, year, float(total_shares)],
        )
        print(f"  {year}: → {total_shares:,.0f} (UPSERT)")

    # 3. 验证修复后
    print("\n=== 修复后 ===")
    for r in conn.execute(
        f"SELECT report_year, total_shares FROM share_structure "
        f"WHERE stock_code='{stock_code}' ORDER BY report_year"
    ).fetchall():
        print(f"  {r[0]}: {r[1]:,.0f}")

    # 4. 算一遍 payout_ratio 验证
    print("\n=== payout_ratio 重算 (用真实总股本) ===")
    for year in [2020, 2021, 2022, 2023, 2024]:
        shares = CORRECT_TOTAL_SHARES[year]
        # 当年所有 cash_per_10_shares 累加
        rows = conn.execute(
            "SELECT cash_per_10_shares FROM capital_change_events "
            "WHERE stock_code=? AND report_year=? AND report_period='FY' "
            "AND event_type='cash_dividend' AND cash_per_10_shares > 0",
            [stock_code, year],
        ).fetchall()
        cash_per_10_sum = sum(r[0] for r in rows)
        total_div = cash_per_10_sum / 10.0 * shares

        # 净利
        net_row = conn.execute(
            "SELECT net_profit FROM consolidated_income_statement "
            "WHERE stock_code=? AND report_year=? AND report_period='FY'",
            [stock_code, year],
        ).fetchone()
        net_profit = net_row[0] if net_row else 0

        ratio = total_div / net_profit * 100 if net_profit else 0
        n_events = len(rows)
        net_str = f"{net_profit/1e8:.2f}亿" if net_profit else "N/A"
        ratio_str = f"{ratio:.2f}%" if net_profit else "N/A"
        print(
            f"  {year}: {n_events} 笔, "
            f"cash/10股={cash_per_10_sum:.4f}, "
            f"派息={total_div/1e8:.2f}亿, "
            f"净利={net_str}, "
            f"派息率={ratio_str}"
        )


if __name__ == "__main__":
    main()