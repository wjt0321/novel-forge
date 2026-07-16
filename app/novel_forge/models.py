"""Pydantic models for service boundaries and API responses."""

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NovelForgeError(Exception):
    """Base exception with a user-facing message for all Novel Forge operations."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ReviewVerdict(str, Enum):
    APPROVE = "APPROVE"
    CONCERNS = "CONCERNS"
    REJECT = "REJECT"


class ChapterState(str, Enum):
    DRAFT = "draft"
    LINTED = "linted"
    REVIEWED = "reviewed"
    REVISION_REQUESTED = "revision_requested"
    REVISED = "revised"
    APPROVED = "approved"
    EXPORTED = "exported"


class Book(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    created_at: str
    updated_at: str


class BookSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    chapter_count: int = 0
    approved_count: int = 0
    created_at: str


class Chapter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    number: int
    title: str
    state: ChapterState
    current_revision_id: int | None = None
    current_revision_number: int | None = None
    current_hash: str | None = None
    created_at: str
    updated_at: str


class ChapterSummary(BaseModel):
    """API-safe chapter metadata; never includes full body."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    number: int
    title: str
    state: ChapterState
    current_revision_id: int | None = None
    current_revision_number: int | None = None
    open_s1: int = 0
    open_s2: int = 0
    open_s3: int = 0
    open_s4: int = 0
    blocking_lint: int = 0


