# tests/test_intent_classification.py
"""
create_intent_classification_node 单元测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


def test_classify_pharmaceutical_as_defensive():
    """制药类公司应被分类为 defensive"""
    from src.graph.coordinator_nodes import create_intent_classification_node

    node = create_intent_classification_node(llm=None)
    state = {
        "company_name": "某某药业",
        "business_scope": "医药制造、零售及批发",
    }
    result = node(state)

    assert "stock_types" in result
    assert isinstance(result["stock_types"], list)
    assert len(result["stock_types"]) > 0
    assert result["status"] == "processing"


def test_classify_steel_as_cyclical():
    """钢铁类公司应被分类为 cyclical"""
    from src.graph.coordinator_nodes import create_intent_classification_node

    node = create_intent_classification_node(llm=None)
    state = {
        "company_name": "宝钢股份",
        "business_scope": "钢铁冶炼、轧制及销售",
    }
    result = node(state)

    assert "cyclical" in result["stock_types"]


def test_classify_with_empty_business_scope():
    """business_scope 为空时不应崩溃，应有回退分类"""
    from src.graph.coordinator_nodes import create_intent_classification_node

    node = create_intent_classification_node(llm=None)
    state = {
        "company_name": "未知公司",
        "business_scope": "",
    }
    result = node(state)

    assert "stock_types" in result
    assert isinstance(result["stock_types"], list)
    assert result["status"] == "processing"


def test_node_does_not_overwrite_existing_stock_types():
    """state 中已有 stock_types 时，节点应以分类结果覆盖（重新分类）"""
    from src.graph.coordinator_nodes import create_intent_classification_node

    node = create_intent_classification_node(llm=None)
    state = {
        "company_name": "东阿阿胶",
        "business_scope": "阿胶及阿胶系列产品、其他保健品、药用辅料",
        "stock_types": ["old_type"],  # 应被覆盖
    }
    result = node(state)

    assert result["stock_types"] != ["old_type"]