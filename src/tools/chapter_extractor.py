"""
chapter_extractor.py     # 负责识别和提取 PDF 指定章节

使用fitz.open().get_toc()的方式定位章节位置和表格关系。
"""

import fitz  # PyMuPDF
from typing import List, Tuple, Dict, Optional

from src.utils.logger import chapter_logger
from src.db.table_models import TableWithHeader

class PDFChapterExtractor:
    def __init__(self, pdf_path: str):
        self.doc = fitz.open(pdf_path)
        self.toc = self.doc.get_toc()
        self.page_heights = [page.rect.height for page in self.doc]
        
    def find_section_range(self, section_title: str, section_level: int=None) -> Tuple[int, int]:
        """
        定位章节页码范围, 支持不指定section_level的模糊匹配。
        :param section_title: 目标章节标题（支持正则）
        :param next_section_pattern: 下一章节标题模式（用于确定结束页）
        :return: (起始页, 结束页) 页码从0开始
        """
        start_page = None
        end_page = len(self.doc) - 1
        
        # 查找起始页
        for index, entry in enumerate(self.toc):
            if section_level is None and section_title in entry[1]:
                start_page = entry[2] - 1
                section_level = entry[0]  # 没有给定section_level时，启用模糊查找
                break
            elif entry[0] == section_level and section_title in entry[1]:
                start_page = entry[2] - 1
                break
        if section_level is None:
            raise ValueError(f"文档中查找不到章节: {section_title}")
        toc_list = self.toc[index:]
        # 在start_page之后，寻找下一个entry[0]==1的页数
        for index in range(1, len(toc_list)):
            if toc_list[index][0] == section_level:
                end_page = toc_list[index][2] - 1
                break
        if start_page is None:
            raise ValueError(f"未找到章节: {section_title}")
        
        chapter_logger.info(f"目标章节：{section_title} 起始页:{start_page} 结束页:{end_page}")
        return start_page, end_page

    def extract_page_elements(self, page_num: int) -> Tuple[List[Dict], List]:
        """
        提取单页的文本块和表格
        :return: (文本块列表, 表格列表)
        """
        page = self.doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        # 提取文本块（过滤图片）
        text_blocks = []
        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        text_blocks.append({
                            "text": span["text"].strip(),
                            "bbox": span["bbox"],  # (x0, y0, x1, y1)
                            "y_top": span["bbox"][1],   # top y
                            "y_bottom": span["bbox"][3] # bottom y
                        })
        
        # 提取表格（使用 find_tables）
        tables = []
        try:
            tabs = page.find_tables()
            for tab in tabs:
                if tab.header and tab.cells:  # 有效表格
                    tables.append({
                        "table": tab,
                        "bbox": tab.bbox,  # (x0, y0, x1, y1)
                        "y_top": tab.bbox[1],
                        "y_bottom": tab.bbox[3],
                        "col_count": len(tab.header.cells) if tab.header else 0
                    })
        except Exception as e:
            print(f"页面 {page_num} 表格提取失败: {e}")
        
        # 按y坐标排序文本块（从上到下）
        text_blocks.sort(key=lambda b: b["y_top"])
        tables.sort(key=lambda t: t["y_top"])
        
        return text_blocks, tables

    def associate_header_with_table(self, text_blocks: List[Dict], table: Dict, 
                                   page_height: float, 
                                   header_search_range: float = 80.0) -> str:
        """
        为表格关联最近的表头文本
        :param header_search_range: 向上搜索表头的最大距离（像素）
        """
        table_top = table["y_top"]
        candidates = []
        
        for block in reversed(text_blocks):  # 从表格向上搜索
            if block["y_bottom"] < table_top and table_top - block["y_bottom"] <= header_search_range:
                candidates.append(block)
            if block["y_bottom"] < table_top - header_search_range:
                break
        
        # 按垂直距离排序，取最近的5个文本块
        candidates.sort(key=lambda b: table_top - b["y_bottom"])
        header_texts = [c["text"] for c in candidates[:5] if c["text"]][::-1]  # 从上到下排列
        
        return " ".join(header_texts).strip() if header_texts else "（未找到表头）"

    def should_merge_tables(self, table1: Dict, table2: Dict, 
                           page1_height: float, page2_height: float,
                           col_tolerance: int = 1) -> bool:
        """
        判断两个表格是否应合并（跨页表格）
        """
        # 条件1: 表1接近页底（底部在页面90%以下）
        if table1["y_bottom"] < page1_height * 0.9:
            return False
        
        # 条件2: 表2接近页顶（顶部在页面15%以上）
        if table2["y_top"] > page2_height * 0.15:
            return False
        
        # 条件3: 列数相同或相近
        if abs(table1["col_count"] - table2["col_count"]) > col_tolerance:
            return False
        
        # 条件4: x方向位置重叠（列对齐）
        x_overlap = max(0, min(table1["bbox"][2], table2["bbox"][2]) - max(table1["bbox"][0], table2["bbox"][0]))
        x_union = max(table1["bbox"][2], table2["bbox"][2]) - min(table1["bbox"][0], table2["bbox"][0])
        if x_union == 0 or x_overlap / x_union < 0.7:  # 重叠度<70%
            return False
        
        return True

    def merge_table_data(self, main_table: List[List[str]], 
                        continuation_table: List[List[str]]) -> List[List[str]]:
        """
        合并跨页表格数据（跳过续表的表头行）
        """
        return main_table + continuation_table

    def extract_tables_in_section(self, start_page: int, end_page: int) -> List[TableWithHeader]:
        """
        提取指定章节范围内的所有表格（含表头关联和跨页合并）
        """
        # 步骤1: 提取所有原始表格
        raw_tables = []
        for page_num in range(start_page, end_page + 1):
            text_blocks, tables = self.extract_page_elements(page_num)
            for tab in tables:
                header = self.associate_header_with_table(
                    text_blocks, tab, self.page_heights[page_num]
                )
                raw_tables.append(TableWithHeader(
                    table_data=tab["table"].extract(),  # 二维列表
                    header_text=header,
                    page_start_num=page_num,
                    page_end_num=page_num,
                    bbox=tab["bbox"]
                ))
        
        # 步骤2: 合并跨页表格
        merged_tables = []
        i = 0
        while i < len(raw_tables):
            current = raw_tables[i]
            # 检查是否与后续表格合并
            j = i + 1
            while j < len(raw_tables):
                next_tab = raw_tables[j]
                # 必须是连续页面
                if next_tab.page_start_num != current.page_start_num + (j - i):
                    break
                # 检查合并条件
                page1_h = self.page_heights[current.page_start_num + (j - i - 1)]
                page2_h = self.page_heights[next_tab.page_start_num]
                if self.should_merge_tables(
                    {"bbox": current.bbox, "y_bottom": current.bbox[3],
                     "col_count": len(current.table_data[0]) if current.table_data else 0},
                    {"bbox": next_tab.bbox, "y_top": next_tab.bbox[1],
                     "col_count": len(next_tab.table_data[0]) if next_tab.table_data else 0},
                    page1_h, page2_h
                ):
                    # 合并数据
                    current.table_data += next_tab.table_data
                    current.page_end_num = next_tab.page_end_num  # 更新结束页码
                    current.bbox = (
                        min(current.bbox[0], next_tab.bbox[0]),
                        current.bbox[1],
                        max(current.bbox[2], next_tab.bbox[2]),
                        next_tab.bbox[3]
                    )
                    current.is_merged = True
                    j += 1
                else:
                    break
            merged_tables.append(current)
            i = j  # 跳过已合并的表格
        
        return merged_tables
    
    def extract_section_tables(self, section_title: str, section_level: int = 1) -> List[TableWithHeader]:
        """
        提取指定章节的所有表格
        """
        start_page, end_page = self.find_section_range(section_title, section_level=section_level)
        tables = self.extract_tables_in_section(start_page, end_page)
        return tables

    # 获取三大主表
    def extract_main_tables(self) -> Dict[str, Optional[TableWithHeader]]:
        """
        获取主要表
        """
        # 主要表情况
        main_tables = {
            "合并资产负债表": [3],
            "母公司资产负债表": [3],
            "合并利润表": [3],
            "母公司利润表": [3],
            "合并现金流量表": [3],
            "母公司现金流量表": [3],
            "股份变动情况表": [3]
        }
        # 提取主要报表
        for section_title in main_tables.keys():
            tables = self.extract_section_tables(section_title, section_level=3)
            if len(tables) > 1:
                # 当前页中找到两个以上的表格，判断表头前的文本中是否出现相关文本
                find_table = False
                for table in tables:
                    if section_title in table.header_text:
                        find_table = True
                        main_tables[section_title] = table
                        break
                if not find_table:
                    chapter_logger.info(f"未找到{section_title}表")
            elif len(tables) < 1:
                main_tables[section_title] = None
                chapter_logger.info(f"未找到{section_title}表")
            else:
                main_tables[section_title] = tables[0]   
        return main_tables

    def close(self):
        self.doc.close()

# ============ 使用示例 ============
if __name__ == "__main__":
    pdf_file = "./data/raw_pdfs/佰仁医疗_2024.pdf"
    section_title = r"财务报告"  # 支持正则匹配
    next_section_pattern = r"第十一节"  # 可选：用于精确定位结束页
    
    extractor = PDFChapterExtractor(pdf_file)
    try:
        tables = extractor.extract_main_tables()
        
        print(f"\n共提取 {len(tables)} 个表格（含跨页合并）:\n")
        for idx, tbl in enumerate(tables, 1):
            status = " [跨页合并]" if tbl.is_merged else ""
            page_range = f"第 {tbl.page_start_num + 1} 页" if tbl.page_start_num == tbl.page_end_num else f"第 {tbl.page_start_num + 1}-{tbl.page_end_num + 1} 页"
            # 打印前3行预览
            for i, row in enumerate(tbl.table_data[:3]):
                print(f"    行{i}: {row[:5]}{'...' if len(row)>5 else ''}")
    finally:
        extractor.close()
