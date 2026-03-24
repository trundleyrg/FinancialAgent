# FinancialAgent 智能财务报告分析系统

## 项目概述

FinancialAgent 是一个基于 LangGraph 构建的智能代理系统，专门用于解析上市公司财务报告的 PDF 文件，并将提取的结构化数据保存到数据库中，以供后续分析使用。

该系统采用现代化的 AI Agent 架构，结合自然语言处理技术，能够自动从复杂的财务报告中提取关键财务指标，并按照标准化的 Schema 存储数据。

## 技术架构

### 核心技术栈
- **Python 3.12+**: 主要开发语言
- **LangGraph**: Agent 图形化编排框架（待开发）
- **LangChain**: 大语言模型接口和工具链
- **PyMuPDF (fitz)**: PDF 文本和图像提取
- **pdfplumber**: PDF 表格提取
- **Peewee**: 数据库 ORM 框架
- **PostgreSQL/DuckDB**: 支持 PostgreSQL 和 DuckDB 两种数据库
- **Pydantic**: 数据验证和结构化输出
- **Gradio**: Web UI 界面框架
- **Poetry**: 依赖管理

### 系统架构组件

#### 1. Agent 架构 (src/agents/)
- **State (state.py)**: 定义了 LangGraph 的状态结构 `FinancialState`，包含 PDF 路径、原始 Markdown、结构化数据、执行状态等。
- **Graph (graph.py)**: 构建 StateGraph、节点和边的逻辑（待开发）。
- **Nodes (nodes.py)**: 具体的节点函数实现（待开发）。

#### 2. 工具层 (src/tools/)
- **chapter_extractor.py**: PDF 章节提取器，核心功能包括：
  - 从 PDF 第一页自动提取公司名称、简称、股票代码、报告年份和期间
  - 基于 PDF 目录（TOC）定位指定章节页码范围
  - 提取章节内所有表格，支持跨页表格自动合并
  - 关联表格与表头文本
- **general_pdf_parser.py**: PDF 通用解析类，提取正文、图片、表格并保存为不同格式。
- **file_manager.py**: Markdown 生成和文件夹管理（待开发）。

#### 3. 数据库层 (src/db/)
- **db_connector.py**: 数据库操作逻辑，核心功能包括：
  - 提供 `DatabaseConnector` 类，统一封装 PostgreSQL 和 DuckDB 操作
  - `DuckDBModelAdapter`: 将 Peewee 模型操作转换为 DuckDB SQL
  - 通用 CRUD 接口：`insert_record`、`get_by_id`、`filter_records`、`update_record`、`delete_record`
  - 综合查询：`get_report_with_metrics`、`get_all_companies`、`get_company_report_years`
  - Excel 导出功能：`export_table_to_excel`
- **models.py**: 定义数据库 ORM 模型和 Pydantic 数据验证 Schema，包括：
  - 财务报告周期枚举（Q1, H1, Q3, FY）
  - `FinancialReport`: 财务报告基础模型
  - `FinancialMetric`: 财务指标模型
  - 完整的财务报表模型：
    - `ConsolidatedBalanceSheet`: 合并资产负债表
    - `ParentCompanyBalanceSheet`: 母公司资产负债表
    - `ConsolidatedIncomeStatement`: 合并利润表
    - `ParentCompanyIncomeStatement`: 母公司利润表
    - `ConsolidatedCashFlowStatement`: 合并现金流量表
    - `ParentCompanyCashFlowStatement`: 母公司现金流量表
    - `ShareStructure`: 股份变动情况表
- **table_models.py**: 定义 `TableWithHeader` 数据结构，用于表格数据的传递和处理。

#### 4. UI 层 (ui/)
- **app.py**: Gradio 主应用入口，整合 PDF 解析和数据库查询功能。
- **pdf_parser_ui.py**: PDF 上传与解析界面，支持：
  - PDF 文件上传
  - 自动提取财务报表
  - 结果展示和 Excel 下载
- **db_query_ui.py**: 数据库查询界面（开发中）。

#### 5. 工具函数 (src/utils/)
- **logger.py**: 日志管理，提供多个预定义 Logger：
  - `pdf_logger`: PDF 解析日志
  - `chapter_logger`: 章节提取日志
  - `node_logger`: Agent 节点日志
  - `db_logger`: 数据库操作日志
  - `main_logger`: 主程序日志
  - `ui_logger`: UI 界面日志
  - `sys_logger`: 系统全局日志

#### 6. 配置 (src/config.py)
- 环境变量与配置信息（待完善）。

## 核心功能

### PDF 解析与数据提取
1. **公司信息提取**: 从 PDF 第一页自动识别公司名称、简称、股票代码、报告年份和期间
2. **章节定位**: 利用 PDF 目录结构精确定位财务报告章节
3. **表格识别**: 从 PDF 中提取表格数据，支持跨页表格的自动合并
4. **表头关联**: 自动为表格关联最近的表头文本
5. **文本提取**: 将 PDF 正文内容转换为 Markdown 格式
6. **图片提取**: 提取 PDF 中的图像并保存

### 数据结构化
1. **关键指标提取**: 从财务报表中识别并提取核心指标
2. **Schema 验证**: 使用 Pydantic 模型确保提取数据的格式和质量
3. **上下文关联**: 保留数据来源的原始上下文和页码信息

