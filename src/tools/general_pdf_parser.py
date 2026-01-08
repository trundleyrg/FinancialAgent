"""
集成文本和表格提取工具 (如 PyMuPDF, TableTransformer)
"""

from typing import List, Optional
# from langchain_openai import ChatOpenAI
from src.schema.models import FinancialExtractionSchema
from src.utils.logger import logger

import os
import fitz  # PyMuPDF
import pdfplumber
import pathlib
from typing import Optional
from src.utils.logger import logger

class PDFParser:
    def __init__(self, output_base_dir: str = "./data/output"):
        self.output_dir = pathlib.Path(output_base_dir)
        self.img_dir = self.output_dir / "imgs"
        self.table_dir = self.output_dir / "tables"
        
        # 初始化目录结构
        self._prepare_dirs()

    def _prepare_dirs(self):
        """初始化必要的文件夹"""
        for d in [self.output_dir, self.img_dir, self.table_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def process_pdf(self, pdf_path: str):
        """
        主控方法：执行正文、图片和表格的提取
        """
        pdf_name = pathlib.Path(pdf_path).stem
        logger.info(f"Processing PDF: {pdf_name}")

        with fitz.open(pdf_path) as doc:
            # 1. 提取正文并保存为 Markdown
            self._extract_text_to_md(doc, pdf_name)
            
            # 2. 提取图片
            self._extract_images(doc)

        # 3. 提取表格 (使用 pdfplumber 获得更好的表格边界识别)
        with pdfplumber.open(pdf_path) as pdf:
            self._extract_tables(pdf, pdf_name)

    def _extract_text_to_md(self, doc, pdf_name: str):
        """提取正文并保存为 .md 文件"""
        md_content = []
        for page in doc:
            md_content.append(page.get_text("text"))
        
        md_file = self.output_dir / f"{pdf_name}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n\n".join(md_content))
        logger.info(f"Markdown saved to {md_file}")

    def _extract_images(self, doc):
        """提取图片并保存至 output/imgs"""
        for page_index in range(len(doc)):
            page = doc[page_index]
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]
                
                img_filename = self.img_dir / f"page{page_index+1}_{img_index+1}.{ext}"
                with open(img_filename, "wb") as f:
                    f.write(image_bytes)

    def _extract_tables(self, pdf, pdf_name: str):
        """
        提取表格。
        选择 Markdown 格式保存，因为它对 LLM 最友好，且易于阅读。
        """
        prev_table = None
        
        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            
            for j, table in enumerate(tables):
                # 数据清洗：移除空行
                clean_table = [[(cell if cell else "") for cell in row] for row in table]
                
                # 简单的跨页逻辑判断：
                # 如果当前页的第一个表格列数与上一页最后一个表格相同，且第一行不含标题特征，
                # 在实际工程中，这里可以进一步通过状态机合并，目前先独立保存并标记。
                
                md_table = self._convert_to_md_table(clean_table)
                table_filename = self.table_dir / f"page{i+1}_{j+1}.md"
                
                with open(table_filename, "w", encoding="utf-8") as f:
                    f.write(md_table)

    def _convert_to_md_table(self, table_data: list) -> str:
        """将嵌套列表转换为 Markdown 表格格式"""
        if not table_data:
            return ""
        
        md_str = ""
        for i, row in enumerate(table_data):
            # 清理换行符避免破坏表格结构
            clean_row = [str(cell).replace("\n", " ") for cell in row]
            md_str += "| " + " | ".join(clean_row) + " |\n"
            if i == 0:  # 添加表头分隔符
                md_str += "| " + " | ".join(["---"] * len(row)) + " |\n"
        return md_str
    
    def map_tables_to_schema(self, pdf_path: str) -> str:
        """
        扫描已提取的表格文件，匹配核心财务指标，并返回符合 Schema 的 JSON 字符串。
        """
        pdf_name = pathlib.Path(pdf_path).stem
        # 初始化一个基础结果字典
        extracted_data = {
            "company_name": pdf_name.split('_')[0],  # 假设文件名包含公司名
            "stock_code": "000000",                # 占位符
            "report_year": 2024,                   # 占位符
            "report_period": ReportPeriod.FY,      # 默认年报
        }

        # 定义需要匹配的指标关键词及其在 Schema 中的字段名
        mapping_config = {
            "营业收入": "operating_revenue",
            "归属于上市公司股东的净利润": "net_profit",
            "净利润": "net_profit",
            "毛利率": "gross_margin",
            "净利润率": "profit_margin",
            "净资产收益率": "roe"
        }

        # 遍历所有提取出的表格 MD 文件
        for table_file in sorted(self.table_dir.glob("*.md")):
            with open(table_file, "r", encoding="utf-8") as f:
                content = f.readlines()
            
            for line in content:
                for keyword, schema_key in mapping_config.items():
                    if keyword in line and schema_key not in extracted_data:
                        # 尝试提取行中的数值（简单逻辑：提取该行中第一个看起来像数字的列）
                        cells = [c.strip() for c in line.split("|") if c.strip()]
                        value = self._parse_numeric_value(cells)
                        
                        if value is not None:
                            # 构造符合 MetricItem 格式的字典
                            extracted_data[schema_key] = {
                                "value": value,
                                "unit": "%" if "率" in keyword or "ROE" in keyword else "元",
                                "context": line.strip(),
                                "page": int(table_file.stem.split('_')[0].replace("page", ""))
                            }

        # 使用 Pydantic 进行校验并转为 JSON
        # 注意：如果缺少必填项，此处会抛出异常，适合在 Agent 节点中捕获
        try:
            validated_data = FinancialExtractionSchema(**extracted_data)
            return validated_data.model_dump_json()
        except Exception as e:
            logger.warning(f"Schema validation failed: {e}. Returning raw dict as JSON.")
            return json.dumps(extracted_data, ensure_ascii=False)

    def _parse_numeric_value(self, cells: list) -> Optional[float]:
        """从表格行单元格中清洗并提取数值"""
        for cell in cells:
            # 移除逗号、百分号、空格
            clean_val = cell.replace(",", "").replace("%", "").strip()
            try:
                # 财务报表中常见括号表示负数： (100.00) -> -100.00
                if clean_val.startswith("(") and clean_val.endswith(")"):
                    return -float(clean_val[1:-1])
                return float(clean_val)
            except ValueError:
                continue
        return None


if __name__ == '__main__':
    # 运行处理
    pdf_file = "./data/raw_pdfs/22.佰仁医疗2024年年报.pdf"
    output_folder = "extracted_tables"
    
   
