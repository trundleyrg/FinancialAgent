"""
测试使用duckdb-engine的DatabaseConnector
"""
import sys
import os
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.db_connector import get_db
from src.db.models import ReportPeriod
import tempfile

def test_duckdb_with_connector():
    # 使用临时文件作为DuckDB测试数据库
    temp_db_path = tempfile.mktemp(suffix='.duckdb')
    
    try:
        # 使用DatabaseConnector连接到DuckDB
        db = get_db(database_type='duckdb', database_url=temp_db_path)
        
        # 测试创建财务报告
        report_id = db.create_report(
            company_name="DuckDB测试公司",
            stock_code="000002",
            report_year=2024,
            report_period=ReportPeriod.FY,
            source_file="./duckdb_test.pdf"
        )
        print(f"创建报告 ID: {report_id}")

        # 测试批量创建指标
        metrics_data = [
            {"metric_name": "营业收入", "value": 2000000000, "unit": "元", "page_number": 10},
            {"metric_name": "净利润", "value": 300000000, "unit": "元", "page_number": 12},
        ]
        metric_ids = db.create_metrics_batch(report_id, metrics_data)
        print(f"创建指标 IDs: {metric_ids}")

        # 测试查询报告及指标
        report = db.get_report_with_metrics(report_id)
        if report:
            print(f"\n报告: {report.company_name} ({report.stock_code})")
            print(f"期间: {report.report_year} {report.report_period}")
        
        metrics = db.get_metrics_by_report(report_id)
        print(f"指标数量: {len(metrics)}")
        for metric in metrics:
            print(f"  - {metric.metric_name}: {metric.value} {metric.unit}")
        
        # 测试其他查询功能
        reports = db.list_reports(company_name="DuckDB测试")
        print(f"\n按公司名查询结果数量: {len(reports)}")
        
        company_list = db.get_all_companies()
        print(f"所有公司列表: {company_list}")
        
        years = db.get_company_report_years("000002")
        print(f"公司000002的报告年份: {years}")
        
        print("DuckDB DatabaseConnector功能测试通过！")
    finally:
        # 尝试清理临时文件
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except PermissionError:
                # 如果无法删除（可能因为文件被占用），跳过
                pass

if __name__ == "__main__":
    test_duckdb_with_connector()