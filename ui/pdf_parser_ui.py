import gradio as gr
import os
import io
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import get_db, save_tables_to_db
from src.db.table_models import TableWithHeader
from src.utils.logger import ui_logger


def table_to_dataframe(table_data: List[List[str]]) -> pd.DataFrame:
    """将表格数据转换为 DataFrame"""
    if not table_data or len(table_data) < 1:
        return pd.DataFrame()
    
    # 使用第一行作为表头
    headers = table_data[0] if table_data else []
    data = table_data[1:] if len(table_data) > 1 else []
    
    # 确保所有行的列数一致
    max_cols = len(headers)
    normalized_data = []
    for row in data:
        if len(row) < max_cols:
            row = row + [''] * (max_cols - len(row))
        elif len(row) > max_cols:
            row = row[:max_cols]
        normalized_data.append(row)
    
    return pd.DataFrame(normalized_data, columns=headers)


def dataframe_to_excel_bytes(df: pd.DataFrame, table_name: str) -> bytes:
    """将 DataFrame 转换为 Excel 字节流"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=table_name[:31], index=False)
    output.seek(0)
    return output.getvalue()


def process_pdf(pdf_file, db_type: str = "duckdb"):
    """
    处理上传的PDF文件，提取财务报表并保存到数据库
    
    Returns:
        tuple: (处理结果消息, 公司信息, 表格列表, 下载文件列表)
    """
    if not pdf_file:
        return "请上传一个PDF文件", "", [], []
    
    extractor = None
    
    try:
        file_path = pdf_file.name
        filename = os.path.basename(file_path)
        ui_logger.info(f"开始处理PDF文件: {filename}")
        
        # 初始化数据库
        db = get_db(database_type=db_type)
        db.create_tables()
        
        # 创建 PDFChapterExtractor 实例
        extractor = PDFChapterExtractor(file_path)
        
        # 从PDF第一页提取公司信息
        company_name, company_short_name, company_code, report_year, report_period = extractor.get_company_info()
        
        ui_logger.info(f"公司信息: {company_name}, 代码: {company_code}, 年份: {report_year}, 期间: {report_period}")
        
        # 提取主要财务报表
        main_tables = extractor.extract_main_tables()
        
        # 过滤出有数据的表格
        valid_tables = {name: table for name, table in main_tables.items() if table is not None}
        
        if not valid_tables:
            return f"未在 {filename} 中找到主要财务报表", "", [], []
        
        # 保存表格数据到数据库
        saved_ids = save_tables_to_db(
            main_tables=main_tables,
            company_name=company_name,
            pdf_path=file_path,
            company_short_name=company_short_name,
            company_code=company_code,
            report_year=report_year,
            report_period=report_period,
            stock_code=company_code,
            db_connector=db
        )
        
        # 准备公司信息文本
        company_info = f"""公司名称: {company_name}
