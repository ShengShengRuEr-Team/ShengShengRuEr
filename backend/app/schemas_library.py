"""Admin-only, optimistic and idempotent library commands."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas_processing import NonEmpty, Sha256, StrictModel


class PaperCreate(StrictModel):
    provider: Literal["deepseek", "bailian"] = "deepseek"
    exam_level: Literal["CET4", "CET6"]
    exam_year: int = Field(ge=1980, le=2200, strict=True)
    exam_month: Literal[6, 12]
    paper_set: int = Field(ge=1, le=3, strict=True)
    expected_question_count: Literal[25] = 25
    expected_question_count_source: NonEmpty = Field(max_length=2000)
    mode: Literal["manual", "upload"] = "manual"


class EditPreconditions(StrictModel):
    expected_row_version: int = Field(gt=0, strict=True)
    expected_content_hash: Sha256


class EditOpen(StrictModel):
    expected_row_version: int = Field(gt=0, strict=True)
    reason: NonEmpty = Field(max_length=2000)


class SaveDraft(EditPreconditions):
    snapshot: dict
    reason: NonEmpty = Field(max_length=2000)


class RestoreDraft(EditPreconditions):
    source_version_id: UUID
    # Empty restores all; otherwise select whole entities, never arbitrary patches.
    sections: list[NonEmpty] = Field(default_factory=list, max_length=20)
    question_src_ids: list[NonEmpty] = Field(default_factory=list, max_length=25)
    reason: NonEmpty = Field(max_length=2000)


class ArchivePaper(EditOpen):
    expected_content_hash: Sha256


class AdoptCandidates(EditPreconditions):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=25)
    scopes: list[NonEmpty] = Field(min_length=1, max_length=10)
    reason: NonEmpty = Field(max_length=2000)


class ManualAnnotation(EditPreconditions):
    candidate: dict
    reason: NonEmpty = Field(max_length=2000)


class PrepareReview(EditPreconditions):
    reason: NonEmpty = Field(max_length=2000)


class GenerateCandidates(PrepareReview):
    question_src_ids: list[NonEmpty] = Field(min_length=1, max_length=25)
    provider: Literal["deepseek", "bailian"] = "deepseek"


class EvaluationCandidates(GenerateCandidates):
    """Local P6 executor only; the normal HTTP endpoint accepts its base class."""

    evaluation_id: UUID
    evaluation_source_hash: Sha256
    evaluation_source_revision_id: UUID
    listening_waiver_reference: NonEmpty = Field(max_length=2000)
