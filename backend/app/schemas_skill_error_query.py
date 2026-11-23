"""技能与错因查询的只读响应模型。"""

from typing import Literal

from pydantic import BaseModel


class PathNode(BaseModel):
    code: str
    display_code: str
    name: str


class SkillNode(BaseModel):
    kind: Literal["skill"] = "skill"
    id: int
    code: str
    display_code: str
    name: str
    level: int
    parent_id: int | None = None
    parent_code: str | None = None
    path: list[PathNode]
    definition: str
    observable_behavior: str | None = None
    counter_example: str | None = None
    usage_scope: str
    exam_level_scope: str
    status: str
    review_status: str
    legacy_codes: str | None = None
    notes: str | None = None
    question_count: int | None = None
    primary_question_count: int | None = None
    auxiliary_question_count: int | None = None


class ErrorCauseNode(BaseModel):
    kind: Literal["error_cause"] = "error_cause"
    id: int
    code: str
    display_code: str
    name: str
    level: int
    parent_id: int | None = None
    parent_code: str | None = None
    path: list[PathNode]
    definition: str
    confirmation_rule: str | None = None
    boundary_rule: str | None = None
    maturity: str
    status: str
    review_status: str
    legacy_codes: str | None = None
    notes: str | None = None
    question_count: int | None = None
    option_relation_count: int | None = None


class DictionaryData(BaseModel):
    dictionary_version: str
    dictionary_snapshot_id: int
    scope_version: str
    skills: list[SkillNode]
    error_causes: list[ErrorCauseNode]


class PaperRef(BaseModel):
    exam_paper_id: int
    exam_paper_code: str
    question_no: int
    paper_count: int = 1


class MatchedSkill(BaseModel):
    code: str
    name: str
    role: str


class SkillRoleItem(BaseModel):
    code: str
    name: str
    role: str


class CandidateCauseSummary(BaseModel):
    code: str
    name: str
    rationale: str
    is_match: bool
    evidence_count: int


class ErrorOptionSummary(BaseModel):
    base_option_letter: str
    display_option_letter: str | None = None
    option_mapping_state: str
    option_mapping_reordered: bool = False
    option_text: str
    matched_error_codes: list[str] = []
    candidate_causes: list[CandidateCauseSummary] = []


class WarningItem(BaseModel):
    code: str
    message: str


class QuestionListItem(BaseModel):
    question_id: int
    question_code: str
    question_text: str
    paper: PaperRef
    annotation_status: Literal["approved"] = "approved"
    annotation_status_label: str = "正式审核通过"
    has_audio: bool
    answer_state: Literal["available", "unavailable"] = "available"
    matched_skills: list[MatchedSkill] = []
    skills: list[SkillRoleItem] = []
    error_options: list[ErrorOptionSummary] = []
    warnings: list[WarningItem] = []


class MatchedLeaf(BaseModel):
    code: str
    name: str
    display_code: str
    question_count: int = 0
    primary_question_count: int | None = None
    auxiliary_question_count: int | None = None
    option_relation_count: int | None = None


class SubjectRef(BaseModel):
    type: str
    code: str
    name: str
    display_code: str


class QuestionListData(BaseModel):
    scope_version: str
    subject: SubjectRef
    matched_leaves: list[MatchedLeaf]
    question_count: int
    primary_question_count: int | None = None
    auxiliary_question_count: int | None = None
    option_relation_count: int | None = None
    items: list[QuestionListItem]
    next_cursor: int | None = None


class QuestionContent(BaseModel):
    id: int
    code: str
    text: str
    content_state: str
    review_status: str
    explanation_text: str
    explanation_source: str


class PaperDetail(BaseModel):
    exam_paper_id: int
    exam_paper_code: str
    exam_level: str
    exam_year: int
    exam_month: int
    paper_set: int
    question_no: int
    question_index: int | None = None
    option_mapping_state: str
    option_mapping_reordered: bool = False
    mapping_source: str
    audio_url: str | None = None
    audio_batch_id: int | None = None
    duration_ms: int | None = None
    paper_count: int = 1


class PaperOptionRef(BaseModel):
    exam_paper_id: int
    exam_paper_code: str
    question_no: int
    option_mapping_state: str
    option_mapping_reordered: bool = False
    is_default: bool


class OptionDisplay(BaseModel):
    display_letter: str
    base_letter: str
    text: str


class CorrectOption(BaseModel):
    display_letter: str | None = None
    base_letter: str | None = None


class SegmentView(BaseModel):
    segment_id: int
    segment_index: int
    segment_type: str
    text: str
    speaker_code: str | None = None
    start_ms: int
    end_ms: int


class PassageView(BaseModel):
    passage_id: int
    passage_index: int
    passage_type: str
    topic: str
    start_ms: int
    body_end_ms: int | None = None
    end_ms: int | None = None
    segments: list[SegmentView]


class EvidenceView(BaseModel):
    evidence_id: int
    text: str
    start_ms: int
    end_ms: int
    source: str
    support_note: str | None = None


class SkillDetail(BaseModel):
    code: str
    name: str
    role: str
    definition: str
    evidence: list[EvidenceView]


class CandidateCauseDetail(BaseModel):
    code: str
    name: str
    rationale: str
    evidence: list[EvidenceView]


class ErrorOptionDetail(BaseModel):
    display_letter: str | None = None
    base_letter: str
    text: str
    candidate_causes: list[CandidateCauseDetail]


class PersonalError(BaseModel):
    state: str
    message: str


class QuestionDetailData(BaseModel):
    scope_version: str
    question: QuestionContent
    paper: PaperDetail
    papers: list[PaperOptionRef]
    options: list[OptionDisplay]
    correct_option: CorrectOption | None = None
    answer_state: Literal["available", "unavailable"] = "available"
    passage: PassageView | None = None
    answer_evidence: list[EvidenceView]
    skills: list[SkillDetail]
    error_options: list[ErrorOptionDetail]
    personal_error: PersonalError
    warnings: list[WarningItem]
