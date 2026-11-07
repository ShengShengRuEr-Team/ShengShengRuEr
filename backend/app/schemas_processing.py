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


class ReferenceSegment(StrictModel):
    segment_id: NonEmpty
    text: NonEmpty
    segment_type: Literal["body", "question"]
    passage_key: NonEmpty
    speaker: Literal["M", "W"] | None = None
    question_no: int | None = Field(default=None, gt=0, strict=True)
    source_storage_key: NonEmpty
    source_sha256: Sha256
    source_pages: list[int] = Field(min_length=1)
    search_start_ms: int = Field(ge=0, strict=True)
    search_end_ms: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def valid_reference(self):
        if self.search_end_ms <= self.search_start_ms:
            raise ValueError("原文搜索范围倒置")
        if self.search_end_ms - self.search_start_ms > 30000:
            raise ValueError("逐句搜索范围不得超过30秒")
        if (self.segment_type == "question") != (self.question_no is not None):
            raise ValueError("提问须有题号，正文不得带题号")
        if len(set(self.source_pages)) != len(self.source_pages) or any(
            type(p) is not int or p < 1 for p in self.source_pages
        ):
            raise ValueError("原文页码须为不重复正整数")
        return self


class TaskRequest(StrictModel):
    exam_paper: PaperMetadata
    material_ids: list[int] = Field(min_length=1)
    document_mode: Literal["text", "scan"]
    stop_after: Literal[
        "align", "assemble", "annotate_sample", "annotate", "completed"
    ] = "align"
    reuse_alignment_task_id: UUID | None = None
    reuse_assembly_task_id: UUID | None = None
    reuse_assembly_scan_task_id: UUID | None = None
    reuse_annotation_task_id: UUID | None = None
    sample_review: dict[str, Any] | None = None
    reuse_full_annotation_task_id: UUID | None = None
    annotation_review: dict[str, Any] | None = None
    text_source: Literal["reference", "asr"] = "reference"
    reference_preparation: Literal["auto", "provided"] | None = None
    reference_segments: list[ReferenceSegment] = Field(default_factory=list)
    material_pages: dict[int, list[int]] = Field(default_factory=dict)
    expected_question_count: int | None = Field(default=None, gt=0, strict=True)
    expected_question_count_source: CountSource | None = None
    expected_question_ranges: list[QuestionRange] = Field(default_factory=list)
    dictionary_snapshot_sha256: Sha256
    profile_version: Literal["M3-WIN64-1.1.0"]

    @model_validator(mode="after")
    def trusted_count(self):
        if self.reference_preparation is None:
            self.reference_preparation = (
                "provided" if self.reference_segments else "auto"
            )
        if self.reference_preparation == "auto" and self.reference_segments:
            raise ValueError("自动原文准备不得混入预录入的逐句原文")
        if (
            self.text_source == "reference"
            and self.reference_preparation == "auto"
            and self.stop_after == "completed"
            and not (
                self.reuse_alignment_task_id
                and self.reuse_assembly_task_id
                and self.reuse_annotation_task_id
                and self.reuse_full_annotation_task_id
                and self.annotation_review
                and self.annotation_review.get("decision") == "approved"
            )
        ):
            raise ValueError("自动原文入库须绑定已核验对齐、组装、小样和整套通过复核")
        if self.reuse_alignment_task_id and self.stop_after not in {
            "assemble",
            "annotate_sample",
            "annotate",
            "completed",
        }:
            raise ValueError("复用对齐只允许下游组装、标注或显式待审入库")
        if (
            self.stop_after in {"assemble", "annotate_sample", "annotate"}
            and not self.reuse_alignment_task_id
        ):
            raise ValueError("下游草稿须先完成align并显式绑定来源任务")
        if (self.reuse_annotation_task_id is None) != (self.sample_review is None):
            raise ValueError("复用5题小样须同时提供绑定草稿哈希的逐题语义复核")
        if self.stop_after == "annotate" and not self.reuse_annotation_task_id:
            raise ValueError("整套标注须先完成并复核5题真实小样")
        if (self.reuse_full_annotation_task_id is None) != (
            self.annotation_review is None
        ):
            raise ValueError("整套标注修复须绑定来源任务和逐题语义复核")
        if self.reuse_full_annotation_task_id and self.stop_after not in {
            "annotate",
            "completed",
        }:
            raise ValueError("整套标注复用只允许标注草稿或显式待审入库")
        if (
            self.reuse_full_annotation_task_id
            and self.stop_after == "completed"
            and self.annotation_review.get("decision") != "approved"
        ):
            raise ValueError("待审入库只接受全部通过的整套标注复核")
        if (
            any(
                (
                    self.reuse_assembly_task_id,
                    self.reuse_assembly_scan_task_id,
                    self.reuse_annotation_task_id,
                )
            )
            and not self.reuse_alignment_task_id
        ):
            raise ValueError("下游复用须显式绑定已核验的上游对齐任务")
        if self.text_source == "asr" and self.reference_segments:
            raise ValueError("已有原文时不得选择ASR文字来源")
        ids = [s.segment_id for s in self.reference_segments]
        if len(ids) != len(set(ids)):
            raise ValueError("原文句子ID重复")
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
    review_basis: Literal["itemized", "user_confirmation"] = "itemized"
    approval_reference: NonEmpty | None = None

    @model_validator(mode="after")
    def explicit_confirmation(self):
        if self.review_basis == "user_confirmation" and (
            self.scope != "audio"
            or self.decision != "approved"
            or not self.approval_reference
        ):
            raise ValueError("用户核听确认仅用于音频通过，必须记录明确审批来源")
        return self


class RetryRequest(StrictModel):
    expected_input_hash: Sha256
    reason: NonEmpty
    from_stage: Literal[
        "preflight",
        "extract",
        "normalize",
        "reference",
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
