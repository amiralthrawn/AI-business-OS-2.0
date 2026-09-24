"""V2 capabilities: the AI reasons over business objects and their relations
through the SAME services the product pages use -- the object graph, the
margin engine and the supplier benchmark -- never a parallel computation.
All three are deterministic reads; the LLM (when configured) only phrases
their results."""

import uuid

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.access.deps import LEGACY_OPERATOR
from app.ai.capabilities.base import Capability, CapabilityExecutionError
from app.core.entities import CommercialDocument
from app.core.events.bus import EventBus
from app.domains.procurement.benchmark import benchmark_suppliers
from app.objects.context import build_context
from app.transactions.margin import compute_document_margin


class ObjectRefInput(BaseModel):
    object_type: str
    object_id: uuid.UUID


class ObjectContextOutput(BaseModel):
    object: dict
    breadcrumb: list[dict]
    related: list[dict]
    intelligence: list[dict]
    timeline: list[dict]


def _read_object_context(session: Session, _bus: EventBus | None, data: ObjectRefInput) -> ObjectContextOutput:
    try:
        ctx = build_context(session, LEGACY_OPERATOR, data.object_type, data.object_id).to_dict()
    except LookupError as exc:
        raise CapabilityExecutionError(str(exc)) from exc
    return ObjectContextOutput(object=ctx["object"], breadcrumb=ctx["breadcrumb"], related=ctx["related"], intelligence=ctx["intelligence"], timeline=ctx["timeline"][:10])


read_object_context_capability = Capability(
    name="read_object_context",
    description="Reads any business object with its related objects (graph), history and open intelligence.",
    input_schema=ObjectRefInput,
    output_schema=ObjectContextOutput,
    requires_human_validation=False,
    executor=_read_object_context,
)


class DocumentInput(BaseModel):
    document_id: uuid.UUID


class DocumentMarginOutput(BaseModel):
    margin: dict


def _analyze_document_margin(session: Session, _bus: EventBus | None, data: DocumentInput) -> DocumentMarginOutput:
    doc = session.get(CommercialDocument, data.document_id)
    if doc is None:
        raise CapabilityExecutionError(f"Document {data.document_id} not found")
    try:
        return DocumentMarginOutput(margin=compute_document_margin(session, doc).to_dict())
    except ValueError as exc:
        raise CapabilityExecutionError(str(exc)) from exc


analyze_document_margin_capability = Capability(
    name="analyze_document_margin",
    description="Planned vs current margin of a customer request/quote/order, walking its whole document chain; every cost carries its basis.",
    input_schema=DocumentInput,
    output_schema=DocumentMarginOutput,
    requires_human_validation=False,
    executor=_analyze_document_margin,
)


class BenchmarkInput(BaseModel):
    product_id: uuid.UUID
    quantity: float = 1.0
    purchase_request_id: uuid.UUID | None = None


class BenchmarkOutput(BaseModel):
    benchmark: dict


def _benchmark(session: Session, _bus: EventBus | None, data: BenchmarkInput) -> BenchmarkOutput:
    try:
        return BenchmarkOutput(benchmark=benchmark_suppliers(session, data.product_id, data.quantity, data.purchase_request_id).to_dict())
    except LookupError as exc:
        raise CapabilityExecutionError(str(exc)) from exc


benchmark_suppliers_capability = Capability(
    name="benchmark_suppliers",
    description="Compares every supplier able to provide a product (price, total cost, lead time ranges, observed performance, availability, MOQ/SPQ).",
    input_schema=BenchmarkInput,
    output_schema=BenchmarkOutput,
    requires_human_validation=False,
    executor=_benchmark,
)