class Revision(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_number: int
    file_path: str
    content_hash: str
    note: str | None = None
    created_at: str


class LintFinding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    revision_id: int
    rule_code: str
    severity: str
    line_number: int | None = None
    message: str
    evidence: str | None = None
    resolved: bool = False
    created_at: str


class ReviewFinding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_id: int | None = None
    perspective: str
    severity: str
    location: str
    evidence: str
    issue: str
    fix: str
    resolved: bool = False
    resolution_note: str | None = None
    created_at: str
    resolved_at: str | None = None


class ReaderReview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_id: int | None = None
    lens: str
    severity: str
    location_start: int
    location_end: int
    evidence: str
    reader_effect: str
    revision_intent: str
    actor: str = "human_or_agent_review"
    status: str = "open"
    resolution_note: str | None = None
    created_at: str
    resolved_at: str | None = None


class ReaderReviewSummary(BaseModel):
    """Counts of open reader reviews for a revision, grouped by lens/severity."""

    lens_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    total_open: int = 0


class ReviewResult(BaseModel):
    verdict: ReviewVerdict
    severity_counts: dict[str, int]
    lint_counts: dict[str, int] = Field(default_factory=dict)
    findings: list[ReviewFinding]
    reader_review_summary: ReaderReviewSummary = Field(default_factory=ReaderReviewSummary)
    reader_reviews: list[ReaderReview] = Field(default_factory=list)
    editorial_memo_status: dict[str, Any] = Field(default_factory=dict)
    blind_experience_status: dict[str, Any] = Field(default_factory=dict)


class EditorialMemo(BaseModel):
    """A structured editorial review memo attached to a specific revision."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_id: int
    reviewer_role: str
    narrative_necessity: str
    character_agency: str
    detail_selection: str
    causal_chain: str
    prose_observation: str
    verdict: str
    blocking_issues: list[dict[str, Any]]
    superseded_at: str | None = None
    created_at: str

    @field_validator("blocking_issues", mode="before")
    @classmethod
    def _parse_blocking_issues(cls, value):
        if isinstance(value, str):
            return json.loads(value or "[]")
        return value


class EditorialMemoSummary(BaseModel):
    """Metadata-only summary of the active editorial memo for a chapter."""

    exists: bool = False
    memo_id: int | None = None
    revision_id: int | None = None
    verdict: str | None = None
    blocking_issue_count: int = 0
    superseded_at: str | None = None
    created_at: str | None = None


class BlindReaderPacket(BaseModel):
    """Metadata for a prose-only packet given to an isolated blind reader."""

    file_path: str
    absolute_path: str
    content_hash: str
    book_slug: str
    chapter_number: int
    revision_id: int


class BlindExperienceReview(BaseModel):
    """A blind reader's reconstruction of experience from prose alone."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_id: int
    reviewer_role: str
    source_scope: str
    spatial_reconstruction: str
    body_position_and_contact: str
    action_constraints: str
    emotional_trajectory: str
    dialogue_dynamics: str
    memorable_images: list[dict[str, str]]
    knowledge_gaps: list[str]
    verdict: str
    blocking_issues: list[dict[str, Any]]
    superseded_at: str | None = None
    created_at: str

    @field_validator("memorable_images", "knowledge_gaps", "blocking_issues", mode="before")
    @classmethod
    def _parse_json_lists(cls, value):
        if isinstance(value, str):
            return json.loads(value or "[]")
        return value


class BlindExperienceSummary(BaseModel):
    exists: bool = False
    review_id: int | None = None
    revision_id: int | None = None
    verdict: str | None = None
    passes: bool = False
    memorable_image_count: int = 0
    knowledge_gap_count: int = 0
    blocking_issue_count: int = 0
    created_at: str | None = None


class ResearchEntry(BaseModel):
    """A single auditable research claim tied to a book."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    url: str
    retrieved_at: str
    source_type: str
    confidence: str
    claim: str
    allowed_use: str
    fiction_boundary: str
    unresolved: bool = False
    verification_state: str = "collected"
    verification_ref: int | None = None
    notes: str | None = None
    created_at: str


class StoryEngine(BaseModel):
    """Book-level story engine: secret, desire, choice, cost."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    secret: str
    desire: str
    alternative_actions: list[str]
    irreversible_choice: str
    immediate_cost: str
    thematic_pressure: str
    created_at: str

    @field_validator("alternative_actions", mode="before")
    @classmethod
    def _parse_alternative_actions(cls, value):
        if isinstance(value, str):
            return json.loads(value or "[]")
        return value


class ScenePlan(BaseModel):
    """One scene inside a ChapterPlan."""

    scene_ref: str
    goal: str
    obstacle: str
    choice: str
    cost: str
    ending_change: str
    promises: list[str] = Field(default_factory=list)


class ChapterPlan(BaseModel):
    """A chapter-level plan with 4-6 scenes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    scenes: list[ScenePlan]
    status: str
    created_at: str
    updated_at: str

    @field_validator("scenes", mode="before")
    @classmethod
    def _parse_scenes(cls, value):
        if isinstance(value, str):
            return [ScenePlan(**s) for s in json.loads(value or "[]")]
        return value

    @model_validator(mode="before")
    @classmethod
    def _load_plan_json(cls, data):
        if isinstance(data, dict) and "plan_json" in data:
            data = dict(data)
            data["scenes"] = [
                ScenePlan(**s) for s in json.loads(data.pop("plan_json") or "[]")
            ]
        return data


class PromiseStatus(str, Enum):
    PLANNED = "planned"
    PLANTED = "planted"
    PARTIALLY_PAID = "partially_paid"
    PAID_OFF = "paid_off"
    ABANDONED = "abandoned"


class Promise(BaseModel):
    """A narrative promise tracked across scenes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    promise_text: str
    status: PromiseStatus
    planted_scene_ref: str | None = None
    target_chapter_number: int | None = None
    target_scene_ref: str | None = None
    advanced_scene_ref: str | None = None
    resolved_scene_ref: str | None = None
    abandoned_scene_ref: str | None = None
    resolution_note: str | None = None
    created_at: str
    updated_at: str


class IterationRun(BaseModel):
    """One round of write → independent edit → revision target capture."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    round_number: int
    writer_role: str
    editor_role: str
    editor_verdict: str
    blocking_issues: list[dict[str, Any]]
    revision_targets: list[str]
    word_count: int
    status: str
    created_at: str

    @field_validator("blocking_issues", mode="before")
    @classmethod
    def _parse_blocking_issues(cls, value):
        if isinstance(value, str):
            return json.loads(value or "[]")
        return value

    @field_validator("revision_targets", mode="before")
    @classmethod
    def _parse_revision_targets(cls, value):
        if isinstance(value, str):
            return json.loads(value or "[]")
        return value


class AcceptanceResult(BaseModel):
    """Result of an automatic acceptance check for a chapter revision."""

    decision: str  # autonomous_acceptance_complete, revision_required, failed_needs_human
    checks: dict[str, Any]
    iteration_count: int
    max_rounds: int
    message: str


class CandidateFact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_id: int | None = None
    kind: str
    subject: str
    predicate: str
    object: str
    evidence: str
    status: str
    resolution_note: str | None = None
    created_at: str
    resolved_at: str | None = None


class CanonFact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_candidate_id: int | None = None
    chapter_id: int
    revision_id: int | None = None
    kind: str
    subject: str
    predicate: str
    object: str
    evidence: str
    created_at: str


class AuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    entity_type: str
    entity_id: int | None = None
    action: str
    details: str | None = None
    created_at: str


class ExportManifest(BaseModel):
    format: str
    book_slug: str
    created_at: str
    source_revisions: list[dict[str, Any]]
    sha256: str


class ExportRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    format: str
    file_path: str | None = None
    manifest_path: str | None = None
    status: str
    message: str | None = None
    created_at: str


class VoiceBibleRevision(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    revision_number: int
    file_path: str
    content_hash: str
    note: str | None = None
    created_at: str


class VoiceBible(BaseModel):
    """Metadata only; never includes the full Markdown body."""

    model_config = ConfigDict(from_attributes=True)

    book_id: int
    exists: bool = False
    current_revision_id: int | None = None
    current_revision_number: int | None = None
    current_file_path: str | None = None
    current_hash: str | None = None
    updated_at: str | None = None


class SceneContractRevision(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    revision_number: int
    file_path: str
    content_hash: str
    note: str | None = None
    created_at: str


class SceneContract(BaseModel):
    """Metadata only; never includes the full Markdown body."""

    model_config = ConfigDict(from_attributes=True)

    chapter_id: int
    exists: bool = False
    current_revision_id: int | None = None
    current_revision_number: int | None = None
    current_file_path: str | None = None
    current_hash: str | None = None
    updated_at: str | None = None


class DraftingPacket(BaseModel):
    """Metadata for an externally-written drafting packet."""

    file_path: str
    absolute_path: str
    content_hash: str
    book_slug: str
    chapter_number: int
    chapter_title: str
    current_revision_id: int | None = None


class DraftingReadiness(BaseModel):
    """Result of assessing whether a chapter is ready for drafting."""

    ready: bool
    blockers: list[dict[str, str | None]] = Field(default_factory=list)
    warnings: list[dict[str, str | None]] = Field(default_factory=list)
    voice_bible_metadata: VoiceBible
    scene_contract_metadata: SceneContract
