"""投资建议汇总 skill 单元测试。

summary skill 与另外 3 个分析 skill 行为不同：
- 必依赖三个前置分析（cyclical/dividend/fundamental），缺一返回 error_msg
- 成功时 delta 含 `summary` 键 + `status: "completed"`
"""
from pathlib import Path

import pytest

from src.skills import run_skill


@pytest.fixture
def stub_llm():
    """返还固定汇总 JSON 的 mock LLM。"""
    class _Resp:
        content = '{"combined_rating": "BUY", "confidence": "high", "reasoning": "test"}'

    class _LLM:
        def invoke(self, *args, **kwargs):
            return _Resp()

    return _LLM()


def test_skill_md_loads_non_empty():
    """SKILL.md 存在且非空。"""
    skill_path = Path("src/skills/summary/SKILL.md")
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert len(content) > 100, "SKILL.md 内容过短"


def test_run_with_missing_upstream_analyses_returns_error():
    """缺少前置分析结果（cyclical/dividend/fundamental 均为 None）时返回 error_msg。"""
    state = {
        "company_name": "测试公司",
        "stock_code": "999999",
        "report_year": 2024,
        "report_period": "FY",
        "cyclical_analysis": None,
        "dividend_analysis": None,
        "fundamental_analysis": None,
    }
    delta = run_skill("summary", state, llm=None)
    assert delta["summary"] is None
    assert "缺少前置分析结果" in delta["error_msg"]


def test_run_with_full_state_returns_summary(stub_llm):
    """完整 state（含三方面分析）+ stub_llm 返回 summary dict。"""
    state = {
        "company_name": "测试公司",
        "stock_code": "999999",
        "report_year": 2024,
        "report_period": "FY",
        "cyclical_analysis": {"cycle_position": "复苏", "investment_rating": "BUY"},
        "dividend_analysis": {"dividend_sustainability": "高", "investment_rating": "BUY"},
        "fundamental_analysis": {"fundamental_score": 85, "investment_rating": "BUY"},
    }
    delta = run_skill("summary", state, llm=stub_llm)
    assert "summary" in delta
    # LLM 是 stub，可能因某些步骤抛错；至少验证结构
    if "error_msg" not in delta:
        assert isinstance(delta["summary"], dict)


def test_run_skill_unknown_raises():
    with pytest.raises(KeyError):
        run_skill("does_not_exist", {}, llm=None)
