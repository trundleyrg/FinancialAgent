"""
测试用例：分步骤测试财报表格提取、保存和导出功能

测试步骤：
1. 调用 chapter_extractor 提取财报中的表格
2. 将表格保存在 duckdb 中
3. 导出 excel 作为备份验证，excel 按照表名保存在 data/output/excel 文件夹下

运行方式：
    # 直接运行（不需要 pytest）
    python tests/test_table_extraction_and_export.py

    # 或使用 pytest
    pytest tests/test_table_extraction_and_export.py -v
"""

import os
import sys
from typing import Dict, Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.chapter_extractor import PDFChapterExtractor, TableWithHeader
from src.db.db_connector import get_db, DatabaseConnector
from src.db.models import ReportPeriod


class TestTableExtractionAndExport:
    """表格提取和导出测试类"""

    # 测试 PDF 文件路径
    TEST_PDF_PATH = "./data/raw_pdfs/22.佰仁医疗2024年年报.pdf"

    # 从文件名提取的公司信息和年份
    COMPANY_NAME = "佰仁医疗"
    REPORT_YEAR = 2024
    REPORT_PERIOD = "FY"  # 年报

    # Excel 输出目录
    EXCEL_OUTPUT_DIR = "./data/output/excel"

    def __init__(self):
        """初始化测试实例"""
        self._extracted_tables = None
        self._db = None

    def setup(self):
        """测试前的设置"""
        print("\n" + "=" * 70)
        print("开始测试：财报表格提取、保存和导出")
        print("=" * 70)
        # 初始化数据库连接
        self._db = get_db(database_type='duckdb')

    def teardown(self):
        """测试后的清理"""
        if self._db:
            self._db.close()
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

    # ============================================================
    # 步骤1：提取表格
    # ============================================================
    def test_step1_extract_tables_from_pdf(self):
        """
        步骤1：测试从 PDF 中提取表格
        目标：验证 chapter_extractor 能正确提取财报中的主要表格
        """
        print("\n" + "-" * 70)
        print("步骤1：测试从 PDF 中提取表格")
        print("-" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            print("跳过步骤1测试")
            return False

        # 创建提取器实例
        extractor = PDFChapterExtractor(self.TEST_PDF_PATH)

        try:
            # 提取主要表格
            main_tables: Dict[str, Optional[TableWithHeader]] = extractor.extract_main_tables()

            # 验证提取结果
            self.assert_not_none(main_tables, "提取结果不能为 None")
            self.assert_true(isinstance(main_tables, dict), "提取结果应该是字典类型")

            print(f"\n[OK] 成功提取表格，共 {len(main_tables)} 个表格类型")

            # 统计有效表格数量
            valid_tables = {k: v for k, v in main_tables.items() if v is not None}
            print(f"[OK] 有效表格数量: {len(valid_tables)}")

            # 打印每个表格的基本信息
            for table_name, table_obj in main_tables.items():
                if table_obj is not None:
                    row_count = len(table_obj.table_data)
                    col_count = len(table_obj.table_data[0]) if table_obj.table_data else 0
                    page_info = f"第 {table_obj.page_start_num + 1} 页"
                    if table_obj.page_start_num != table_obj.page_end_num:
                        page_info = f"第 {table_obj.page_start_num + 1}-{table_obj.page_end_num + 1} 页"

                    print(f"\n  【{table_name}】")
                    print(f"    - 页码: {page_info}")
                    print(f"    - 行数: {row_count}, 列数: {col_count}")
                    print(f"    - 跨页合并: {'是' if table_obj.is_merged else '否'}")
                    header_preview = table_obj.header_text[:50] if table_obj.header_text else "无"
                    print(f"    - 表头文本: {header_preview}...")

                    # 验证表格数据
                    self.assert_true(table_obj.table_data, f"{table_name} 的表格数据不能为空")
                    self.assert_greater(row_count, 0, f"{table_name} 应该至少有 1 行数据")
                else:
                    print(f"\n  【{table_name}】")
                    print(f"    - 未找到")

            # 验证至少找到了一些主要表格
            main_table_names = [
                "合并资产负债表", "母公司资产负债表",
                "合并利润表", "母公司利润表",
                "合并现金流量表", "母公司现金流量表"
            ]
            found_main_tables = [name for name in main_table_names if main_tables.get(name) is not None]

            print(f"\n[OK] 找到的主要财务报表: {len(found_main_tables)}/{len(main_table_names)}")
            for name in found_main_tables:
                print(f"    - {name}")

            # 断言至少找到了部分主要表格
            self.assert_greater(len(found_main_tables), 2, "应该至少找到 3 个主要财务报表")

            # 将提取的表格保存为实例变量供后续测试使用
            self._extracted_tables = main_tables

        finally:
            # 关闭提取器
            extractor.close()
            print("\n[OK] 步骤1 完成：PDF 表格提取测试通过")

        return True

    # ============================================================
    # 步骤2：保存到 DuckDB
    # ============================================================
    def test_step2_save_tables_to_duckdb(self):
        """
        步骤2：测试将表格保存到 DuckDB 数据库
        目标：验证表格数据能正确保存到数据库中
        """
        print("\n" + "-" * 70)
        print("步骤2：测试将表格保存到 DuckDB 数据库")
        print("-" * 70)

        # 确保步骤1已执行
        if not self._extracted_tables:
            print("步骤1未执行，先执行步骤1...")
            success = self.test_step1_extract_tables_from_pdf()
            if not success:
                print("步骤1执行失败，跳过步骤2")
                return False

        main_tables = self._extracted_tables

        try:
            # 创建财务报告记录
            report_id = self._db.create_report(
                company_name=self.COMPANY_NAME,
                company_short_name=self.COMPANY_NAME,
                stock_code="",  # 可以从PDF中提取
                report_year=self.REPORT_YEAR,
                report_period=ReportPeriod(self.REPORT_PERIOD),
                source_file=self.TEST_PDF_PATH
            )
            print(f"\n[OK] 创建财务报告记录，ID: {report_id}")

            # 为每个表格创建指标记录
            metrics_count = 0
            for table_name, table_obj in main_tables.items():
                if table_obj is None:
                    continue

                # 将表格数据作为指标保存
                row_count = len(table_obj.table_data)
                self._db.create_metric(
                    report_id=report_id,
                    metric_name=f"{table_name}_行数",
                    value=float(row_count),
                    unit="行",
                    period=self.REPORT_PERIOD,
                    source_context=table_obj.header_text,
                    page_number=table_obj.page_start_num + 1
                )
                metrics_count += 1

            print(f"[OK] 已保存 {metrics_count} 个表格指标到数据库")

            # 验证数据是否正确保存
            retrieved_report = self._db.get_report(report_id)
            self.assert_not_none(retrieved_report, "应该能从数据库中读取到报告")
            
            metrics = self._db.get_metrics_by_report(report_id)
            self.assert_equal(len(metrics), metrics_count, "指标数量应该一致")

            print(f"\n[OK] 数据库保存验证通过")
            print(f"    - 报告ID: {report_id}")
            print(f"    - 指标数量: {len(metrics)}")

        except Exception as e:
            print(f"\n[X] 保存到数据库失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        print("\n[OK] 步骤2 完成：DuckDB 保存测试通过")
        return True

    # ============================================================
    # 步骤3：导出 Excel
    # ============================================================
    def test_step3_export_tables_to_excel(self):
        """
        步骤3：测试将表格导出为 Excel 文件
        目标：验证表格数据能正确导出为 Excel 文件
        """
        print("\n" + "-" * 70)
        print("步骤3：测试将表格导出为 Excel 文件")
        print("-" * 70)

        # 确保步骤1已执行
        if not self._extracted_tables:
            print("步骤1未执行，先执行步骤1...")
            success = self.test_step1_extract_tables_from_pdf()
            if not success:
                print("步骤1执行失败，跳过步骤3")
                return False

        main_tables = self._extracted_tables

        # 导出 Excel
        print(f"\n正在导出 Excel 文件到: {self.EXCEL_OUTPUT_DIR}")

        exported_files = []
        for table_name, table_obj in main_tables.items():
            if table_obj is None:
                continue

            # 准备表格数据
            table_data = table_obj.table_data
            
            # 准备元数据
            metadata = {
                '表名': table_name,
                '表头文本': table_obj.header_text,
                '起始页': table_obj.page_start_num + 1,
                '结束页': table_obj.page_end_num + 1,
                '是否跨页合并': '是' if table_obj.is_merged else '否',
                '行数': len(table_obj.table_data),
                '列数': len(table_obj.table_data[0]) if table_obj.table_data else 0
            }

            # 导出到Excel
            excel_file = self._db.export_table_to_excel(
                table_data=table_data,
                table_name=table_name,
                metadata=metadata,
                output_dir=os.path.join(self.EXCEL_OUTPUT_DIR, f"{self.COMPANY_NAME}_{self.REPORT_YEAR}")
            )
            
            if excel_file:
                exported_files.append(excel_file)

        print(f"\n[OK] 成功导出 {len(exported_files)} 个 Excel 文件")

        # 验证导出的文件
        self.assert_true(len(exported_files) > 0, "应该至少导出 1 个 Excel 文件")

        for excel_file in exported_files:
            print(f"\n  【{os.path.basename(excel_file)}】")
            print(f"    - 路径: {excel_file}")
            print(f"    - 文件大小: {os.path.getsize(excel_file)} 字节")

            # 验证文件存在且可读
            self.assert_true(os.path.exists(excel_file), f"Excel 文件应该存在: {excel_file}")
            self.assert_true(os.path.getsize(excel_file) > 0, f"Excel 文件大小应该大于 0: {excel_file}")

            # 验证文件可以被 pandas 读取
            import pandas as pd
            try:
                # 尝试读取 Excel 文件
                excel_file_obj = pd.ExcelFile(excel_file)
                sheet_names = excel_file_obj.sheet_names

                print(f"    - Sheet 列表: {sheet_names}")

                # 应该至少有数据 sheet 和元数据 sheet
                self.assert_true(len(sheet_names) >= 1, "Excel 文件应该至少有 1 个 sheet")

                # 读取第一个 sheet 的数据
                df = pd.read_excel(excel_file, sheet_name=sheet_names[0])
                print(f"    - 数据行数: {len(df)}, 数据列数: {len(df.columns)}")

            except Exception as e:
                raise AssertionError(f"无法读取 Excel 文件 {excel_file}: {e}")

        # 验证输出目录结构
        expected_subdir = os.path.join(self.EXCEL_OUTPUT_DIR, f"{self.COMPANY_NAME}_{self.REPORT_YEAR}")
        self.assert_true(os.path.exists(expected_subdir), f"输出子目录应该存在: {expected_subdir}")

        print(f"\n[OK] Excel 文件导出验证通过")
        print(f"[OK] 输出目录: {expected_subdir}")
        print("\n[OK] 步骤3 完成：Excel 导出测试通过")

        return True

    # ============================================================
    # 集成测试：完整流程
    # ============================================================
    def test_integration_full_workflow(self):
        """
        集成测试：完整的提取、保存和导出流程
        目标：一次性完成所有步骤并验证
        """
        print("\n" + "=" * 70)
        print("集成测试：完整的提取、保存和导出流程")
        print("=" * 70)

        # 检查测试文件是否存在
        if not os.path.exists(self.TEST_PDF_PATH):
            print(f"[!] 测试文件不存在: {self.TEST_PDF_PATH}")
            return False

        try:
            # 步骤1：提取表格
            print("\n--- 步骤1：提取表格 ---")
            extractor = PDFChapterExtractor(self.TEST_PDF_PATH)
            main_tables = extractor.extract_main_tables()
            extractor.close()

            valid_tables = {k: v for k, v in main_tables.items() if v is not None}
            print(f"[OK] 提取到 {len(valid_tables)} 个有效表格")

            # 步骤2：保存到数据库
            print("\n--- 步骤2：保存到数据库 ---")
            report_id = self._db.create_report(
                company_name=self.COMPANY_NAME,
                company_short_name=self.COMPANY_NAME,
                stock_code="",
                report_year=self.REPORT_YEAR,
                report_period=ReportPeriod(self.REPORT_PERIOD),
                source_file=self.TEST_PDF_PATH
            )
            print(f"[OK] 创建财务报告记录，ID: {report_id}")

            # 保存表格指标
            for table_name, table_obj in valid_tables.items():
                if table_obj:
                    self._db.create_metric(
                        report_id=report_id,
                        metric_name=f"{table_name}_行数",
                        value=float(len(table_obj.table_data)),
                        unit="行",
                        source_context=table_obj.header_text,
                        page_number=table_obj.page_start_num + 1
                    )

            # 验证数据库保存
            metrics = self._db.get_metrics_by_report(report_id)
            print(f"[OK] 已保存 {len(metrics)} 个指标到数据库")

            # 步骤3：导出 Excel
            print("\n--- 步骤3：导出 Excel ---")
            exported_files = self._db.export_report_tables_to_excel(
                report_id=report_id,
                output_dir=self.EXCEL_OUTPUT_DIR
            )
            print(f"[OK] 已导出 {len(exported_files)} 个 Excel 文件")

            # 验证 Excel 文件
            for excel_file in exported_files:
                self.assert_true(os.path.exists(excel_file), f"Excel 文件应该存在: {excel_file}")
                self.assert_true(os.path.getsize(excel_file) > 0, f"Excel 文件大小应该大于 0: {excel_file}")

            print("\n[OK] 集成测试完成：所有功能正常")

        except Exception as e:
            print(f"\n[X] 集成测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True


# ============================================================
# 主程序：运行所有测试
# ============================================================

def run_all_tests():
    """运行所有测试步骤"""
    test = TestTableExtractionAndExport()
    test.setup()

    results = {
        "步骤1：提取表格": False,
        "步骤2：保存到数据库": False,
        "步骤3：导出 Excel": False,
        "集成测试": False
    }

    try:
        # 运行集成测试（包含所有步骤）
        print("\n运行集成测试...")
        if test.test_integration_full_workflow():
            results["集成测试"] = True
            results["步骤1：提取表格"] = True
            results["步骤2：保存到数据库"] = True
            results["步骤3：导出 Excel"] = True

    except Exception as e:
        print(f"\n[X] 集成测试失败: {e}")
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