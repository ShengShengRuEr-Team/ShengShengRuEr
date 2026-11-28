"""Student-facing notebook response fields."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

LearningStatus = Literal["pending", "mastered"]
NotebookVisibility = Literal["visible", "hidden", "all"]
WrongAnswerType = Literal["incorrect", "unanswered"]
ExplanationStatus = Literal["available", "missing", "restricted"]


class WrongAnswerQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=2**31 - 1)
    limit: int = Field(default=20, ge=1, le=50)
    exam_paper_id: int | None = Field(default=None, gt=0, le=2**63 - 1)
    answer_type: WrongAnswerType | None = None
    learning_status: LearningStatus | None = None
    visibility: NotebookVisibility = "visible"


class WrongAnswerItem(BaseModel):
    attempt_code: str
    exam_paper_id: int
    question_no: int
    paper_title: str
    submitted_at: datetime
    answer_type: WrongAnswerType
    learning_status: LearningStatus
    is_hidden: bool
    updated_at: datetime
    reviewed_at: datetime | None


class WrongAnswerPage(BaseModel):
    items: list[WrongAnswerItem]
    total: int
    state_writes_enabled: bool


class WrongAnswerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learning_status: LearningStatus | None = None
    is_hidden: StrictBool | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("至少提供一个有效的状态字段")
        return self


class ReviewAnnotation(BaseModel):
    code: str
    name: str
    evidence_status: Literal["restricted"] = "restricted"


class ReviewSkill(ReviewAnnotation):
    role: Literal["PRIMARY", "AUXILIARY"]
    definition: str | None


class ReviewCandidate(ReviewAnnotation):
    option_letter: str
    basis_summary: str | None


class ReviewAudio(BaseModel):
    status: Literal["available", "missing", "batch_mismatch"]
    url: str | None = None


class WrongAnswerDetail(WrongAnswerItem):
    question_text: str
    options: dict[str, str]
    selected_option: str | None
    correct_option: str
    explanation_text: str | None
    explanation_status: ExplanationStatus
    has_explanation: bool
    snapshot_note: Literal["交卷时内容快照"] = "交卷时内容快照"
    review_materials_source: Literal["submission_batch", "matched_current_batch"] = (
        "submission_batch"
    )
    audio_source_note: str = "当前卷音频（同交卷来源批次）"
    audio: ReviewAudio
    skills: list[ReviewSkill]
    candidate_causes: list[ReviewCandidate]
    annotation_reviewed_at: datetime | None
    evidence_access: Literal["none", "restricted"]
    personal_cause_status: Literal["unconfirmed"] = "unconfirmed"
    annotation_note: str = "候选错因不代表个人已确认的错因"
    annotation_source_note: str = (
        "关联标注来自交卷来源批次的当前有效审核结果，可能与交卷时不同。"
    )