公司简称: {company_short_name}
股票代码: {company_code}
报告年份: {report_year}
报告期间: {report_period if report_period else 'FY'}
提取表格数: {len(valid_tables)}
保存记录ID: {saved_ids}"""
        
        # 准备表格列表（用于显示）
        table_list = []
        download_files = []
        
        for table_name, table_obj in valid_tables.items():
            if table_obj is None or not table_obj.table_data:
                continue
            
            # 转换为 DataFrame
            df = table_to_dataframe(table_obj.table_data)
            
            # 添加到表格列表
            table_list.append({
                "表格名称": table_name,
                "行数": len(table_obj.table_data),
                "列数": len(table_obj.table_data[0]) if table_obj.table_data else 0,
                "页码": f"{table_obj.page_start_num + 1}-{table_obj.page_end_num + 1}"
            })
            
            # 生成 Excel 文件
            excel_bytes = dataframe_to_excel_bytes(df, table_name)
            safe_name = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            download_files.append((f"{safe_name}.xlsx", excel_bytes))
        
        success_msg = f"✅ PDF处理成功！文件: {filename}\n成功提取 {len(valid_tables)} 个财务报表并已保存到数据库。"
        
        ui_logger.info(f"PDF处理完成: {filename}, 提取 {len(valid_tables)} 个表格")
        
        return success_msg, company_info, table_list, download_files
        
    except Exception as e:
        error_msg = f"❌ 处理PDF时发生错误: {str(e)}"
        ui_logger.error(error_msg)
        return error_msg, str(e), [], []
        
    finally:
        if extractor:
            extractor.close()


def create_pdf_parser_tab():
    """
    创建PDF解析界面
    """
    with gr.Tab("PDF财务报表解析"):
        gr.Markdown("## 📄 PDF财务报告上传与解析")
        gr.Markdown("上传PDF财务报告文件，系统将自动提取主要财务报表（资产负债表、利润表、现金流量表）并保存到数据库")
        
        # 用于存储下载文件的 State
        download_files_state = gr.State([])
        
        with gr.Row():
            with gr.Column(scale=1):
                # 数据库类型选择
                db_type = gr.Radio(
                    # choices=["duckdb", "postgresql"],
                    choices=["duckdb"],
                    value="duckdb",
                    label="数据库类型"
                )
                
                # PDF文件上传
                pdf_input = gr.File(
                    label="上传PDF文件",
                    file_types=[".pdf"],
                    file_count="single"
                )
                
                process_btn = gr.Button("开始解析", variant="primary", size="lg")
                
                # 处理结果显示
                result_text = gr.Textbox(
                    label="处理结果",
                    interactive=False,
                    max_lines=5,
                    lines=3
                )
            
            with gr.Column(scale=2):
                # 公司信息
                company_info = gr.Textbox(
                    label="公司信息",
                    interactive=False,
                    max_lines=8,
                    lines=6
                )
        
        # 提取的表格列表
        gr.Markdown("### 📊 提取的财务报表列表")
        tables_output = gr.Dataframe(
            headers=["表格名称", "行数", "列数", "页码"],
            label="财务报表列表",
            interactive=False
        )
        
        # Excel 下载区域
        gr.Markdown("### ⬇️ 下载Excel文件")
        gr.Markdown("点击下方按钮下载各个报表的Excel文件")
        
        with gr.Row():
            # 动态生成下载按钮
            download_btn_1 = gr.DownloadButton("下载: 合并资产负债表", visible=False)
            download_btn_2 = gr.DownloadButton("下载: 母公司资产负债表", visible=False)
            download_btn_3 = gr.DownloadButton("下载: 合并利润表", visible=False)
            download_btn_4 = gr.DownloadButton("下载: 母公司利润表", visible=False)
            download_btn_5 = gr.DownloadButton("下载: 合并现金流量表", visible=False)
            download_btn_6 = gr.DownloadButton("下载: 母公司现金流量表", visible=False)
        
        download_buttons = [download_btn_1, download_btn_2, download_btn_3, 
                           download_btn_4, download_btn_5, download_btn_6]
        
        def update_download_buttons(file_list):
            """根据提取的表格更新下载按钮"""
            updates = []
            for i, btn in enumerate(download_buttons):
                if i < len(file_list):
                    filename, file_bytes = file_list[i]
                    # 从文件名提取表格名称
                    table_name = filename.replace(".xlsx", "").replace("_", "")
                    updates.append({
                        "visible": True,
                        "value": (filename, file_bytes),
                        "label": f"下载: {table_name}"
                    })
                else:
                    updates.append({"visible": False})
            return updates
        
        # 处理按钮点击事件
        def on_process(pdf_file, db_type_val):
            result_msg, company_txt, table_list, download_files = process_pdf(pdf_file, db_type_val)
            
            # 更新下载按钮
            button_updates = update_download_buttons(download_files)
            
            return [result_msg, company_txt, table_list, download_files] + button_updates
        
        process_btn.click(
            fn=on_process,
            inputs=[pdf_input, db_type],
            outputs=[result_text, company_info, tables_output, download_files_state] + download_buttons
        )