"""
程序入口，初始化 Agent 并运行
"""
import os
import re
from pathlib import Path
import fitz  # PyMuPDF

from src.tools.chapter_extractor import PDFChapterExtractor
from src.db.db_connector import get_db
from src.db.models import ReportPeriod
from src.db.db_connector import save_tables_to_db
from src.utils.logger import main_logger


def get_company_info(pdf_path: str):
    """
    从PDF文档第一页中提取公司名称、公司代码和年份
    :param pdf_path: PDF 文件路径
    :return: tuple of (company_name, company_code, year)
    """
    # 打开PDF文档并读取第一页
    doc = fitz.open(pdf_path)
    page = doc[0]  # 第一页
    text = page.get_text()
    lines = text.split('\n')
    
    company_name = ""
    company_short_name = ""
    company_code = ""
    year = 0
    
    # 查找公司名称
    for line in lines:
        line = line.strip()
        
        # 查找公司名称，通常包含"股份有限公司"或"有限公司"
        if "股份有限公司" in line or "有限公司" in line:
            company_name = line.strip()
            match = re.search(r'(.+?(?:股份有限公司|有限公司))', line)
            if match:
                company_name = match.group(1).strip()
            break
        elif "公司" in line and ("有限" in line or "股份" in line):
            company_name = line.strip()
            break
    
    # 查找公司简称
    for line in lines:
        line = line.strip()
        # 匹配"公司简称"、"股票代码"、"证券代码"等
        match = re.search(r'(?:公司简称)[:：\s]*([^0-9]+)', line)
        if match:
            company_short_name = match.group(1).strip()
            break
    
    # 查找公司代码，通常在文档中以"证券代码"、"股票代码"等形式出现
    for line in lines:
        line = line.strip()
        # 匹配证券代码、股票代码等
        code_matches = re.search(r'(?:证券代码|股票代码|代码)[:：\s]*([0-9]{6})', line)
        if code_matches:
            company_code = code_matches.group(1)
            break
        # 也可能在公司名称附近直接出现6位数字代码
        if company_name and company_name in line:
            nearby_lines = [line]
            line_idx = lines.index(line)
            if line_idx > 0:
                nearby_lines.append(lines[line_idx - 1])
            if line_idx < len(lines) - 1:
                nearby_lines.append(lines[line_idx + 1])
            
            for near_line in nearby_lines:
                code_match = re.search(r'([0-9]{6})', near_line)
                if code_match and code_match.group(1) != '000000':  # 排除无效代码
                    company_code = code_match.group(1)
                    break
            if company_code:
                break
    
    # 从标题中提取年份，寻找年报中的年份信息
    for line in lines:
        line = line.strip()
        if "年度报告" in line or "年报" in line:
            year_match = re.search(r'(\d{4})', line)
            if year_match:
                year = int(year_match.group(1))
                break
    
    # 确定报告期间
    report_period = None
    for line in lines:
        if '年度报告' in text or '年报' in text:
            report_period = 'FY'
        elif '三季报' in text or '第三季度报告' in text:
            report_period = 'Q3'
        elif '半年报' in text or '中报' in text or '半年度报告' in text:
            report_period = 'H1'
        elif '一季报' in text or '第一季度报告' in text:
            report_period = 'Q1'
        elif '半年度财务报告' in text:
            report_period = 'H1'
        elif '年度财务报告' in text:
            report_period = 'FY'
        if report_period is not None:
            break
    
    doc.close()
    
    return company_name, company_short_name, company_code, year, report_period


def process_pdf_file(pdf_path: str):
    """
    处理单个 PDF 文件
    :param pdf_path: PDF 文件路径
    """
    # 初始化数据库表
    db = get_db()
    db.create_tables()

    filename = os.path.basename(pdf_path)
    main_logger.info(f"正在处理文件: {filename}")
    
    try:
        # 从PDF第一页提取公司名称、公司代码和年份
        company_name, company_short_name, company_code, report_year, report_period = get_company_info(pdf_path)
        
        main_logger.info(f"公司名称: {company_name}, 公司代码: {company_code}, 公司简称： {company_short_name}, 年份: {report_year}, 期间: {report_period}")

        # 使用 PDFChapterExtractor 提取主要表格
        extractor = PDFChapterExtractor(pdf_path)

        main_tables = extractor.extract_main_tables()

        # 保存表格数据到 DuckDB
        save_tables_to_db(
            main_tables=main_tables,
            company_name=company_name,
            pdf_path=pdf_path,
            company_short_name=company_short_name,
            company_code=company_code,
            report_year=report_year,
            report_period=report_period,
            stock_code=company_code,
            db_connector=db
        )
        
        main_logger.info(f"已成功处理并保存: {filename}")
    except Exception as e:
        main_logger.error(f"处理文件 {filename} 时出错: {str(e)}")
        raise
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
            raise
    
    main_logger.info("PDF 文件处理完成！")


if __name__ == "__main__":
    main()