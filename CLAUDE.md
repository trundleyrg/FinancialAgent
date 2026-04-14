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
   - `stock_type_config.py`: 股票类型分类关键词（位于 `src/agents/stock_tools/`）
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
   - `models.py`: Peewee ORM 模型 + Pydantic 数据验证模型

5. **Utils** (`src/utils/`)
   - `logger.py`: LoggerManager，包含预定义日志器（pdf_logger, chapter_logger, db_logger 等）
   - `llm_client.py`: AI 客户端封装

### 数据库配置

- `DATABASE=duckdb`（默认）或 `DATABASE=postgresql`
- DuckDB 文件: `data/db/financial_data.duckdb`
- PostgreSQL: 通过 `.env` 中的 `POSTGRES_DB_URL` 配置

### 入口点

| 入口点 | 用途 |
|--------|------|
| `main.py` | CLI - 处理 `data/000423/` 中的 PDF |
| `ui/backend/main.py` | FastAPI Web 服务器 |
| `script/start_fastapi.py` | 备选 FastAPI 启动方式 |
| `src/tools/download_cninfo_reports.py` | 从 CNInfo 下载年报（支持代码或名称查询） |

## 股票类型分类

支持的类型（多选）: `cyclical`, `dividend`, `growth`, `value`, `defensive`, `fundamental`

分类配置: `src/agents/stock_tools/stock_type_config.py` - 修改 `STOCK_TYPE_KEYWORDS` 可调整规则

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
