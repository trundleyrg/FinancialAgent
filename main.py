"""
FinancialAgent 统一入口

支持完整流程:
  1. download — 从巨潮资讯网下载指定股票的年度报告 PDF
  2. parse    — 用 PDFChapterExtractor 提取主要财务表格
  3. persist  — 写入 DuckDB(consolidated_balance_sheet / income_statement / cash_flow_statement / share_structure)
  4. dividend — 跑红利股分析,产出 markdown 报告 + CSV 趋势 + 负债结构图

命令:
  python main.py download <code> [year ...]       只下载
  python main.py parse <pdf_path>                  只解析
  python main.py analyze <code> [year]            跑红利分析(假设已入库)
  python main.py run <code> [year ...]            完整流程 download→parse→analyze
  python main.py batch <file>                     批量处理(file 每行: code year)

默认参数:
  code = 600285    羚锐制药
  year = 2024
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd

from src.db.db_connector import get_db, save_tables_to_db
from src.skills.dividend.skill import run as run_dividend_skill
from src.tools.chapter_extractor import PDFChapterExtractor
from src.tools.download_cninfo_reports import CNInfoReportDownloader
from src.utils.llm_client import AIClient
from src.utils.logger import main_logger

# 默认 demo 数据(以 600285 羚锐制药 2024 年报为参考流程)
DEFAULT_CODE = "600285"
DEFAULT_YEAR = 2024


def download_annual_reports(stock_code: str, years: list[int]) -> list[Path]:
    """Step 1:从巨潮下载年报 PDF,保存到 data/{stock_code}/。

    返回已成功下载的 PDF 路径列表(本地已有的也一并返回)。
    """
    main_logger.info("=" * 70)
    main_logger.info("Step 1 / Download annual reports")
    main_logger.info("=" * 70)
    main_logger.info("stock=%s, years=%s", stock_code, years)

    pdf_dir = Path("data") / stock_code
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # 本地已有 PDF:复用(避免重复下载)
    local_pdfs = list(pdf_dir.glob(f"*_{stock_code}_*.pdf"))
    expected_years = set(years)
    local_years = set()
    for p in local_pdfs:
        m = re.search(rf"{stock_code}_(\d{{4}})\.pdf", p.name)
        if m:
            local_years.add(int(m.group(1)))
    need_download = sorted(expected_years - local_years)
    main_logger.info("本地已有: %s, 还需下载: %s", sorted(local_years), need_download)

    if need_download:
        downloader = CNInfoReportDownloader()
        try:
            downloader.download_reports(stock_code, need_download)
        except Exception as exc:
            main_logger.warning("下载流程异常(可能网络问题):%s", exc)

    # 列出最终 PDF(本地 + 刚下载的)
    pdfs = sorted(pdf_dir.glob(f"*_{stock_code}_*.pdf"))
    main_logger.info("下载/本地共 %d 份 PDF: %s", len(pdfs), [p.name for p in pdfs])
    return pdfs


def parse_pdf_to_db(pdf_path: Path) -> dict[str, int]:
    """Step 2 + 3:解析 PDF,主要表格写入 DuckDB。

    Returns:
        {table_name: id} — 已保存到 DB 的记录 id 映射(合并资产负债表/利润表等)。
    """
    main_logger.info("=" * 70)
    main_logger.info("Step 2+3 / Parse PDF → DuckDB: %s", pdf_path.name)
    main_logger.info("=" * 70)

    db = get_db()
    db.create_tables()

    extractor = PDFChapterExtractor(str(pdf_path))
    try:
        company_name, company_short_name, company_code, report_year, report_period = (
            extractor.get_company_info()
        )
        main_logger.info(
            "公司: %s(%s), 报告期: %s %s",
            company_name, company_code, report_year, report_period,
        )

        main_tables = extractor.extract_main_tables()

        # 保存到 Excel(便于人工检查)
        excel_base = f"./data/excel/{company_short_name}_{report_year}"
        os.makedirs(excel_base, exist_ok=True)
        for table_name, table_obj in main_tables.items():
            if table_obj is None or not table_obj.table_data:
                continue
            safe = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            df = pd.DataFrame(table_obj.table_data)
            df.to_excel(os.path.join(excel_base, f"{safe}.xlsx"), index=False, header=False)

        # 写入 DB
        saved_ids = save_tables_to_db(
            main_tables=main_tables,
            company_name=company_name,
            pdf_path=str(pdf_path),
            company_short_name=company_short_name,
            company_code=company_code,
            report_year=report_year,
            report_period=report_period,
            stock_code=company_code,
            db_connector=db,
        )
        main_logger.info("入库完成,保存记录: %s", saved_ids)
        return saved_ids
    finally:
        extractor.close()


def run_dividend_analysis(
    stock_code: str,
    year: int,
    *,
    trend_years: int = 5,
    use_llm: bool = True,
) -> dict:
    """Step 4:跑红利股分析。

    use_llm=False 时跳过 LLM 调用,只用 code 算关键指标(快速冒烟)。
    """
    main_logger.info("=" * 70)
    main_logger.info("Step 4 / Dividend analysis: %s %s", stock_code, year)
    main_logger.info("=" * 70)

    # 从 DB 取公司名(优先 full_name,fallback 到 name column)
    db = get_db()
    row = db._duckdb_conn.execute(
        "SELECT company_name FROM consolidated_balance_sheet "
        "WHERE stock_code=? AND report_year=? AND report_period='FY' "
        "ORDER BY created_at DESC LIMIT 1",
        [stock_code, year],
    ).fetchone()
    company_name = row[0] if row else stock_code

    state = {
        "company_name": company_name,
        "company_short_name": company_name.split("股份有限公司")[0]
            if "股份有限公司" in company_name else company_name,
        "stock_code": stock_code,
        "business_scope": "",
        "report_year": year,
        "report_period": "FY",
        "stock_types": ["dividend"],
    }

    llm = None
    if use_llm:
        try:
            ai = AIClient({"TEMPERATURE": 0.7, "MAX_TOKENS": 16384})
            valid, err = ai.validate_config()
            if valid:
                llm = ai.llm
            else:
                main_logger.warning("LLM 配置无效(%s),将用 code-only 模式", err)
        except Exception as exc:
            main_logger.warning("LLM 初始化失败:%s", exc)

    try:
        delta = run_dividend_skill(state, llm=llm, trend_years=trend_years)
    except Exception as exc:
        main_logger.error("红利分析异常: %s", exc)
        return {"error_msg": str(exc)}

    if delta.get("error_msg"):
        main_logger.warning("skill 报错: %s", delta["error_msg"])
        return delta

    main_logger.info(
        "skill 完成: rating=%s, dividend_yield=%s, payout_ratio=%s",
        delta.get("dividend_analysis", {}).get("investment_rating"),
        delta.get("dividend_analysis", {}).get("dividend_yield"),
        delta.get("dividend_analysis", {}).get("payout_ratio"),
    )

    # 列出生成的报告文件
    memory_dir = Path("data") / stock_code / "memory"
    md_files = sorted(memory_dir.glob("分析报告_分红_*.md"))
    main_logger.info("分红报告文件: %s", [f.name for f in md_files])
    return delta


def full_pipeline(
    stock_code: str,
    years: list[int],
    *,
    trend_years: int = 5,
) -> None:
    """完整流程:download → parse → analyze。

    任何一步失败都不阻塞后续步骤(降级策略)。
    """
    pdfs = download_annual_reports(stock_code, years)

    for pdf_path in pdfs:
        try:
            parse_pdf_to_db(pdf_path)
        except Exception as exc:
            main_logger.error("解析/入库失败(%s): %s", pdf_path.name, exc)

    # 红利分析(对最新 year)
    if years:
        latest = max(years)
        run_dividend_analysis(stock_code, latest, trend_years=trend_years)


# ──────────────────────────────────────────────────────────────────────────────
# 命令分派
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        # 默认:600285 跑全流程
        main_logger.info("默认参数:stock=%s, year=%s", DEFAULT_CODE, DEFAULT_YEAR)
        full_pipeline(DEFAULT_CODE, [DEFAULT_YEAR])
        return

    cmd = sys.argv[1]

    if cmd == "download":
        # python main.py download 600285 2024 [2023]
        code = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CODE
        years = [int(y) for y in sys.argv[3:]] if len(sys.argv) > 3 else [DEFAULT_YEAR]
        download_annual_reports(code, years)

    elif cmd == "parse":
        # python main.py parse data/600285/xxx.pdf
        path = Path(sys.argv[2])
        parse_pdf_to_db(path)

    elif cmd == "analyze":
        # python main.py analyze 600285 2024
        code = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CODE
        year = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_YEAR
        run_dividend_analysis(code, year)

    elif cmd == "run":
        # python main.py run 600285 2024 2023
        code = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CODE
        years = [int(y) for y in sys.argv[3:]] if len(sys.argv) > 3 else [DEFAULT_YEAR]
        full_pipeline(code, years)

    elif cmd == "batch":
        # python main.py batch stocks.txt  (file 每行: code year)
        file = Path(sys.argv[2])
        for line in file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            code = parts[0]
            years = [int(p) for p in parts[1:]] if len(parts) > 1 else [DEFAULT_YEAR]
            try:
                full_pipeline(code, years)
            except Exception as exc:
                main_logger.error("批量 %s 失败:%s", code, exc)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
