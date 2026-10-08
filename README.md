# FinancialAgent

解析上市公司财务报告的pdf，并保存在数据库中，以供后续分析。

## 技术架构

- **Python 3.12.13**: 主要开发语言
- **LangGraph / LangChain**: Agent 图形化编排框架
- **LangChain OpenAI**: AI 模型接口（支持 OpenAI、DeepSeek 等）
- **Peewee ORM**: 数据库 ORM 框架
- **PostgreSQL/DuckDB**: 支持两种数据库
- **Gradio**: Web UI 界面

## 文件结构

```text
FinancialAgent/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py          # 定义 LangGraph 的 State 结构 (TypedDict)
│   │   ├── graph.py          # 构建 StateGraph、节点和边的逻辑
│   │   └── nodes.py          # 具体的节点函数实现 (如 parse_pdf, save_data)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── general_pdf_parser.py     # 解析pdf，将正文保存为md，表格保存为md，图片保存为png
│   │   ├── chapter_extractor.py      # 专门负责识别和提取 PDF 指定章节
│   │   ├── file_manager.py           # 负责 Markdown 生成和文件夹管理
│   │   ├── skill_result_writer.py    # skill 产出结果统一持久化
│   │   └── visualization.py          # 通用多序列趋势图(PNG + DataFrame)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── db_connector.py   # 数据库操作逻辑 (Peewee ORM)
│   │   ├── models.py         # Pydantic 数据验证模型
│   │   ├── table_models.py   # Peewee 数据库表模型
│   │   └── repository/       # 查询层（项目唯一的读入口）
│   │       ├── keys.py       # ReportKey
│   │       ├── base.py       # BaseRepository + _ModelToDict
│   │       ├── reports.py    # ReportRepository
│   │       ├── statements.py # StatementRepository + 注册表
│   │       ├── metrics.py    # MetricRepository
│   │       └── share_structure.py # ShareStructureRepository
│   ├── script/
│   │   ├── init_duckdb.py     # DuckDB 数据库初始化脚本
│   │   ├── init_postgresql_db.py  # PostgreSQL 数据库初始化脚本
│   │   ├── extract_financial_statements.py  # 离线提取财报到 Excel
│   │   └── start_fastapi.py   # 启动 FastAPI 服务
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py         # 日志管理
│   │   └── llm_client.py     # AI 客户端（基于 LangChain OpenAI）
│   └── config.py             # 环境变量与配置信息
├── ui/
│   ├── app.py                # Gradio 主界面入口
│   ├── pdf_parser_ui.py      # PDF 解析功能界面
│   └── db_query_ui.py        # 数据库查询功能界面
├── data/
│   ├── raw_pdfs/             # 原始 PDF 输入目录
│   ├── output/               # 生成的 Markdown 文件存储目录
│   └── db/                   # DuckDB 数据库文件存储目录
├── script/                   # 工具脚本目录
├── tests/                    # 单元测试与集成测试
├── logs/                     # 日志文件目录
├── docs/                     # 文档目录
├── .env                      # 敏感信息 (API Keys, DB Credentials)
├── main.py                   # 程序入口
├── requirements.txt          # 依赖声明（uv pip install -r requirements.txt）
├── ruff.toml                 # Ruff 配置
├── mypy.ini                  # Mypy 配置
└── pytest.ini                # pytest 配置
```

## 可视化工具

`src/tools/visualization.py` 提供 3 个公开 API:

- `build_trend_table(series)` — 把 `{period: {metric: value}}` 展平成 DataFrame
- `plot_multi_series_trend(series, output_path)` — 渲染 PNG 趋势图
- `render_trend_chart_and_table(series, output_path)` — 一步到位（写图 + 返回表）

按指标数量自动选择布局：1 → single，2 → twinx，3+ → subplot。

最小示例：

```python
from src.tools.visualization import render_trend_chart_and_table

series = {
    "2021": {"营收": 38.5e8, "净利": 4.4e8, "分红率": 44.77},
    "2022": {"营收": 40.4e8, "净利": 7.8e8, "分红率": 53.72},
    # ...
}
chart_path, table = render_trend_chart_and_table(series, output_path="trend.png")
table.to_csv("trend.csv")
```

详细文档与周期股复用指引见 [docs/visualization_usage.md](docs/visualization_usage.md)。

## 数据库查询层

项目在 `src/db/db_connector.py`（CRUD/DDL/PDF-parse/Excel）之上构建了一套**统一的查询层** `src/db/repository/`，作为项目唯一的读入口：

- **唯一读入口**：所有读路径必须走 repository，禁止直连 `db_connector.filter_records`
- **纯 dict 返回**：消除 Peewee Model / dict 双轨
- **`ReportKey` 寻址**：`stock_code` / `company_name` / `year` / `period` 一处贯通
- **缺失数据保持缺失**：跨年/跨期查询中缺失年份不抛错、不填充
- **注册表扩展**：新增报表只需 `register_statement(StatementSpec(...))`，无需改 repo 方法

使用示例：

```python
from src.db import ReportKey, StatementRepository
from src.db.db_connector import get_db

db = get_db()
repo = StatementRepository(db)
rows = repo.get_multi_year_statement(
    ReportKey(stock_code="000423", period="FY"),
    "consolidated_balance_sheet",
    start_year=2020, end_year=2024,
)
# rows 是 {year: dict}；缺失年份键缺失
```

消费方已迁移：`src/agents/tools/db_tools.py` / `ui/backend/services/db_service.py` / `src/agents/tools/roe_calculator.py` / `src/tools/pdf_db_comparator.py` / `script/verify_parent_company.py` 全部改走 repository。

新增报表的扩展步骤详见 [`docs/添加新报表指南.md`](docs/添加新报表指南.md)。
