from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
import regex
from pydantic import BaseModel, Field, AwareDatetime, model_validator, field_validator


def utcnow():
    return datetime.now(timezone.utc)


class Entity(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["organization", "location", "person", "topic", "object"] = "topic"
    confidence: float = Field(default=1, ge=0, le=1)
    track_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None


class TDO(BaseModel):
    """An immutable observation interval, aligned to the source's UTC clock."""

    id: UUID = Field(default_factory=uuid4)
    channel_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    start: AwareDatetime
    end: AwareDatetime
    language: str = Field(default="ar", max_length=12)
    transcript: str = Field(default="", max_length=16000)
    translation: str = Field(default="", max_length=16000)
    ocr: str = Field(default="", max_length=8000)
    visual: str = Field(default="", max_length=8000)
    speaker: str | None = Field(default=None, max_length=100)
    entities: list[Entity] = Field(default_factory=list, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    simulated: bool = False
    source: str = Field(default="adapter", max_length=256)
    received_at: AwareDatetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("end must not precede start")
        if (self.end - self.start).total_seconds() > 3600:
            raise ValueError("observation exceeds one hour")
        return self

    def text(self):
        return " ".join([self.transcript, self.translation, self.ocr, self.visual])


class Rule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["keyword", "regex"] = "keyword"
    pattern: str = Field(min_length=1, max_length=256)
    severity: Literal["info", "warning", "critical"] = "warning"
    enabled: bool = True
    channel_id: str | None = None

    @field_validator("pattern")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("pattern cannot be blank")
        return value

    @model_validator(mode="after")
    def valid_regex(self):
        if self.kind == "regex":
            try:
                regex.compile(self.pattern)
            except regex.error as exc:
                raise ValueError("invalid regular expression") from exc
        return self


class Alert(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tdo_id: UUID
    channel_id: str
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    rule_name: str
    severity: str
    detail: str
    kind: Literal["keyword", "regex", "spike"]
    acknowledged: bool = False
    simulated: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    channel_id: str | None = None
    language: str | None = None
    speaker: str | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    modality: Literal["auto", "transcript", "ocr", "visual"] = "auto"
    limit: int = Field(default=20, ge=1, le=100)
    min_similarity: float = Field(default=0.3, ge=-1, le=1)

    @model_validator(mode="after")
    def validate_search(self):
        if not self.query.strip():
            raise ValueError("query cannot be blank")
        if self.since and self.until and self.since > self.until:
            raise ValueError("since must precede until")
        return self

    def accepts(self, t: TDO):
        return (
            (not self.channel_id or t.channel_id == self.channel_id)
            and (not self.language or t.language == self.language)
            and (not self.speaker or t.speaker == self.speaker)
            and (not self.since or t.end >= self.since)
            and (not self.until or t.start <= self.until)
        )


class Brief(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: AwareDatetime = Field(default_factory=utcnow)
    title: str
    content: str
    evidence_ids: list[str]
    input_evidence_ids: list[str] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
    mode: Literal["extractive", "local-llm", "cloud-llm"]
    kind: Literal["morning", "narrative"] = "morning"
    simulated: bool = False
    error: str | None = None
