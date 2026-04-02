"""
chapter_extractor.py     # 负责识别和提取 PDF 指定章节

使用fitz.open().get_toc()的方式定位章节位置和表格关系。
支持异步并行解析以加快处理速度。
"""
import re
import fitz  # PyMuPDF
from typing import List, Tuple, Dict, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import os

from src.utils.logger import chapter_logger
from src.db.table_models import TableWithHeader

class PDFChapterExtractor:
    def __init__(self, pdf_path: str):
        self.doc = fitz.open(pdf_path)
        self.toc = self.doc.get_toc()
        self.page_heights = [page.rect.height for page in self.doc]
        
    def get_company_info(self):
        """
        从PDF文档第一页中提取公司名称、公司代码和年份
        :return: tuple of (company_name, company_code, year)
        """
        page = self.doc[0]  # 第一页
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
        
        return company_name, company_short_name, company_code, year, report_period

    
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

    def _is_header_or_footer(self, text_block: Dict, page_height: float,
                              header_ratio: float = 0.10,
                              footer_ratio: float = 0.10) -> bool:
        """
        判断文本块是否为页眉或页脚
        
        :param text_block: 文本块字典，包含 bbox、y_top、y_bottom 等信息
        :param page_height: 页面高度
        :param header_ratio: 页眉区域占页面高度的比例，默认顶部10%
        :param footer_ratio: 页脚区域占页面高度的比例，默认底部10%
        :return: True 表示是页眉或页脚，False 表示不是
        """
        y_top = text_block["y_top"]
        y_bottom = text_block["y_bottom"]
        
        header_threshold = page_height * header_ratio
        footer_threshold = page_height * (1 - footer_ratio)
        
        # 页眉区域：文本块顶部在页眉阈值内
        is_header = y_top < header_threshold
        
        # 页脚区域：文本块底部在页脚阈值内
        is_footer = y_bottom > footer_threshold
        
        return is_header or is_footer

    def _is_in_table(self, bbox: Tuple[float, float, float, float], table_bboxes: List[Tuple[float, float, float, float]], overlap_threshold: float = 0.5) -> bool:
        """
        判断文本块是否位于表格区域内
        
        :param bbox: 文本块的边界框 (x0, y0, x1, y1)
        :param table_bboxes: 表格边界框列表
        :param overlap_threshold: 重叠面积比例阈值，超过此值认为文本块属于表格
        :return: True 表示文本块在表格内，False 表示不在
        """
        if not table_bboxes:
            return False
        
        text_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if text_area == 0:
            return False
        
        for table_bbox in table_bboxes:
            # 计算重叠区域
            x_overlap = max(0, min(bbox[2], table_bbox[2]) - max(bbox[0], table_bbox[0]))
            y_overlap = max(0, min(bbox[3], table_bbox[3]) - max(bbox[1], table_bbox[1]))
            overlap_area = x_overlap * y_overlap
            
            # 如果重叠面积占文本块面积的50%以上，认为属于表格
            if overlap_area / text_area >= overlap_threshold:
                return True
        
        return False

    def extract_page_elements(self, page_num: int) -> Tuple[List[Dict], List]:
        """
        提取单页的文本块和表格（过滤页眉、页脚和表格区域内的文本）
        :return: (文本块列表, 表格列表)
        """
        page = self.doc[page_num]
        page_height = page.rect.height
        blocks = page.get_text("dict")["blocks"]
        
        # 先提取表格，获取表格边界框列表（用于过滤文本块）
        table_bboxes = []
        tables = []
        try:
            tabs = page.find_tables()
            for tab in tabs:
                if tab.header and tab.cells:  # 有效表格
                    table_bboxes.append(tab.bbox)
                    tables.append({
                        "table": tab,
                        "bbox": tab.bbox,  # (x0, y0, x1, y1)
                        "y_top": tab.bbox[1],
                        "y_bottom": tab.bbox[3],
                        "col_count": len(tab.header.cells) if tab.header else 0
                    })
        except Exception as e:
            chapter_logger.warning(f"页面 {page_num} 表格提取失败: {e}")
        
        # 提取文本块（过滤图片、页眉页脚和表格区域内的文本）
        text_blocks = []
        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        if span["text"].strip() == "":
                            continue
                        text_block = {
                            "text": span["text"].strip(),
                            "bbox": span["bbox"],  # (x0, y0, x1, y1)
                            "y_top": span["bbox"][1],   # top y
                            "y_bottom": span["bbox"][3] # bottom y
                        }
                        # 过滤页眉和页脚
                        if self._is_header_or_footer(text_block, page_height):
                            continue
                        # 过滤表格区域内的文本（避免重复）
                        if self._is_in_table(span["bbox"], table_bboxes):
                            continue
                        text_blocks.append(text_block)
        
        # 按 y 坐标（从上到下）和 x 坐标（从左到右）排序文本块
        # 使用 y 坐标容差（5像素）来判断是否在同一行
        def sort_key(block):
            y_top = block["y_top"]
            x_left = block["bbox"][0]
            # 将 y 坐标分组，同一行（容差5px）的文本按 x 坐标排序
            y_group = round(y_top / 5)
            return (y_group, x_left)

        text_blocks.sort(key=sort_key)
        tables.sort(key=lambda t: t["y_top"])
        
        return text_blocks, tables

    def associate_header_with_table(self, text_blocks: List[Dict], table: Dict, 
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

            # 从 header_text 中提取单位（货币单位，如千元、万元、美元等）
            # 匹配 "单位：XXX 币种" 的模式，排除"编制单位"
            unit_match = re.search(r'(?<!编制)单位[：:]\s*([千百万美港元欧元\d元]+)', current.header_text)
            if unit_match and not current.unit:
                current.unit = unit_match.group(1).strip()
            #
            currency_match = re.search(r'币种[：:]\s*([A-Za-z人民币港元美元欧元]+)', current.header_text)
            if currency_match and not current.currency:
                current.currency = currency_match.group(1).strip()

            merged_tables.append(current)
            i = j  # 跳过已合并的表格
        
        if (len(merged_tables) == 1 and start_page == merged_tables[0].page_start_num - 1) or (len(merged_tables) > 1 and start_page == merged_tables[-2].page_start_num - 1):
            # 第一个表的表头在start_page页的底部
            # 从start_page页提取文本块
            text_blocks, _ = self.extract_page_elements(start_page)
            
            # 获取最后10个非空的行
            bottom_text_blocks = []
            len_i = 10
            for i in range(len(text_blocks) - 1, -1, -1):
                block = text_blocks[i]["text"]
                if block != "":
                    bottom_text_blocks.append(block)
                    len_i -= 1
                if len_i == 0:
                    break
            
            # 按Y坐标排序，从下到上
            bottom_text_blocks = bottom_text_blocks[::-1]
            
            # 组合表头文本
            if bottom_text_blocks:
                new_header_text = "\n".join(bottom_text_blocks)  # 使用最后3个文本块
                # 更新第一个表格的表头
                merged_tables[0].header_text = new_header_text + merged_tables[0].header_text

        return merged_tables
    
    def extract_section_tables(self, section_title: str, section_level: int = 1) -> List[TableWithHeader]:
        """
        提取指定章节的所有表格
        """
        start_page, end_page = self.find_section_range(section_title, section_level=section_level)
        tables = self.extract_tables_in_section(start_page, end_page)
        return tables

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

    def _extract_core_title(self, title: str) -> str:
        """
        从章节标题中提取核心标题部分（去掉"第X节"等前缀）
        
        例如：
        - "第九节 债券相关情况" -> "债券相关情况"
        - "第一节 释义" -> "释义"
        - "第三节 管理层讨论与分析" -> "管理层讨论与分析"
        
        :param title: 原始章节标题
        :return: 核心标题部分
        """
        import re
        # 匹配"第X节"或"第X章"等前缀，并提取后面的内容
        patterns = [
            r'^第[一二三四五六七八九十百千\d]+节\s*[、.\s]*\s*(.+)$',  # 第九节 债券相关情况
            r'^第[一二三四五六七八九十百千\d]+章\s*[、.\s]*\s*(.+)$',  # 第一章 xxx
            r'^\d+[、.\s]+(.+)$',  # 1. 释义 或 1、释义
        ]
        
        for pattern in patterns:
            match = re.match(pattern, title.strip())
            if match:
                return match.group(1).strip()
        
        # 如果没有匹配到前缀，返回原标题
        return title.strip()

    def _find_title_y_position(self, page_num: int, title: str) -> Optional[float]:
        """
        在指定页面中查找标题文本的 y 坐标位置
        
        支持以下匹配策略（按优先级排序）：
        1. 完整标题匹配（如 "第九节 债券相关情况"）
        2. 核心标题匹配（如 "债券相关情况"）
        3. 部分匹配（标题包含在页面文本中）
        
        :param page_num: 页码（从0开始）
        :param title: 标题文本
        :return: 标题的 y_top 坐标，如果未找到则返回 None
        """
        if page_num < 0 or page_num >= len(self.doc):
            return None
        
        page = self.doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        # 准备标题变体
        clean_title = title.strip()
        core_title = self._extract_core_title(clean_title)
        
        # 收集所有候选匹配
        candidates = []
        
        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue
                        
                        y_pos = span["bbox"][1]
                        match_score = 0
                        
                        # 优先级1：完整标题完全匹配或页面文本以完整标题开头
                        if text == clean_title or text.startswith(clean_title):
                            match_score = 100
                        # 优先级2：核心标题完全匹配或页面文本以核心标题开头
                        elif text == core_title or text.startswith(core_title):
                            match_score = 80
                        # 优先级3：完整标题包含在页面文本中
                        elif clean_title in text:
                            match_score = 60
                        # 优先级4：核心标题包含在页面文本中
                        elif core_title in text and core_title != clean_title:
                            match_score = 40
                        # 优先级5：页面文本包含在标题中（较少见）
                        elif text in clean_title and len(text) >= 3:
                            match_score = 20
                        
                        if match_score > 0:
                            candidates.append((match_score, y_pos, text))
        
        if not candidates:
            return None
        
        # 按匹配分数降序排序，返回最高分的y坐标
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_match = candidates[0]
        
        chapter_logger.debug(f"标题匹配: '{clean_title}' -> 找到 '{best_match[2]}' (分数: {best_match[0]}) at y={best_match[1]}")
        
        return best_match[1]

    @staticmethod
    def _extract_single_chapter(args: Tuple) -> Optional[Dict]:
        """
        静态方法：提取单个章节的内容（用于进程池并行处理）
        
        :param args: 包含以下元素的元组：
            - pdf_path: PDF 文件路径
            - toc_idx: TOC 索引
            - entry: TOC 条目 (level, title, page_num)
            - toc_list: 完整 TOC 列表
            - total_pages: 文档总页数
        :return: 章节字典或 None
        """
        pdf_path, toc_idx, entry, toc_list, total_pages = args
        level, title, start_page = entry[0], entry[1], entry[2] - 1
        
        # 在每个进程中独立打开文档（PyMuPDF 不是线程安全的）
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            chapter_logger.error(f"无法打开 PDF 文件 {pdf_path}: {e}")
            return None
        
        try:
            # 确定结束页：下一个同级或更高层级的起始页，或文档末尾
            end_page = total_pages - 1
            for next_idx, next_entry in enumerate(toc_list[toc_idx + 1:], start=toc_idx + 1):
                if next_entry[0] <= level:  # 同级或更高级别
                    end_page = next_entry[2] - 2  # 前一页
                    break
            
            chapter_logger.info(f"[并行] 提取章节: [{level}] {title}, 页码范围: {start_page}-{end_page}")
            
            # 创建临时 extractor 实例用于调用辅助方法
            extractor = PDFChapterExtractor.__new__(PDFChapterExtractor)
            extractor.doc = doc
            extractor.toc = toc_list
            extractor.page_heights = [page.rect.height for page in doc]
            
            # 提取章节内容
            content_parts = []
            content_parts.append(f"# {'#' * level} {title}\n")
            
            # 获取起始页章节标题的 y 坐标
            start_y = extractor._find_title_y_position(start_page, title)
            
            # 获取下一章节信息
            next_chapter_page = None
            next_chapter_y = None
            for next_idx, next_entry in enumerate(toc_list[toc_idx + 1:], start=toc_idx + 1):
                if next_entry[0] <= level:
                    next_chapter_page = next_entry[2] - 1
                    next_chapter_y = extractor._find_title_y_position(next_chapter_page, next_entry[1])
                    break
            
            # 提取每页的文本和表格
            all_elements = []
            for page_num in range(start_page, min(end_page + 1, total_pages)):
                text_blocks, tables = extractor.extract_page_elements(page_num)
                
                # 确定当前页的有效 y 范围
                page_min_y = None
                page_max_y = None
                
                if page_num == start_page and start_y is not None:
                    page_min_y = start_y
                
                if page_num == end_page:
                    if next_chapter_page is not None and next_chapter_page == end_page and next_chapter_y is not None:
                        page_max_y = next_chapter_y
                
                # 添加文本块
                for block in text_blocks:
                    block_y = block["y_top"]
                    if page_min_y is not None and block_y < page_min_y:
                        continue
                    if page_max_y is not None and block_y >= page_max_y:
                        continue
                    all_elements.append((block["y_top"], block["bbox"][0], "text", block["text"], page_num))
                
                # 添加表格
                for tab in tables:
                    tab_y = tab["y_top"]
                    if page_min_y is not None and tab_y < page_min_y:
                        continue
                    if page_max_y is not None and tab_y >= page_max_y:
                        continue
                    table_data = tab["table"].extract()
                    table_md = extractor._table_to_markdown(table_data)
                    all_elements.append((tab["y_top"], tab["bbox"][0], "table", table_md, page_num))
            
            # 排序并组装内容
            def element_sort_key(elem):
                y_top = elem[0]
                x_left = elem[1]
                page_num = elem[4]
                y_group = round(y_top / 5)
                return (page_num, y_group, x_left)
            
            all_elements.sort(key=element_sort_key)
            
            current_page = None
            for y_top, x_left, elem_type, content, page_num in all_elements:
                if current_page != page_num:
                    current_page = page_num
                content_parts.append(content)
            
            full_content = "\n\n".join(content_parts)
            
            chapter = {
                "level": level,
                "title": title,
                "content": full_content,
                "page_range": (start_page, end_page)
            }
            
            return chapter
            
        except Exception as e:
            chapter_logger.error(f"提取章节 '{title}' 时出错: {e}")
            return None
        finally:
            doc.close()

    def extract_all_chapters(
        self,
        save_md: bool = False,
        output_dir: str = "data/output",
        min_level: int = 1,
        max_level: int = 1,
        max_workers: Optional[int] = None,
        use_parallel: bool = True
    ) -> List[Dict]:
        """
        按 TOC 的层级结构提取所有章节内容（文本+表格），保存为 chunk 文档。
        只提取 level 为 1 的一级章节。
        支持并行处理以加快解析速度。

        :param save_md: 是否将每个章节保存为 .md 文件
        :param output_dir: .md 文件的输出目录（仅在 save_md=True 时有效）
        :param min_level: 提取的最小层级（默认为1，即只提取一级章节）
        :param max_level: 提取的最大层级（默认为1，即只提取一级章节）
        :param max_workers: 并行工作进程数，默认为 CPU 核心数
        :param use_parallel: 是否使用并行处理，默认为 True
        :return: 章节内容列表，每个元素为 {"level": int, "title": str, "content": str, "page_range": Tuple[int, int]}
        """
        from pathlib import Path
        
        chapters = []
        total_pages = len(self.doc)
        pdf_path = self.doc.name
        
        # 只提取 level 为 1 的 TOC 条目（一级章节）
        filtered_toc = [
            (idx, entry) for idx, entry in enumerate(self.toc)
            if entry[0] == 1
        ]

        if not filtered_toc:
            chapter_logger.warning("TOC 中未找到 level 为 1 的一级章节")
            return chapters
        
        # 创建输出目录
        if save_md:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        if use_parallel and len(filtered_toc) > 1:
            # 使用并行处理
            chapter_logger.info(f"使用并行模式处理 {len(filtered_toc)} 个章节，工作进程数: {max_workers or 'CPU核心数'}")
            
            # 准备任务参数
            task_args = [
                (pdf_path, toc_idx, entry, self.toc, total_pages)
                for toc_idx, entry in filtered_toc
            ]
            
            # 使用进程池并行处理
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._extract_single_chapter, args): args for args in task_args}
                
                for future in as_completed(futures):
                    try:
                        chapter = future.result()
                        if chapter:
                            chapters.append(chapter)
                    except Exception as e:
                        toc_idx, entry = futures[future][0], futures[future][1]
                        chapter_logger.error(f"处理章节 '{entry[1]}' 时出错: {e}")
            
            # 按 TOC 顺序排序结果
            chapters.sort(key=lambda x: next(
                (i for i, (idx, entry) in enumerate(filtered_toc) if entry[1] == x["title"]),
                float('inf')
            ))
            
        else:
            # 使用串行处理
            chapter_logger.info(f"使用串行模式处理 {len(filtered_toc)} 个章节")
            
            for toc_idx, entry in filtered_toc:
                args = (pdf_path, toc_idx, entry, self.toc, total_pages)
                chapter = self._extract_single_chapter(args)
                if chapter:
                    chapters.append(chapter)
        
        # 保存为 md 文件
        if save_md:
            for chapter in chapters:
                safe_title = re.sub(r'[\\/*?:"<>|]', '_', chapter["title"])
                md_path = os.path.join(output_dir, f"{safe_title}.md")
                
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(chapter["content"])
                
                chapter_logger.info(f"已保存章节到: {md_path}")
        
        chapter_logger.info(f"共提取 {len(chapters)} 个章节")
        return chapters
    
    def _table_to_markdown(self, table_data: List[List[str]]) -> str:
        """
        将表格数据转换为 Markdown 格式
        
        :param table_data: 二维列表，表格数据
        :return: Markdown 格式的表格字符串
        """
        if not table_data:
            return ""
        
        # 清理单元格内容中的换行符
        cleaned_data = []
        for row in table_data:
            cleaned_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
            cleaned_data.append(cleaned_row)
        
        # 计算每列最大宽度
        if not cleaned_data:
            return ""
        
        col_count = max(len(row) for row in cleaned_data)
        
        # 构建Markdown表格
        lines = []
        
        # 表头
        if cleaned_data:
            header = cleaned_data[0]
            # 补齐列数
            while len(header) < col_count:
                header.append("")
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * col_count) + " |")
            
            # 数据行
            for row in cleaned_data[1:]:
                while len(row) < col_count:
                    row.append("")
                lines.append("| " + " | ".join(row) + " |")
        
        return "\n".join(lines)

    def _extract_table_units(self, table_data: List[List[str]]) -> Tuple[str, Dict[int, str]]:
        """
        从表格数据中提取单位信息

        表格的单位信息通常出现在以下位置：
        1. 表头行中的括号内，如 "金额（万元）"、"比率（%）"
        2. 表头行中的"单位："或"金额单位："等标注
        3. 第一列的项目名称中包含单位

        :param table_data: 表格数据（二维列表）
        :return: (整体单位, 每列单位字典) 整体单位为空字符串表示无统一单位
        """
        if not table_data or len(table_data) == 0:
            return "", {}

        # 常见的单位模式
        unit_patterns = [
            r'（([^）]+)）',  # 中文括号：金额（万元）
            r'\(([^)]+)\)',  # 英文括号：Amount(USD)
            r'单位[：:]\s*([^，,。\n]+)',  # 单位：万元
            r'金额单位[：:]\s*([^，,。\n]+)',  # 金额单位：万元
        ]

        overall_unit = ""  # 整体单位（如表格通用的"万元"）
        column_units: Dict[int, str] = {}  # 每列的具体单位

        # 获取表头行（通常是第一行）
        header_row = table_data[0] if table_data else []

        # 首先检查表头行是否有整体单位标注（如"金额（万元）"）
        header_text = " ".join(str(cell) for cell in header_row)

        for pattern in unit_patterns:
            matches = re.findall(pattern, header_text)
            if matches:
                # 取最长的匹配作为单位（避免短单位被长单位包含）
                longest_match = max(matches, key=len)
                if longest_match.strip() and longest_match not in ["", "0"]:
                    # 检查是否是有效的单位
                    if any(u in longest_match for u in ["万", "亿", "元", "%", "比率", "比例", "USD", "HKD", "EUR"]):
                        overall_unit = longest_match.strip()
                        break

        # 检查每列的单位（通常是第二行或表头行中的括号内容）
        if len(table_data) > 1:
            second_row = table_data[1]
            for col_idx, cell in enumerate(second_row):
                cell_text = str(cell).strip()
                for pattern in unit_patterns:
                    matches = re.findall(pattern, cell_text)
                    if matches:
                        for match in matches:
                            if match.strip() and match not in ["", "0"]:
                                if any(u in match for u in ["万", "亿", "元", "%", "USD", "HKD", "EUR"]):
                                    column_units[col_idx] = match.strip()
                                    break

        # 如果没有找到列单位，但有整体单位，则所有数值列使用整体单位
        if not column_units and overall_unit:
            # 假设从第二列开始是数值列
            for col_idx in range(1, len(header_row)):
                column_units[col_idx] = overall_unit

        chapter_logger.debug(f"提取表格单位: 整体={overall_unit}, 列单位={column_units}")
        return overall_unit, column_units

    def close(self):
        self.doc.close()
