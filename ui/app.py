import gradio as gr
import os
import sys

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from pdf_parser_ui import create_pdf_parser_tab
# from db_query_ui import create_db_query_tab


def create_main_app():
    """
    创建主应用界面，整合PDF解析和数据库查询功能
    """
    with gr.Blocks(
        title="财务报告分析系统"
    ) as demo:
        gr.Markdown(
            """
            <div class="logo">FinancialAgent 智能财务报告分析系统</div>
            """,
            elem_classes=["logo"]
        )
        
        gr.Markdown(
            """
            欢使用智能财务报告分析系统！本系统提供以下功能：
            1. PDF财务报告上传与智能解析
            2. 财务数据查询与分析
            """
        )
        
        with gr.Tab("PDF上传与解析"):
            create_pdf_parser_tab()
        
        # with gr.Tab("数据查询"):
        #     create_db_query_tab()
        
    return demo


if __name__ == "__main__":
    demo = create_main_app()
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        server_port=7861,
        show_error=True,
        theme=gr.themes.Soft(),
        css="""
        .logo {
            font-size: 24px;
            font-weight: bold;
            text-align: center;
            margin-bottom: 20px;
        }
        """
    )