### 数据存储
1. **数据库模型**: 提供完整的财务报表数据库模型
2. **多数据库支持**: 支持 PostgreSQL 和 DuckDB 两种数据库
3. **批量操作**: 支持批量创建和更新财务指标
4. **关联查询**: 支持报告与指标之间的关联查询
5. **DuckDB 文件位置**: 当使用 DuckDB 时，数据库文件默认存储在 `data/db/` 目录下

### Web UI
1. **PDF 上传与解析**: 通过 Web 界面上传 PDF 文件并自动解析
2. **结果展示**: 显示提取的公司信息和表格列表
3. **Excel 下载**: 支持下载提取的财务报表 Excel 文件
4. **数据查询**: 数据库查询界面（开发中）

## 文件目录结构

```
FinancialAgent/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py          # 定义 LangGraph 的 State 结构 (TypedDict)
│   │   ├── graph.py          # 构建 StateGraph、节点和边的逻辑（待开发）
│   │   └── nodes.py          # 具体的节点函数实现（待开发）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── general_pdf_parser.py     # PDF 通用解析类
│   │   ├── chapter_extractor.py      # PDF 章节提取器（核心）
│   │   └── file_manager.py           # Markdown 生成和文件夹管理（待开发）
│   ├── db/
│   │   ├── __init__.py
│   │   ├── db_connector.py           # 数据库连接器（核心）
│   │   ├── models.py                 # 数据库 ORM 模型及 Pydantic 验证
│   │   └── table_models.py           # 表格数据结构定义
│   ├── utils/
│   │   ├── __init__.py
│   │   └── logger.py         # 日志管理
│   └── config.py             # 环境变量与配置信息
├── ui/
│   ├── app.py                # Gradio 主应用入口
│   ├── pdf_parser_ui.py      # PDF 解析界面
│   └── db_query_ui.py        # 数据库查询界面
├── data/
│   ├── raw_pdfs/             # 原始 PDF 输入目录
│   ├── output/               # 生成的 Markdown 文件存储目录
│   ├── excel/                # 导出的 Excel 文件存储目录
│   ├── temp/                 # UI 临时文件目录
│   └── db/                   # DuckDB 数据库文件存储目录
├── logs/                     # 日志文件目录
├── script/
│   └── init_postgresql_db.py # PostgreSQL 数据库初始化脚本
├── tests/                    # 单元测试与集成测试
├── docs/                     # 文档目录
├── .env                      # 敏感信息 (API Keys, DB Credentials)
├── .env.example              # 环境变量示例文件
├── main.py                   # 程序入口
└── pyproject.toml            # 项目依赖和配置
```

## 使用场景

1. **财务数据分析**: 自动化处理大量上市公司的财务报告，提取关键财务指标
2. **投资研究**: 为投资分析师提供标准化的财务数据
3. **财务监控**: 持续监控特定公司的财务表现变化
4. **数据仓库构建**: 为财务数据仓库提供标准化的数据输入

## 环境配置

### 依赖管理
使用 Poetry 进行依赖管理：
```bash
poetry install
poetry shell
```

### 数据库配置
- 支持 PostgreSQL 和 DuckDB 两种数据库
- 默认使用 DuckDB，数据库文件位于 `data/db/financial_data.duckdb`
- 通过 `.env` 文件中的 `DATABASE` 变量指定数据库类型（postgresql 或 duckdb）
- PostgreSQL 连接字符串格式：`postgresql://username:password@host:port/database`
- DuckDB 数据库文件路径可通过 `DUCKDB_DB_PATH` 环境变量自定义

### 环境变量配置
参考 `.env.example` 文件：
```env
# 数据库类型配置
DATABASE=duckdb

# PostgreSQL 数据库连接字符串
POSTGRES_DB_URL=postgresql://postgres:postgres@localhost:5432/financial_statements

# DuckDB 数据库文件路径
DUCKDB_DB_PATH=./data/db/financial_data.duckdb
```

### 运行系统
```bash
# 命令行方式处理 PDF
python main.py

# 启动 Web UI
python ui/app.py
```

## 开发规范

### 代码风格
- 遵循 PEP 8 代码规范
- 使用 Black 进行代码格式化
- 使用 Ruff 进行代码检查
- 使用 MyPy 进行类型检查

### 测试
- 使用 PyTest 进行单元测试
- 覆盖率检查通过 `pytest-cov` 实现
- 测试文件位于 `tests/` 目录

### 日志管理
- 使用统一的 LoggerManager 管理日志
- 日志文件存储在 `logs/` 目录
- 支持日志轮转，默认单个文件最大 10MB，保留 5 个历史文件

## 扩展性

该系统设计具有良好的扩展性：
1. **新增财务指标**: 可通过扩展 ORM 模型添加新的财务指标字段
2. **支持新格式**: 工具层设计支持处理多种文档格式
3. **多数据库支持**: 通过 Peewee ORM 可以轻松切换数据库类型
4. **多语言模型**: 支持集成不同的 LLM 服务（如 OpenAI、其他模型）
5. **UI 扩展**: 基于 Gradio 的模块化 UI 设计，便于添加新功能

## 当前开发状态

### 已完成
- PDF 解析与章节提取
- 数据库模型设计与实现
- DuckDB/PostgreSQL 双数据库支持
- 跨页表格合并
- Excel 导出功能
- Web UI 基础功能

### 开发中
- LangGraph Agent 流程编排
- 数据库查询 UI
- 智能财务指标提取

### 待开发
- LangGraph 节点和图实现
- LLM 集成与智能分析
- 报告生成功能
