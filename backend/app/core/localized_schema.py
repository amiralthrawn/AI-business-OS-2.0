"""Shared read-schema base for Risks, Opportunities and Tasks."""

from pydantic import BaseModel, Field, model_validator

from app.core.i18n import localized


class LocalizedTextRead(BaseModel):
    """Title and description of a generated text, in the request's language
    (app.core.i18n): rows a person wrote have no `i18n` and keep their text."""

    title: str
    description: str | None
    i18n: dict | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _localize(self):
        self.title = localized(self.i18n, "title", self.title)
        self.description = localized(self.i18n, "description", self.description)
        return self
