# LangGraph 架构文档

本文档介绍 FinancialAgent 项目中使用的 LangGraph 组件及其工作流程。

## 1. 核心组件

### 1.1 StateGraph

**文件**: `src/graph/state.py`

状态图的核心结构，定义了 Agent 处理过程中的所有状态信息。

```python
from src.graph.state import FinancialState
```

**FinancialState 关键字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `pdf_path` | str | 待处理的 PDF 文件路径 |
| `raw_markdown` | str | 提取的原始 Markdown 内容 |
| `structured_data` | Annotated[List[dict], add] | 结构化财务数据（累积） |
| `company_name` | str | 公司全名 |
| `stock_code` | str | 股票代码 |
| `stock_types` | Annotated[List[str], add] | 股票类型分类（多选） |
| `status` | str | 任务状态 |
| `record_id` | int | 数据库记录 ID |

### 1.2 StateGraph

**文件**: `src/graph/graph.py`

状态图的构建器，用于定义节点和边的流转逻辑。

```python
from langgraph.graph import StateGraph, END
```

**主要方法**:
- `StateGraph(FinancialState)` - 创建状态图
- `graph.add_node(name, func)` - 添加节点
- `graph.add_edge(from_node, to_node)` - 添加普通边
- `graph.add_conditional_edges(source, routing_fn, path_map)` - 添加条件边
- `graph.set_entry_point(node_name)` - 设置入口点
- `graph.compile()` - 编译图为可执行图

### 1.3 END

**文件**: `langgraph.graph`

标记图终点的特殊节点。

```python
from langgraph.graph import END
```

## 2. 节点类型

### 2.1 协调器节点 (Coordinator Nodes)

**文件**: `src/graph/coordinator_nodes.py`

负责调用具体工具完成特定任务，不包含 LLM 调用。

| 节点名称 | 函数 | 作用 |
|---------|------|------|
| `check_data_availability` | `create_check_data_availability_node()` | 检查数据库中是否有近 N 年数据 |
| `parse_pdf` | `create_parse_pdf_node()` | 使用 PDFChapterExtractor 解析 PDF |
| `extract_financial_data` | `create_extract_financial_data_node()` | 提取三大主表结构化数据 |
| `save_to_database` | `create_save_to_database_node()` | 保存数据到数据库 |

### 2.2 分析 Agent 节点 (Analysis Agent Nodes)

**文件**: `src/agents/analysis/`

使用 LLM 进行专业分析的节点。

| 节点名称 | 文件 | 作用 |
|---------|------|------|
| `analysis_cyclical` | `cyclical_stock_agent.py` | 周期股分析 |
| `analysis_dividend` | `dividend_stock_agent.py` | 红利股分析 |
| `analysis_fundamental` | `fundamental_agent.py` | 基本面分析 |
| `aggregate` | `summary_agent.py` | 结果汇总 |

### 2.3 意图分类节点

**文件**: `src/graph/graph.py`

```python
intent_classification_node(state) -> FinancialState
```

根据公司经营范围和名称，使用关键词匹配判断股票类型（多选）。

## 3. 工作流程图

### 3.1 主工作流程 (`src/graph/graph.py`)

```
┌─────────────────────────────┐
│   check_data_availability    │ ← 入口点
└───────────┬─────────────────┘
            │
            ▼
    ┌───────┴───────┐
    │ 条件路由      │
    │ should_parse_ │
    │ pdf           │
    └───┬───────┬───┘
        │       │
   有数据│       │无数据
        │       ▼
        │  ┌──────────┐
        │  │ parse_pdf│
        │  └────┬────┘
        │       ▼
        │  ┌───────────────────┐
        │  │extract_financial_ │
        │  │data               │
        │  └────┬─────────────┘
        │       ▼
        │  ┌──────────────┐
        │  │save_to_      │
        │  │database      │
        │  └────┬─────────┘
        │       │
        ▼───────┴──────┐
                       │
            ┌──────────┴──────────┐
            │                      │
            ▼                      ▼
   ┌────────────────┐    ┌────────────────┐
   │run_cyclical_   │    │run_fundamental_│
   │analysis        │    │analysis        │
   └───────┬────────┘    └───────┬────────┘
           │                     │
           └─────────┬───────────┘
                     ▼
            ┌──────────────┐
            │  run_summary │
            └──────┬───────┘
                   ▼
                 END
```

