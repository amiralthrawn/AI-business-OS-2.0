import pytest

from app.core.baseline import margin_baseline
from app.core.entities import RelatedEntityType
from app.observation import build_observable_registry
from app.observation.registry import Observable, ObservableRegistry


def test_registry_contains_the_mvp_observables():
    registry = build_observable_registry()

    names = {o.name for o in registry.list()}
    assert names == {
        "margin_pct",
        "delivery_delay_days",
        "customer_revenue_variation_pct",
        "supplier_unanswered_message_age_days",
        "customer_unanswered_message_age_days",
        # V2: fed by business objects (sent quotes awaiting an answer)
        "customer_quote_pending_age_days",
    }


def test_register_and_get_a_new_observable_without_touching_the_engine():
    registry = ObservableRegistry()
    observable = Observable(
        name="stock_days_of_cover",
        domain="supply_chain",
        entity_type=RelatedEntityType.PRODUCT,
        description="A hypothetical future observable, registered without any engine change.",
        compute=margin_baseline,  # arbitrary compatible signature for this test
        impact_thresholds=(1.0, 2.0),
    )

    registry.register(observable)

    assert registry.get("stock_days_of_cover") is observable
    assert observable in registry.list()


def test_registry_rejects_duplicate_registration():
    registry = build_observable_registry()

    with pytest.raises(ValueError):
        registry.register(registry.get("margin_pct"))


def test_get_unknown_observable_raises():
    registry = build_observable_registry()

    with pytest.raises(KeyError):
        registry.get("does_not_exist")


def test_for_entity_type_filters_correctly():
    registry = build_observable_registry()

    product_observables = registry.for_entity_type(RelatedEntityType.PRODUCT)
    supplier_observables = registry.for_entity_type(RelatedEntityType.SUPPLIER)

    assert {o.name for o in product_observables} == {"margin_pct"}
    assert {o.name for o in supplier_observables} == {"delivery_delay_days", "supplier_unanswered_message_age_days"}
