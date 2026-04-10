#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查 data/000423 目录中的 PDF 文件数据与 DuckDB 中保存的数据是否一致
并生成 Excel 报告
"""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

# 设置 UTF-8 编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime

# 添加项目路径 - src/tools/ 目录下需要上三层才能到项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)
from src.tools.chapter_extractor import PDFChapterExtractor


def get_db_data(read_only=True):
    """获取 DuckDB 中的财务数据"""
    db_path = './data/db/financial_data.duckdb'
    conn = duckdb.connect(db_path, read_only=read_only)

    # 查询合并资产负债表
    balance_sheet = conn.execute("""
        SELECT id, stock_code, report_year, report_period,
               monetary_funds, total_assets, total_liabilities, total_owners_equity,
               accounts_receivable, inventory, fixed_assets
        FROM consolidated_balance_sheet
        WHERE stock_code = '' OR stock_code IS NULL
        ORDER BY report_year
    """).df()

    # 查询合并利润表
    income_stmt = conn.execute("""
        SELECT id, stock_code, report_year, report_period,
               operating_revenue, operating_costs, operating_profit, net_profit
        FROM consolidated_income_statement
        WHERE stock_code = '' OR stock_code IS NULL
        ORDER BY report_year
    """).df()

    # 查询合并现金流量表
    cash_flow = conn.execute("""
        SELECT id, stock_code, report_year, report_period,
               net_cash_from_operations, net_cash_from_investing, net_cash_from_financing
        FROM consolidated_cash_flow_statement
        WHERE stock_code = '' OR stock_code IS NULL
        ORDER BY report_year
    """).df()

    conn.close()
    return balance_sheet, income_stmt, cash_flow


def parse_pdf_for_year(pdf_path, year):
    """解析单个 PDF 文件，提取关键财务指标"""
    try:
        extractor = PDFChapterExtractor(pdf_path)
        tables = extractor.extract_main_tables()

        result = {
            'year': year,
            'has_data': False,
            'tables_found': list(tables.keys()),
            'total_assets': None,
            'total_liabilities': None,
            'total_owners_equity': None,
            'operating_revenue': None,
            'operating_cost': None,
            'net_profit': None,
            'monetary_funds': None,
            'accounts_receivable': None,
            'inventory': None,
            'fixed_assets': None,
            'net_cash_from_operations': None,
        }

        # 从合并资产负债表中提取数据
        if '合并资产负债表' in tables:
            table = tables['合并资产负债表']
            data = table.table_data
            result['has_data'] = True

            # 查找关键指标
            for row in data:
                if not row or len(row) < 2:
                    continue
                item_name = str(row[0]).strip() if row[0] else ''

                if '货币资金' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['monetary_funds'] = float(val)
                    except:
                        pass

                if '总资产' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['total_assets'] = float(val)
                    except:
                        pass

                if '总负债' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['total_liabilities'] = float(val)
                    except:
                        pass

                if '所有者权益' in item_name and '合计' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['total_owners_equity'] = float(val)
                    except:
                        pass

                if '应收账款' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['accounts_receivable'] = float(val)
                    except:
                        pass

                if '存货' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['inventory'] = float(val)
                    except:
                        pass

                if '固定资产' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['fixed_assets'] = float(val)
                    except:
                        pass

        # 从合并利润表中提取数据
        if '合并利润表' in tables:
            table = tables['合并利润表']
            data = table.table_data

            for row in data:
                if not row or len(row) < 2:
                    continue
                item_name = str(row[0]).strip() if row[0] else ''

                if '营业收入' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['operating_revenue'] = float(val)
                    except:
                        pass

                if '营业成本' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['operating_cost'] = float(val)
                    except:
                        pass

                if '净利润' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['net_profit'] = float(val)
                    except:
                        pass

        # 从合并现金流量表中提取数据
        if '合并现金流量表' in tables:
            table = tables['合并现金流量表']
            data = table.table_data

            for row in data:
                if not row or len(row) < 2:
                    continue
                item_name = str(row[0]).strip() if row[0] else ''

                if '经营活动' in item_name and '现金流量净额' in item_name and len(row) > 1:
                    try:
                        val = row[1].replace(',', '').strip()
                        if val and val != '-':
                            result['net_cash_from_operations'] = float(val)
                    except:
                        pass

        return result

    except Exception as e:
        print(f"Error parsing {pdf_path}: {e}")
        return {
            'year': year,
            'has_data': False,
            'error': str(e)
        }


def compare_and_generate_report(pdf_dir, output_path):
    """对比 PDF 和 DB 数据，生成报告"""
    print("开始检查数据一致性...")

    # 获取 DuckDB 数据
    print("读取 DuckDB 数据...")
    balance_sheet_df, income_df, cash_flow_df = get_db_data()

    print(f"  - 合并资产负债表: {len(balance_sheet_df)} 条记录")
    print(f"  - 合并利润表: {len(income_df)} 条记录")
    print(f"  - 合并现金流量表: {len(cash_flow_df)} 条记录")

    # 获取 PDF 文件列表
    pdf_dir = Path(pdf_dir)
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    print(f"\n找到 {len(pdf_files)} 个 PDF 文件")

    # 解析每个 PDF
    pdf_results = []
    for pdf_file in pdf_files:
        # 从文件名提取年份: 东阿阿胶_000423_2016.pdf
        filename = pdf_file.stem
        year = int(filename.split('_')[-1])
        print(f"解析: {filename} (年份: {year})")
        result = parse_pdf_for_year(str(pdf_file), year)
        result['filename'] = filename
        result['pdf_path'] = str(pdf_file)
        pdf_results.append(result)

    # 对比数据
    print("\n开始对比数据...")
    inconsistencies = []

    for pdf_result in pdf_results:
        year = pdf_result['year']
        filename = pdf_result['filename']

        # 在 DB 中查找对应年份的数据
        bs_match = balance_sheet_df[balance_sheet_df['report_year'] == year]
        inc_match = income_df[income_df['report_year'] == year]
        cf_match = cash_flow_df[cash_flow_df['report_year'] == year]

        # 对比合并资产负债表
        if len(bs_match) > 0:
            db_record = bs_match.iloc[0]
            compare_fields = [
                ('monetary_funds', '货币资金'),
                ('total_assets', '总资产'),
                ('total_liabilities', '总负债'),
                ('total_owners_equity', '所有者权益合计'),
                ('accounts_receivable', '应收账款'),
                ('inventory', '存货'),
                ('fixed_assets', '固定资产'),
            ]

            for db_field, display_name in compare_fields:
                pdf_val = pdf_result.get(db_field)
                db_val = db_record.get(db_field)

                # 处理 None 和 NaN
                pdf_val_str = str(pdf_val) if pdf_val is not None else '空'
                db_val_str = str(db_val) if db_val is not None and str(db_val) != 'nan' else '空'

                # 检查是否不一致
                if pdf_val is not None and db_val is not None:
                    if not pd.isna(db_val):
                        diff_pct = abs(pdf_val - db_val) / abs(db_val) * 100 if db_val != 0 else 0
                        if diff_pct > 0.01:  # 差异大于 0.01%
                            inconsistencies.append({
                                'filename': filename,
                                'year': year,
                                'table': '合并资产负债表',
                                'field': display_name,
                                'pdf_value': pdf_val,
                                'db_value': db_val,
                                'difference': pdf_val - db_val,
                                'diff_percent': f"{diff_pct:.2f}%",
                                'status': '数值不一致'
                            })
                elif (pdf_val is None or pdf_val == '空') and (db_val is None or pd.isna(db_val)):
                    pass  # 都是空，一致
                else:
                    inconsistencies.append({
                        'filename': filename,
                        'year': year,
                        'table': '合并资产负债表',
                        'field': display_name,
                        'pdf_value': pdf_val,
                        'db_value': db_val,
                        'difference': None,
                        'diff_percent': None,
                        'status': '一方为空'
                    })

        # 对比合并利润表
        if len(inc_match) > 0:
            db_record = inc_match.iloc[0]
            compare_fields = [
                ('operating_revenue', '营业收入'),
                ('operating_cost', '营业成本'),
                ('net_profit', '净利润'),
            ]

            for db_field, display_name in compare_fields:
                pdf_val = pdf_result.get(db_field)
                db_val = db_record.get(db_field)

                if pdf_val is not None and db_val is not None:
                    if not pd.isna(db_val):
                        diff_pct = abs(pdf_val - db_val) / abs(db_val) * 100 if db_val != 0 else 0
                        if diff_pct > 0.01:
                            inconsistencies.append({
                                'filename': filename,
                                'year': year,
                                'table': '合并利润表',
                                'field': display_name,
                                'pdf_value': pdf_val,
                                'db_value': db_val,
                                'difference': pdf_val - db_val,
                                'diff_percent': f"{diff_pct:.2f}%",
                                'status': '数值不一致'
                            })
                elif (pdf_val is None or pdf_val == '空') and (db_val is None or pd.isna(db_val)):
                    pass
                else:
                    inconsistencies.append({
                        'filename': filename,
                        'year': year,
                        'table': '合并利润表',
                        'field': display_name,
                        'pdf_value': pdf_val,
                        'db_value': db_val,
                        'difference': None,
                        'diff_percent': None,
                        'status': '一方为空'
                    })

        # 对比合并现金流量表
        if len(cf_match) > 0:
            db_record = cf_match.iloc[0]
            compare_fields = [
                ('net_cash_from_operations', '经营活动现金流量净额'),
            ]

            for db_field, display_name in compare_fields:
                pdf_val = pdf_result.get(db_field)
                db_val = db_record.get(db_field)

                if pdf_val is not None and db_val is not None:
                    if not pd.isna(db_val):
                        diff_pct = abs(pdf_val - db_val) / abs(db_val) * 100 if db_val != 0 else 0
                        if diff_pct > 0.01:
                            inconsistencies.append({
                                'filename': filename,
                                'year': year,
                                'table': '合并现金流量表',
                                'field': display_name,
                                'pdf_value': pdf_val,
                                'db_value': db_val,
                                'difference': pdf_val - db_val,
                                'diff_percent': f"{diff_pct:.2f}%",
                                'status': '数值不一致'
                            })
                elif (pdf_val is None or pdf_val == '空') and (db_val is None or pd.isna(db_val)):
                    pass
                else:
                    inconsistencies.append({
                        'filename': filename,
                        'year': year,
                        'table': '合并现金流量表',
                        'field': display_name,
                        'pdf_value': pdf_val,
                        'db_value': db_val,
                        'difference': None,
                        'diff_percent': None,
                        'status': '一方为空'
                    })

    # 生成 Excel 报告
    print(f"\n发现 {len(inconsistencies)} 个不一致项")

    if inconsistencies:
        df_inconsistencies = pd.DataFrame(inconsistencies)
        df_inconsistencies = df_inconsistencies[[
            'filename', 'year', 'table', 'field', 'pdf_value', 'db_value',
            'difference', 'diff_percent', 'status'
        ]]
    else:
        df_inconsistencies = pd.DataFrame(columns=[
            'filename', 'year', 'table', 'field', 'pdf_value', 'db_value',
            'difference', 'diff_percent', 'status'
        ])

    # 保存到 Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df_inconsistencies.to_excel(writer, sheet_name='不一致项', index=False)

        # 同时保存完整对比数据供参考
        summary_data = []
        for pdf_result in pdf_results:
            year = pdf_result['year']
            bs_match = balance_sheet_df[balance_sheet_df['report_year'] == year]
            inc_match = income_df[income_df['report_year'] == year]
            cf_match = cash_flow_df[cash_flow_df['report_year'] == year]

            summary_data.append({
                '年份': year,
                'PDF文件': pdf_result['filename'],
                'PDF总资产': pdf_result.get('total_assets'),
                'DB总资产': bs_match.iloc[0]['total_assets'] if len(bs_match) > 0 else None,
                'PDF总负债': pdf_result.get('total_liabilities'),
                'DB总负债': bs_match.iloc[0]['total_liabilities'] if len(bs_match) > 0 else None,
                'PDF营业收入': pdf_result.get('operating_revenue'),
                'DB营业收入': inc_match.iloc[0]['operating_revenue'] if len(inc_match) > 0 else None,
                'PDF净利润': pdf_result.get('net_profit'),
                'DB净利润': inc_match.iloc[0]['net_profit'] if len(inc_match) > 0 else None,
            })

        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='数据对比总览', index=False)

    print(f"\n报告已保存到: {output_path}")
    return df_inconsistencies


if __name__ == '__main__':
    pdf_dir = './data/000423'
    output_path = './data/pdf_db_comparison_report.xlsx'
    result = compare_and_generate_report(pdf_dir, output_path)
    print(f"\n完成! 共发现 {len(result)} 个不一致项")