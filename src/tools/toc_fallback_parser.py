"""
TOC Fallback Parser - 当 PyMuPDF 的 get_toc() 返回空时，尝试从 PDF 内容中解析目录
"""
import re
import fitz  # PyMuPDF
from typing import List, Tuple, Optional

from src.utils.logger import chapter_logger


class TOCFallbackParser:
    """
    当 PDF 的内置 TOC (get_toc()) 为空时，从 PDF 页面内容中解析目录结构

    返回格式与 get_toc() 一致: [[level, title, page], ...]
    level: 1 表示一级章节, 2 表示二级章节, 以此类推
    title: 章节标题
    page: 页码（从1开始，与 get_toc() 保持一致）
    """

    # 使用正则表达式匹配各级别章节标题
    # 一级章节: 第一节、第二节、...、第十二节、第十三节...
    LEVEL_1_PATTERN = re.compile(
        r'^第([一二三四五六七八九十百千零\d]+)节\s+(.+?)$'
    )

    # 二级章节: 一、二、三、...、十、十一、...
    LEVEL_2_PATTERN = re.compile(
        r'^([一二三四五六七八九十百千零]+、\s+)$'
    )

    # 三级章节: 1、2、3、...、10、11、...
    LEVEL_3_PATTERN = re.compile(
        r'^(\d+、.+?)$'
    )

    # 四级章节: （1）、（2）、...、（10）、... 或 (1)、(2)、...
    LEVEL_4_PATTERN = re.compile(
        r'^[\（\(]([^）\)]+)[\）\)]\s*(.+?)$'
    )

    # 章节标题级别映射
    CHAPTER_PATTERNS = [
        (1, LEVEL_1_PATTERN),
        (2, LEVEL_2_PATTERN),
        (3, LEVEL_3_PATTERN),
        (4, LEVEL_4_PATTERN),
    ]

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.toc: List[Tuple[int, str, int]] = []

    def parse(self) -> List[Tuple[int, str, int]]:
        """
        执行 TOC 解析主流程
        :return: [[level, title, page], ...]
        """
        # # 策略1: 查找"目录"页
        # toc_entries = self._find_toc_page()
        # if toc_entries:
        #     chapter_logger.info(f"[TOC Fallback] 通过目录页解析到 {len(toc_entries)} 个条目")
        #     self.toc = toc_entries
        #     return self.toc

        # 策略2: 扫描全文寻找章节标题
        toc_entries = self._scan_chapter_titles()
        if toc_entries:
            chapter_logger.info(f"[TOC Fallback] 通过扫描章节标题解析到 {len(toc_entries)} 个条目")
            self.toc = toc_entries
            return self.toc

        chapter_logger.warning(f"[TOC Fallback] 无法从 PDF 中解析出 TOC")
        self.toc = []
        return self.toc

    def _find_toc_page(self) -> List[Tuple[int, str, int]]:
        """
        查找并解析目录页
        :return: [(level, title, page), ...] 或空列表
        """
        for page_num in range(min(10, len(self.doc))):
            page = self.doc[page_num]
            text = page.get_text()
            text = text.lower()

            # 检查是否是目录页
            if any(kw in text for kw in ["目录", "TABLE OF CONTENTS", " CONTENTS ", "索引", "INDEX"]):
                entries = self._parse_toc_page(page_num, text)
                if entries:
                    return entries

        return []

    def _parse_toc_page(self, page_num: int, text: str) -> List[Tuple[int, str, int]]:
        """
        解析目录页内容
        :param page_num: 页码（从0开始）
        :param text: 页面文本
        :return: [(level, title, page), ...]
        """
        entries = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            entry = self._parse_toc_line(line, page_num)
            if entry:
                entries.append(entry)

        return entries

    def _parse_toc_line(self, line: str, base_page: int) -> Optional[Tuple[int, str, int]]:
        """
        使用正则表达式解析单行目录条目
        支持格式:
        - "第一节 释义" -> 1, "释义", 页码
        - "1. 释义" -> 1, "释义", 页码
        - "（一）释义" -> 2, "释义", 页码
        - "第一节 债券相关情况 ........ 10" -> 1, "债券相关情况", 10
        """
        # 清理 line，去除首尾空白
        line = line.strip()
        if not line:
            return None

        # 遍历各级别正则表达式进行匹配
        for level, pattern in self.CHAPTER_PATTERNS:
            match = pattern.match(line)
            if match:
                groups = match.groups()

                # 提取标题
                if level == 1:
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else self._extract_page_number(line, base_page)
                elif level == 2:
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else self._extract_page_number(line, base_page)
                elif level == 3:
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else self._extract_page_number(line, base_page)
                elif level == 4:
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else self._extract_page_number(line, base_page)
                else:
                    continue

                if not title:
                    return None

                return (level, title, page)

        return None

    def _extract_page_number(self, line: str, base_page: int) -> int:
        """
        从目录行中提取页码
        支持格式:
        - "第一节 释义" -> base_page + 1 (默认偏移)
        - "第一节 释义 10" -> 10
        - "第一节 释义 ... 10" -> 10
        - "1. 释义 ........................ 10" -> 10
        """
        # 去掉标题部分，只保留可能包含页码的后缀
        # 匹配行末尾的数字（页码）
        # 常见格式: " ........ 10" 或 " ... 10" 或 " 10"
        patterns = [
            r'[.。…\-_]{2,}\s*(\d+)\s*$',  # "........ 10" 或 ".... 10"
            r'\s+(\d+)\s*$',                 # " 10" 结尾
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    page = int(match.group(1))
                    # 验证页码合理性（1 到 文档总页数之间）
                    if 1 <= page <= len(self.doc):
                        return page
                except ValueError:
                    pass

        # 如果无法提取页码，使用 base_page 作为参考估算
        # 目录页通常是实际内容的前几页
        return max(1, base_page)

    def _scan_chapter_titles(self) -> List[Tuple[int, str, int]]:
        """
        扫描 PDF 所有页面，使用正则表达式匹配章节标题
        :return: [(level, title, page), ...]
        """
        entries = []

        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text = page.get_text()

            # 按行处理文本
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                entry = self._try_parse_chapter_title(line, page_num + 1)
                if entry:
                    # 避免重复条目
                    if entry not in entries:
                        entries.append(entry)

        # 按页码和级别排序
        entries.sort(key=lambda x: (x[2], x[0]))
        return entries

    def _try_parse_chapter_title(self, text: str, page_num: int) -> Optional[Tuple[int, str, int]]:
        """
        使用正则表达式解析章节标题
        :param text: 文本内容
        :param page_num: 页码（从1开始）
        :return: (level, title, page) 或 None
        """
        text = text.strip()
        if not text:
            return None

        # 遍历各级别正则表达式进行匹配
        for level, pattern in self.CHAPTER_PATTERNS:
            match = pattern.match(text)
            if match:
                groups = match.groups()

                # 根据不同级别提取标题和页码
                if level == 1:
                    # 第一组是章节编号，第二组是标题，第三组是页码（可选）
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else page_num
                elif level == 2:
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else page_num
                elif level == 3:
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else page_num
                elif level == 4:
                    # 第一组是编号内容，第二组是标题，第三组是页码（可选）
                    title = groups[1].strip() if len(groups) > 1 else ""
                    page = int(groups[2]) if len(groups) > 2 and groups[2] else page_num
                else:
                    continue

                # 过滤无效标题
                if not title or len(title) < 1:
                    continue

                # 过滤掉明显不是章节标题的内容
                skip_patterns = [
                    r'^\d+$',  # 纯数字
                    r'^[a-zA-Z]+$',  # 纯字母
                    r'^\d+\.\d+',  # 小数
                    r'^第\d+页',  # 页码标注
                ]
                for skip_pattern in skip_patterns:
                    if re.match(skip_pattern, title):
                        return None

                return (level, text, page)

        return None

    def close(self):
        self.doc.close()


def parse_toc_fallback(pdf_path: str) -> List[Tuple[int, str, int]]:
    """
    便捷函数：当 get_toc() 返回空时，尝试解析 PDF 的目录
    :param pdf_path: PDF 文件路径
    :return: [[level, title, page], ...] 或空列表
    """
    parser = TOCFallbackParser(pdf_path)
    try:
        return parser.parse()
    finally:
        parser.close()
