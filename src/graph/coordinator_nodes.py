"""
协调器节点函数

定义 PDF 解析、数据提取、数据库保存等协调器节点
这些节点负责同步操作，调用具体工具完成工作
"""

from typing import Callable, Dict, Any
import logging

from src.graph.state import FinancialState
from src.agents.tools.db_tools import check_company_data_availability
from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import get_db

logger = logging.getLogger("Agent.Coordinator")


def create_check_data_availability_node(years: int = 10) -> Callable:
    """
    创建数据可用性检查节点

    Args:
        years: 检查近 N 年的数据，默认 10 年

    Returns:
        检查数据可用性的节点函数
    """

    def check_data_availability_node(state: FinancialState) -> FinancialState:
        """
        检查数据可用性节点

        检查数据库中是否存在该公司近 N 年的数据
        """
        company_name = state.get("company_name")
        stock_code = state.get("stock_code")

        if not company_name:
            logger.error("缺少公司名称，无法检查数据可用性")
            return {
                "status": "error",
                "error_msg": "缺少公司名称"
            }

        logger.info(f"检查数据可用性: {company_name} ({stock_code}), 近 {years} 年")

        try:
            # 调用数据检查工具
            result = check_company_data_availability(
                company_name=company_name,
                stock_code=stock_code,
                years=years
            )

            has_data = result.get("has_data", False)
            data_coverage = result.get("data_coverage", 0)
            available_years = result.get("available_years", [])

            logger.info(f"数据可用性检查完成: has_data={has_data}, coverage={data_coverage:.0%}, 可用年份={available_years}")

            return {
                "data_availability": result,
                "status": "processing"
            }

        except Exception as e:
            logger.error(f"检查数据可用性失败: {e}")
            return {
                "data_availability": {
                    "has_data": False,
                    "error": str(e)
                },
                "status": "processing"  # 继续执行，让后续节点处理
            }

    return check_data_availability_node


def create_parse_pdf_node() -> Callable:
    """
    创建 PDF 解析节点

    Returns:
        解析 PDF 的节点函数
    """

    def parse_pdf_node(state: FinancialState) -> FinancialState:
        """
        解析 PDF 节点

        使用 PDFChapterExtractor 解析 PDF，提取：
        - 公司信息（名称、代码、年份、周期）
        - 原始文本内容
        """
        pdf_path = state.get("pdf_path")

        if not pdf_path:
            logger.error("缺少 PDF 路径")
            return {
                "status": "error",
                "error_msg": "缺少 PDF 路径"
            }

        logger.info(f"开始解析 PDF: {pdf_path}")

        try:
            extractor = PDFChapterExtractor(pdf_path)

            # 提取公司信息
            company_name, company_short_name, stock_code, report_year, report_period = \
                extractor.get_company_info()

            # 提取所有章节内容
            raw_content = extractor.extract_all_chapters()

            extractor.close()

            logger.info(f"PDF 解析完成: {company_name} ({stock_code}) {report_year} {report_period}")

            return {
                "raw_markdown": str(raw_content),
                "company_name": company_name,
                "company_short_name": company_short_name,
                "stock_code": stock_code,
                "report_year": report_year,
                "report_period": report_period,
                "status": "processing"
            }

        except Exception as e:
            logger.error(f"PDF 解析失败: {e}")
            return {
                "status": "error",
                "error_msg": f"PDF 解析失败: {str(e)}"
            }

    return parse_pdf_node


def create_extract_financial_data_node() -> Callable:
    """
    创建财务数据提取节点

    Returns:
        提取财务数据的节点函数
    """

    def extract_financial_data_node(state: FinancialState) -> FinancialState:
        """
        提取财务数据节点

        使用 PDFChapterExtractor 提取三大主表结构化数据
        """
        pdf_path = state.get("pdf_path")

        if not pdf_path:
            logger.error("缺少 PDF 路径")
            return {
                "status": "error",
                "error_msg": "缺少 PDF 路径"
            }

        logger.info("开始提取财务数据")

        try:
            extractor = PDFChapterExtractor(pdf_path)

            # 提取主要财务报表
            main_tables = extractor.extract_main_tables()

            extractor.close()

            # 将 TableWithHeader 转换为字典列表
            structured_data = []
            for table_name, table in main_tables.items():
                structured_data.append({
                    "table_name": table_name,
                    "table_data": table.table_data,
                    "header_text": table.header_text,
                    "page_start_num": table.page_start_num,
                    "page_end_num": table.page_end_num,
                    "unit": table.unit,
                    "currency": table.currency
                })

            logger.info(f"财务数据提取完成，共 {len(structured_data)} 个表格")

            return {
                "structured_data": structured_data,
                "status": "processing"
            }

        except Exception as e:
            logger.error(f"财务数据提取失败: {e}")
            return {
                "status": "error",
                "error_msg": f"财务数据提取失败: {str(e)}"
            }

    return extract_financial_data_node


def create_save_to_database_node() -> Callable:
    """
    创建数据库保存节点

    Returns:
        保存数据到数据库的节点函数
    """

    def save_to_database_node(state: FinancialState) -> FinancialState:
        """
        保存到数据库节点

        将提取的财务数据保存到数据库
        """
        company_name = state.get("company_name")
        company_short_name = state.get("company_short_name")
        stock_code = state.get("stock_code")
        report_year = state.get("report_year")
        report_period = state.get("report_period")
        structured_data = state.get("structured_data", [])
        pdf_path = state.get("pdf_path")

        if not company_name or not report_year:
            logger.error("缺少公司信息，无法保存")
            return {
                "status": "error",
                "error_msg": "缺少公司信息"
            }

        logger.info(f"开始保存数据到数据库: {company_name} {report_year} {report_period}")

        try:
            db = get_db()

            # 创建财务报告记录
            report_id = db.create_report(
                company_name=company_name,
                company_short_name=company_short_name or "",
                stock_code=stock_code or "",
                report_year=report_year,
                report_period=report_period or "",
                source_file=pdf_path
            )

            # 保存每个表格的数据
            for table_info in structured_data:
                table_name = table_info.get("table_name")
                table_data = table_info.get("table_data", [])

                if table_name and table_data:
                    db.save_financial_table(
                        report_id=report_id,
                        table_name=table_name,
                        table_data=table_data,
                        unit=table_info.get("unit", ""),
                        currency=table_info.get("currency", "")
                    )

            logger.info(f"数据保存完成，记录 ID: {report_id}")

            return {
                "record_id": report_id,
                "status": "processing"
            }

        except Exception as e:
            logger.error(f"数据保存失败: {e}")
            return {
                "status": "error",
                "error_msg": f"数据保存失败: {str(e)}"
            }

    return save_to_database_node


def get_coordinator_nodes() -> Dict[str, Callable]:
    """
    获取所有协调器节点

    Returns:
        协调器节点字典
    """
    return {
        "check_data_availability": create_check_data_availability_node(),
        "parse_pdf": create_parse_pdf_node(),
        "extract_financial_data": create_extract_financial_data_node(),
        "save_to_database": create_save_to_database_node()
    }
