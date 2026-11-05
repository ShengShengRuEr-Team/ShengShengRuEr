"""Public administrator contracts; reject unknown fields at every boundary."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Code = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterialRequest(StrictModel):
    exam_paper_code: Code
    source_kind: Literal[
        "paper_text", "paper_scan", "answer_explanation", "audio", "transcript"
    ]
    storage_key: NonEmpty
    expected_sha256: Sha256
    source_locator: NonEmpty
    derived_from_material_id: int | None = Field(default=None, gt=0)
    generation: dict[str, Any] | None = None


class PaperMetadata(StrictModel):
    exam_paper_code: Code
    exam_level: Literal["CET4", "CET6"]
    exam_year: int = Field(ge=1980, le=2200, strict=True)
    exam_month: int = Field(ge=1, le=12, strict=True)
    paper_set: int = Field(ge=1, strict=True)
    source: str = ""
    mapping_source: str = ""


class CountSource(StrictModel):
    document: NonEmpty
    sha256: Sha256
    locator: NonEmpty


class QuestionRange(StrictModel):
    section: NonEmpty
    start: int = Field(gt=0, strict=True)
    end: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def ascending(self):
        if self.end < self.start:
            raise ValueError("题组范围倒置")
        return self


class TaskRequest(StrictModel):
    exam_paper: PaperMetadata
    material_ids: list[int] = Field(min_length=1)
    document_mode: Literal["text", "scan"]
    material_pages: dict[int, list[int]] = Field(default_factory=dict)
    expected_question_count: int | None = Field(default=None, gt=0, strict=True)
    expected_question_count_source: CountSource | None = None
    expected_question_ranges: list[QuestionRange] = Field(default_factory=list)
    dictionary_snapshot_sha256: Sha256
    profile_version: Literal["M3-WIN64-1.1.0"]

    @model_validator(mode="after")
    def trusted_count(self):
        for material_id, pages in self.material_pages.items():
            if (
                material_id not in self.material_ids
                or not pages
                or len(pages) != len(set(pages))
                or any(type(p) is not int or p < 1 for p in pages)
            ):
                raise ValueError("材料页码须为本任务材料内不重复的正整数")
        if len(set(self.material_ids)) != len(self.material_ids):
            raise ValueError("材料重复")
        if any(type(i) is not int or i <= 0 for i in self.material_ids):
            raise ValueError("材料ID必须为正整数")
        count, source = (
            self.expected_question_count,
            self.expected_question_count_source,
        )
        if (count is None) != (source is None):
            raise ValueError("可信题量与来源须同时提供")
        if count is not None:
            numbers = [
                n
                for r in self.expected_question_ranges
                for n in range(r.start, r.end + 1)
            ]
            if sorted(numbers) != list(range(1, count + 1)):
                raise ValueError("题组范围须完整且不重复覆盖可信题量")
        return self


class CheckRequest(StrictModel):
    expected_result_hash: Sha256


class ReviewRequest(StrictModel):
    result_hash: Sha256
    scope: Literal["content", "audio", "annotations"]
    decision: Literal["approved", "changes_required"]
    items: list[dict[str, Any]] = Field(min_length=1)
    evidence_refs: list[NonEmpty] = Field(min_length=1)
    note: NonEmpty


class RetryRequest(StrictModel):
    expected_input_hash: Sha256
    reason: NonEmpty
    from_stage: Literal[
        "preflight",
        "extract",
        "normalize",
        "transcribe",
        "align",
        "assemble",
        "annotate",
        "validate",
        "persist",
    ] = "preflight"


class Correction(StrictModel):
    entity: Literal[
        "passages",
        "transcript_segments",
        "questions",
        "presentations",
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ]
    src_id: NonEmpty
    field: NonEmpty
    value: Any


class CorrectionRequest(StrictModel):
    expected_result_hash: Sha256
    reason: NonEmpty
    source_refs: list[NonEmpty] = Field(min_length=1)
    changes: list[Correction] = Field(min_length=1)


class ActivationRequest(StrictModel):
    task_id: UUID
    batch_id: int = Field(gt=0)
    check_id: int = Field(gt=0)
    result_hash: Sha256
    expected_current_batch_id: int | None = Field(default=None, gt=0)
