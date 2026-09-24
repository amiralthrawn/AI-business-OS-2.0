"""V2 relationships and contextual APIs: the object graph behind every
object page (customer <-> product <-> supplier <-> documents <-> emails),
search, links, catalog and stock -- through the real HTTP API."""

import pytest

from app.core.entities import DocumentKind, UserProfile, Role
from tests.v2_support import api_client, build_world


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


def _create(client, payload, headers=None):
    response = client.post("/documents", json=payload, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_supplier_product_customer_relations_are_navigable(session_factory, world):
    with api_client(session_factory) as client:
        order = _create(client, {"kind": "customer_order", "customer_id": str(world.customer.id), "lines": [{"product_id": str(world.product.id), "quantity": 10}]})
        client.post(f"/documents/{order['id']}/status", json={"status": "confirmed"})

        product_ctx = client.get(f"/objects/product/{world.product.id}/context").json()
        groups = {g["type"]: g for g in product_ctx["related"]}
        supplier_names = {i["title"] for i in groups["supplier"]["items"]}
        assert supplier_names == {"Hotel Riviera", "Alpine Lodges"}  # preferred + ProductSupplier
        assert world.customer.name in {i["title"] for i in groups["customer"]["items"]}  # bought it
        assert any(i["id"] == order["id"] for i in groups["commercial_document"]["items"])
        assert all(i["href"] for i in groups["supplier"]["items"])  # every related object is a link

        supplier_ctx = client.get(f"/objects/supplier/{world.supplier_b.id}/context").json()
        assert world.product.name in {i["title"] for g in supplier_ctx["related"] if g["type"] == "product" for i in g["items"]}
        assert {a["key"] for a in supplier_ctx["actions"]} >= {"create:purchase_request", "email:reply"}

        customer_ctx = client.get(f"/objects/customer/{world.customer.id}/context").json()
        customer_groups = {g["type"] for g in customer_ctx["related"]}
        assert {"commercial_document", "contact", "product", "transaction"} <= customer_groups


def test_document_context_has_breadcrumb_timeline_intelligence_and_actions(session_factory, world, db_session):
    from app.core.entities import RelatedEntityType, Risk, RiskSeverity

    db_session.add(Risk(company_id=world.company.id, title="Délais en dégradation", severity=RiskSeverity.HIGH, related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=world.supplier_a.id))
    db_session.commit()
    with api_client(session_factory) as client:
        request = _create(client, {"kind": "purchase_request", "lines": [{"product_id": str(world.product.id), "quantity": 10}]})
        po = client.post(f"/documents/{request['id']}/derive", json={"kind": "purchase_order", "supplier_id": str(world.supplier_a.id)}).json()

        ctx = client.get(f"/objects/commercial_document/{po['id']}/context").json()
        assert [b["id"] for b in ctx["breadcrumb"]] == [request["id"], po["id"]]  # where it comes from
        assert any(e["event_type"] == "DocumentCreated" for e in ctx["timeline"])  # indexed per-object history
        # The PO shows the open risk on its supplier -- V1 intelligence on a V2 object.
        assert any(s["title"] == "Délais en dégradation" and s["via"].endswith("Hotel Riviera") for s in ctx["intelligence"])
        keys = {a["key"] for a in ctx["actions"]}
        assert {"status:sent", "derive:reception", "derive:supplier_invoice", "email:send_purchase_order"} <= keys

        detail = client.get(f"/documents/{po['id']}").json()
        assert [d["number"] for d in detail["chain"]] == [request["number"], po["number"]]
        assert detail["party"]["name"] == "Hotel Riviera"


def test_purchase_request_detail_carries_its_benchmark(session_factory, world):
    with api_client(session_factory) as client:
        pr = _create(client, {"kind": "purchase_request", "lines": [{"product_id": str(world.product.id), "quantity": 12}]})
        assert len(pr["benchmarks"]) == 1
        assert len(pr["benchmarks"][0]["candidates"]) == 2
        assert client.get(f"/catalog/products/{world.product.id}/benchmark?quantity=12").json()["product_name"] == world.product.name


def test_links_search_and_idempotence(session_factory, world, db_session):
    from app.core.entities import Communication, CommunicationDirection
    from tests.v2_support import NOW

    email = Communication(company_id=world.company.id, channel="email", direction=CommunicationDirection.INBOUND, subject="Question sur le séminaire", occurred_at=NOW, status="received")
    db_session.add(email)
    db_session.commit()
    with api_client(session_factory) as client:
        quote = _create(client, {"kind": "customer_quote", "customer_id": str(world.customer.id)})
        payload = {"source_type": "communication", "source_id": str(email.id), "target_type": "commercial_document", "target_id": quote["id"]}
        first = client.post("/objects/links", json=payload).json()
        assert client.post("/objects/links", json=payload).json()["id"] == first["id"]  # idempotent

        quote_ctx = client.get(f"/objects/commercial_document/{quote['id']}/context").json()
        assert email.id.hex in {i["id"].replace("-", "") for g in quote_ctx["related"] if g["type"] == "communication" for i in g["items"]}
        email_ctx = client.get(f"/objects/communication/{email.id}/context").json()
        assert any(i["id"] == quote["id"] for g in email_ctx["related"] for i in g["items"])

        bad = client.post("/objects/links", json={**payload, "target_id": "00000000-0000-0000-0000-000000000000"})
        assert bad.status_code == 400

        found = client.get("/objects/search", params={"q": "SEM-3N"}).json()
        assert any(r["type"] == "product" for r in found)
        assert any(r["type"] == "commercial_document" for r in client.get("/objects/search", params={"q": quote["number"]}).json())


def test_catalog_suppliers_and_three_kinds_of_stock_including_csv_import(session_factory, world):
    with api_client(session_factory) as client:
        created = client.post("/catalog/products", json={"name": "Dîner de gala", "sku": "GALA-01", "sale_price": 85}).json()
        assert client.post("/catalog/products", json={"name": "autre", "sku": "GALA-01"}).json()["id"] == created["id"]  # no duplicate

        terms = client.put(
            f"/catalog/products/{created['id']}/suppliers/{world.supplier_c.id}",
            json={"unit_price": 52, "lead_time_min_days": 3, "lead_time_max_days": 5, "is_preferred": True},
        ).json()
        assert terms["preferred_supplier_id"] == str(world.supplier_c.id)
        assert terms["suppliers"][0]["lead_time_basis"] == "declared"

        csv = "sku;kind;quantity;supplier;location\nSEM-3N;physical;40;;Paris\nSEM-3N;supplier;120;Alpine Lodges;\nGALA-01;potential;300;;site web\nINCONNU;physical;5;;\n"
        result = client.post("/catalog/stock/import?filename=stock.csv", content=csv, headers={"Content-Type": "text/csv"}).json()
        assert result["created_or_updated"] == 3 and len(result["errors"]) == 1
        again = client.post("/catalog/stock/import?filename=stock.csv", content=csv, headers={"Content-Type": "text/csv"}).json()
        assert again["created_or_updated"] == 3  # re-import upserts, no duplicates

        stock = client.get(f"/catalog/products/{world.product.id}").json()["stock"]
        assert [p["quantity"] for p in stock["physical"]] == [40] and stock["physical"][0]["basis"] == "observed"
        assert stock["supplier"][0]["supplier_name"] == "Alpine Lodges" and stock["supplier"][0]["basis"] == "declared"
        assert stock["supplier"][0]["source"] == "csv:stock.csv"
        gala = client.get(f"/catalog/products/{created['id']}").json()["stock"]
        assert gala["potential"][0]["basis"] == "estimated"


def test_permissions_by_role(session_factory, world, db_session):
    sales = UserProfile(company_id=world.company.id, name="Sam", role=Role.SALES)
    buyer = UserProfile(company_id=world.company.id, name="Bea", role=Role.PROCUREMENT)
    employee = UserProfile(company_id=world.company.id, name="Eli", role=Role.EMPLOYEE)
    db_session.add_all([sales, buyer, employee])
    db_session.commit()
    as_sales, as_buyer, as_employee = ({"X-User-Id": str(u.id)} for u in (sales, buyer, employee))

    with api_client(session_factory) as client:
        me = client.get("/users/me", headers=as_sales).json()
        assert me["role"] == "sales" and "write:sales" in me["permissions"] and "write:procurement" not in me["permissions"]
        assert client.get("/users/me").json()["profile"] is None  # no header: legacy single operator

        assert client.post("/documents", json={"kind": "customer_quote", "customer_id": str(world.customer.id)}, headers=as_sales).status_code == 200
        assert client.post("/documents", json={"kind": "purchase_request"}, headers=as_sales).status_code == 403
        assert client.post("/documents", json={"kind": "purchase_request"}, headers=as_buyer).status_code == 200
        assert client.post("/documents", json={"kind": "customer_quote", "customer_id": str(world.customer.id)}, headers=as_employee).status_code == 403
        assert client.post("/catalog/products", json={"name": "X"}, headers=as_employee).status_code == 403
        assert client.get("/users/me", headers={"X-User-Id": "not-a-uuid"}).status_code == 401

        # A buyer does not see customers at all (view enforced by the backend)...
        assert client.get(f"/objects/customer/{world.customer.id}/context", headers=as_buyer).status_code == 403
        # ...operations sees them, but the quote action is offered disabled, with its reason.
        ops = UserProfile(company_id=world.company.id, name="Olga", role=Role.OPERATIONS)
        db_session.add(ops)
        db_session.commit()
        ctx = client.get(f"/objects/customer/{world.customer.id}/context", headers={"X-User-Id": str(ops.id)}).json()
        quote_action = next(a for a in ctx["actions"] if a["key"] == "create:customer_quote")
        assert quote_action["allowed"] is False and quote_action["reason"]

        # Only a director (or someone holding write:settings) manages users once one exists.
        assert client.post("/users", json={"name": "New", "role": "director"}, headers=as_sales).status_code == 403


def test_document_meta_exposes_the_lifecycle(session_factory, world):
    with api_client(session_factory) as client:
        meta = client.get("/documents/meta").json()
    kinds = {k["kind"]: k for k in meta["kinds"]}
    assert set(kinds) == {k.value for k in DocumentKind}
    assert kinds["customer_quote"]["prefix"] == "DEV"
    assert "customer_order" in kinds["customer_quote"]["derivations"]
    assert set(meta["value_basis"]) == {"observed", "declared", "estimated", "benchmark", "simulated", "unknown"}
