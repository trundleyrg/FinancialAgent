# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

## 项目概述

FinancialAgent 是一个基于 LangGraph 的智能代理系统，用于解析上市公司财务报告 PDF 并将结构化数据存储到数据库中进行投资分析。

## 命令

```bash
# 安装依赖
poetry install
poetry shell

# 运行 CLI（处理 data/000423/ 中的 PDF）
python main.py

# 运行 FastAPI 后端（http://127.0.0.1:8000，文档在 /docs）
python ui/backend/main.py
# 或
python script/start_fastapi.py

# 运行测试
pytest tests/ -v

# 调试模式测试（LangGraph 构建 + 东阿阿胶分析，输出到 data/000423/mmemory/）
PYTHONIOENCODING=utf-8 python tests/test_graph_debug.py

# 代码质量
black src/
ruff check src/
mypy src/
```

### 调试输出目录

- `data/{stock_code}/memory/langgraph_trace.jsonl` - LangGraph 对话流程追踪记录
- `data/{stock_code}/memory/分析报告_*.md` - 生成的 Markdown 分析报告

## 架构

### 分层结构

1. **Graph** (`src/graph/`) - LangGraph 编排和状态管理
   - `state.py`: `FinancialState` TypedDict - 定义代理状态，包括股票类型分类字段
   - `graph.py`: `create_financial_agent_graph()` 构建主工作流；`FinancialAgentsGraph` 类编排完整工作流
   - `stock_type_config.py`: 股票类型分类关键词（位于 `src/stock_tools/`）
   - `coordinator_nodes.py`: 协调器节点（check_data_availability, parse_pdf, extract_financial_data, save_to_database）
   - `propagation.py`: `Propagator` 类用于状态初始化
   - `result_persister.py`: 分析结果持久化 - 从 jsonl 提取结果并生成 Markdown 报告

2. **Agents** (`src/agents/analysis/`) - 独立分析代理
   - `cyclical_stock_agent.py`: `create_cyclical_analysis(llm)` - 周期股分析
   - `dividend_stock_agent.py`: `create_dividend_analysis(llm)` - 红利股分析
   - `fundamental_agent.py`: `create_fundamental_analysis(llm)` - 基本面分析
   - `summary_agent.py`: `create_summary_agent(llm)` - 投资建议汇总

3. **Tools** (`src/tools/`) - PDF 处理和数据下载
   - `chapter_extractor.py`: `PDFChapterExtractor` - 通过目录定位章节，提取跨页表格，关联表头
   - `general_pdf_parser.py`: 通用 PDF 解析器，用于文本、图片、表格
   - `download_cninfo_reports.py`: CNInfo 年报下载器，支持代码或名称查询

4. **Database** (`src/db/`) - 数据持久化
   - `db_connector.py`: `DatabaseConnector` 类 - PostgreSQL 和 DuckDB 的统一接口，提供 CRUD 操作
   - `db_connector.py`: `parse_chinese_unit_to_factor(unit_str)` - 将 PDF 报表抬头的"单位：xxx"换算到「人民币元」
   - `db_connector.py`: `_parse_table_data_to_model_data(table_data, model_class, unit_str)` - 解析表格数据并按单位换算；每股收益字段不参与换算
   - `models.py`: Peewee ORM 模型 + Pydantic 数据验证模型；依据财政部财会〔2014〕6号、〔2018〕15号、〔2019〕6号/16号、〔2023〕21号、〔2024〕24号 标准设计

5. **Utils** (`src/utils/`)
   - `logger.py`: LoggerManager，包含预定义日志器（pdf_logger, chapter_logger, db_logger 等）
   - `llm_client.py`: AI 客户端封装

### 数据库配置

- `DATABASE=duckdb`（默认）或 `DATABASE=postgresql`
- DuckDB 文件: `data/db/financial_data.duckdb`
- PostgreSQL: 通过 `.env` 中的 `POSTGRES_DB_URL` 配置

### 数据库初始化

| 脚本 | 用途 |
|------|------|
| `script/init_duckdb.py` | DuckDB 数据库初始化（推荐默认数据库） |
| `script/init_postgresql_db.py` | PostgreSQL 数据库初始化 |

DuckDB 用法：

```bash
# 默认路径初始化（./data/db/financial_data.duckdb）
python script/init_duckdb.py

# 指定路径 / 重置 / 检查 / 列出现有表 / 查看 ORM 模型
python script/init_duckdb.py --path ./data/db/financial_data.duckdb
python script/init_duckdb.py --reset
python script/init_duckdb.py --check
python script/init_duckdb.py --list
python script/init_duckdb.py --models
```

PostgreSQL 用法：

```bash
# 默认（自动读 .env 的 POSTGRES_DB_URL）
python script/init_postgresql_db.py

# 显式指定连接参数
python script/init_postgresql_db.py --host localhost --port 5432 --user postgres --password postgres --dbname financial

# 仅测试连接 / drop 重建
python script/init_postgresql_db.py --check-only
python script/init_postgresql_db.py --reset
```

