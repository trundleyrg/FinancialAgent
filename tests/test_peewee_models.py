"""
测试Peewee ORM模型定义
"""
import sys
import os
import tempfile
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.models import FinancialReport, FinancialMetric, ReportPeriod, db
from src.db.db_connector import DatabaseConnector
from peewee import SqliteDatabase

def test_models():
    # 使用DuckDB作为测试数据库
    # 创建临时的DuckDB文件
    temp_db_path = tempfile.mktemp(suffix='.duckdb')
    
    try:
        # 使用SQLite兼容模式连接到DuckDB文件（因为当前实现使用SQLite后端）
        test_db = SqliteDatabase(temp_db_path)
        db.initialize(test_db)
        
        # 创建表
        db.create_tables([FinancialReport, FinancialMetric])
        
        # 测试创建财务报告
        report = FinancialReport.create(
            company_name="测试公司",
            company_short_name="测试",
            stock_code="000001",
            report_year=2024,
            report_period=ReportPeriod.FY.value,
            shares_total=1000000.0,
            source_file="test.pdf"
        )
        print(f"创建报告: {report.id}, {report.company_name}")
        
        # 测试创建财务指标
        metric = FinancialMetric.create(
            report=report,
            metric_name="营业收入",
            value=1000000000.0,
            unit="元",
            page_number=10
        )
        print(f"创建指标: {metric.id}, {metric.metric_name}")
        
        # 测试查询
        found_report = FinancialReport.get(FinancialReport.id == report.id)
        print(f"查询报告: {found_report.company_name}")
        
        metrics = FinancialMetric.select().where(FinancialMetric.report_id == report.id)
        for m in metrics:
            print(f"查询指标: {m.metric_name} = {m.value} {m.unit}")
        
        print("所有测试通过！")
    finally:
        # 尝试清理临时文件
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except PermissionError:
                # 如果无法删除（可能因为文件被占用），跳过
                pass

if __name__ == "__main__":
    test_models()