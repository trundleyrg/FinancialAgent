"""自动扫描 src/skills/<name>/ 并构建 registry。

兼容 deepagents 标准 SKILL.md 格式：
- YAML frontmatter（--- name/description ---）必需
- 复用 deepagents.middleware.skills._parse_skill_metadata 解析
- 校验 frontmatter.name 与目录名一致
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path

from deepagents.middleware.skills import _parse_skill_metadata

logger = logging.getLogger("Skills")

SKILLS_ROOT = Path(__file__).parent


def discover_skills(skills_dir: Path | None = None) -> dict[str, object]:
    """扫描 skills_dir/<name>/skill.py，返回 {dir_name: module}。

    跳过：
    - 以 '_' 开头的目录（私有）
    - 没有 skill.py 或 SKILL.md 的目录
    - SKILL.md frontmatter 不合法（缺 name/description）
    - frontmatter.name 与目录名不一致
    """
    root = skills_dir or SKILLS_ROOT
    result: dict[str, object] = {}
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_"):
            continue
        skill_md = sub / "SKILL.md"
        skill_py = sub / "skill.py"
        if not skill_md.exists():
            logger.warning("Skill '%s' 缺少 SKILL.md，已跳过加载", sub.name)
            continue
        if not skill_py.exists():
            logger.warning("Skill '%s' 缺少 skill.py，已跳过加载", sub.name)
            continue
        content = skill_md.read_text(encoding="utf-8")
        # _parse_skill_metadata 第 2 参数类型为 str（用于错误日志输出 skill_path）
        metadata = _parse_skill_metadata(content, str(skill_md), sub.name)
        if metadata is None:
            logger.warning(
                "Skill '%s' SKILL.md frontmatter 不合法（缺 name/description），已跳过",
                sub.name,
            )
            continue
        if metadata["name"] != sub.name:
            logger.warning(
                "Skill '%s' frontmatter.name='%s' 与目录名不符，已跳过",
                sub.name, metadata["name"],
            )
            continue
        mod = importlib.import_module(f"src.skills.{sub.name}.skill")
        result[sub.name] = mod
    return result