两个脚本均通过 [src/db/db_connector.py](src/db/db_connector.py) 共用底层建表逻辑。

### 入口点

| 入口点 | 用途 |
|--------|------|
| `main.py` | CLI - 处理 `data/000423/` 中的 PDF |
| `ui/backend/main.py` | FastAPI Web 服务器 |
| `script/start_fastapi.py` | 备选 FastAPI 启动方式 |
| `script/init_duckdb.py` | DuckDB 数据库初始化 |
| `script/init_postgresql_db.py` | PostgreSQL 数据库初始化 |
| `script/extract_financial_statements.py` | 离线提取财报到 Excel |
| `src/tools/download_cninfo_reports.py` | 从 CNInfo 下载年报（支持代码或名称查询） |

## 股票类型分类

支持的类型（多选）: `cyclical`, `dividend`, `growth`, `value`, `defensive`, `fundamental`

分类配置: `src/stock_tools/stock_type_config.py` - 修改 `STOCK_TYPE_KEYWORDS` 可调整规则

## 财务报表单位规范

所有从 PDF 提取的财务数据必须**统一换算到「人民币元」**后入库。

- 单位识别：依靠 `PDFChapterExtractor` 提取的 `TableWithHeader.unit` 字段（来自报表抬头"单位：xxx"）
- 单位换算由 `src/db/db_connector.py:parse_chinese_unit_to_factor` 实现：
  - 元 → 1；千元 → 1,000；万元 → 10,000；百万元 → 1,000,000；亿元 → 100,000,000
  - "人民币元/万元" 等前缀会自动剥离
- 每股收益字段（help_text 含"每股"）不参与金额换算，保持「元/股」
- 项目范围：**仅考虑人民币元计价的国内企业报表**，不做汇率换算

参考资料：

- 财政部《企业会计准则第 30 号——财务报表列报》（财会〔2014〕6 号）
- 财政部《关于修订印发合并财务报表格式（2019 版）的通知》（财会〔2019〕16 号）
- 详细标准：[docs/合并资产负债表标准.md](docs/合并资产负债表标准.md)、[docs/合并利润表标准.md](docs/合并利润表标准.md)、[docs/合并现金流量表标准.md](docs/合并现金流量表标准.md)、[docs/财报三表索引.md](docs/财报三表索引.md)

## 母公司报表与合并报表的差异

[src/db/models.py](src/db/models.py) 中 6 张主要报表分两组：合并报表（3 张）+ 母公司报表（3 张）。
两组共用相同的「单位换算到人民币元」规范，但在结构与项目上有重要差异：

| 维度 | 合并报表 | 母公司报表 |
|---|---|---|
| 视角 | 集团（含子公司） | 单一法人（母公司自身） |
| 长期股权投资 | 抵消后按权益法 | 按**成本法**全额列示对子公司投资 |
| 内部往来 | 已抵消 | 完整列示 |
| 商誉 | 单列（合并成本 > 可辨认净资产公允价值） | **不存在** |
| 少数股东权益 / 少数股东损益 | 单列 | **不存在** |
| 投资收益 | 含权益法对联营/合营企业投资收益 | 主要为子公司分红（成本法） |
| 利润表编号 | 一/二/三/四/五/六/七/八 | **一/二/三/四/五/六/七**（编号前移） |

`src/db/models.py` 已按此差异严格划分字段：
- `ParentCompanyBalanceSheet` 无 `minority_interest`、`total_equity_attributable_to_parent_company`、`goodwill` 业务通常为 NULL
- `ParentCompanyIncomeStatement` 无 `net_profit_attributable_to_parent`、`minority_interest_net_profit`、`*_attributable_to_minority` 等
- `ParentCompanyCashFlowStatement` 无 `capital_contribution_from_minority`、`dividend_to_minority` 等

详细差异与编号对照表：[docs/母公司三表索引.md](docs/母公司三表索引.md)、[docs/母公司资产负债表标准.md](docs/母公司资产负债表标准.md)、[docs/母公司利润表标准.md](docs/母公司利润表标准.md)、[docs/母公司现金流量表标准.md](docs/母公司现金流量表标准.md)

## 核心工作流

主图（`src/graph/graph.py`）实现以下流程：

1. **check_data_availability** → 检查数据库中是否存在历史数据
2. **条件路由** → 如无数据：parse_pdf → extract → save_to_database
3. **并行分析** → 根据股票类型分类运行 cyclical/fundamental/dividend 分析
4. **汇总** → Summary 代理合并所有结果

`FinancialAgentsGraph` 类（`src/graph/graph.py`）提供高级接口：

```python
from src.graph import FinancialAgentsGraph

agent = FinancialAgentsGraph(llm=your_llm)
result = agent.propagate(
    company_name="某公司",
    business_scope="房地产开发、经营",
    stock_code="000423",
    report_year=2024
)
```
