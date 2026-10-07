"""A thin LLM abstraction so the Orchestrator depends on an interface, never
directly on the OpenAI SDK. This is what lets tests run deterministically
without an API key or network access, and what would let the provider be
swapped later without touching the Orchestrator."""

from abc import ABC, abstractmethod

from app.config import get_settings


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class OpenAILLMClient(LLMClient):
    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = model or settings.openai_model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


# Prefix of the deterministic fallback's raw output. It must never reach a
# user-facing text (the Interpretation/Decision engines and Ask AI build
# their own French sentences; tests check that this marker never leaks).
DETERMINISTIC_MARKER = "[réponse déterministe — aucun modèle de langage configuré]"


class DeterministicLLMClient(LLMClient):
    """Dependency-free fallback used when no OpenAI API key is configured. Also
    the natural choice to inject directly in tests: no network, no key, fully
    reproducible. Produces a plain echo of the structured context instead of a
    natural-language answer -- the Orchestrator goes through the exact same
    code path either way, only the final phrasing changes."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return f"{DETERMINISTIC_MARKER} {user_prompt}"


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.openai_api_key:
        return OpenAILLMClient()
    return DeterministicLLMClient()
