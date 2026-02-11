"""
table_data_saver.py
将从 PDF 提取的表格数据保存到 DuckDB 数据库中
"""

import duckdb
from typing import List, Dict, Any, Optional
from src.utils.logger import db_logger
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class TableDataSaver:
    """用于将表格数据保存到 DuckDB 的工具类"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库连接
        :param db_path: DuckDB 数据库文件路径，默认从环境变量获取
        """
        if db_path is None:
            db_path = os.getenv("DUCKDB_DB_PATH", "./data/db/financial_data.duckdb")
        
        self.db_path = db_path
        self.conn = duckdb.connect(self.db_path)
        self._create_tables()
    
    def _create_tables(self):
        """创建表格数据存储表"""
        # 创建财务报表主表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS extracted_tables (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                table_name VARCHAR,
                header_text VARCHAR,
                page_start INTEGER,
                page_end INTEGER,
                is_merged BOOLEAN,
                company_name VARCHAR,
                report_year INTEGER,
                report_period VARCHAR,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建表格数据详情表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS table_data (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                table_id INTEGER,
                row_index INTEGER,
                col_index INTEGER,
                cell_value VARCHAR,
                FOREIGN KEY (table_id) REFERENCES extracted_tables(id)
            )
        """)
        
        db_logger.info("表格数据存储表创建完成")
    
    def save_extracted_tables(self, main_tables: Dict[str, Any], company_name: str, report_year: int, report_period: str):
        """
        保存提取的表格数据到数据库
        :param main_tables: 从 extract_main_tables 返回的表格字典
        :param company_name: 公司名称
        :param report_year: 报告年份
        :param report_period: 报告期间
        """
        for table_name, table_obj in main_tables.items():
            if table_obj is None:
                db_logger.info(f"跳过空表格: {table_name}")
                continue
                
            # 插入表格主记录
            table_id = self.conn.execute("""
                INSERT INTO extracted_tables 
                (table_name, header_text, page_start, page_end, is_merged, company_name, report_year, report_period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, [
                table_name,
                table_obj.header_text,
                table_obj.page_start_num,
                table_obj.page_end_num,
                table_obj.is_merged,
                company_name,
                report_year,
                report_period
            ]).fetchone()[0]
            
            # 插入表格数据
            for row_idx, row_data in enumerate(table_obj.table_data):
                for col_idx, cell_value in enumerate(row_data):
                    self.conn.execute("""
                        INSERT INTO table_data 
                        (table_id, row_index, col_index, cell_value)
                        VALUES (?, ?, ?, ?)
                    """, [table_id, row_idx, col_idx, str(cell_value)])
            
            db_logger.info(f"已保存表格数据: {table_name}, ID: {table_id}, 共 {len(table_obj.table_data)} 行")
    
    def get_table_by_name(self, table_name: str, company_name: str, report_year: int, report_period: str) -> List[Dict[str, Any]]:
        """
        根据名称获取表格数据
        :param table_name: 表格名称
        :param company_name: 公司名称
        :param report_year: 报告年份
        :param report_period: 报告期间
        :return: 表格数据列表
        """
        result = self.conn.execute("""
            SELECT et.*, td.row_index, td.col_index, td.cell_value
            FROM extracted_tables et
            JOIN table_data td ON et.id = td.table_id
            WHERE et.table_name = ? AND et.company_name = ? AND et.report_year = ? AND et.report_period = ?
            ORDER BY td.table_id, td.row_index, td.col_index
        """, [table_name, company_name, report_year, report_period]).fetchall()
        
        # 将结果转换为二维表格格式
        table_data = {}
        for row in result:
            table_id = row[0]
            if table_id not in table_data:
                table_data[table_id] = {
                    'table_info': {
                        'id': row[0],
                        'table_name': row[1],
                        'header_text': row[2],
                        'page_start': row[3],
                        'page_end': row[4],
                        'is_merged': row[5],
                        'company_name': row[6],
                        'report_year': row[7],
                        'report_period': row[8],
                        'extracted_at': row[9]
                    },
                    'data': []
                }
            
            # 计算需要扩展的行数
            row_idx = row[10]
            col_idx = row[11]
            cell_value = row[12]
            
            # 确保有足够的行
            while len(table_data[table_id]['data']) <= row_idx:
                table_data[table_id]['data'].append([])
            
            # 确保有足够的列
            while len(table_data[table_id]['data'][row_idx]) <= col_idx:
                table_data[table_id]['data'][row_idx].append(None)
            
            table_data[table_id]['data'][row_idx][col_idx] = cell_value
        
        return [table_info for table_info in table_data.values()]
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            db_logger.info("数据库连接已关闭")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


def save_tables_to_db(main_tables: Dict[str, Any], company_name: str, report_year: int, report_period: str, db_path: Optional[str] = None):
    """
    便捷函数：将提取的表格数据保存到数据库
    :param main_tables: 从 extract_main_tables 返回的表格字典
    :param company_name: 公司名称
    :param report_year: 报告年份
    :param report_period: 报告期间
    :param db_path: DuckDB 数据库路径
    """
    with TableDataSaver(db_path) as saver:
        saver.save_extracted_tables(main_tables, company_name, report_year, report_period)