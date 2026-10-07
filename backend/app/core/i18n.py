"""Interface language of the current request: French or English
(brain/decisions.md #58).

The frontend sends the language chosen in its FR / EN switch as
`Accept-Language`; `LocaleMiddleware` stores it in a context variable for
the duration of the request, so every service can render the texts it
generates (labels, explanations, recommendations, AI prompts) in that
language without the locale being threaded through every signature.

What is never translated: source data (company, customer, supplier, product
and people names, references, URLs, the content of real emails and
documents) and canonical API values (`"status": "pending"`, ...), which only
the display localizes.

Texts that are generated once and stored (Risks, Opportunities, system Tasks,
Event Log analyses) are rendered in both languages when they are written --
`both()` -- and kept in an `i18n` mapping next to the French columns;
`localized()` picks the active language back at read time.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

Locale = Literal["fr", "en"]
LOCALES: tuple[Locale, ...] = ("fr", "en")
DEFAULT_LOCALE: Locale = "fr"

_current: ContextVar[Locale] = ContextVar("locale", default=DEFAULT_LOCALE)


def parse_accept_language(header: str | None) -> Locale:
    """First supported language of an Accept-Language header; French otherwise."""

    for part in (header or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith("en"):
            return "en"
        if tag.startswith("fr"):
            return "fr"
    return DEFAULT_LOCALE


def current_locale() -> Locale:
    return _current.get()


@contextmanager
def use_locale(locale: Locale) -> Iterator[None]:
    token = _current.set(locale)
    try:
        yield
    finally:
        _current.reset(token)


def tx(fr: str, en: str) -> str:
    """The text of the active language."""

    return en if _current.get() == "en" else fr


def both(render: Callable[[], Any]) -> dict[str, Any]:
    """Runs `render` once per language: {"fr": ..., "en": ...}."""

    out: dict[str, Any] = {}
    for locale in LOCALES:
        with use_locale(locale):
            out[locale] = render()
    return out


def localized(i18n: dict | None, field: str, fallback: Any) -> Any:
    """`field` of the active language in a stored {"fr": {...}, "en": {...}}
    mapping, or the stored column (`fallback`) for rows written before it."""

    entry = (i18n or {}).get(_current.get())
    if isinstance(entry, dict) and field in entry:
        return entry[field]
    return fallback


def text_of(obj: Any, field: str) -> Any:
    """`localized` for an ORM row with an `i18n` column (Risk, Opportunity, Task)."""

    return localized(getattr(obj, "i18n", None), field, getattr(obj, field))


def llm_language() -> str:
    """Instruction appended to every LLM prompt: the AI content itself is
    generated in the active language, not translated afterwards."""

    return tx("Réponds en français.", "Respond in English.")


# --- Number formatting ---------------------------------------------------------------------
# French: 1 234,56 € / 59,3 % (narrow no-break spaces). English: €1,234.56 / 59.3%.

NNBSP = " "


def num(value: float, digits: int = 1) -> str:
    text = f"{value:,.{digits}f}"
    if _current.get() == "en":
        return text
    return text.replace(",", NNBSP).replace(".", ",")


def money(value: float, digits: int = 2) -> str:
    if _current.get() == "en":
        return f"-€{num(abs(value), digits)}" if value < 0 else f"€{num(value, digits)}"
    return f"{num(value, digits)} €"


def pct(ratio: float, digits: int = 1) -> str:
    """0.593 -> "59,3 %" / "59.3%"."""

    return num(ratio * 100, digits) + tx(f"{NNBSP}%", "%")


def colon() -> str:
    """French puts a space before a colon."""

    return tx(" :", ":")


class LocaleMiddleware:
    """Pure ASGI middleware (so the context variable is set in the task that
    runs the endpoint, sync endpoints included)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"accept-language"), None)
        token = _current.set(parse_accept_language(header))
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
