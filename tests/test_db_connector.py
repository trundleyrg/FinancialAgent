"""
测试完整的DatabaseConnector功能
"""
import sys
import os
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.db_connector import get_db
from src.db.models import ReportPeriod

def test_database_connector():
    # 设置环境变量以使用SQLite进行测试
    os.environ['DATABASE'] = 'duckdb'  # 实际上会使用SQLite作为后备
    os.environ['DUCKDB_DB_PATH'] = ':memory:'  # 使用内存数据库进行测试
    
    # 获取数据库连接器
    db = get_db(database_type='duckdb')
    
    # 测试创建财务报告
    report_id = db.create_report(
        company_name="测试公司",
        stock_code="000001",
        report_year=2024,
        report_period=ReportPeriod.FY,
        source_file="./test.pdf"
    )
    print(f"创建报告 ID: {report_id}")

    # 测试批量创建指标
    metrics_data = [
        {"metric_name": "营业收入", "value": 1000000000, "unit": "元", "page_number": 10},
        {"metric_name": "净利润", "value": 150000000, "unit": "元", "page_number": 12},
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
    reports = db.list_reports(company_name="测试")
    print(f"\n按公司名查询结果数量: {len(reports)}")
    
    company_list = db.get_all_companies()
    print(f"所有公司列表: {company_list}")
    
    years = db.get_company_report_years("000001")
    print(f"公司000001的报告年份: {years}")
    
    print("DatabaseConnector功能测试通过！")

if __name__ == "__main__":
    test_database_connector()