"""
pdf通用解析类
将pdf正文保存为md，图片保存为 png，表格保存为 md
"""

import fitz  # PyMuPDF
import pdfplumber
import pathlib
import json

from typing import Optional
from collections import defaultdict
from src.db.models import FinancialExtractionSchema, ReportPeriod
from src.utils.logger import pdf_logger

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
        pdf_logger.info(f"Processing PDF: {pdf_name}")

        # 正文和图片
        with fitz.open(pdf_path) as doc:
            self._extract_text_to_md(doc, pdf_name)
            self._extract_images(doc)

        # 表格
        with pdfplumber.open(pdf_path) as pdf:
            self._extract_tables(pdf)

    def _extract_text_to_md(self, doc, pdf_name: str):
        """提取正文并保存为 .md 文件"""
        md_content = []
        for page in doc:
            md_content.append(page.get_text("text"))
        
        md_file = self.output_dir / f"{pdf_name}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n\n".join(md_content))
        pdf_logger.info(f"Markdown saved to {md_file}")

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

    # region 表格处理

    def _extract_tables(self, pdf):
        """
        提取表格，以 Markdown 格式保存
        支持跨页表格的正确合并
        """
        def clean_tabel_cell(cell):
            """
            数据清洗：将None替换为空字符串，去除表格中的换行符
            """
            cell = str(cell).replace("\n", "")
            cell = cell.strip()
            return "" if cell is None else str(cell)
        
        # 用于存储所有提取的表格，包括跨页合并后的表格
        all_tables = []

        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables()

            tables = page.find_tables()  

            for j, table in enumerate(tables):
                # todo: 依据bbox位置判断是否表格连接
                bbox = table.bbox  # 左上右下
                content = table.extract()
                if not content:
                    continue

                # 数据清洗：移除空行，并用空字符串替换None
                # 注意，填充为None的情况，表明该单元格是合并单元格
                clean_table = [[clean_tabel_cell(cell) for cell in row] for row in content]
                all_tables.append({
                    "data": clean_table,
                    "page": i+1
                })

        # 合并跨页表格
        all_tables = self._merge_tables(all_tables)

        # 保存所有表格
        for idx, table_info in enumerate(all_tables):
            md_table = self._convert_to_md_table(table_info["data"])
            page_range = table_info["range"]
            table_filename = self.table_dir / f"page{page_range}_table{idx+1}.md"

            with open(table_filename, "w", encoding="utf-8") as f:
                f.write(md_table)
            pdf_logger.info(f"Saved table: {table_filename}")

    def _merge_tables(self, all_tables):
        """
        合并连续的表格数据

        Args:
            all_tables: List[Dict], 每个元素包含 "data" 和 "page"

        Returns:
            List[Dict]: 合并后的列表，每个元素包含 "data", "range"
        """
        if not all_tables:
            return []

        # 步骤1: 按 page 分组，保持每页内表格的原始顺序
        pages_dict = defaultdict(list)
        for table in all_tables:
            pages_dict[table["page"]].append(table["data"])

        # 获取所有唯一 page 并排序
        sorted_pages = sorted(pages_dict.keys())
        if not sorted_pages:
            return []
        
        # 步骤2: 识别连续段并合并
        results = []
        start, end = 0, len(sorted_pages)
        pre_table= None
        while start < end:
            current_page = sorted_pages[start]
            if pre_table is None:
                for i in range(len(pages_dict[current_page]) - 1):
                    results.append({
                            "data": pages_dict[current_page][i],
                            "range": str(current_page)
                    })
                pre_table = {
                    "data": pages_dict[current_page][-1],
                    "page": current_page,  # 记录跨页表格起始页
                    "pre_page": current_page,  # 记录跨页表格当前页
                }  # 保留后一段匹配后面的页数
            else:
                if current_page - pre_table["pre_page"] == 1:
                    # 尝试合并
                    if self._tables_match(pre_table["data"], pages_dict[current_page][0]):
                        pre_table["pre_page"] = current_page
                        pre_table = self._merge_tables_data(pre_table, pages_dict[current_page][0])
                        if len(pages_dict[current_page]) > 1 and pre_table:
                            results.append({
                                "data": pre_table["data"],
                                "range": str(pre_table["page"]) + "-" + str(current_page)
                            })
                            for i in range(1, len(pages_dict[current_page]) - 1):
                                results.append({
                                        "data": pages_dict[current_page][i],
                                        "range": str(current_page)
                                })
                            pre_table = {
                                "data": pages_dict[current_page][-1],
                                "page": current_page,  # 记录跨页表格起始页
                                "pre_page": current_page,  # 记录跨页表格当前页
                            }
                    else:
                        results.append({
                            "data": pre_table["data"],
                            "range": str(pre_table["page"]) if pre_table["page"] == pre_table["pre_page"] else str(pre_table["page"]) + "-" + str(pre_table["page"]),
                        })
                        for i in range(len(pages_dict[current_page]) - 1):
                            results.append({
                                    "data": pages_dict[current_page][i],
                                    "range": str(current_page)
                            })
                        pre_table = {
                                "data": pages_dict[current_page][-1],
                                "page": current_page,  # 记录跨页表格起始页
                                "pre_page": current_page,  # 记录跨页表格当前页
                        }
                else:
                    results.append({
                        "data": pre_table["data"],
                        "range": str(pre_table["page"]) if pre_table["page"] == pre_table["pre_page"] else str(pre_table["page"]) + "-" + str(pre_table["page"]),
                    })
                    for i in range(len(pages_dict[current_page]) - 1):
                        results.append({
                            "data": pages_dict[current_page][i],
                            "range": str(current_page)
                        })
                    pre_table = {
                        "data": pages_dict[current_page][-1],
                        "page": current_page,  # 记录跨页表格起始页
                        "pre_page": current_page,  # 记录跨页表格当前页
                    }
            start += 1

        if pre_table:
            results.append({
                "data": pre_table["data"],
                "range": str(pre_table["page"]) if pre_table["page"] == pre_table["pre_page"] else str(pre_table["page"]) + "-" + str(pre_table["page"]),
            })

        return results

    def _merge_tables_data(self, pre_table: dict, table2: list):
        """
        合并两个表格数据
        """
        return {
            "data": pre_table["data"] + table2,
            "page": pre_table["page"],
            "pre_page": pre_table["pre_page"]
        }

    # def _is_header_row(self, row: list) -> bool:
    #     """
    #     检测一行是否为表头
    #     通过常见的关键词和特征来判断
    #     """
    #     header_keywords = [  # todo: 修改表头检查
    #         "项目", "金额", "比例", "本期", "上期", "单位", "年度",
    #         "营业收入", "营业成本", "毛利率", "净利润", "ROE", "收益率",
    #         "报告期", "日期", "期初", "期末", "变动", "增减"
    #     ]
    #     # 将行内容合并为一个字符串进行检测
    #     row_text = " ".join([str(cell) for cell in row if cell])
    #     # 如果包含多个关键词，或者第一列包含关键词，则认为是表头
    #     keyword_count = sum(1 for kw in header_keywords if kw in row_text)
    #     return keyword_count >= 2

    def _tables_match(self, table1: list, table2: list) -> bool:
        """
        判断两个表格是否可能属于同一个跨页表格
        """
        if not table1 or not table2:
            return False
        if len(table1[0]) != len(table2[0]):
            return False
        # # 第二个表格的第一行不应该被识别为表头
        # if self._is_header_row(table2[0]):
        #     return False
        return True

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
        # todo: 其他来源填充下面的metadata
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
            pdf_logger.warning(f"Schema validation failed: {e}. Returning raw dict as JSON.")
            return json.dumps(extracted_data, ensure_ascii=False)

    def _parse_numeric_value(self, cells: list) -> Optional[float]:
        """从表格行单元格中清洗并提取数值"""
        for cell in cells:
            # 移除逗号、百分号、空格
            clean_val = cell.replace(",", "").replace("%", "").strip()
            try:
                # # 财务报表中常见括号表示负数： (100.00) -> -100.00
                # if clean_val.startswith("(") and clean_val.endswith(")"):
                #     return -float(clean_val[1:-1])
                return float(clean_val)
            except ValueError:
                continue
        return None
    
    # endregion


if __name__ == '__main__':
    # 运行处理
    pdf_file = "./data/raw_pdfs/22.佰仁医疗2024年年报.pdf"
    output_folder = "extracted_tables"
    pdf_parser = PDFParser(output_base_dir=r"./data/output")
    pdf_parser.process_pdf(pdf_file)
