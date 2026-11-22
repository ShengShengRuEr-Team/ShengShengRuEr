"""Student-facing notebook response fields."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, StrictBool, model_validator

LearningStatus = Literal["pending", "mastered"]
NotebookVisibility = Literal["visible", "hidden"]
WrongAnswerType = Literal["incorrect", "unanswered"]


class WrongAnswerItem(BaseModel):
    attempt_code: str
    exam_paper_id: int
    question_no: int
    question_text: str
    paper_title: str
    submitted_at: datetime
    selected_option: str | None
    learning_status: LearningStatus
    is_hidden: bool
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
    has_restricted_evidence: bool


class ReviewSkill(ReviewAnnotation):
    role: Literal["PRIMARY", "AUXILIARY"]


class ReviewCandidate(ReviewAnnotation):
    option_letter: str


class WrongAnswerDetail(WrongAnswerItem):
    options: dict[str, str]
    correct_option: str
    explanation_text: str
    snapshot_note: Literal["交卷时内容快照"] = "交卷时内容快照"
    audio_url: str | None
    skills: list[ReviewSkill]
    candidate_causes: list[ReviewCandidate]
    personal_cause_status: Literal["unconfirmed"] = "unconfirmed"
