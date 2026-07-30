"""Agent 模块。

注意：原 __init__.py 曾在此处 eager-import analysis 子模块中的 agent 构造器，
但 analysis 内部依赖 src.graph.graph，而 graph 也从 src.agents.analysis import，
触发循环导入。现改为 lazy：消费者直接
`from src.agents.analysis.cyclical_stock_agent import create_cyclical_analysis`
即可（目前唯一消费者 src/graph/graph.py 已用此方式）。
"""