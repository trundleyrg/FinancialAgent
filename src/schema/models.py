"""
数据库 ORM 模型及 Pydantic 数据验证
"""    
from typing import Optional, List
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship
from pydantic import BaseModel, Field, field_validator

Base = declarative_base()

# --- 0. 定义周期枚举 ---

class ReportPeriod(str, Enum):
    """
    财务报告周期枚举
    定义了常见的财务报告发布周期类型
    """
    Q1 = "Q1"          # 第一季度报告，通常在4月底前发布
    H1 = "H1"          # 半年度报告，通常在8月底前发布（Q2结束）
    Q3 = "Q3"          # 第三季度报告，通常在10月底前发布
    FY = "FY"          # 年度报告，通常在次年4月底前发布（Full Year）

# --- 1. SQLAlchemy ORM Models ---
# （用于数据库持久化）

class FinancialReport(Base):
    """
    财务报告 ORM 模型
    用于存储财务报告的基本元数据信息
    """
    __tablename__ = 'financial_reports'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # 报告唯一标识符，自增主键
    company_name = Column(String(255), nullable=False, index=True)  # 公司全名，用于查询索引
    stock_code = Column(String(20), nullable=False, index=True)  # 股票代码，用于查询索引
    
    # 年份 + 周期 共同定义时间点
    report_year = Column(Integer, nullable=False, index=True)  # 报告所属年份，如2023，用于查询索引
    report_period = Column(SQLEnum(ReportPeriod), nullable=False, index=True)  # 报告周期（Q1/H1/Q3/FY），用于查询索引
    
    source_file = Column(String(500))  # 源PDF文件路径，用于追溯原始数据
    created_at = Column(DateTime, default=datetime.now)  # 记录创建时间，自动填充当前时间
    metrics = relationship("FinancialMetric", back_populates="report")  # 关联的财务指标列表

class FinancialMetric(Base):
    """
    财务指标 ORM 模型
    用于存储从财务报告中提取的具体财务数据指标
    """
    __tablename__ = 'financial_metrics'
    id = Column(Integer, primary_key=True, autoincrement=True)  # 指标唯一标识符，自增主键
    report_id = Column(Integer, ForeignKey('financial_reports.id'))  # 外键，关联到财务报告
    metric_name = Column(String(100), nullable=False)  # 指标名称，如"营业收入"、"净利润"等
    value = Column(Float, nullable=False)  # 指标的具体数值
    unit = Column(String(20))  # 数值单位，如"元"、"万元"、"%"等
    period = Column(String(50))  # 报告期间，如"年度"、"季度"等
    source_context = Column(Text)  # 指标在原报告中的上下文内容，用于溯源验证
    page_number = Column(Integer)  # 指标在原报告中的页码位置
    report = relationship("FinancialReport", back_populates="metrics")  # 关联回财务报告


# --- 2. Pydantic V2 Models (用于结构化输出提取) ---

class MetricItem(BaseModel):
    """
    单条指标的提取定义
    用于LLM结构化输出，包含指标的数值、单位、上下文和页码信息
    """
    value: float = Field(..., description="指标的具体数值")  # 指标的浮点数值
    unit: str = Field(default="元", description="数值单位，如：元、万元、亿元、%")  # 数值的计量单位，默认为"元"
    context: str = Field(..., description="数据所在的原文句子或表格行内容，用于溯源")  # 原始数据的上下文，用于验证和溯源
    page: int = Field(..., description="数据来源的页码")  # 数据在PDF中的页码位置

class FinancialExtractionSchema(BaseModel):
    """
    LLM 结构化提取 Schema
    定义了LLM从财务报告中提取结构化数据的标准格式
    """
    company_name: str = Field(..., description="公司名称")  # 财报所属公司的全名
    report_year: int = Field(..., description="财报所属年份")  # 财报报告的年份
    report_period: ReportPeriod = Field(
        ..., 
        description="财报周期：Q1(一季报), H1(半年报), Q3(三季报), FY(年报)"
    )  # 财报的发布周期，与年份共同确定具体的财务报告期
    
    # 核心财务指标
    operating_revenue: MetricItem = Field(..., description="营业收入")  # 公司主营业务产生的收入总额
    net_profit: MetricItem = Field(..., description="归属于上市公司股东的净利润")  # 扣除所有成本费用和税项后的净利润
    gross_margin: MetricItem = Field(..., description="毛利率")  # 毛利润与营业收入的比率，反映公司盈利能力
    profit_margin: MetricItem = Field(..., description="净利润率")  # 净利润与营业收入的比率，反映公司盈利水平
    roe: MetricItem = Field(..., description="加权平均净资产收益率 (ROE)")  # 净利润与净资产的比率，衡量股东权益的回报率

    @field_validator('gross_margin', 'profit_margin', 'roe', mode='before')
    @classmethod
    def handle_percentage_strings(cls, v):
        """
        处理 LLM 可能返回的带百分号的字符串 (如 "25.5%") 
        或者将 0.255 统一格式化为百分比数值。
        """
        if isinstance(v, dict) and 'value' in v:
            val = v['value']
            if isinstance(val, str) and '%' in val:
                try:
                    v['value'] = float(val.replace('%', ''))
                    v['unit'] = '%'
                except ValueError:
                    pass
        return v
