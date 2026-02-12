import gradio as gr
import os
import sys
from typing import List, Dict

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 直接从src导入
from db.db_connector import get_db
from db.models import ReportPeriod


def get_available_tables():
    """
    获取可用的数据库表
    """
    try:
        db = get_db()
        
        # 获取所有公司信息
        companies = db.get_all_companies()
        
        # 转换为Gradio需要的格式
        company_choices = []
        for comp in companies:
            display_name = f"{comp['company_name']} ({comp['stock_code']})"
            value = comp['stock_code']
            company_choices.append((display_name, value))
        
        # 获取所有可能的年份
        all_years = set()
        for comp in companies:
            years = db.get_company_report_years(comp['stock_code'])
            all_years.update(years)
        
        year_choices = [(str(year), year) for year in sorted(list(all_years), reverse=True)]
        
        # 返回空值选项加上数据库中的选项
        if company_choices:
            return (
                [("请选择公司", "")] + company_choices,
                [("请选择年份", "")] + year_choices
            )
        else:
            # 如果没有数据，返回空选项
            return (
                [("暂无数据", "")],
                [("暂无数据", "")]
            )
    except Exception as e:
        print(f"获取数据库表信息时出错: {e}")
        return (
            [("数据库连接失败", "")],
            [("数据库连接失败", "")]
        )


def get_available_periods(stock_code: str, year: int):
    """
    获取指定公司和年份的可用报告周期
    """
    if not stock_code or not year:
        return [("请选择周期", "")]
    
    db = get_db()
    reports = db.list_reports(stock_code=stock_code, report_year=year)
    
    periods = []
    for report in reports:
        periods.append((report.report_period.value, report.report_period.value))
    
    if not periods:
        return [("无可用周期", "")]
    
    return [("请选择周期", "")] + periods


def query_financial_data(stock_code: str, year: int, period: str):
    """
    查询财务数据
    """
    if not stock_code or not year or not period:
        return "请选择所有查询条件"
    
    try:
        db = get_db()
        
        # 查询财务报告
        report = db.get_report_by_company("", stock_code, year, ReportPeriod(period))
        if not report:
            # 尝试通过代码查询
            reports = db.list_reports(stock_code=stock_code, report_year=year, report_period=ReportPeriod(period))
            if reports:
                report = reports[0]
        
        if not report:
            return f"未找到 {year}年{period} {stock_code} 的财务报告"
        
        # 查询相关财务指标
        metrics = db.get_metrics_by_report(report.id)
        
        if not metrics:
            return f"未找到 {year}年{period} {stock_code} 的财务指标数据"
        
        # 格式化输出
        result = f"## 财务报告信息\n"
        result += f"- 公司名称: {report.company_name}\n"
        result += f"- 股票代码: {report.stock_code}\n"
        result += f"- 报告年份: {report.report_year}\n"
        result += f"- 报告周期: {report.report_period.value}\n"
        result += f"- 创建时间: {report.created_at}\n\n"
        
        result += f"## 财务指标\n"
        for metric in metrics:
            result += f"- **{metric.metric_name}**: {metric.value:,.2f} {metric.unit}\n"
            if metric.source_context:
                result += f"  - 来源上下文: {metric.source_context[:100]}...\n"
            if metric.page_number:
                result += f"  - 页码: {metric.page_number}\n"
            result += "\n"
        
        return result
    
    except Exception as e:
        return f"查询过程中发生错误: {str(e)}"


def create_db_query_tab():
    """
    创建数据库查询界面
    """
    with gr.Tab("数据库查询"):
        gr.Markdown("## 财务数据查询")
        gr.Markdown("选择公司、年份和报告周期来查询财务数据")
        
        # 初始化选项
        initial_companies, initial_years = get_available_tables()
        
        with gr.Row():
            with gr.Column(scale=1):
                company_dropdown = gr.Dropdown(
                    choices=initial_companies,
                    value="",
                    label="选择公司"
                )
                
                year_dropdown = gr.Dropdown(
                    choices=initial_years,
                    value="",
                    label="选择年份"
                )
                
                period_dropdown = gr.Dropdown(
                    choices=[("请选择周期", "")],
                    value="",
                    label="选择报告周期"
                )
                
                query_btn = gr.Button("查询数据", variant="primary")
            
            with gr.Column(scale=2):
                result_output = gr.Markdown(
                    label="查询结果",
                    value="请选择查询条件并点击查询数据按钮"
                )
        
        def update_periods(stock_code, year):
            """
            根据选择的公司和年份更新周期选项
            """
            if stock_code and year:
                return gr.Dropdown(
                    choices=get_available_periods(stock_code, int(year))
                )
            else:
                return gr.Dropdown(
                    choices=[("请选择周期", "")]
                )
        
        # 当公司或年份改变时更新周期选项
        company_dropdown.change(
            fn=update_periods,
            inputs=[company_dropdown, year_dropdown],
            outputs=[period_dropdown]
        )
        
        year_dropdown.change(
            fn=update_periods,
            inputs=[company_dropdown, year_dropdown],
            outputs=[period_dropdown]
        )
        
        # 查询按钮事件
        query_btn.click(
            fn=query_financial_data,
            inputs=[company_dropdown, year_dropdown, period_dropdown],
            outputs=[result_output]
        )
        
        # 刷新按钮，重新获取数据库中的选项
        with gr.Row():
            refresh_btn = gr.Button("刷新数据", variant="secondary")
            
            def refresh_data():
                companies, years = get_available_tables()
                return (
                    gr.Dropdown(choices=companies),
                    gr.Dropdown(choices=years),
                    gr.Dropdown(choices=[("请选择周期", "")])
                )
            
            refresh_btn.click(
                fn=refresh_data,
                inputs=[],
                outputs=[company_dropdown, year_dropdown, period_dropdown]
            )


if __name__ == "__main__":
    with gr.Blocks(title="财务数据查询") as demo:
        create_db_query_tab()
    
    demo.launch(share=True)
