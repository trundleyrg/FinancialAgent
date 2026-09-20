"""Skill 接口协议（typing.Protocol，不强制运行时检查）。"""
from pathlib import Path
from typing import Any, Protocol


class Skill(Protocol):
    """一个 skill 模块的形态约定。"""
    DESCRIPTION: str
    SKILL_DIR: Path

    def run(self, state: Any, llm: Any) -> dict:
        """执行 skill；返回 state delta。"""