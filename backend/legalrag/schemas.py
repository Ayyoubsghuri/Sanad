"""Request / response models for the HTTP API."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import field_validator, BaseModel, Field

Mode = Literal["offline", "hybrid", "cloud_assisted"]

StrictFactKind = Literal[
    "start_date", "end_date", "filing_date", "decision_date", "notification_date", "event_date",
    "amount", "salary", "rent", "price", "duration_months", "seniority_years", "role",
]


class StrictFact(BaseModel):
    kind: StrictFactKind
    value: str = Field(..., max_length=40, pattern=r"^[\w .,:/\-]+$")


class StrictInput(BaseModel):
    """Strict mode for sensitive cases: only a legal-issue id from the glossary plus typed facts. No free text leaves the device."""
    issue: str = Field(..., max_length=40, pattern=r"^[a-z_]+$")
    facts: list[StrictFact] = []


class CalcRequest(BaseModel):
    tool: str
    inputs: dict[str, Any] = {}


class HistoryTurn(BaseModel):
    """One earlier message of the same chat.  Used only to understand follow-ups ("and the next article?"); never a legal source."""
    role: Literal["user", "assistant"]
    text: str = Field("", description="longer messages are cut to 2500 characters instead of being refused")
    cited: list[str] = Field([], description="provision ids the assistant message rested on")

    @field_validator("text", mode="before")
    @classmethod
    def _cut(cls, v):
        return (v or "")[:2500] if isinstance(v, str) else ""

    @field_validator("cited", mode="before")
    @classmethod
    def _cited(cls, v):
        return [x for x in (v or []) if isinstance(x, str)][:50]


class PrepareRequest(BaseModel):
    history: list[HistoryTurn] = Field([], description="earlier turns of this chat, oldest first (only the last 40 are kept)")

    @field_validator("session_id", mode="before")
    @classmethod
    def _sid(cls, v):
        return str(v)[:64] if v else None

    @field_validator("history", mode="before")
    @classmethod
    def _last40(cls, v):
        return v[-40:] if isinstance(v, list) else v
    new_topic: bool = Field(False, description="true = answer this question on its own: the earlier turns of the chat are not used for it (the chat itself is kept)")
    mask: bool = Field(True, description="false = chat text is sent as written (what the app sends: only uploaded files are masked, by the documents service)")
    session_id: str | None = Field(None, description="the chat's id: the server then keeps the whole chat (summary + recent turns) and `history` only seeds it")
    question: str | None = Field(None, max_length=8000)
    strict: StrictInput | None = None
    case_id: str | None = None
    as_of: date | None = None
    as_of_declined: bool = Field(False, description="user will not say the date: both versions are shown and labelled")
    calculations: list[CalcRequest] = []
    document_ids: list[str] = []
    extra_sensitive_terms: list[str] = Field([], description="words the detector missed; also remembered for next time when remember_terms=true")
    remember_terms: bool = False
    keep_places: bool | None = None
    auto_run: bool = Field(False, description="run immediately when the user has switched on automatic approval of the send preview")


class RunRequest(BaseModel):
    approved: bool = True
    edited_text: str | None = Field(None, max_length=8000, description="user-edited preview text; it is re-checked before sending")
    preview_payload: bool = Field(False, description="return the exact generation payload instead of sending it")
    extra_sensitive_terms: list[str] = []
    review_confirmed: bool = Field(False, description="user reviewed a low-confidence preview and accepts sending")
    depth: Literal["normal", "deep", "max"] = Field("normal", description="deep / max: a bounded deeper-search loop (judge the passages, search again) before the answer")
    web: bool = Field(False, description="also search official Moroccan legal websites (Hybrid mode only); links shown apart from the answer")


class SettingsUpdate(BaseModel):
    mode: Mode | None = None
    auto_approve_send: bool | None = None
    keep_places: bool | None = None
    strict_mode: bool | None = None
    store_question_text: bool | None = None
    explain_language: Literal["ar", "fr", "en"] | None = None
    citizen_mode: bool | None = None
    weak_device: bool | None = None
    benchmark: dict[str, Any] | None = None
    provider_consent: dict[str, Any] | None = None


class SecretIn(BaseModel):
    value: str = Field(..., min_length=8, max_length=512)


class MarkTermIn(BaseModel):
    term: str = Field(..., min_length=2, max_length=100)
    kind: Literal["PERSON", "ORG", "ADDRESS"] = "PERSON"


class PseudoIn(BaseModel):
    text: str = Field(..., max_length=20000)
    case_id: str | None = None
    keep_places: bool | None = None
    extra_sensitive_terms: list[str] = []


class SearchIn(BaseModel):
    query: str = Field(..., max_length=2000)
    as_of: date | None = None
    limit: int = Field(10, ge=1, le=30)
    expand: bool = False


class CompareIn(BaseModel):
    provision_id: str
    date_a: date
    date_b: date
    lang: Literal["ar", "fr"] = "ar"


class WizardIn(BaseModel):
    instrument_id: str
    filing_date: date | None = None
    judgment_date: date | None = None
    facts_date: date | None = None


class ErrorReportIn(BaseModel):
    trace_id: str | None = None
    what_is_wrong: str = Field("", max_length=2000)
    correct_source: str = Field("", max_length=500, description="official source showing the correct text (BO issue, SGG page...)")


class SavedSearchIn(BaseModel):
    name: str = Field(..., max_length=120)
    query_id: str | None = None
    trace_id: str | None = None
    note: str = Field("", max_length=1000)


class ExportIn(BaseModel):
    trace_id: str
    format: Literal["md", "html", "docx"] = "md"


class ReminderIn(BaseModel):
    title: str = Field(..., max_length=200)
    due_date: date
    calculator_tool: str = "procedural_deadline"


class ProviderIn(BaseModel):
    kind: Literal["openai", "anthropic", "openai_compat", "local"]
    label: str = Field(..., min_length=1, max_length=60)
    model: str = Field(..., min_length=1, max_length=100)
    base_url: str | None = Field(None, max_length=300)  # openai_compat only (OpenRouter, Azure, a local server...); the OpenAI / Anthropic presets need none
    api_key: str | None = Field(None, min_length=8, max_length=512)  # omit to keep the stored key


class ActiveIn(BaseModel):
    id: str | None = None
