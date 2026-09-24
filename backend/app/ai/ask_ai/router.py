from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.ask_ai.schemas import AskAIRequest, AskAIResponse
from app.ai.capabilities import capability_registry
from app.ai.llm import LLMClient, get_llm_client
from app.ai.orchestrator import AIOrchestrator, OrchestratorError
from app.core.events.bus import EventBus
from app.database import get_db
from app.dependencies import get_event_bus

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/ask", response_model=AskAIResponse)
def ask_ai(
    payload: AskAIRequest,
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    event_bus: EventBus = Depends(get_event_bus),
) -> AskAIResponse:
    orchestrator = AIOrchestrator(db, capability_registry, llm, event_bus)
    try:
        result = orchestrator.ask(payload.question, object_type=payload.object_type, object_id=payload.object_id)
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AskAIResponse(
        answer=result.answer,
        agent=result.agent,
        capabilities_used=result.capabilities_used,
        context=result.context,
        requires_human_validation=result.requires_human_validation,
        action_result=result.action_result,
    )
