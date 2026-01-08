# FinancialAgent

解析上市公司财务报告的pdf，并保存在数据库中，以供后续分析。

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
│   │   ├── general_pdf_parser.py     # 集成文本和表格提取工具 (如 PyMuPDF, TableTransformer)
│   │   ├── db_connector.py   # 数据库操作逻辑 (SQLAlchemy 或 DuckDB)
│   │   └── file_manager.py   # 负责 Markdown 生成和文件夹管理
│   ├── schema/
│   │   ├── __init__.py
│   │   └── models.py         # 数据库 ORM 模型及 Pydantic 数据验证
│   ├── utils/
│   │   ├── __init__.py
│   │   └── logger.py         # 日志管理
│   └── config.py             # 环境变量与配置信息
├── data/
│   ├── raw_pdfs/             # 原始 PDF 输入目录
│   └── output/               # 生成的 Markdown 文件存储目录
├── tests/                    # 单元测试与集成测试
├── .env                      # 敏感信息 (API Keys, DB Credentials)
├── main.py                   # 程序入口，初始化 Agent 并运行
└── requirements.txt          # 依赖列表
```
