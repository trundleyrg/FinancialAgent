"""
Agent 分析模块

包含各种分析 Agent：
- 总结 Agent

注：周期股 / 红利股 / 基本面分析 agent 已分别迁移至 src/skills/cyclical/（Task 4）、
src/skills/dividend/（Task 5）和 src/skills/fundamental/（Task 6）。
"""
from .summary_agent import create_summary_agent

__all__ = [
    "create_summary_agent",
]
