"""Capability registry: typed units of read or action, some deterministic,
some LLM-backed later. Wired once here so agents resolve capabilities by name
through the registry rather than importing capability modules directly."""

from app.ai.capabilities.analyze_customer_value import analyze_customer_value_capability
from app.ai.capabilities.analyze_margin import analyze_margin_capability
from app.ai.capabilities.analyze_supplier_performance import analyze_supplier_performance_capability
from app.ai.capabilities.business_objects import (
    analyze_document_margin_capability,
    benchmark_suppliers_capability,
    read_object_context_capability,
)
from app.ai.capabilities.base import Capability, CapabilityError, CapabilityExecutionError, CapabilityNotFoundError
from app.ai.capabilities.create_task import create_task_capability
from app.ai.capabilities.get_business_state_snapshot import get_business_state_snapshot_capability
from app.ai.capabilities.list_priorities import list_priorities_capability
from app.ai.capabilities.read_customer import read_customer_capability
from app.ai.capabilities.read_product import read_product_capability
from app.ai.capabilities.read_supplier import read_supplier_capability
from app.ai.capabilities.read_transactions import read_transactions_capability
from app.ai.capabilities.registry import CapabilityRegistry


def build_capability_registry() -> CapabilityRegistry:
    """Exposed as a function (rather than only the singleton below) so tests can
    build an isolated registry instead of depending on shared global state."""

    registry = CapabilityRegistry()
    registry.register(read_supplier_capability)
    registry.register(read_product_capability)
    registry.register(read_customer_capability)
    registry.register(read_transactions_capability)
    registry.register(analyze_margin_capability)
    registry.register(analyze_supplier_performance_capability)
    registry.register(analyze_customer_value_capability)
    registry.register(list_priorities_capability)
    registry.register(get_business_state_snapshot_capability)
    registry.register(create_task_capability)
    # V2 business objects (app.ai.capabilities.business_objects)
    registry.register(read_object_context_capability)
    registry.register(analyze_document_margin_capability)
    registry.register(benchmark_suppliers_capability)
    return registry


capability_registry = build_capability_registry()

__all__ = [
    "Capability",
    "CapabilityError",
    "CapabilityExecutionError",
    "CapabilityNotFoundError",
    "CapabilityRegistry",
    "build_capability_registry",
    "capability_registry",
]
