"""
数据库操作逻辑 (支持postgresql和duckdb)
统一使用models.py中的模型定义，提供一致的ORM风格接口
"""
import os
from dotenv import load_dotenv
from peewee import *
from typing import List, Optional, Dict, Any, Type
import pandas as pd
import duckdb
from datetime import datetime
from contextlib import contextmanager

# 导入所有模型
from src.db.models import (
    FinancialReport, FinancialMetric, ReportPeriod, db,
    ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
    ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
    ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement
)
from src.utils.logger import db_logger

# 加载环境变量
load_dotenv()


class DuckDBModelAdapter:
    """
    DuckDB模型适配器
    将Peewee模型操作转换为DuckDB SQL操作
    """
    
    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn
    
    def _get_table_name(self, model_class: Type[Model]) -> str:
        """获取模型对应的表名"""
        return model_class._meta.table_name
    
    def _get_fields(self, model_class: Type[Model]) -> Dict[str, Field]:
        """获取模型的所有字段"""
        return model_class._meta.fields
    
    def _model_to_dict(self, model_instance: Model) -> Dict[str, Any]:
        """将模型实例转换为字典"""
        data = {}
        for field_name, field in model_instance._meta.fields.items():
            if field_name == 'id' and getattr(model_instance, field_name) is None:
                continue  # 跳过自增id
            
            # 处理外键字段 - 获取原始值而不是关联对象
            if isinstance(field, ForeignKeyField):
                # 获取外键的原始值（如 report_id）
                fk_value = getattr(model_instance, field.column_name, None)
                if fk_value is not None:
                    data[field.column_name] = fk_value
            else:
                value = getattr(model_instance, field_name)
                if value is not None:
                    data[field_name] = value
        return data
    
    def create(self, model_instance: Model) -> int:
        """创建记录，返回id"""
        table_name = self._get_table_name(type(model_instance))
        data = self._model_to_dict(model_instance)
        
        if not data:
            raise ValueError("没有数据要插入")
        
        columns = list(data.keys())
        placeholders = ['?' for _ in columns]
        values = list(data.values())
        
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING id"
        result = self.conn.execute(sql, values)
        return result.fetchone()[0]
    
    def get_by_id(self, model_class: Type[Model], record_id: int) -> Optional[Dict[str, Any]]:
        """根据id获取记录"""
        table_name = self._get_table_name(model_class)
        sql = f"SELECT * FROM {table_name} WHERE id = ?"
        result = self.conn.execute(sql, [record_id]).fetchone()
        
        if result is None:
            return None
        
        # 获取列名
        columns = [desc[0] for desc in self.conn.execute(sql, [record_id]).description]
        return dict(zip(columns, result))
    
    def filter(self, model_class: Type[Model], **kwargs) -> List[Dict[str, Any]]:
        """根据条件筛选记录"""
        table_name = self._get_table_name(model_class)
        
        if not kwargs:
            sql = f"SELECT * FROM {table_name}"
            result = self.conn.execute(sql).fetchall()
            if not result:
                return []
            columns = [desc[0] for desc in self.conn.execute(sql).description]
            return [dict(zip(columns, row)) for row in result]
        
        conditions = []
        values = []
        for key, value in kwargs.items():
            conditions.append(f"{key} = ?")
            values.append(value)
        
        sql = f"SELECT * FROM {table_name} WHERE {' AND '.join(conditions)}"
        result = self.conn.execute(sql, values).fetchall()
        
        if not result:
            return []
        
        columns = [desc[0] for desc in self.conn.execute(sql, values).description]
        return [dict(zip(columns, row)) for row in result]
    
    def update(self, model_class: Type[Model], record_id: int, **kwargs) -> bool:
        """更新记录"""
        table_name = self._get_table_name(model_class)
        
        if not kwargs:
            return False
        
        set_clauses = []
        values = []
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
        values.append(record_id)
        
        sql = f"UPDATE {table_name} SET {', '.join(set_clauses)} WHERE id = ?"
        self.conn.execute(sql, values)
        return True
    
    def delete(self, model_class: Type[Model], record_id: int) -> bool:
        """删除记录"""
        table_name = self._get_table_name(model_class)
        sql = f"DELETE FROM {table_name} WHERE id = ?"
        self.conn.execute(sql, [record_id])
        return True


