from app.ai.agents import AGENTS, finance_agent, priorities_agent, procurement_agent, sales_agent
from app.ai.capabilities import build_capability_registry


def test_finance_agent_exposes_only_its_declared_capabilities():
    registry = build_capability_registry()

    assert finance_agent.capability_names == ("read_transactions", "analyze_margin")
    names = {c.name for c in finance_agent.capabilities(registry)}
    assert names == {"read_transactions", "analyze_margin"}


def test_procurement_agent_exposes_only_its_declared_capabilities():
    registry = build_capability_registry()

    assert procurement_agent.capability_names == (
        "read_supplier",
        "read_product",
        "read_transactions",
        "analyze_supplier_performance",
        "create_task",
    )
    names = {c.name for c in procurement_agent.capabilities(registry)}
    assert names == {
        "read_supplier",
        "read_product",
        "read_transactions",
        "analyze_supplier_performance",
        "create_task",
    }


def test_sales_agent_exposes_only_its_declared_capabilities():
    registry = build_capability_registry()

    assert sales_agent.capability_names == ("read_customer", "read_transactions", "analyze_customer_value")
    names = {c.name for c in sales_agent.capabilities(registry)}
    assert names == {"read_customer", "read_transactions", "analyze_customer_value"}


def test_priorities_agent_exposes_only_its_declared_capabilities():
    registry = build_capability_registry()

    assert priorities_agent.capability_names == ("list_priorities", "get_business_state_snapshot")
    names = {c.name for c in priorities_agent.capabilities(registry)}
    assert names == {"list_priorities", "get_business_state_snapshot"}


def test_agents_are_not_business_domains():
    # Agent identity is defined by its capability bundle, not by a Business
    # navigation domain -- Finance has no read_supplier, Procurement has no
    # analyze_margin, even though both could theoretically touch Transactions.
    assert "read_supplier" not in finance_agent.capability_names
    assert "analyze_margin" not in procurement_agent.capability_names


def test_only_procurement_can_create_tasks():
    assert "create_task" in procurement_agent.capability_names
    assert "create_task" not in finance_agent.capability_names
    assert "create_task" not in sales_agent.capability_names


def test_agents_registry_contains_all_mvp_agents():
    assert set(AGENTS.keys()) == {"finance", "procurement", "sales", "priorities", "deals"}  # "deals": V2 business-object agent
