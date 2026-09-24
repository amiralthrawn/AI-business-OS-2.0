from app.ai.agents.base import Agent

# V2: reasons over business objects and their relations (a deal's document
# chain, an order's margin, which supplier to contact for a product). A new
# agent rather than new entries in finance/procurement/sales, whose exact
# capability sets are V1 contracts; like every agent it only *declares*
# capabilities -- all three are deterministic reads over the same services
# the product pages use.
deals_agent = Agent(
    name="deals",
    description="Answers questions about a specific deal, quote, order or purchase: its related objects, "
    "planned vs current margin, and which supplier to choose -- read-only.",
    capability_names=("read_object_context", "analyze_document_margin", "benchmark_suppliers"),
)
