from fastapi.testclient import TestClient

from app.ai.llm import DETERMINISTIC_MARKER
from app.ai.llm import DeterministicLLMClient, get_llm_client
from app.core.entities import Company, Product, Supplier
from app.database import get_db
from app.main import app


def _seed(db_session):
    company = Company(name="API Co")
    db_session.add(company)
    db_session.flush()
    supplier = Supplier(company_id=company.id, name="Northline Steel")
    db_session.add(supplier)
    db_session.flush()
    product = Product(company_id=company.id, supplier_id=supplier.id, name="Sensor Module", sku="PCB-011", unit_cost=61.0)
    db_session.add(product)
    db_session.commit()
    return supplier, product


def test_ask_ai_endpoint_answers_a_procurement_question(db_session):
    supplier, product = _seed(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Explicitly inject the dependency-free LLM double: this test must never
    # call the real OpenAI API, regardless of what's in the local .env.
    app.dependency_overrides[get_llm_client] = lambda: DeterministicLLMClient()
    try:
        response = TestClient(app).post(
            "/ai/ask", json={"question": "What is our supplier for the Sensor Module?"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "procurement"
    assert "read_supplier" in body["capabilities_used"]
    assert "read_product" in body["capabilities_used"]
    assert body["context"]["read_supplier"]["name"] == "Northline Steel"

    # Step 27: `answer` is the field the frontend renders directly -- it must
    # never be a raw JSON/prompt dump, even without a real LLM configured.
    assert "Context:" not in body["answer"]
    assert "{" not in body["answer"]
    assert DETERMINISTIC_MARKER not in body["answer"]
    assert "Northline Steel" in body["answer"]


def test_ask_ai_endpoint_answers_a_finance_question(db_session):
    supplier, product = _seed(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_client] = lambda: DeterministicLLMClient()
    try:
        response = TestClient(app).post(
            "/ai/ask", json={"question": "What is our margin on the Sensor Module?"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "finance" in body["agent"]
    assert "analyze_margin" in body["capabilities_used"]


def test_ask_ai_endpoint_returns_400_for_an_unroutable_question(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_client] = lambda: DeterministicLLMClient()
    try:
        response = TestClient(app).post("/ai/ask", json={"question": "What time is it?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_ask_ai_endpoint_returns_422_for_an_empty_question(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post("/ai/ask", json={"question": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
