"""tests/test_skills/ 共享 fixture。"""
import pytest


@pytest.fixture
def mock_llm():
    """返回固定 JSON 的 mock LLM。"""
    class _Mock:
        def invoke(self, *args, **kwargs):
            class _Resp:
                content = '{"ok": true}'
            return _Resp()
    return _Mock()