class DatabaseConnector:
    """数据库连接器，提供增删查改操作，支持 PostgreSQL 和 DuckDB"""

    def __init__(self, database_type: str = None, database_url: str = None):
        """
        初始化数据库连接
        :param database_type: 数据库类型 ('postgresql' 或 'duckdb')，如果为 None，则从环境变量读取
        :param database_url: 数据库连接字符串，如果为 None，则根据数据库类型使用默认值
        """
        if database_type is None:
            database_type = os.getenv("DATABASE")
            if database_type is None:
                raise ValueError("环境变量 DATABASE 未设置")
            database_type = database_type.lower()

        self.database_type = database_type
        self._duckdb_conn = None
        self._duckdb_adapter = None

        # 根据数据库类型创建对应的引擎
        if database_type == "postgresql":
            self._init_postgresql(database_url)
        elif database_type == "duckdb":
            self._init_duckdb(database_url)
        else:
            raise ValueError(f"不支持的数据库类型: {database_type}. 支持的类型: 'postgresql', 'duckdb'")

    def _init_postgresql(self, database_url: str = None):
        """初始化PostgreSQL连接"""
        if database_url is None:
            database_url = os.getenv("POSTGRES_DB_URL")
            if database_url is None:
                raise ValueError("环境变量 POSTGRES_DB_URL 未设置")
        
        self.engine = PostgresqlDatabase(
            database=database_url.split('/')[-1],
            user=database_url.split('://')[1].split(':')[0],
            password=database_url.split('@')[0].split(':')[-1],
            host=database_url.split('@')[1].split(':')[0],
            port=database_url.split(':')[-1].split('/')[0]
        )
        db.initialize(self.engine)

    def _init_duckdb(self, database_url: str = None):
        """初始化DuckDB连接"""
        if database_url is None:
            database_url = os.getenv("DUCKDB_DB_PATH")
            if database_url is None:
                raise ValueError("环境变量 DUCKDB_DB_PATH 未设置")
        
        # 确保数据库目录存在
        db_dir = os.path.dirname(database_url)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # 检查文件是否存在且是有效的DuckDB文件
        if os.path.exists(database_url):
            try:
                test_conn = duckdb.connect(database_url)
                test_conn.execute("SELECT 1")
                test_conn.close()
            except Exception as e:
                db_logger.warning(f"数据库文件损坏，正在重新创建: {e}")
                os.remove(database_url)
                wal_file = database_url + ".wal"
                if os.path.exists(wal_file):
                    os.remove(wal_file)
        
        # 创建DuckDB连接
        self._duckdb_conn = duckdb.connect(database_url)
        self._duckdb_adapter = DuckDBModelAdapter(self._duckdb_conn)
        
        # 为Peewee模型初始化一个内存数据库（用于模型定义）
        self.engine = SqliteDatabase(":memory:")
        db.initialize(self.engine)

    def create_tables(self):
        """创建所有数据表"""
        if self.database_type == "duckdb":
            self._create_duckdb_tables()
        else:
            tables = [
                FinancialReport, FinancialMetric,
                ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
                ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
                ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
            ]
            self.engine.create_tables(tables, safe=True)
            db_logger.info("PostgreSQL表格创建完成")

    def _create_duckdb_tables(self):
        """
        使用DuckDB创建所有数据表
        根据models.py中的Peewee模型定义自动生成表结构
        """
        # 定义所有需要创建的模型
        tables = [
            FinancialReport, FinancialMetric,
            ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
            ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
            ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
        ]
        
        for table in tables:
            self._create_duckdb_table_for_model(table)
        
        db_logger.info("DuckDB表格创建完成")
    
    def _create_duckdb_table_for_model(self, model_class: Type[Model]):
        """
        根据Peewee模型创建对应的DuckDB表
        """
        table_name = model_class._meta.table_name
        fields = model_class._meta.fields
        
        # 检查表是否已存在
        result = self._duckdb_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [table_name]
        ).fetchone()
        
        if result:
            db_logger.debug(f"表 {table_name} 已存在，跳过创建")
            return
        
        # 创建序列（用于自增ID）
        seq_name = f"seq_{table_name}_id"
        self._duckdb_conn.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name} START 1")
        
        # 构建列定义
        columns = []
        foreign_keys = []
        
        for field_name, field in fields.items():
            column_def = self._peewee_field_to_duckdb_sql(field_name, field)
            if column_def:
                columns.append(column_def)
            
            # 处理外键 - 使用 column_name（如 report_id）
            if isinstance(field, ForeignKeyField):
                ref_table = field.rel_model._meta.table_name
                foreign_keys.append(
                    f"FOREIGN KEY ({field.column_name}) REFERENCES {ref_table}(id)"
                )
        
        # 添加外键约束
        columns.extend(foreign_keys)
        
        # 构建完整的CREATE TABLE语句
        columns_sql = ",\n                ".join(columns)
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {columns_sql}
            )
        """
        
        self._duckdb_conn.execute(create_sql)
        db_logger.debug(f"表 {table_name} 创建成功")
    
    def _peewee_field_to_duckdb_sql(self, field_name: str, field: Field) -> str:
        """
        将Peewee字段转换为DuckDB SQL列定义
        """
        table_name = field.model._meta.table_name if hasattr(field, 'model') else 'unknown'
        
        # 处理主键自增字段
        if isinstance(field, AutoField):
            return f"{field_name} INTEGER PRIMARY KEY DEFAULT nextval('seq_{table_name}_id')"
        
        # 处理外键字段 - 使用 column_name（如 report_id）而不是字段名（如 report）
        if isinstance(field, ForeignKeyField):
            return f"{field.column_name} INTEGER NOT NULL"
        
        # 映射字段类型
        type_mapping = {
            CharField: "VARCHAR",
            IntegerField: "INTEGER",
            FloatField: "DOUBLE",
            DoubleField: "DOUBLE",
            DecimalField: "DECIMAL",
            BooleanField: "BOOLEAN",
            DateTimeField: "TIMESTAMP",
            DateField: "DATE",
            TimeField: "TIME",
            TextField: "TEXT",
            BlobField: "BLOB",
            UUIDField: "UUID",
        }
        
        # 获取字段类型
        field_type = type(field)
        duckdb_type = type_mapping.get(field_type, "VARCHAR")
        
        # 处理CharField的长度
        if isinstance(field, CharField) and hasattr(field, 'max_length') and field.max_length:
            duckdb_type = f"VARCHAR({field.max_length})"
        
        # 构建列定义
        column_def = f"{field_name} {duckdb_type}"
        
        # 处理非空约束
        if hasattr(field, 'null') and not field.null:
            column_def += " NOT NULL"
        
        # 处理默认值
        if hasattr(field, 'default') and field.default is not None:
            if callable(field.default):
                # 对于函数默认值（如datetime.now），使用DuckDB的等效函数
                if field.default == datetime.now:
                    column_def += " DEFAULT CURRENT_TIMESTAMP"
            elif isinstance(field.default, str):
                column_def += f" DEFAULT '{field.default}'"
            elif isinstance(field.default, (int, float)):
                column_def += f" DEFAULT {field.default}"
        
        return column_def

    # ==================== 通用 CRUD 接口 ====================

    def _get_model_class(self, table_name: str) -> Type[Model]:
        """根据表名获取模型类"""
        model_map = {
            'financial_reports': FinancialReport,
            'financial_metrics': FinancialMetric,
            'consolidated_balance_sheet': ConsolidatedBalanceSheet,
            'parent_company_balance_sheet': ParentCompanyBalanceSheet,
            'consolidated_income_statement': ConsolidatedIncomeStatement,
            'parent_company_income_statement': ParentCompanyIncomeStatement,
            'consolidated_cash_flow_statement': ConsolidatedCashFlowStatement,
            'parent_company_cash_flow_statement': ParentCompanyCashFlowStatement,
        }
        if table_name not in model_map:
            raise ValueError(f"未知的表名: {table_name}")
        return model_map[table_name]

    def insert_record(self, table_name: str, **kwargs) -> int:
        """
        通用创建记录方法
        :param table_name: 表名
        :param kwargs: 字段名和值的键值对
        :return: 新创建记录的 ID
        """
        model_class = self._get_model_class(table_name)
        
        if self.database_type == "duckdb":
            # 创建模型实例
            instance = model_class(**kwargs)
            return self._duckdb_adapter.create(instance)
        else:
            # PostgreSQL 使用 Peewee
            instance = model_class.create(**kwargs)
            return instance.id

    def get_by_id(self, table_name: str, record_id: int) -> Optional[Model]:
        """
        通用根据 ID 查询记录方法
        :param table_name: 表名
        :param record_id: 记录 ID
        :return: 模型实例或 None
        """
        model_class = self._get_model_class(table_name)
        
        if self.database_type == "duckdb":
            data = self._duckdb_adapter.get_by_id(model_class, record_id)
            if data:
                return model_class(**data)
            return None
        else:
            try:
                return model_class.get(model_class.id == record_id)
            except model_class.DoesNotExist:
                return None

    def filter_records(self, table_name: str, **kwargs) -> List[Model]:
        """
        通用条件查询记录方法
        :param table_name: 表名
        :param kwargs: 查询条件
        :return: 模型实例列表
        """
        model_class = self._get_model_class(table_name)
        
        if self.database_type == "duckdb":
            results = self._duckdb_adapter.filter(model_class, **kwargs)
            return [model_class(**data) for data in results]
        else:
            query = model_class.select()
            for key, value in kwargs.items():
                if hasattr(model_class, key):
                    field = getattr(model_class, key)
                    query = query.where(field == value)
            return list(query)

    def update_record(self, table_name: str, record_id: int, **kwargs) -> bool:
        """
        通用更新记录方法
        :param table_name: 表名
        :param record_id: 记录 ID
        :param kwargs: 要更新的字段名和值
        :return: 是否更新成功
        """
        model_class = self._get_model_class(table_name)
        
        if self.database_type == "duckdb":
            return self._duckdb_adapter.update(model_class, record_id, **kwargs)
        else:
            try:
                instance = model_class.get(model_class.id == record_id)
                for key, value in kwargs.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
                instance.save()
                return True
            except model_class.DoesNotExist:
                return False

    def delete_record(self, table_name: str, record_id: int) -> bool:
        """
        通用删除记录方法
        :param table_name: 表名
        :param record_id: 记录 ID
        :return: 是否删除成功
        """
        model_class = self._get_model_class(table_name)
        
        if self.database_type == "duckdb":
            return self._duckdb_adapter.delete(model_class, record_id)
        else:
            try:
                instance = model_class.get(model_class.id == record_id)
                instance.delete_instance()
                return True
            except model_class.DoesNotExist:
                return False

    def drop_tables(self):
        """删除所有数据表"""
        # 定义所有表名（按依赖关系倒序，先删子表）
        table_names = [
            'financial_metrics',  # 先删有外键的表
            'consolidated_balance_sheet',
            'parent_company_balance_sheet',
            'consolidated_income_statement',
            'parent_company_income_statement',
            'consolidated_cash_flow_statement',
            'parent_company_cash_flow_statement',
            'financial_reports',  # 最后删主表
        ]
        
        if self.database_type == "duckdb":
            for table_name in table_names:
                self._duckdb_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                self._duckdb_conn.execute(f"DROP SEQUENCE IF EXISTS seq_{table_name}_id")
        else:
            tables = [
                FinancialMetric,
                ConsolidatedBalanceSheet, ParentCompanyBalanceSheet,
                ConsolidatedIncomeStatement, ParentCompanyIncomeStatement,
                ConsolidatedCashFlowStatement, ParentCompanyCashFlowStatement,
                FinancialReport,
            ]
            self.engine.drop_tables(tables, safe=True)

    # ==================== 综合查询 ====================

    def get_report_with_metrics(self, report_id: int) -> Optional[Dict[str, Any]]:
        """查询财务报告及其关联的所有财务指标"""
        report = self.get_report(report_id)
        if not report:
            return None
        
        metrics = self.get_metrics_by_report(report_id)
        return {
            'report': report,
            'metrics': metrics
        }

    def get_all_companies(self) -> List[Dict[str, Any]]:
        """获取所有公司的列表（去重）"""
        if self.database_type == "duckdb":
            sql = """
                SELECT DISTINCT company_name, stock_code 
                FROM financial_reports
            """
            results = self._duckdb_conn.execute(sql).fetchall()
            return [{"company_name": row[0], "stock_code": row[1]} for row in results]
        else:
            result = (FinancialReport
                      .select(FinancialReport.company_name, FinancialReport.stock_code)
                      .distinct())
            return [{"company_name": row.company_name, "stock_code": row.stock_code} for row in result]

    def get_company_report_years(self, stock_code: str) -> List[int]:
        """获取指定公司的所有报告年份"""
        if self.database_type == "duckdb":
            sql = """
                SELECT DISTINCT report_year 
                FROM financial_reports 
                WHERE stock_code = ? 
                ORDER BY report_year DESC
            """
            results = self._duckdb_conn.execute(sql, [stock_code]).fetchall()
            return [row[0] for row in results]
        else:
            result = (FinancialReport
                      .select(FinancialReport.report_year)
                      .where(FinancialReport.stock_code == stock_code)
                      .distinct()
                      .order_by(FinancialReport.report_year.desc()))
            return [row.report_year for row in result]

    # ==================== Excel导出功能 ====================

    def export_table_to_excel(self, table_data: List[List[Any]], table_name: str, 
                              metadata: Optional[Dict[str, Any]] = None,
                              output_dir: str = "./data/output/excel") -> Optional[str]:
        """
        将表格数据导出为 Excel 文件
        :param table_data: 表格数据（二维列表）
        :param table_name: 表格名称（用于文件名）
        :param metadata: 表格元数据字典
        :param output_dir: 输出目录
        :return: 导出的文件路径，如果失败返回 None
        """
        try:
            os.makedirs(output_dir, exist_ok=True)

            if not table_data:
                db_logger.warning(f"表格 {table_name} 数据为空，跳过导出")
                return None

            # 清理文件名
            safe_table_name = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            excel_file = os.path.join(output_dir, f"{safe_table_name}.xlsx")

            # 创建 DataFrame
            df = pd.DataFrame(table_data)

            # 导出到 Excel
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=table_name[:31], index=False)

                # 添加元数据 sheet
                if metadata:
                    meta_df = pd.DataFrame([metadata])
                    meta_df.to_excel(writer, sheet_name='元数据', index=False)

            db_logger.info(f"表格 {table_name} 已导出到 {excel_file}")
            return excel_file

        except Exception as e:
            db_logger.error(f"导出表格 {table_name} 到 Excel 失败: {e}")
            return None

    # ==================== 上下文管理器 ====================

    def close(self):
        """关闭数据库连接"""
        if self.database_type == "duckdb" and self._duckdb_conn:
            self._duckdb_conn.close()
            db_logger.info("DuckDB连接已关闭")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


# ============ 表格名称到模型类的映射 ============
TABLE_NAME_TO_MODEL = {
    # 合并资产负债表
    '合并资产负债表': ConsolidatedBalanceSheet,
    'consolidated_balance_sheet': ConsolidatedBalanceSheet,
    # 母公司资产负债表
    '母公司资产负债表': ParentCompanyBalanceSheet,
    'parent_company_balance_sheet': ParentCompanyBalanceSheet,
    # 合并利润表
    '合并利润表': ConsolidatedIncomeStatement,
    'consolidated_income_statement': ConsolidatedIncomeStatement,
    # 母公司利润表
    '母公司利润表': ParentCompanyIncomeStatement,
    'parent_company_income_statement': ParentCompanyIncomeStatement,
    # 合并现金流量表
    '合并现金流量表': ConsolidatedCashFlowStatement,
    'consolidated_cash_flow_statement': ConsolidatedCashFlowStatement,
    # 母公司现金流量表
    '母公司现金流量表': ParentCompanyCashFlowStatement,
    'parent_company_cash_flow_statement': ParentCompanyCashFlowStatement,
}

# 报表类型到表名的映射
TABLE_TYPE_NAMES = {
    'consolidated_balance_sheet': '合并资产负债表',
    'parent_company_balance_sheet': '母公司资产负债表',
    'consolidated_income_statement': '合并利润表',
    'parent_company_income_statement': '母公司利润表',
    'consolidated_cash_flow_statement': '合并现金流量表',
    'parent_company_cash_flow_statement': '母公司现金流量表',
}


def _parse_table_data_to_model_data(table_data: List[List[str]], model_class: Type[Model]) -> Dict[str, Any]:
    """
    将表格数据解析为模型数据字典
    表格数据格式：第一行通常是表头，后续行是数据
    支持两种常见的财务报表格式：
    1. 两列格式：项目名 | 金额
    2. 多列格式：项目名 | 本期金额 | 上期金额
    """
    if not table_data or len(table_data) < 2:
        return {}

    model_data = {}
    fields = model_class._meta.fields

    # 获取模型的字段名和帮助文本映射
    field_help_text_map = {}
    for field_name, field in fields.items():
        if hasattr(field, 'help_text') and field.help_text:
            field_help_text_map[field.help_text] = field_name
        else:
            field_help_text_map[field_name] = field_name

    # 遍历表格数据，尝试匹配字段
    for row in table_data:
        if len(row) < 2:
            continue

        # 第一列通常是项目名称
        item_name = str(row[0]).strip() if row[0] else ""
        # 第二列通常是数值
        value_str = str(row[1]).strip() if len(row) > 1 and row[1] else ""

        if not item_name:
            continue

        # 尝试找到对应的字段名
        field_name = None
        for help_text, fn in field_help_text_map.items():
            if help_text in item_name or item_name in help_text:
                field_name = fn
                break

        # 如果没找到，尝试直接匹配字段名（忽略大小写和下划线）
        if not field_name:
            normalized_item = item_name.replace(' ', '').replace('_', '').lower()
            for fn in fields.keys():
                normalized_field = fn.replace('_', '').lower()
                if normalized_field in normalized_item or normalized_item in normalized_field:
                    field_name = fn
                    break

        # 解析数值
        if field_name and value_str:
            try:
                # 处理常见的数值格式
                # 移除逗号、空格和单位
                value_str_clean = value_str.replace(',', '').replace(' ', '').replace('元', '').replace('万元', '').replace('亿元', '')
                # 处理括号表示的负数 (123) -> -123
                if '(' in value_str_clean and ')' in value_str_clean:
                    value_str_clean = '-' + value_str_clean.replace('(', '').replace(')', '')
                # 处理百分比
                if '%' in value_str_clean:
                    value_str_clean = value_str_clean.replace('%', '')
                    value = float(value_str_clean)
                else:
                    value = float(value_str_clean)
                model_data[field_name] = value
            except (ValueError, TypeError):
                # 如果无法解析为数字，跳过
                continue

    return model_data


def _normalize_table_name(table_name: str) -> str:
    """标准化表格名称，映射到模型类"""
    # 直接匹配
    if table_name in TABLE_NAME_TO_MODEL:
        return table_name

    # 尝试小写匹配
    table_name_lower = table_name.lower().replace(' ', '_')
    for key in TABLE_NAME_TO_MODEL.keys():
        if key.lower() == table_name_lower or key.lower().replace('_', '') == table_name_lower.replace('_', ''):
            return key

    return table_name


# ============ 全局单例 ============
_db_connector: Optional[DatabaseConnector] = None


def get_db(database_type: str = None, database_url: str = None) -> DatabaseConnector:
    """获取数据库连接器单例"""
    global _db_connector
    if _db_connector is None:
        _db_connector = DatabaseConnector(database_type, database_url)
        _db_connector.create_tables()
    return _db_connector


def save_tables_to_db(main_tables: Dict[str, Any], company_name: str, pdf_path:str,
                      company_short_name: str, company_code: str, report_year: int,
                      report_period: str, stock_code: str = "", db_connector: DatabaseConnector = None) -> Dict[str, int]:
    """
    将提取的表格数据保存到数据库

    :param main_tables: 提取的表格数据字典，键为表格名称，值为 TableWithHeader 对象
    :param company_name: 公司名称
    :param report_year: 报告年份
    :param report_period: 报告期间 (Q1, H1, Q3, FY)
    :param stock_code: 股票代码（可选）
    :param db_connector: 数据库连接器实例（可选，默认使用全局单例）
    :return: 保存的记录ID字典，键为表格类型，值为记录ID
    """
    db = db_connector or get_db()
    saved_ids = {}

    # 标准化报告期间
    period_value = report_period if report_period else "FY"
    if isinstance(period_value, ReportPeriod):
        period_value = period_value.value

    # 检查 financial_reports 表中是否已存在相同 stock_code 和 report_year 的记录
    existing_reports = db.filter_records(
        "financial_reports",
        stock_code=company_code,
        report_year=report_year
    )

    report_data = {
        "company_name": company_name,
        "company_short_name": company_short_name,
        "stock_code": company_code,
        "report_year": report_year,
        "report_period": ReportPeriod(report_period) if report_period else ReportPeriod.FY,
        "source_file": pdf_path
    }

    if existing_reports:
        # 更新现有记录
        existing_report = existing_reports[0]
        report_id = existing_report.id if hasattr(existing_report, 'id') else existing_report['id']
        db.update_record("financial_reports", report_id, **report_data)
        db_logger.info(f"更新 financial_reports 记录，ID: {report_id}")
    else:
        # 创建新记录
        report_id = db.insert_record("financial_reports", **report_data)
        db_logger.info(f"创建 financial_reports 记录，ID: {report_id}")
    if isinstance(period_value, ReportPeriod):
        period_value = period_value.value

    for table_name, table_obj in main_tables.items():
        if table_obj is None:
            continue

        # 标准化表格名称
        normalized_name = _normalize_table_name(table_name)
        model_class = TABLE_NAME_TO_MODEL.get(normalized_name)

        if not model_class:
            db_logger.warning(f"未知的表格类型: {table_name}，跳过保存")
            continue

        try:
            # 解析表格数据为模型数据
            model_data = _parse_table_data_to_model_data(table_obj.table_data, model_class)

            if not model_data:
                db_logger.warning(f"表格 {table_name} 未能解析出有效数据")
                continue

            # 添加基础信息
            model_data['company_name'] = company_name
            model_data['stock_code'] = stock_code
            model_data['report_year'] = report_year
            model_data['report_period'] = period_value

            # 获取表名
            table_db_name = model_class._meta.table_name

            # 检查是否已存在相同记录
            existing_records = db.filter_records(
                table_db_name,
                company_name=company_name,
                report_year=report_year,
                report_period=period_value
            )

            if existing_records:
                # 更新现有记录
                record_id = existing_records[0].id if hasattr(existing_records[0], 'id') else existing_records[0]['id']
                db.update_record(table_db_name, record_id, **model_data)
                db_logger.info(f"更新 {table_name} 记录，ID: {record_id}")
                saved_ids[table_db_name] = record_id
            else:
                # 创建新记录
                record_id = db.insert_record(table_db_name, **model_data)
                db_logger.info(f"创建 {table_name} 记录，ID: {record_id}")
                saved_ids[table_db_name] = record_id

        except Exception as e:
            db_logger.error(f"保存表格 {table_name} 失败: {e}")
            continue

    db_logger.info(f"成功保存 {len(saved_ids)} 个表格到数据库")
    return saved_ids


def export_tables_to_excel(company_name: str, report_year: int, report_period: str = None,
                          stock_code: str = "", output_dir: str = "./data/output/excel",
                          db_connector: DatabaseConnector = None) -> List[str]:
    """
    将数据库中的财务报表数据导出为 Excel 文件

    :param company_name: 公司名称
    :param report_year: 报告年份
    :param report_period: 报告期间 (Q1, H1, Q3, FY)，为 None 则导出所有期间
    :param stock_code: 股票代码（可选）
    :param output_dir: 输出目录
    :param db_connector: 数据库连接器实例（可选，默认使用全局单例）
    :return: 导出的 Excel 文件路径列表
    """
    db = db_connector or get_db()
    exported_files = []

    # 标准化报告期间
    period_value = report_period
    if isinstance(report_period, ReportPeriod):
        period_value = report_period.value

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 定义要导出的报表类型
    report_types = [
        ('consolidated_balance_sheet', ConsolidatedBalanceSheet),
        ('parent_company_balance_sheet', ParentCompanyBalanceSheet),
        ('consolidated_income_statement', ConsolidatedIncomeStatement),
        ('parent_company_income_statement', ParentCompanyIncomeStatement),
        ('consolidated_cash_flow_statement', ConsolidatedCashFlowStatement),
        ('parent_company_cash_flow_statement', ParentCompanyCashFlowStatement),
    ]

    for table_type, model_class in report_types:
        try:
            # 构建查询条件
            filters = {
                'company_name': company_name,
                'report_year': report_year,
            }
            if period_value:
                filters['report_period'] = period_value
            if stock_code:
                filters['stock_code'] = stock_code

            # 查询记录
            records = db.filter_records(table_type, **filters)

            if not records:
                db_logger.debug(f"未找到 {table_type} 的记录")
                continue

            # 获取记录数据
            record = records[0]
            if hasattr(record, '__dict__'):
                record_data = record.__dict__
            elif hasattr(record, '_data'):
                record_data = record._data
            else:
                record_data = dict(record) if isinstance(record, dict) else {}

            # 移除内部字段
            for key in ['id', '_database', '_dirty']:
                record_data.pop(key, None)

            # 构建表格数据
            table_data = []
            headers = ['项目', '金额']
            table_data.append(headers)

            # 获取字段和帮助文本的映射
            fields = model_class._meta.fields
            for field_name, field in fields.items():
                if field_name in ['id', 'company_name', 'stock_code', 'report_year', 'report_period']:
                    continue

                help_text = field.help_text if hasattr(field, 'help_text') and field.help_text else field_name
                value = record_data.get(field_name)

                if value is not None:
                    table_data.append([help_text, value])

            # 准备元数据
            metadata = {
                '表名': TABLE_TYPE_NAMES.get(table_type, table_type),
                '公司名称': company_name,
                '股票代码': stock_code,
                '报告年份': report_year,
                '报告期间': period_value or '全部',
            }

            # 导出到 Excel
            excel_file = db.export_table_to_excel(
                table_data=table_data,
                table_name=f"{company_name}_{report_year}_{table_type}",
                metadata=metadata,
                output_dir=output_dir
            )

            if excel_file:
                exported_files.append(excel_file)
                db_logger.info(f"导出 {table_type} 到 {excel_file}")

        except Exception as e:
            db_logger.error(f"导出 {table_type} 失败: {e}")
            continue

    db_logger.info(f"成功导出 {len(exported_files)} 个 Excel 文件")
    return exported_files
