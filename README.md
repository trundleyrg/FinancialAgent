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
│   │   └── file_manager.py   # 负责 Markdown 生成和文件夹管理
│   ├── db/
│   │   ├── __init__.py
│   │   ├── db_connector.py   # 数据库操作逻辑 (Peewee ORM)
│   │   ├── init_postgresql_db.py     # PostgreSQL 数据库初始化脚本
│   │   ├── models.py         # Pydantic 数据验证模型
│   │   └── table_models.py   # Peewee 数据库表模型
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
├── pyproject.toml            # Poetry 依赖管理配置
└── poetry.lock               # Poetry 锁定文件
```
