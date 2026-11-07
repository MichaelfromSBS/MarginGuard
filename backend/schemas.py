import base64
import binascii
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(StrictModel):
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=32000)


class RunRequest(StrictModel):
    task: str = Field(min_length=1, max_length=4000)
    sources: list[Source] = Field(default_factory=list, max_length=8)
    image: str | None = Field(default=None, max_length=4_200_000)

    @field_validator("task")
    @classmethod
    def task_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Write a task first.")
        return value.strip()

    @field_validator("image")
    @classmethod
    def image_data_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            header, data = value.split(",", 1)
            if header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
                raise ValueError("Use a PNG, JPEG, or WebP image.")
            decoded = base64.b64decode(data, validate=True)
            if not decoded or len(decoded) > 3 * 1024 * 1024:
                raise ValueError("Image must be between 1 byte and 3 MB.")
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Use a valid base64 PNG, JPEG, or WebP image up to 3 MB.") from exc
        return value

    @model_validator(mode="after")
    def check_sources(self):
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Source IDs must be unique.")
        if sum(len(source.text) for source in self.sources) > 64000:
            raise ValueError("Combined source text must be at most 64,000 characters.")
        return self


# Keep every field required and extra='forbid' for strict JSON Schema providers.
# Change these models when your team chooses the actual product.
class Evidence(StrictModel):
    source_id: str
    quote: str


class Finding(StrictModel):
    title: str
    detail: str
    evidence: list[Evidence]


class Analysis(StrictModel):
    summary: str
    findings: list[Finding]
    next_steps: list[str]
    unknowns: list[str]


class Metadata(StrictModel):
    mode: Literal["mock", "openrouter"]
    model: str
    elapsed_ms: int
    usage: dict
    warnings: list[str]


class RunResponse(StrictModel):
    result: Analysis
    meta: Metadata
