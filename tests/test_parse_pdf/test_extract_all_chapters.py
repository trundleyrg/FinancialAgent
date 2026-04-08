"""
测试用例：测试 PDFChapterExtractor.extract_all_chapters 方法

测试功能：
1. 基本功能测试 - 提取所有章节内容
2. save_md 参数测试 - 保存为 Markdown 文件
3. 层级过滤测试 - min_level 和 max_level 参数
4. 表格转换测试 - 表格转 Markdown 功能
5. 边界条件测试 - 空 TOC、无效参数等

运行方式：
    # 直接运行（不需要 pytest）
    python tests/test_extract_all_chapters.py

    # 或使用 pytest
    pytest tests/test_extract_all_chapters.py -v
"""

import os
import sys
import shutil
from typing import List, Dict

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.chapter_extractor import PDFChapterExtractor


class TestExtractAllChapters:
    """章节提取测试类"""

    # 测试 PDF 文件路径
    TEST_PDF_PATH = "./data/000423/东阿阿胶_000423_2018.pdf"

    # 输出目录
    OUTPUT_DIR = "./data/output/test_chapters"

    def __init__(self):
        """初始化测试实例"""
        self._chapters = None
        self._extractor = None

    def setup(self):
        """测试前的设置"""
        print("\n" + "=" * 70)
        print("开始测试：extract_all_chapters 方法")
        print("=" * 70)

        # 清理并创建输出目录
        if os.path.exists(self.OUTPUT_DIR):
            shutil.rmtree(self.OUTPUT_DIR)
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    def teardown(self):
        """测试后的清理"""
        if self._extractor:
            self._extractor.close()
        
        # 可选：清理输出目录
        # if os.path.exists(self.OUTPUT_DIR):
        #     shutil.rmtree(self.OUTPUT_DIR)
        
        print("\n" + "=" * 70)
        print("测试完成")
        print("=" * 70)

    def assert_true(self, condition, message=""):
        """断言为真"""
        if not condition:
            raise AssertionError(f"断言失败: {message}")

    def assert_not_none(self, value, message=""):
        """断言不为 None"""
        if value is None:
            raise AssertionError(f"值不应为 None: {message}")

    def assert_equal(self, actual, expected, message=""):
        """断言相等"""
        if actual != expected:
            raise AssertionError(f"{message}\n期望: {expected}\n实际: {actual}")

    def assert_greater(self, actual, min_value, message=""):
        """断言大于"""
        if actual <= min_value:
            raise AssertionError(f"{message}\n期望 > {min_value}\n实际: {actual}")

    def assert_less_equal(self, actual, max_value, message=""):
        """断言小于等于"""
        if actual > max_value:
            raise AssertionError(f"{message}\n期望 <= {max_value}\n实际: {actual}")

    # ============================================================
    # 测试1：基本功能测试
    # ============================================================
    def test_basic_extraction(self):
        """
        测试1：基本功能测试
        目标：验证 extract_all_chapters 能正确提取所有章节
        """
        print("\n" + "-" * 70)
        print("测试1：基本功能测试")
        print("-" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            print("跳过测试")
            return False

        self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)

        try:
            # 提取所有章节（不保存文件）
            chapters = self._extractor.extract_all_chapters(save_md=False)

            # 验证返回结果类型
            self.assert_not_none(chapters, "返回结果不能为 None")
            self.assert_true(isinstance(chapters, list), "返回结果应该是列表类型")

            print(f"\n[OK] 成功提取章节，共 {len(chapters)} 个章节")

            # 验证章节数量合理（年报通常有多个章节）
            self.assert_greater(len(chapters), 5, "年报应该有多个章节")

            # 验证每个章节的结构
            for i, chapter in enumerate(chapters):
                self.assert_true(isinstance(chapter, dict), f"章节 {i} 应该是字典类型")
                self.assert_true("level" in chapter, f"章节 {i} 应该包含 'level' 字段")
                self.assert_true("title" in chapter, f"章节 {i} 应该包含 'title' 字段")
                self.assert_true("content" in chapter, f"章节 {i} 应该包含 'content' 字段")
                self.assert_true("page_range" in chapter, f"章节 {i} 应该包含 'page_range' 字段")

                # 验证字段值
                self.assert_true(isinstance(chapter["level"], int), f"章节 {i} 的 level 应该是整数")
                self.assert_true(isinstance(chapter["title"], str), f"章节 {i} 的 title 应该是字符串")
                self.assert_true(isinstance(chapter["content"], str), f"章节 {i} 的 content 应该是字符串")
                self.assert_true(isinstance(chapter["page_range"], tuple), f"章节 {i} 的 page_range 应该是元组")
                self.assert_equal(len(chapter["page_range"]), 2, f"章节 {i} 的 page_range 应该包含 2 个元素")

                # 打印部分章节信息
                if i < 5 or chapter["level"] == 1:
                    level = chapter["level"]
                    title = chapter["title"]
                    start_page, end_page = chapter["page_range"]
                    content_len = len(chapter["content"])
                    print(f"  [{level}] {title[:30]}... (页 {start_page}-{end_page}, 内容长度: {content_len})")

            # 保存章节供后续测试使用
            self._chapters = chapters

            print("\n[OK] 测试1 完成：基本功能测试通过")
            return True

        finally:
            if self._extractor:
                self._extractor.close()

    # ============================================================
    # 测试2：save_md 参数测试
    # ============================================================
    def test_save_md_option(self):
        """
        测试2：save_md 参数测试
        目标：验证 save_md=True 时能正确保存 Markdown 文件
        """
        print("\n" + "-" * 70)
        print("测试2：save_md 参数测试")
        print("-" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            print("跳过测试")
            return False

        self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)

        try:
            # 使用自定义输出目录
            test_output_dir = os.path.join(self.OUTPUT_DIR, "md_test")

            # 提取章节并保存为 MD 文件
            chapters = self._extractor.extract_all_chapters(
                save_md=True,
                output_dir=test_output_dir
            )

            print(f"\n[OK] 成功提取 {len(chapters)} 个章节")

            # 验证输出目录存在
            self.assert_true(os.path.exists(test_output_dir), f"输出目录应该存在: {test_output_dir}")

            # 验证 MD 文件数量
            md_files = [f for f in os.listdir(test_output_dir) if f.endswith('.md')]
            self.assert_equal(len(md_files), len(chapters), "MD 文件数量应该与章节数量一致")

            print(f"[OK] 已生成 {len(md_files)} 个 Markdown 文件")

            # 验证 MD 文件内容
            for md_file in md_files[:3]:  # 只检查前 3 个文件
                md_path = os.path.join(test_output_dir, md_file)
                
                # 验证文件存在且可读
                self.assert_true(os.path.exists(md_path), f"MD 文件应该存在: {md_path}")
                
                # 验证文件大小
                file_size = os.path.getsize(md_path)
                self.assert_greater(file_size, 0, f"MD 文件大小应该大于 0: {md_path}")
                
                # 读取并验证文件内容
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.assert_true(len(content) > 0, f"MD 文件内容不应为空: {md_file}")
                    
                    # 验证文件以标题开头
                    self.assert_true(content.startswith('#'), f"MD 文件应该以标题开头: {md_file}")

                print(f"  - {md_file}: {file_size} 字节")

            print("\n[OK] 测试2 完成：save_md 参数测试通过")
            return True

        finally:
            if self._extractor:
                self._extractor.close()

    # ============================================================
    # 测试3：层级过滤测试
    # ============================================================
    def test_level_filtering(self):
        """
        测试3：层级过滤测试
        目标：验证 min_level 和 max_level 参数能正确过滤章节
        """
        print("\n" + "-" * 70)
        print("测试3：层级过滤测试")
        print("-" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            print("跳过测试")
            return False

        self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)

        try:
            # 测试提取 Level 1 章节
            print("\n测试 min_level=1, max_level=1 (仅提取 Level 1 章节)")
            chapters_level_1 = self._extractor.extract_all_chapters(
                save_md=False,
                min_level=1,
                max_level=1
            )
            
            print(f"[OK] 提取到 {len(chapters_level_1)} 个 Level 1 章节")
            
            # 验证所有章节的 level 都是 1
            for chapter in chapters_level_1:
                self.assert_equal(chapter["level"], 1, f"所有章节的 level 应该是 1: {chapter['title']}")
            
            # 测试提取 Level 1-2 章节
            print("\n测试 min_level=1, max_level=2 (提取 Level 1-2 章节)")
            chapters_level_1_2 = self._extractor.extract_all_chapters(
                save_md=False,
                min_level=1,
                max_level=2
            )
            
            print(f"[OK] 提取到 {len(chapters_level_1_2)} 个 Level 1-2 章节")
            
            # 验证所有章节的 level 在 1-2 范围内
            for chapter in chapters_level_1_2:
                self.assert_true(
                    1 <= chapter["level"] <= 2,
                    f"章节 level 应该在 1-2 范围内: {chapter['title']} (level={chapter['level']})"
                )
            
            # 验证 Level 1-2 章节数量 >= Level 1 章节数量
            self.assert_true(
                len(chapters_level_1_2) >= len(chapters_level_1),
                "Level 1-2 章节数量应该 >= Level 1 章节数量"
            )

            # 测试提取 Level 3 章节
            print("\n测试 min_level=3, max_level=3 (仅提取 Level 3 章节)")
            chapters_level_3 = self._extractor.extract_all_chapters(
                save_md=False,
                min_level=3,
                max_level=3
            )
            
            print(f"[OK] 提取到 {len(chapters_level_3)} 个 Level 3 章节")
            
            # 验证所有章节的 level 都是 3
            for chapter in chapters_level_3:
                self.assert_equal(chapter["level"], 3, f"所有章节的 level 应该是 3: {chapter['title']}")

            print("\n[OK] 测试3 完成：层级过滤测试通过")
            return True

        finally:
            if self._extractor:
                self._extractor.close()

    # ============================================================
    # 测试4：表格转换测试
    # ============================================================
    def test_table_to_markdown(self):
        """
        测试4：表格转换测试
        目标：验证表格能正确转换为 Markdown 格式
        """
        print("\n" + "-" * 70)
        print("测试4：表格转换测试")
        print("-" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            print("跳过测试")
            return False

        self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)

        try:
            # 提取章节
            chapters = self._extractor.extract_all_chapters(save_md=False)

            # 查找包含表格的章节（通常财务报表章节会有表格）
            table_keywords = ["资产负债表", "利润表", "现金流量表", "财务报表"]
            chapters_with_tables = []
            
            for chapter in chapters:
                content = chapter["content"]
                # 检查是否包含 Markdown 表格格式
                if "|" in content and "---" in content:
                    chapters_with_tables.append(chapter)
                # 或者章节标题包含财务报表相关关键词
                elif any(keyword in chapter["title"] for keyword in table_keywords):
                    chapters_with_tables.append(chapter)

            print(f"\n[OK] 找到 {len(chapters_with_tables)} 个可能包含表格的章节")

            # 验证至少找到了一些包含表格的章节
            self.assert_greater(len(chapters_with_tables), 0, "应该找到包含表格的章节")

            # 验证表格格式
            for chapter in chapters_with_tables[:3]:  # 只检查前 3 个
                content = chapter["content"]
                
                # 检查 Markdown 表格格式
                lines = content.split('\n')
                table_lines = [line for line in lines if line.strip().startswith('|')]
                
                if table_lines:
                    print(f"\n  章节: {chapter['title'][:30]}...")
                    print(f"    - 表格行数: {len(table_lines)}")
                    
                    # 验证表格分隔线
                    has_separator = any('---' in line for line in table_lines)
                    self.assert_true(has_separator, "表格应该包含分隔线 (---)")
                    
                    # 打印表格预览
                    print(f"    - 表格预览:")
                    for line in table_lines[:3]:
                        print(f"      {line[:60]}...")

            print("\n[OK] 测试4 完成：表格转换测试通过")
            return True

        finally:
            if self._extractor:
                self._extractor.close()

    # ============================================================
    # 测试5：内容完整性测试
    # ============================================================
    def test_content_integrity(self):
        """
        测试5：内容完整性测试
        目标：验证章节内容包含文本和表格，且页码范围合理
        """
        print("\n" + "-" * 70)
        print("测试5：内容完整性测试")
        print("-" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            print("跳过测试")
            return False

        self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)

        try:
            # 提取章节
            chapters = self._extractor.extract_all_chapters(save_md=False)

            total_pages = len(self._extractor.doc)
            print(f"\n文档总页数: {total_pages}")

            for i, chapter in enumerate(chapters):
                start_page, end_page = chapter["page_range"]
                
                # 验证页码范围有效
                self.assert_greater(start_page, -1, f"起始页码应该 >= 0: {chapter['title']}")
                self.assert_less_equal(end_page, total_pages - 1, f"结束页码应该 <= 文档总页数: {chapter['title']}")
                self.assert_true(start_page <= end_page, f"起始页应该 <= 结束页: {chapter['title']}")
                
                # 验证内容长度
                content = chapter["content"]
                self.assert_greater(len(content), 0, f"章节内容不应为空: {chapter['title']}")
                
                # 验证内容包含章节标题
                self.assert_true(
                    chapter["title"] in content or f"# {chapter['title']}" in content,
                    f"章节内容应该包含章节标题: {chapter['title']}"
                )

            print(f"\n[OK] 所有 {len(chapters)} 个章节的页码范围和内容验证通过")
            print("\n[OK] 测试5 完成：内容完整性测试通过")
            return True

        finally:
            if self._extractor:
                self._extractor.close()

    # ============================================================
    # 测试6：_table_to_markdown 方法单独测试
    # ============================================================
    def test_table_to_markdown_method(self):
        """
        测试6：_table_to_markdown 方法单独测试
        目标：验证表格数据能正确转换为 Markdown 格式
        """
        print("\n" + "-" * 70)
        print("测试6：_table_to_markdown 方法单独测试")
        print("-" * 70)

        # 创建一个临时的 extractor 实例用于测试 _table_to_markdown 方法
        # 使用局部变量，避免影响 teardown
        temp_extractor = PDFChapterExtractor.__new__(PDFChapterExtractor)

        try:
            # 测试用例1：空表格
            result = temp_extractor._table_to_markdown([])
            self.assert_equal(result, "", "空表格应该返回空字符串")
            print("[OK] 空表格测试通过")

            # 测试用例2：简单表格
            table_data = [
                ["项目", "金额"],
                ["收入", "1000"],
                ["支出", "500"]
            ]
            result = temp_extractor._table_to_markdown(table_data)
            
            self.assert_true("| 项目 | 金额 |" in result, "表格应该包含表头")
            self.assert_true("| --- | --- |" in result, "表格应该包含分隔线")
            self.assert_true("| 收入 | 1000 |" in result, "表格应该包含数据行")
            print("[OK] 简单表格测试通过")
            print(f"\n生成的 Markdown:\n{result}")

            # 测试用例3：包含换行符的表格
            table_data_with_newlines = [
                ["项目", "说明"],
                ["项目A", "第一行\n第二行"],
                ["项目B", "正常说明"]
            ]
            result = temp_extractor._table_to_markdown(table_data_with_newlines)
            
            # 验证换行符被替换为空格
            self.assert_true("\n第二行" not in result, "换行符应该被替换")
            self.assert_true("第一行 第二行" in result, "换行符应该被替换为空格")
            print("\n[OK] 包含换行符的表格测试通过")

            # 测试用例4：不规则表格（列数不一致）
            table_data_irregular = [
                ["A", "B", "C"],
                ["1", "2"],
                ["x", "y", "z", "w"]
            ]
            result = temp_extractor._table_to_markdown(table_data_irregular)
            
            # 验证表格仍然能正常生成
            self.assert_true("| A | B | C |" in result, "表头应该正确")
            print("\n[OK] 不规则表格测试通过")

            print("\n[OK] 测试6 完成：_table_to_markdown 方法测试通过")
            return True

        finally:
            pass

    # ============================================================
    # 集成测试
    # ============================================================
    def test_integration(self):
        """
        集成测试：完整流程测试
        目标：验证所有功能能协同工作
        """
        print("\n" + "=" * 70)
        print("集成测试：完整流程测试")
        print("=" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            return False

        try:
            # 步骤1：提取所有章节
            print("\n--- 步骤1：提取所有章节 ---")
            self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)
            chapters = self._extractor.extract_all_chapters(
                save_md=False,
                min_level=1,
                max_level=3
            )
            print(f"[OK] 提取到 {len(chapters)} 个章节")
            self._extractor.close()

            # 步骤2：保存为 Markdown 文件
            print("\n--- 步骤2：保存为 Markdown 文件 ---")
            test_output_dir = os.path.join(self.OUTPUT_DIR, "integration_test")
            self._extractor = PDFChapterExtractor(self.TEST_PDF_PATH)
            chapters = self._extractor.extract_all_chapters(
                save_md=True,
                output_dir=test_output_dir,
                min_level=1,
                max_level=2
            )
            print(f"[OK] 已保存 {len(chapters)} 个章节到 {test_output_dir}")
            self._extractor.close()

            # 步骤3：验证文件
            print("\n--- 步骤3：验证 Markdown 文件 ---")
            md_files = [f for f in os.listdir(test_output_dir) if f.endswith('.md')]
            print(f"[OK] 找到 {len(md_files)} 个 Markdown 文件")

            # 验证至少有一些文件
            self.assert_greater(len(md_files), 0, "应该生成至少一个 Markdown 文件")

            print("\n[OK] 集成测试完成：所有功能正常")
            return True

        except Exception as e:
            print(f"\n[X] 集成测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            if self._extractor:
                self._extractor.close()


# ============================================================
# 主程序：运行所有测试
# ============================================================

def run_all_tests():
    """运行所有测试"""
    test = TestExtractAllChapters()
    test.setup()

    results = {
        "测试1：基本功能测试": False,
        "测试2：save_md 参数测试": False,
        "测试3：层级过滤测试": False,
        "测试4：表格转换测试": False,
        "测试5：内容完整性测试": False,
        "测试6：_table_to_markdown 方法测试": False,
        "集成测试": False
    }

    try:
        # 运行各个测试
        if test.test_basic_extraction():
            results["测试1：基本功能测试"] = True

        if test.test_save_md_option():
            results["测试2：save_md 参数测试"] = True

        if test.test_level_filtering():
            results["测试3：层级过滤测试"] = True

        if test.test_table_to_markdown():
            results["测试4：表格转换测试"] = True

        if test.test_content_integrity():
            results["测试5：内容完整性测试"] = True

        if test.test_table_to_markdown_method():
            results["测试6：_table_to_markdown 方法测试"] = True

        if test.test_integration():
            results["集成测试"] = True

    except Exception as e:
        print(f"\n[X] 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

    test.teardown()

    # 打印测试结果摘要
    print("\n" + "=" * 70)
    print("测试结果摘要")
    print("=" * 70)
    for test_name, passed in results.items():
        status = "[OK] 通过" if passed else "[X] 失败"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\n[OK] 所有测试通过！")
    else:
        print("\n[X] 部分测试失败，请检查输出")

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