**流程说明**:
1. `check_data_availability` 检查数据库中是否有近十年数据
2. 根据检查结果条件路由：
   - **有数据** → 直接执行分析
   - **无数据** → `parse_pdf` → `extract_financial_data` → `save_to_database`
3. 数据准备好后，**并行**执行 `run_cyclical_analysis` 和 `run_fundamental_analysis`
4. 两个分析都完成后，执行 `run_summary` 汇总结果
5. `run_summary` 后进入 `END`，流程结束

### 3.2 意图分类流程 (`src/graph/graph.py`)

```
┌──────────────────────────┐
│ intent_classification     │ ← 入口点
└───────────┬──────────────┘
            │
            ▼
    ┌───────┴────────┐
    │ 条件边          │
    │ add_conditional_│
    │ edges          │
    └───┬────┬───┬───┘
        │    │   │
   cyclical│   │dividend
        │    │   │fundamental
        ▼    ▼   ▼
   ┌────┐ ┌───┐ ┌──────────┐
   │    │ │   │ │analysis_ │
   │    │ │   │ │fundamenta│
   │    │ │   │ │l         │
   └──┬─┘ └──┬─┘ └────┬────┘
      │       │        │
      └───┬───┴────────┘
          ▼
      ┌────────┐
      │aggregate│
      └───┬────┘
          ▼
        END
```

## 4. 条件路由

### 4.1 `should_parse_pdf`

**文件**: `src/graph/graph.py`

```python
def should_parse_pdf(state: FinancialState) -> Literal["parse_pdf", "run_analysis"]:
    data_availability = state.get("data_availability", {})
    has_data = data_availability.get("has_data", False)
    return "run_analysis" if has_data else "parse_pdf"
```

### 4.2 `should_run_cyclical` / `should_run_dividend` / `should_run_fundamental`

**文件**: `src/graph/graph.py`

```python
def should_run_cyclical(state: FinancialState) -> bool:
    return "cyclical" in state.get("stock_types", [])

def should_run_dividend(state: FinancialState) -> bool:
    return "dividend" in state.get("stock_types", [])

def should_run_fundamental(state: FinancialState) -> bool:
    stock_types = state.get("stock_types", [])
    return "fundamental" in stock_types or not any(t in stock_types for t in ["cyclical", "dividend"])
```

## 5. 图的构建与编译

### 5.1 创建主图

```python
from src.graph.graph import create_financial_agent_graph, compile_graph

graph = create_financial_agent_graph(llm)
compiled_graph = graph.compile()
```

### 5.2 执行图

```python
# 初始化状态
initial_state = {
    "pdf_path": "/path/to/report.pdf",
    "company_name": "某公司",
    "stock_code": "000001",
    "status": "pending"
}

# 执行图
result = compiled_graph.invoke(initial_state)
```

## 6. 状态累积机制

LangGraph 的 `Annotated[List[T], add]` 语法允许在多个节点间累积数据：

```python
# 在 FinancialState 中定义
structured_data: Annotated[List[dict], add]
stock_types: Annotated[List[str], add]

# 节点返回值会自动累积
return {"structured_data": [new_item]}  # 追加到列表
return {"stock_types": ["cyclical"]}    # 追加到列表
```

## 7. 组件依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                      StateGraph (主控)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   FinancialState                     │   │
│  │  (TypedDict: pdf_path, raw_markdown, stock_types...) │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                        节点 (Nodes)                          │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Coordinator      │  │ Analysis Agent  │                  │
│  │ Nodes            │  │ Nodes           │                  │
│  │ (nodes.py)       │  │ (analysis/)     │                  │
│  └─────────────────┘  └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     边 (Edges)                               │
│  - add_edge(): 普通边                                        │
│  - add_conditional_edges(): 条件边                          │
│  - END: 终点                                                │
└─────────────────────────────────────────────────────────────┘
```

## 8. 文件索引

| 文件 | 职责 |
|------|------|
| `src/graph/state.py` | FinancialState 定义 |
| `src/agents/stock_tools/stock_type_config.py` | 股票类型分类配置 |
| `src/graph/coordinator_nodes.py` | 协调器节点实现 |
| `src/graph/graph.py` | 主图构建 (`create_financial_agent_graph`) |
| `src/graph/propagation.py` | 状态传播器 |
| `src/agents/analysis/*.py` | 分析 Agent 节点实现 |
