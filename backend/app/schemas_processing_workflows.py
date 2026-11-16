"""Strict workflow commands; authenticated identity is never client supplied."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas_processing import NonEmpty, ReferenceSegment, Sha256, StrictModel


class ListeningPages(StrictModel):
    paper: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=list, max_length=100
    )
    answer: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def ordered_unique_pages(self):
        for pages in (self.paper, self.answer):
            if any(type(p) is not int or p < 1 for p in pages) or pages != sorted(
                set(pages)
            ):
                raise ValueError("页码须为递增、不重复的正整数")
        return self


class WorkflowCreate(StrictModel):
    exam_level: Literal["CET4", "CET6"]
    exam_year: int = Field(ge=1980, le=2200, strict=True)
    exam_month: int = Field(ge=1, le=12, strict=True)
    paper_set: int = Field(ge=1, le=100, strict=True)
    document_mode: Literal["text", "scan"]
    listening_pages: ListeningPages = Field(default_factory=ListeningPages)


class WorkflowPreconditions(StrictModel):
    expected_workflow_version: int = Field(gt=0, strict=True)
    expected_revision_id: UUID


class RevisionCreate(WorkflowPreconditions):
    reason: NonEmpty = Field(max_length=2000)
    document_mode: Literal["text", "scan"]
    listening_pages: ListeningPages


class UploadReserve(WorkflowPreconditions):
    kind: Literal["paper", "answer", "audio"]
    filename: NonEmpty = Field(max_length=255)
    declared_size: int = Field(gt=0, strict=True)
    declared_sha256: Sha256 | None = None
    expected_upload_version: int = Field(ge=0, strict=True)


class UploadCancel(WorkflowPreconditions):
    expected_upload_version: int = Field(gt=0, strict=True)
    reason: NonEmpty = Field(max_length=2000)


class WorkflowAction(WorkflowPreconditions):
    reason: NonEmpty = Field(max_length=2000)


class StageApprovalItem(StrictModel):
    reference: NonEmpty
    decision: Literal["approved", "changes_required"]
    reason: NonEmpty = Field(max_length=2000)


class StageApprovalRequest(WorkflowPreconditions):
    stage: Literal["align", "source", "sample"]
    expected_stage_dependency_hash: Sha256
    artifact_hash: Sha256
    decision: Literal["approved", "changes_required"]
    items: list[StageApprovalItem] = Field(min_length=1, max_length=500)
    review_basis: Literal["itemized", "user_confirmation"] = "itemized"
    approval_reference: NonEmpty | None = None


class ContinueRequest(WorkflowPreconditions):
    stage: Literal["align", "source", "sample"]
    expected_stage_dependency_hash: Sha256


class RetryOperationRequest(WorkflowAction):
    retry_of_operation_id: UUID


class ReviewDecision(StrictModel):
    reference: NonEmpty
    decision: Literal["approved", "changes_required"]


class ReviewItemRequest(StrictModel):
    question_src_id: NonEmpty
    content: Literal["approved", "changes_required"]
    primary_skills: list[ReviewDecision]
    answer_evidence: list[ReviewDecision]
    error_causes: list[ReviewDecision]
    empty_errors_confirmed: bool
    note: str = Field(default="", max_length=4000)
    issues: list[dict] = Field(default_factory=list, max_length=30)


class ReviewSaveRequest(WorkflowPreconditions):
    expected_result_hash: Sha256
    expected_session_version: int = Field(gt=0, strict=True)
    items: list[ReviewItemRequest] = Field(min_length=1, max_length=25)


class ReviewSubmitRequest(WorkflowPreconditions):
    expected_result_hash: Sha256
    expected_session_version: int = Field(gt=0, strict=True)
    audio_confirmed: bool
    approval_reference: NonEmpty = Field(max_length=2000)


class PublishRequest(WorkflowPreconditions):
    expected_result_hash: Sha256
    review_session_id: UUID
    expected_current_batch_id: int | None = Field(default=None, gt=0, strict=True)
    retry_of_operation_id: UUID | None = None


class ReprocessPreview(WorkflowPreconditions):
    expected_result_hash: Sha256
    question_src_ids: list[NonEmpty] = Field(min_length=1, max_length=100)
    feedback: NonEmpty = Field(max_length=4000)


class ReprocessRequest(ReprocessPreview):
    expected_plan_hash: Sha256


class SourceChange(StrictModel):
    question_src_id: NonEmpty
    field: Literal[
        "question_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_option",
        "explanation_text",
    ]
    expected_value: str
    value: NonEmpty = Field(max_length=20000)
    material_id: int = Field(gt=0, strict=True)
    page: int = Field(gt=0, strict=True)
    locator: NonEmpty = Field(max_length=2000)


class SourceCorrectionRequest(WorkflowPreconditions):
    expected_result_hash: Sha256
    reason: NonEmpty = Field(max_length=2000)
    changes: list[SourceChange] = Field(min_length=1, max_length=100)


class AlignmentCorrectionRequest(WorkflowPreconditions):
    expected_alignment_artifact_hash: Sha256
    reason: NonEmpty = Field(max_length=2000)
    source_basis: NonEmpty = Field(max_length=2000)
    reference_segments: list[ReferenceSegment] = Field(min_length=1, max_length=1000)


class WorkflowEnvelope[T](StrictModel):
    code: int
    msg: str
    data: T


class WorkflowErrorResponse(StrictModel):
    code: int
    msg: str
    data: None
    error_code: str | None = None
    context: dict | None = None


class OperationDto(StrictModel):
    operation_id: UUID
    workflow_id: UUID
    revision_id: UUID
    action: str
    state: Literal[
        "accepted", "running", "waiting", "succeeded", "failed", "conflict", "stopped"
    ]
    failure_code: str | None
    result: dict
    created_at: datetime


class WorkflowSummaryDto(StrictModel):
    workflow_id: UUID
    revision_id: UUID
    row_version: int
    exam_level: Literal["CET4", "CET6"]
    exam_year: int
    exam_month: int
    paper_set: int
    exam_paper_id: int | None
    processing_state: str
    content_review_state: str
    error_review_state: str
    publication_state: str
    created_at: datetime
    updated_at: datetime


class WorkflowListDto(StrictModel):
    items: list[WorkflowSummaryDto]
    next_cursor: str | None


class WorkflowMaterialDto(StrictModel):
    kind: Literal["paper", "answer", "audio"]
    upload_id: UUID | None
    upload_version: int
    state: Literal[
        "missing",
        "reserved",
        "uploading",
        "validating",
        "ready",
        "failed",
        "cancelled",
        "superseded",
    ]
    material_id: int | None
    lease_expired: bool
    failure_code: str | None
    filename: str | None


class WorkflowProgressDto(StrictModel):
    stage: str
    description: str
    completed_count: int
    total_count: int | None
    unit: str
    current_item: str | None
    active: bool
    observed_at: datetime
    started_at: datetime | None
    last_progress_at: datetime | None
    elapsed_ms: int
    checkpoint: str | None


class AllowedActionDto(StrictModel):
    action: str
    enabled: bool
    blocked_reason: str | None


class WorkflowUsageDto(StrictModel):
    known_usd: str
    reserved_usd: str
    has_unknown_charges: bool


class WorkflowDetailDto(WorkflowSummaryDto):
    task_id: UUID | None
    result_hash: Sha256 | None
    current_batch_id: int | None
    is_student_visible: bool
    document_mode: Literal["text", "scan"]
    listening_pages: ListeningPages
    materials: list[WorkflowMaterialDto]
    error_generation_summary: dict[str, int]
    progress: WorkflowProgressDto
    gates: list[dict]
    issues: list[dict]
    allowed_actions: list[AllowedActionDto]
    usage: WorkflowUsageDto
    stages: dict
    review_session_id: UUID | None
    review_session_version: int | None


class RevisionSummaryDto(StrictModel):
    revision_id: UUID
    revision_no: int
    parent_revision_id: UUID | None
    reason: str
    document_mode: Literal["text", "scan"]
    listening_pages: ListeningPages
    materials_hash: Sha256 | None
    result_hash: Sha256 | None
    batch_id: int | None
    created_at: datetime


class RevisionListDto(StrictModel):
    items: list[RevisionSummaryDto]
    next_cursor: str | None
