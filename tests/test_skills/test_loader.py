"""src/skills/ 加载器测试。"""
from pathlib import Path

import pytest


def test_discover_skills_finds_four_skills():
    from src.skills._loader import discover_skills
    skills = discover_skills()
    assert set(skills.keys()) == {"cyclical", "dividend", "fundamental", "summary"}
    for name, mod in skills.items():
        assert hasattr(mod, "run"), f"{name} 缺少 run()"
        assert hasattr(mod, "DESCRIPTION"), f"{name} 缺少 DESCRIPTION"


def test_run_skill_dispatches_to_correct_module():
    from src.skills import run_skill
    delta = run_skill("cyclical", {"company_name": None}, llm=None)
    assert delta == {}  # 空 skill 当前返回空字典


def test_run_skill_unknown_raises_keyerror():
    from src.skills import run_skill
    with pytest.raises(KeyError):
        run_skill("nonexistent", {}, llm=None)


def test_skill_md_has_deepagents_frontmatter():
    """deepagents 标准：SKILL.md 必须以 --- 包围的 YAML frontmatter 起始，含 name + description。"""
    from src.skills._loader import SKILLS_ROOT
    from deepagents.middleware.skills import _parse_skill_metadata
    for name in ("cyclical", "dividend", "fundamental", "summary"):
        path = SKILLS_ROOT / name / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        # _parse_skill_metadata 第 2 参数类型为 str
        meta = _parse_skill_metadata(content, str(path), name)
        assert meta is not None, f"{name} SKILL.md frontmatter 不合法（缺 name/description）"
        assert meta["name"] == name, f"{name} frontmatter.name 与目录名不一致"
        assert meta["description"], f"{name} frontmatter.description 为空"


def test_loader_compatible_with_deepagents_skillsmiddleware():
    """校验 src/skills/ 可被 deepagents.middleware.skills.SkillsMiddleware 加载（不报错）。"""
    from deepagents.middleware.skills import SkillsMiddleware
    from deepagents.backends.filesystem import FilesystemBackend
    backend = FilesystemBackend(root_dir="src/skills/")
    mw = SkillsMiddleware(backend=backend, sources=["src/skills/"])
    # 仅校验构造不抛错；不进入 invoke 链路
    assert mw is not None