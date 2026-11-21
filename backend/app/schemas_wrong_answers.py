"""Student-facing notebook response fields."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WrongAnswerItem(BaseModel):
    attempt_code: str
    question_no: int
    question_text: str
    paper_title: str
    submitted_at: datetime
    selected_option: str | None


class WrongAnswerPage(BaseModel):
    items: list[WrongAnswerItem]
    total: int


class ReviewEvidence(BaseModel):
    text: str
    note: str | None


class ReviewAnnotation(BaseModel):
    code: str
    name: str
    reason: str | None
    evidence: list[ReviewEvidence]


class ReviewSkill(ReviewAnnotation):
    role: str | None


class ReviewCandidate(ReviewAnnotation):
    option_letter: str


class WrongAnswerDetail(WrongAnswerItem):
    options: dict[str, str]
    correct_option: str
    explanation_text: str
    transcript: list[str]
    audio_url: str | None
    skills: list[ReviewSkill]
    candidate_causes: list[ReviewCandidate]
    personal_cause_status: Literal["unconfirmed"] = "unconfirmed"
