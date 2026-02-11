"""
程序入口，初始化 Agent 并运行
"""
import os
import re
from pathlib import Path
import fitz  # PyMuPDF

from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import get_db
from src.db.table_data_saver import save_tables_to_db
from src.utils.logger import main_logger


def extract_year_from_filename(filename: str) -> int:
    """
    从文件名中提取年份信息
    :param filename: PDF 文件名
    :return: 年份
    """
    # 尝试多种年份提取模式
    patterns = [
        r'(\d{4})年',      # 匹配 "2024年"
        r'(\d{4})年报',     # 匹配 "2024年报"
        r'(\d{4})',        # 匹配 "2024"
        r'(\d{2})年',      # 匹配 "24年"
        r'(\d{2})年报'      # 匹配 "24年报"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            year = int(match.group(1))
            # 如果是两位数年份，转换为四位数
            if year < 100:
                year = 2000 + year if year < 50 else 1900 + year
            return year
    
    # 如果没有找到年份，使用当前年份
    import datetime
    return datetime.datetime.now().year


def extract_company_name_from_filename(filename: str) -> str:
    """
    从文件名中提取公司名称
    :param filename: PDF 文件名
    :return: 公司名称
    """
    # 去除扩展名
    name = Path(filename).stem
    
    # 移除序号和年份等信息，保留公司名称
    # 例如: "22.佰仁医疗2024年年报.pdf" -> "佰仁医疗"
    patterns = [
        r'^\d+\.(.*?)\d{4}年',  # 匹配 "序号.公司名年份年"
        r'^\d+\.(.*?)\d{4}年报', # 匹配 "序号.公司名年份年报"
        r'^\d+\.(.*?)\d{2}年',  # 匹配 "序号.公司名年份年" (两位年份)
        r'^\d+\.(.*?)\d{2}年报', # 匹配 "序号.公司名年份年报" (两位年份)
        r'(.*?)(?:\d{4}|年)',    # 匹配 "公司名年份" 或 "公司名年"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            company_name = match.group(1).strip()
            return company_name
    
    # 如果没有匹配，返回原始名称（去除序号）
    match = re.match(r'^\d+\.(.*)', name)
    if match:
        return match.group(1).strip()
    
    return name


def process_pdf_file(pdf_path: str):
    """
    处理单个 PDF 文件
    :param pdf_path: PDF 文件路径
    """
    filename = os.path.basename(pdf_path)
    
    # 从文件名提取公司名称和年份
    company_name = extract_company_name_from_filename(filename)
    report_year = extract_year_from_filename(filename)
    
    # 确定报告期间
    if '年报' in filename:
        report_period = 'FY'
    elif '三季报' in filename:
        report_period = 'Q3'
    elif '半年报' in filename or '中报' in filename:
        report_period = 'H1'
    elif '一季报' in filename:
        report_period = 'Q1'
    else:
        report_period = 'FY'  # 默认年报
    
    main_logger.info(f"正在处理文件: {filename}")
    main_logger.info(f"公司名称: {company_name}, 年份: {report_year}, 期间: {report_period}")
    
    # 使用 PDFChapterExtractor 提取主要表格
    extractor = PDFChapterExtractor(pdf_path)
    try:
        main_tables = extractor.extract_main_tables()
        
        # 保存表格数据到 DuckDB
        save_tables_to_db(main_tables, company_name, report_year, report_period)
        
        main_logger.info(f"已成功处理并保存: {filename}")
    except Exception as e:
        main_logger.error(f"处理文件 {filename} 时出错: {str(e)}")
    finally:
        extractor.close()


def main():
    """
    主函数：处理 data/raw_pdfs 目录下的所有 PDF 文件
    """
    main_logger.info("开始处理 PDF 文件...")
    
    # 获取 data/raw_pdfs 目录下的所有 PDF 文件
    pdf_dir = Path("data/raw_pdfs")
    if not pdf_dir.exists():
        main_logger.error(f"目录 {pdf_dir} 不存在")
        return
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        main_logger.warning(f"在 {pdf_dir} 中未找到 PDF 文件")
        return
    
    main_logger.info(f"找到 {len(pdf_files)} 个 PDF 文件")
    
    # 依次处理每个 PDF 文件
    for pdf_file in pdf_files:
        try:
            process_pdf_file(str(pdf_file))
        except Exception as e:
            main_logger.error(f"处理文件 {pdf_file} 时发生未预期错误: {str(e)}")
    
    main_logger.info("PDF 文件处理完成！")


if __name__ == "__main__":
    main()