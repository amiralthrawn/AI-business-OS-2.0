from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.access.deps import require
from app.access import policy as access
from app.access.router import router as users_router
from app.actions.router import router as tasks_router
from app.ai.ask_ai.router import router as ask_ai_router
from app.business_context.router import router as business_context_router
from app.catalog.router import router as catalog_router
from app.communications.router import router as communications_router
from app.company.router import router as company_router
from app.config import get_settings
from app.connectors.router import router as connectors_router
from app.data.router import router as data_router
from app.database import engine
from app.decision.router import router as decision_router
from app.domains.finance.router import router as finance_router
from app.domains.procurement.router import router as procurement_router
from app.domains.sales.router import router as sales_router
from app.home.router import router as home_router
from app.intelligence.opportunities.router import router as opportunities_router
from app.intelligence.risks.router import router as risks_router
from app.intelligence.router import router as monitoring_router
from app.interpretation.router import router as interpretation_router
from app.objects.router import router as objects_router
from app.observation.router import router as observation_router
from app.transactions.router import router as documents_router
from app.compliance.router import router as compliance_router
from app.people.router import router as people_router
from app.sourcing.router import router as sourcing_router
from app.treasury.router import ownership_router, treasury_router
from app.website.router import router as website_router

app = FastAPI(title="AI Business OS", version="0.1.0")

# The frontend's Server Components fetch server-to-server (no CORS involved),
# but client components (Ask AI's form, Tasks board, ...) call this API
# directly from the browser, which is cross-origin as soon as origins
# differ. `ALLOWED_ORIGINS` unset (local dev) -> any localhost/127.0.0.1
# port, matching the frontend dev server on whichever port it picked.
# `ALLOWED_ORIGINS` set (deployment, e.g. Render) -> exactly the configured
# origin(s) (e.g. the Vercel frontend URL) -- never both at once, so a
# deployed backend never also trusts "http://localhost:*". No credentials
# either way; no authentication is added by this.
_allowed_origins = get_settings().cors_allowed_origins()
if _allowed_origins is None:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(business_context_router)
app.include_router(company_router)
app.include_router(connectors_router)
app.include_router(data_router)
app.include_router(procurement_router, dependencies=[Depends(require(access.VIEW_PROCUREMENT))])
app.include_router(finance_router, dependencies=[Depends(require(access.VIEW_FINANCE))])
app.include_router(sales_router, dependencies=[Depends(require(access.VIEW_SALES))])
app.include_router(risks_router, dependencies=[Depends(require(access.VIEW_INTELLIGENCE))])
app.include_router(opportunities_router, dependencies=[Depends(require(access.VIEW_INTELLIGENCE))])
app.include_router(monitoring_router, dependencies=[Depends(require(access.VIEW_INTELLIGENCE))])
app.include_router(observation_router, dependencies=[Depends(require(access.VIEW_INTELLIGENCE))])
app.include_router(interpretation_router, dependencies=[Depends(require(access.VIEW_INTELLIGENCE))])
app.include_router(decision_router, dependencies=[Depends(require(access.VIEW_INTELLIGENCE))])
app.include_router(tasks_router, dependencies=[Depends(require(access.VIEW_ACTIONS))])
app.include_router(home_router)
app.include_router(ask_ai_router, dependencies=[Depends(require(access.ACTION_ASK_AI))])
# V2: business objects, relationships, transactions (brain/architecture.md).
# Workspace routers carry their view permission (brain/permissions.md): the
# UI hides what a profile cannot see, and the backend refuses it too.
app.include_router(users_router)
app.include_router(objects_router)
app.include_router(documents_router)
app.include_router(catalog_router, dependencies=[Depends(require(access.VIEW_CATALOG))])
app.include_router(communications_router, dependencies=[Depends(require(access.VIEW_COMMUNICATIONS))])
# V2.1: people, director finance, compliance, sourcing, website (each router
# carries its own view permission -- the sensitive ones are director-only by default).
app.include_router(people_router, dependencies=[Depends(require(access.VIEW_PEOPLE))])
app.include_router(treasury_router)
app.include_router(ownership_router)
app.include_router(compliance_router)
app.include_router(sourcing_router)
app.include_router(website_router)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
