"""周期股分析 skill（占位 — P3 阶段实现完整逻辑）。"""
from pathlib import Path

from src.skills._loader import read_skill_description

SKILL_DIR = Path(__file__).parent

DESCRIPTION = read_skill_description(SKILL_DIR / "SKILL.md")


def run(state, llm) -> dict:
    """占位实现：返回空 state delta。"""
    return {}