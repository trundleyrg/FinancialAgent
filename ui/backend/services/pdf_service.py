"""
PDF处理服务
"""
import os
import uuid
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import get_db, save_tables_to_db
from src.db.table_models import TableWithHeader
from src.utils.logger import ui_logger


@dataclass
class TableData:
    """表格数据"""
    table_name: str
    table_data: List[List[str]]
    row_count: int
    col_count: int
    page_range: str
    unit: str
    column_units: Dict[int, str]


class PDFService:
    """PDF处理服务"""

    def __init__(self, db_type: str = "duckdb"):
        self.db_type = db_type
        self.temp_dir = None

    def _create_temp_dir(self) -> Path:
        """创建临时目录"""
        temp_base_dir = Path("./data/temp").resolve()
        temp_base_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = temp_base_dir / f"pdf_service_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def _table_to_dataframe(self, table_data: List[List[str]]) -> pd.DataFrame:
        """将表格数据转换为DataFrame"""
        if not table_data or len(table_data) < 1:
            return pd.DataFrame()

        headers = table_data[0] if table_data else []
        data = table_data[1:] if len(table_data) > 1 else []

        max_cols = len(headers)
        normalized_data = []
        for row in data:
            if len(row) < max_cols:
                row = row + [''] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            normalized_data.append(row)

        return pd.DataFrame(normalized_data, columns=headers)

    def _save_table_to_excel(self, table_name: str, table_data: List[List[str]], temp_dir: Path) -> Path:
        """保存表格为Excel文件"""
        df = self._table_to_dataframe(table_data)
        safe_name = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        file_path = temp_dir / f"{safe_name}.xlsx"

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=table_name[:31], index=False)

        return file_path

    def process_pdf(self, pdf_path: str) -> Tuple[bool, str, Optional[Dict], List[Dict], Dict, List[str]]:
        """
        处理PDF文件，提取财务报表并保存到数据库

        Returns:
            Tuple: (success, message, company_info, tables, saved_ids, download_urls)
        """
        extractor = None

        try:
            filename = os.path.basename(pdf_path)
            ui_logger.info(f"开始处理PDF文件: {filename}")

            # 创建临时目录
            self.temp_dir = self._create_temp_dir()

            # 初始化数据库
            db = get_db(database_type=self.db_type)
            db.create_tables()

            # 创建PDFChapterExtractor实例
            extractor = PDFChapterExtractor(pdf_path)

            # 提取公司信息
            company_name, company_short_name, company_code, report_year, report_period = extractor.get_company_info()

            ui_logger.info(f"公司信息: {company_name}, 代码: {company_code}, 年份: {report_year}, 期间: {report_period}")

            # 提取主要财务报表
            main_tables = extractor.extract_main_tables()

            # 过滤出有数据的表格
            valid_tables = {name: table for name, table in main_tables.items() if table is not None}

            if not valid_tables:
                return False, f"未在 {filename} 中找到主要财务报表", None, [], {}, []

            # 保存表格数据到数据库
            saved_ids = save_tables_to_db(
                main_tables=main_tables,
                company_name=company_name,
                pdf_path=pdf_path,
                company_short_name=company_short_name,
                company_code=company_code,
                report_year=report_year,
                report_period=report_period,
                stock_code=company_code,
                db_connector=db
            )

            # 准备公司信息
            company_info = {
                "company_name": company_name,
                "company_short_name": company_short_name,
                "stock_code": company_code,
                "report_year": report_year,
                "report_period": report_period if report_period else "FY"
            }

            # 准备表格列表和下载链接
            table_list = []
            download_urls = []

            for table_name, table_obj in valid_tables.items():
                if table_obj is None or not table_obj.table_data:
                    continue

                # 添加到表格列表
                table_list.append({
                    "table_name": table_name,
                    "row_count": len(table_obj.table_data),
                    "col_count": len(table_obj.table_data[0]) if table_obj.table_data else 0,
                    "page_range": f"{table_obj.page_start_num + 1}-{table_obj.page_end_num + 1}",
                    "unit": table_obj.unit,
                    "column_units": table_obj.column_units
                })

                # 保存Excel文件
                excel_path = self._save_table_to_excel(table_name, table_obj.table_data, self.temp_dir)
                download_urls.append(f"/api/files/{excel_path.name}")

            success_msg = f"PDF处理成功！文件: {filename}，成功提取 {len(valid_tables)} 个财务报表并已保存到数据库"

            ui_logger.info(f"PDF处理完成: {filename}, 提取 {len(valid_tables)} 个表格")

            return True, success_msg, company_info, table_list, saved_ids, download_urls

        except Exception as e:
            error_msg = f"处理PDF时发生错误: {str(e)}"
            ui_logger.error(error_msg)
            return False, error_msg, None, [], {}, []

        finally:
            if extractor:
                extractor.close()

    def get_table_data(self, table_name: str, company_name: str, report_year: int,
                       report_period: str = "FY") -> Optional[List[List[str]]]:
        """获取指定表格的数据"""
        try:
            db = get_db(database_type=self.db_type)
            table_type_map = {
                "合并资产负债表": "consolidated_balance_sheet",
                "母公司资产负债表": "parent_company_balance_sheet",
                "合并利润表": "consolidated_income_statement",
                "母公司利润表": "parent_company_income_statement",
                "合并现金流量表": "consolidated_cash_flow_statement",
                "母公司现金流量表": "parent_company_cash_flow_statement",
                "股份变动情况表": "share_structure",
            }

            table_type = table_type_map.get(table_name)
            if not table_type:
                return None

            records = db.filter_records(
                table_type,
                company_name=company_name,
                report_year=report_year,
                report_period=report_period
            )

            if not records:
                return None

            record = records[0]
            # 将记录转换为表格数据
            if hasattr(record, '__dict__'):
                data = record.__dict__
            elif hasattr(record, '_data'):
                data = record._data
            else:
                data = dict(record) if isinstance(record, dict) else {}

            # 移除内部字段
            for key in ['id', '_database', '_dirty', 'company_name', 'stock_code', 'report_year', 'report_period']:
                data.pop(key, None)

            # 构建表格数据
            table_data = []
            for field_name, value in data.items():
                if value is not None:
                    # 获取字段的帮助文本作为名称
                    help_text = field_name  # 简化处理
                    table_data.append([help_text, str(value)])

            return table_data

        except Exception as e:
            ui_logger.error(f"获取表格数据失败: {e}")
            return None
