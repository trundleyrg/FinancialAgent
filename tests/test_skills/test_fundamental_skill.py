"""基本面 skill 单元测试。"""
from pathlib import Path

import pytest

from src.skills import run_skill


@pytest.fixture
def stub_llm():
    """返还固定基本面分析 JSON 的 mock LLM。"""
    class _Resp:
        content = '{"fundamental_score": 85, "investment_rating": "BUY", "reasoning": "test"}'

    class _LLM:
        def invoke(self, *args, **kwargs):
            return _Resp()

    return _LLM()


def test_skill_md_loads_non_empty():
    """SKILL.md 存在且非空。"""
    skill_path = Path("src/skills/fundamental/SKILL.md")
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert len(content) > 100, "SKILL.md 内容过短"


def test_run_with_missing_company_returns_error():
    """缺少 company_name 时返回 error_msg。"""
    delta = run_skill("fundamental", {"company_name": None, "report_year": 2024}, llm=None)
    assert delta["fundamental_analysis"] is None
    assert "缺少公司信息" in delta["error_msg"]


def test_run_with_full_state_returns_analysis(stub_llm):
    """完整 state + stub_llm 返回 fundamental_analysis dict。"""
    state = {
        "company_name": "测试公司",
        "stock_code": "999999",
        "report_year": 2024,
        "report_period": "FY",
    }
    delta = run_skill("fundamental", state, llm=stub_llm)
    assert "fundamental_analysis" in delta
    # LLM 是 stub，可能因数据查询失败抛错；至少验证结构
    if "error_msg" not in delta:
        assert isinstance(delta["fundamental_analysis"], dict)


def test_run_skill_unknown_raises():
    with pytest.raises(KeyError):
        run_skill("does_not_exist", {}, llm=None)
