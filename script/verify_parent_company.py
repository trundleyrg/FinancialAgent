"""Compare 东阿阿胶 parent-company tables between data/000423 PDFs and DuckDB.

Usage:
    DATABASE=duckdb DUCKDB_DB_PATH=./data/db/financial_data.duckdb \
        python script/verify_parent_company.py

Writes data/000423/parent_diff_report.json.
"""
import json
import os
from pathlib import Path

import duckdb

from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import _parse_table_data_to_model_data
from src.db.models import (
    ParentCompanyBalanceSheet,
    ParentCompanyIncomeStatement,
    ParentCompanyCashFlowStatement,
)

REPORT_TABLES = {
    "母公司资产负债表": (ParentCompanyBalanceSheet, "parent_company_balance_sheet"),
    "母公司利润表": (ParentCompanyIncomeStatement, "parent_company_income_statement"),
    "母公司现金流量表": (ParentCompanyCashFlowStatement, "parent_company_cash_flow_statement"),
}

TOLERANCE = 0.02


def _pdf_value(cells):
    raw = str(cells[1]).strip() if len(cells) > 1 else ""
    if not raw or raw in {"-", "—", "--"}:
        return None
    cleaned = raw.replace(",", "").replace("，", "").replace("元", "")
    if "(" in cleaned and ")" in cleaned:
        cleaned = "-" + cleaned.replace("(", "").replace(")", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


# Labels that map to the period-split field for ParentCompanyBalanceSheet,
# distinguishing the period-flow value from the year-end value.
PARENT_PERIOD_SPLIT_LABELS = {
    "本期发生额-应付职工薪酬",
    "本期发生额应付职工薪酬",
}


def _resolve_field(model_class, label: str):
    field_map = {f.help_text: name for name, f in model_class._meta.fields.items()
                 if getattr(f, "help_text", None)}
    if label in PARENT_PERIOD_SPLIT_LABELS:
        return "employee_benefits_payable_current_period"
    if label in field_map:
        return field_map[label]
    return None


def _db_row(db_path: str, table_name: str, year: int):
    con = duckdb.connect(db_path, read_only=True)
    try:
        cols = [r[0] for r in con.execute(f"describe {table_name}").fetchall()]
        rows = con.execute(
            f"select * from {table_name} where report_year = ?", [year]
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return None
    return dict(zip(cols, rows[0]))


def _compare_year(year: int, pdf_path: str, db_path: str):
    extractor = PDFChapterExtractor(pdf_path)
    try:
        tables = extractor.extract_main_tables()
    finally:
        extractor.close()

    summary = {}
    differences = []
    for table_label, (model_class, db_table) in REPORT_TABLES.items():
        table_obj = tables.get(table_label)
        if table_obj is None or not table_obj.table_data or len(table_obj.table_data) < 2:
            summary[table_label] = {
                "matched": 0,
                "mismatched": 0,
                "missing_in_db": 0,
                "unmatched_rows": 0,
                "skipped": "table not extracted",
            }
            continue

        db_row = _db_row(db_path, db_table, year) or {}
        matched = mismatched = missing = unmatched = 0
        for idx in range(1, len(table_obj.table_data)):
            cells = table_obj.table_data[idx]
            if not cells:
                continue
            label = str(cells[0]).strip()
            field = _resolve_field(model_class, label)
            if not field:
                unmatched += 1
                continue
            pdf_val = _pdf_value(cells)
            db_val = db_row.get(field)
            if pdf_val is None and db_val is None:
                matched += 1
                continue
            if db_val is None:
                missing += 1
                continue
            if pdf_val is None:
                continue
            if abs(pdf_val - float(db_val)) <= TOLERANCE:
                matched += 1
            else:
                mismatched += 1
                differences.append(
                    {
                        "year": year,
                        "table": table_label,
                        "field": field,
                        "pdf_value": pdf_val,
                        "db_value": float(db_val),
                    }
                )
        summary[table_label] = {
            "matched": matched,
            "mismatched": mismatched,
            "missing_in_db": missing,
            "unmatched_rows": unmatched,
        }
    return summary, differences


def main():
    db_path = os.environ.get("DUCKDB_DB_PATH", "./data/db/financial_data.duckdb")
    pdf_dir = Path("data/000423")
    report = {"summary": {}, "differences": []}
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        year = int(pdf.stem.split("_")[-1])
        summary, diffs = _compare_year(year, str(pdf), db_path)
        report["summary"][year] = summary
        report["differences"].extend(diffs)
    out = Path("data/000423/parent_diff_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report written to {out}")
    for year, summary in report["summary"].items():
        for table, stats in summary.items():
            print(year, table, stats)


if __name__ == "__main__":
    main()