# FinancialAgent 智能财务报告分析系统

## 项目概述

FinancialAgent 是一个基于 LangGraph 构建的智能代理系统，专门用于解析上市公司财务报告的 PDF 文件，并将提取的结构化数据保存到数据库中，以供后续分析使用。

该系统采用现代化的 AI Agent 架构，结合自然语言处理技术，能够自动从复杂的财务报告中提取关键财务指标，并按照标准化的 Schema 存储数据。

## 技术架构

### 核心技术栈
- **Python 3.12+**: 主要开发语言
- **LangGraph**: Agent 图形化编排框架
- **LangChain**: 大语言模型接口和工具链
- **PyMuPDF (fitz)**: PDF 文本和图像提取
- **pdfplumber**: PDF 表格提取
- **SQLAlchemy**: 数据库 ORM 框架
- **PostgreSQL/DuckDB**: 支持 PostgreSQL 和 DuckDB 两种数据库
- **Pydantic**: 数据验证和结构化输出
- **Poetry**: 依赖管理

### 系统架构组件

#### 1. Agent 架构
- **State (src/agents/state.py)**: 定义了 LangGraph 的状态结构，包含 PDF 路径、原始 Markdown、结构化数据、执行状态等。
- **Graph (src/agents/graph.py)**: 构建 StateGraph、节点和边的逻辑（当前为空文件）。
- **Nodes (src/agents/nodes.py)**: 具体的节点函数实现（如 parse_pdf, save_data）（当前为空文件）。

#### 2. 工具层 (src/tools/)
- **general_pdf_parser.py**: PDF 通用解析类，提取正文、图片、表格并保存为不同格式。
- **file_manager.py**: Markdown 生成和文件夹管理。
- **chapter_extractor.py**: 专门负责识别和提取 PDF 指定章节，支持跨页表格合并。

#### 3. 数据库层 (src/db/)
- **db_connector.py**: 数据库操作逻辑，提供对 PostgreSQL 和 DuckDB 的增删查改操作。
- **table_data_saver.py**: 表格数据保存工具，将提取的表格数据保存到数据库。
- **models.py**: 定义数据库 ORM 模型和 Pydantic 数据验证 Schema，包括：
  - 财务报告周期枚举（Q1, H1, Q3, FY）
  - 财务报告和财务指标基础模型
  - 完整的财务报表模型（合并/母公司资产负债表、利润表、现金流量表）
  - 结构化数据提取 Schema（FinancialExtractionSchema）

#### 4. 工具函数 (src/utils/)
- **logger.py**: 日志管理

#### 5. 配置 (src/config.py)
- 环境变量与配置信息

## 核心功能

### PDF 解析与数据提取
1. **文本提取**: 将 PDF 正文内容转换为 Markdown 格式
2. **表格识别**: 从 PDF 中提取表格数据，支持跨页表格的自动合并
3. **图片提取**: 提取 PDF 中的图像并保存为 PNG 格式
4. **章节定位**: 利用 PDF 目录结构精确定位财务报告章节

### 数据结构化
1. **关键指标提取**: 从财务报表中识别并提取核心指标（营业收入、净利润、毛利率、净资产收益率等）
2. **Schema 验证**: 使用 Pydantic 模型确保提取数据的格式和质量
3. **上下文关联**: 保留数据来源的原始上下文和页码信息

### 数据存储
1. **数据库模型**: 提供完整的财务报表数据库模型
2. **多数据库支持**: 支持 PostgreSQL 和 DuckDB 两种数据库
3. **批量操作**: 支持批量创建和更新财务指标
4. **关联查询**: 支持报告与指标之间的关联查询
5. **DuckDB 文件位置**: 当使用 DuckDB 时，数据库文件默认存储在 `data/db/` 目录下

## 文件目录结构

```
FinancialAgent/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py          # 定义 LangGraph 的 State 结构 (TypedDict)
│   │   ├── graph.py          # 构建 StateGraph、节点和边的逻辑
│   │   └── nodes.py          # 具体的节点函数实现 (如 parse_pdf, save_data)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── general_pdf_parser.py     # 解析pdf，按照给定目录，将正文保存为md，表格保存为md，图片保存为jpg
│   │   ├── chapter_extractor.py      # 专门负责识别和提取 PDF 指定章节
│   │   └── file_manager.py   # 负责 Markdown 生成和文件夹管理
│   ├── db/
│   │   ├── __init__.py
│   │   ├── db_connector.py   # 数据库操作逻辑 (SQLAlchemy 或 DuckDB)
│   │   ├── table_data_saver.py       # 表格数据保存工具
│   │   └── models.py         # 数据库 ORM 模型及 Pydantic 数据验证
│   ├── utils/
│   │   ├── __init__.py
│   │   └── logger.py         # 日志管理
│   └── config.py             # 环境变量与配置信息
├── data/
│   ├── raw_pdfs/             # 原始 PDF 输入目录
│   ├── output/               # 生成的 Markdown 文件存储目录
│   └── db/                   # DuckDB 数据库文件存储目录
├── script/
│   └── init_postgresql_db.py # 数据库初始化脚本
├── tests/                    # 单元测试与集成测试
├── .env                      # 敏感信息 (API Keys, DB Credentials)
├── main.py                   # 程序入口，初始化 Agent 并运行
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
- 可通过环境变量或直接在 `src/db/db_connector.py` 中修改

### 运行系统
```bash
# 初始化数据库
python script/init_postgresql_db.py

# 运行主程序
python main.py
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

## 扩展性

该系统设计具有良好的扩展性：
1. **新增财务指标**: 可通过扩展 `FinancialExtractionSchema` 模型添加新的财务指标
2. **支持新格式**: 工具层设计支持处理多种文档格式
3. **多数据库支持**: 通过 SQLAlchemy ORM 可以轻松切换数据库类型
4. **多语言模型**: 支持集成不同的 LLM 服务（如 OpenAI、其他模型）