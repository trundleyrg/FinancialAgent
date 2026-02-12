import gradio as gr
import os
import sys
from pathlib import Path

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 直接从src导入
from tools.general_pdf_parser import PDFParser
from db.db_connector import get_db
from db.models import FinancialExtractionSchema


def process_pdf(pdf_file):
    """
    处理上传的PDF文件
    """
    if not pdf_file:
        return "请上传一个PDF文件", "", "", ""
    
    try:
        # 创建PDF解析器实例
        pdf_parser = PDFParser()
        
        # 获取文件路径
        file_path = pdf_file.name
        
        # 处理PDF文件
        pdf_parser.process_pdf(file_path)
        
        # 尝试从PDF中提取结构化财务数据
        json_result = pdf_parser.map_tables_to_schema(file_path)
        
        # 解析JSON结果
        try:
            validated_data = FinancialExtractionSchema.model_validate_json(json_result)
            extraction_result = f"公司名称: {validated_data.company_name}\n"
            extraction_result += f"报告年份: {validated_data.report_year}\n"
            extraction_result += f"报告周期: {validated_data.report_period.value}\n"
            extraction_result += f"营业收入: {validated_data.operating_revenue.value} {validated_data.operating_revenue.unit}\n"
            extraction_result += f"净利润: {validated_data.net_profit.value} {validated_data.net_profit.unit}\n"
            extraction_result += f"毛利率: {validated_data.gross_margin.value} {validated_data.gross_margin.unit}\n"
            extraction_result += f"净利润率: {validated_data.profit_margin.value} {validated_data.profit_margin.unit}\n"
            extraction_result += f"净资产收益率: {validated_data.roe.value} {validated_data.roe.unit}\n"
        except Exception as e:
            extraction_result = f"结构化数据提取失败: {str(e)}\n\n原始JSON结果:\n{json_result}"
        
        # 读取生成的Markdown文件
        pdf_name = Path(file_path).stem
        md_file_path = os.path.join(pdf_parser.output_dir, f"{pdf_name}.md")
        
        if os.path.exists(md_file_path):
            with open(md_file_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
        else:
            markdown_content = "未找到生成的Markdown文件"
        
        # 获取图片文件
        img_dir = pdf_parser.img_dir
        img_files = []
        if os.path.exists(img_dir):
            img_files = [os.path.join(img_dir, f) for f in os.listdir(img_dir) 
                         if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        
        # 获取表格文件
        table_dir = pdf_parser.table_dir
        table_files = []
        if os.path.exists(table_dir):
            table_files = [os.path.join(table_dir, f) for f in os.listdir(table_dir) 
                           if f.lower().endswith('.md')]
        
        return (
            f"PDF处理成功！文件: {os.path.basename(file_path)}",
            markdown_content,
            extraction_result,
            img_files[:5]  # 只返回前5张图片
        )
    
    except Exception as e:
        return f"处理PDF时发生错误: {str(e)}", "", "", []


def create_pdf_parser_tab():
    """
    创建PDF解析界面
    """
    with gr.Tab("PDF文件上传与解析"):
        gr.Markdown("## PDF财务报告上传与解析")
        gr.Markdown("上传PDF财务报告文件，系统将自动解析并提取财务数据")
        
        with gr.Row():
            with gr.Column(scale=1):
                pdf_input = gr.File(
                    label="上传PDF文件",
                    file_types=[".pdf"],
                    file_count="single"
                )
                
                process_btn = gr.Button("开始解析", variant="primary")
                
                result_text = gr.Textbox(
                    label="处理结果",
                    interactive=False,
                    max_lines=3
                )
            
            with gr.Column(scale=2):
                with gr.Tab("提取的结构化数据"):
                    extracted_data = gr.Textbox(
                        label="结构化财务数据",
                        interactive=False,
                        max_lines=15,
                        lines=10
                    )
                
                with gr.Tab("生成的Markdown"):
                    markdown_output = gr.Textbox(
                        label="PDF转Markdown内容",
                        interactive=False,
                        max_lines=20,
                        lines=10
                    )
                
                with gr.Tab("提取的图片"):
                    image_gallery = gr.Gallery(
                        label="从PDF中提取的图片",
                        show_label=True,
                        elem_id="gallery",
                        columns=3,
                        object_fit="contain",
                        height="auto"
                    )
        
        process_btn.click(
            fn=process_pdf,
            inputs=[pdf_input],
            outputs=[result_text, markdown_output, extracted_data, image_gallery]
        )


if __name__ == "__main__":
    with gr.Blocks(title="财务报告PDF解析器") as demo:
        create_pdf_parser_tab()
    
    demo.launch(share=True)
