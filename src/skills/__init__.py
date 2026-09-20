"""Skills 命名空间。

LangGraph 节点通过 run_skill(name, state, llm) 调用 skill。
skill 模块在导入时一次性扫描，避免运行时反射开销。
"""
from src.skills._loader import discover_skills

_REGISTRY: dict[str, object] = discover_skills()


def run_skill(name: str, state, llm) -> dict:
    """统一 skill 调用入口；返回 state delta。

    Raises:
        KeyError: name 不在 registry 中
    """
    skill = _REGISTRY[name]
    return skill.run(state, llm)


__all__ = ["run_skill", "discover_skills"]