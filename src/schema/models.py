"""
数据库 ORM 模型及 Pydantic 数据验证
"""    
from typing import Optional, List
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from pydantic import BaseModel, Field, field_validator

Base = declarative_base()

# --- 1. SQLAlchemy ORM Models ---
# （保持不变，用于数据库持久化）

class FinancialReport(Base):
    __tablename__ = 'financial_reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_year = Column(Integer, nullable=False)
    source_file = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
    metrics = relationship("FinancialMetric", back_populates="report")

class FinancialMetric(Base):
    __tablename__ = 'financial_metrics'
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey('financial_reports.id'))
    metric_name = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20))
    period = Column(String(50))
    source_context = Column(Text)
    page_number = Column(Integer)
    report = relationship("FinancialReport", back_populates="metrics")


# --- 2. Pydantic V2 Models (用于结构化输出提取) ---

class MetricItem(BaseModel):
    """单条指标的提取定义"""
    value: float = Field(..., description="指标的具体数值")
    unit: str = Field(default="元", description="数值单位，如：元、万元、亿元、%")
    context: str = Field(..., description="数据所在的原文句子或表格行内容，用于溯源")
    page: int = Field(..., description="数据来源的页码")

class FinancialExtractionSchema(BaseModel):
    """LLM 结构化提取 Schema"""
    company_name: str = Field(..., description="公司名称")
    report_year: int = Field(..., description="财报所属年份")
    
    # 核心指标
    operating_revenue: MetricItem = Field(..., description="营业收入")
    net_profit: MetricItem = Field(..., description="归属于上市公司股东的净利润")
    gross_margin: MetricItem = Field(..., description="毛利率")
    profit_margin: MetricItem = Field(..., description="净利润率")
    roe: MetricItem = Field(..., description="加权平均净资产收益率 (ROE)")

    # 使用 Pydantic V2 的 field_validator
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
