"""
程序入口，初始化 Agent 并运行
"""

import os
import re
from pathlib import Path
import fitz  # PyMuPDF

from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import get_db
from src.db.models import ReportPeriod
from src.db.db_connector import save_tables_to_db
from src.utils.logger import main_logger


def process_pdf_file(pdf_path: str):
    """
    处理单个 PDF 文件
    :param pdf_path: PDF 文件路径
    """
    # 初始化数据库表
    db = get_db()
    db.create_tables()

    filename = os.path.basename(pdf_path)
    main_logger.info(f"正在处理文件: {filename}")

    try:
        # 使用 PDFChapterExtractor 提取主要表格
        extractor = PDFChapterExtractor(pdf_path)

        # 从PDF第一页提取公司名称、公司代码和年份
        company_name, company_short_name, company_code, report_year, report_period = (
            extractor.get_company_info()
        )

        main_logger.info(
            f"公司名称: {company_name}, 公司代码: {company_code}, 公司简称： {company_short_name}, 年份: {report_year}, 期间: {report_period}"
        )

        main_tables = extractor.extract_main_tables()

        # 保存为excel
        excel_base_dir = f"./data/excel/{company_short_name}_{report_year}"
        os.makedirs(excel_base_dir, exist_ok=True)

        for table_name, table_obj in main_tables.items():
            if table_obj is None or not table_obj.table_data:
                continue

            # 清理文件名中的非法字符
            safe_table_name = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            excel_path = os.path.join(excel_base_dir, f"{safe_table_name}.xlsx")

            # 使用 pandas 导出为 Excel
            import pandas as pd

            df = pd.DataFrame(table_obj.table_data)
            df.to_excel(excel_path, index=False, header=False)
            main_logger.info(f"表格 {table_name} 已保存到 {excel_path}")

        # 保存表格数据到 DuckDB
        save_tables_to_db(
            main_tables=main_tables,
            company_name=company_name,
            pdf_path=pdf_path,
            company_short_name=company_short_name,
            company_code=company_code,
            report_year=report_year,
            report_period=report_period,
            stock_code=company_code,
            db_connector=db,
        )

        main_logger.info(f"已成功处理并保存: {filename}")
    except Exception as e:
        main_logger.error(f"处理文件 {filename} 时出错: {str(e)}")
        raise
    finally:
        extractor.close()


def main():
    """
    主函数：处理 data/raw_pdfs 目录下的所有 PDF 文件
    """
    main_logger.info("开始处理 PDF 文件...")

    pdf_dir = Path("data/000423")
    pdf_files = list(pdf_dir.glob("*.pdf"))
    # pdf_files = list(pdf_dir.glob("*2022*.pdf"))
    main_logger.info(f"找到 {len(pdf_files)} 个 PDF 文件")

    # 依次处理每个 PDF 文件
    for pdf_file in pdf_files:
        try:
            process_pdf_file(str(pdf_file))
        except Exception as e:
            main_logger.error(f"处理文件 {pdf_file} 时发生未预期错误: {str(e)}")
            raise

    main_logger.info("PDF 文件处理完成！")


if __name__ == "__main__":
    main()
