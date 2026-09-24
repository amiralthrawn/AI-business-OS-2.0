"""Domain-specialized agents: bundles of capabilities, not wrappers around a
Business navigation domain. The Orchestrator can combine capabilities from
several agents in a single request (see app.ai.orchestrator) -- an agent is
never the sole gate on which single domain a question "belongs to"."""

from app.ai.agents.base import Agent
from app.ai.agents.deals import deals_agent
from app.ai.agents.finance import finance_agent
from app.ai.agents.priorities import priorities_agent
from app.ai.agents.procurement import procurement_agent
from app.ai.agents.sales import sales_agent

AGENTS: dict[str, Agent] = {
    finance_agent.name: finance_agent,
    procurement_agent.name: procurement_agent,
    sales_agent.name: sales_agent,
    priorities_agent.name: priorities_agent,
    deals_agent.name: deals_agent,
}

__all__ = ["Agent", "finance_agent", "procurement_agent", "sales_agent", "priorities_agent", "deals_agent", "AGENTS"]
