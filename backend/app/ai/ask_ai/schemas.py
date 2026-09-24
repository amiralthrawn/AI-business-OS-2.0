import uuid

from pydantic import BaseModel, Field


class AskAIRequest(BaseModel):
    question: str = Field(min_length=1)
    # V2: the object the user is looking at when asking ("cette commande").
    # Optional; a document number in the question works too.
    object_type: str | None = None
    object_id: uuid.UUID | None = None


class AskAIResponse(BaseModel):
    answer: str
    agent: str
    capabilities_used: list[str]
    context: dict
    requires_human_validation: bool = False
    action_result: dict | None = None
