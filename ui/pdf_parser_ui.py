import gradio as gr
import os
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


def save_dataframe_to_excel_file(df: pd.DataFrame, table_name: str, temp_dir: Path) -> Path:
    """将DataFrame保存为Excel文件到临时目录，返回文件路径"""
    safe_name = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    file_path = temp_dir / f"{safe_name}.xlsx"
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=table_name[:31], index=False)
    return file_path


def process_pdf(pdf_file, db_type: str = "duckdb"):
    """
    处理上传的PDF文件，提取财务报表并保存到数据库
    
    Returns:
        tuple: (处理结果消息, 公司信息, 表格列表, 下载文件路径列表)
    """
    if not pdf_file:
        return "请上传一个PDF文件", "", [], []
    
    extractor = None
    temp_dir = None
    
    try:
        file_path = pdf_file.name
        filename = os.path.basename(file_path)
        ui_logger.info(f"开始处理PDF文件: {filename}")
        
        # 创建临时文件夹（项目路径下的 data/temp 目录）
        import uuid
        temp_base_dir = Path("./data/temp").resolve()
        temp_base_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = temp_base_dir / f"pdf_parser_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        ui_logger.info(f"创建临时文件夹: {temp_dir}")
        
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
            
            # 保存Excel文件到临时文件夹
            excel_path = save_dataframe_to_excel_file(df, table_name, temp_dir)
            download_files.append(excel_path)
        
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
            # 使用 gr.File 组件替代 DownloadButton，更可靠
            download_file_1 = gr.File(label="合并资产负债表", visible=False)
            download_file_2 = gr.File(label="母公司资产负债表", visible=False)
            download_file_3 = gr.File(label="合并利润表", visible=False)
            download_file_4 = gr.File(label="母公司利润表", visible=False)
            download_file_5 = gr.File(label="合并现金流量表", visible=False)
            download_file_6 = gr.File(label="母公司现金流量表", visible=False)
            download_file_7 = gr.File(label="股份变动情况表", visible=False)
        
        download_files = [download_file_1, download_file_2, download_file_3, 
                         download_file_4, download_file_5, download_file_6, download_file_7]
        
        # 处理按钮点击事件
        def on_process(pdf_file, db_type_val):
            result_msg, company_txt, table_list, download_file_paths = process_pdf(pdf_file, db_type_val)
            
            file_updates = []
            for i, file_comp in enumerate(download_files):
                if i < len(download_file_paths):
                    file_path = download_file_paths[i]
                    table_name = file_path.stem.replace("_", "")
                    file_updates.append(gr.update(
                        visible=True,
                        value=str(file_path),
                        label=f"下载: {table_name}"
                    ))
                else:
                    file_updates.append(gr.update(visible=False))
            
            return result_msg, company_txt, table_list, download_file_paths, *file_updates
        
        process_btn.click(
            fn=on_process,
            inputs=[pdf_input, db_type],
            outputs=[result_text, company_info, tables_output, download_files_state] + download_files
        )